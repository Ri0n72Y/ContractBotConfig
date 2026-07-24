from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from plugins.astrbot_plugin_opencontracts_gateway.config.settings import (
    GatewaySettings,
)
from plugins.astrbot_plugin_opencontracts_gateway.domain.models import (
    ImportResponse,
)
from plugins.astrbot_plugin_opencontracts_gateway.services.file_service import (
    FileService,
)
from plugins.astrbot_plugin_opencontracts_gateway.services.upload_service import (
    UploadService,
)
from plugins.astrbot_plugin_opencontracts_gateway.storage.receipt_store import (
    ReceiptStore,
)


class FakeClient:
    def __init__(self, response: ImportResponse) -> None:
        self.response = response
        self.calls = 0

    async def upload(self, source, data):
        self.calls += 1
        return self.response


class FakeConfirmations:
    def __init__(self, valid: bool) -> None:
        self.valid = valid

    def validate(self, session_key, source_sha256, confirmation_id):
        return self.valid


class UploadServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.inbox = root / "inbox"
        self.inbox.mkdir()
        self.data_dir = root / "data"
        self.settings = GatewaySettings.from_config(
            {
                "base_url": "http://opencontracts-api:8000",
                "auth_token": "worker-secret",
                "allowed_roots": [str(self.inbox)],
                "data_dir": str(self.data_dir),
                "router_state_path": str(root / "pending.json"),
                "default_corpus_slug": "contracts",
            }
        )
        self.source = self.inbox / "contract.docx"
        self.source.write_bytes(b"contract-data")
        self.sha256 = hashlib.sha256(b"contract-data").hexdigest()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def service(
        self,
        response: ImportResponse,
        *,
        confirmation_valid: bool = False,
    ) -> tuple[UploadService, FakeClient]:
        client = FakeClient(response)
        service = UploadService(
            self.settings,
            FileService(self.settings),
            FakeConfirmations(confirmation_valid),
            client,
            ReceiptStore(self.data_dir),
        )
        return service, client

    async def upload(
        self,
        service: UploadService,
        *,
        confirmation_id: str = "",
        task_id: str = "task-1",
    ) -> dict:
        return json.loads(
            await service.upload(
                session_key="wecom:1",
                task_id=task_id,
                staged_path=str(self.source),
                expected_sha256=self.sha256,
                source_filename="contract.docx",
                title="",
                description="",
                custom_meta=None,
                duplicate_confirmation_id=confirmation_id,
            )
        )

    def test_status_separates_read_and_write_channels(self) -> None:
        service, _ = self.service(ImportResponse(500, {}))
        result = json.loads(service.status())
        self.assertTrue(result["configured"])
        self.assertEqual(result["read_channel"], "opencontracts_mcp")
        self.assertEqual(
            result["write_channel"], "worker_key_document_import"
        )
        self.assertNotIn("lookup_path", result)

    async def test_successful_import_returns_processing(self) -> None:
        service, client = self.service(
            ImportResponse(
                201,
                {"ok": True, "document_id": 9, "status": "created"},
            )
        )
        result = await self.upload(service)
        self.assertEqual(result["status"], "processing")
        self.assertEqual(result["server_import_status"], "created")
        self.assertEqual(client.calls, 1)
        self.assertEqual(ReceiptStore(self.data_dir).count, 1)

    async def test_unconfirmed_updated_write_requires_review(self) -> None:
        service, client = self.service(
            ImportResponse(
                201,
                {"ok": True, "document_id": 10, "status": "updated"},
            )
        )
        result = await self.upload(service)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(
            result["failure_stage"],
            "unexpected_unconfirmed_update",
        )
        self.assertTrue(result["write_committed"])
        self.assertTrue(result["manual_review_required"])
        self.assertEqual(client.calls, 1)
        receipt_payload = json.loads(
            (self.data_dir / "receipts.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(receipt_payload["receipts"]), 1)
        self.assertTrue(
            receipt_payload["receipts"][0]["manual_review_required"]
        )

    async def test_unconfirmed_conflict_requests_confirmation(self) -> None:
        service, _ = self.service(
            ImportResponse(409, {"error": "document_path_exists"})
        )
        result = await self.upload(service)
        self.assertEqual(result["status"], "confirmation_required")
        self.assertTrue(result["duplicate"])

    async def test_invalid_confirmation_stops_before_request(self) -> None:
        service, client = self.service(
            ImportResponse(201, {"ok": True, "document_id": 1})
        )
        result = await self.upload(
            service,
            confirmation_id="confirmation-id",
        )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["failure_stage"], "confirmation_validation")
        self.assertEqual(client.calls, 0)

    async def test_confirmed_import_accepts_updated_version(self) -> None:
        service, client = self.service(
            ImportResponse(
                201,
                {"ok": True, "document_id": 12, "status": "updated"},
            ),
            confirmation_valid=True,
        )
        result = await self.upload(
            service,
            confirmation_id="confirmation-id",
            task_id="task-4",
        )
        self.assertEqual(result["status"], "processing")
        self.assertTrue(result["reupload_confirmed"])
        self.assertTrue(result["imported_as_new_version"])
        self.assertEqual(client.calls, 1)
