from __future__ import annotations

import json
from typing import Any

from ..clients.import_client import ImportClient
from ..config.settings import GatewaySettings
from ..domain.results import json_result
from ..storage.receipt_store import ReceiptStore
from .confirmation_service import ConfirmationService
from .file_service import FileService
from .import_result_service import ImportResultService


RESERVED_META_KEYS = {
    "source",
    "source_sha256",
    "source_filename",
    "original_filename",
    "normalized_filename",
    "contract_date",
    "contract_title",
    "astrbot_task_id",
}


class UploadService:
    """Coordinate identity, validation, confirmation and WorkerKey import."""

    def __init__(
        self,
        settings: GatewaySettings,
        files: FileService,
        confirmations: ConfirmationService,
        client: ImportClient,
        receipts: ReceiptStore,
    ) -> None:
        self.settings = settings
        self.files = files
        self.confirmations = confirmations
        self.client = client
        self.receipts = receipts
        self.results = ImportResultService(settings, receipts)

    def status(self) -> str:
        error = self.settings.validation_error()
        return json_result(
            configured=error is None,
            configuration_error=error,
            read_channel="opencontracts_mcp",
            write_channel="worker_key_bound_document_import",
            base_url=self.settings.base_url,
            import_path=self.settings.import_path,
            worker_key_configured=bool(self.settings.worker_key),
            receipt_role="append_only_upload_audit",
            receipt_count=self.receipts.count,
            allowed_roots=[str(root) for root in self.settings.allowed_roots],
        )

    @staticmethod
    def _task_meta(
        task_id: str | None,
        source_sha256: str,
        original_filename: str,
        normalized_filename: str,
        contract_date: str,
        contract_title: str,
        custom_meta: dict | None,
    ) -> dict[str, Any]:
        safe: dict[str, Any] = {}
        if isinstance(custom_meta, dict):
            safe.update(
                {
                    str(key): value
                    for key, value in custom_meta.items()
                    if str(key) not in RESERVED_META_KEYS
                }
            )
        safe.update(
            {
                "source": "astrbot",
                "source_sha256": source_sha256,
                "source_filename": normalized_filename,
                "original_filename": original_filename,
                "normalized_filename": normalized_filename,
                "contract_date": contract_date,
                "contract_title": contract_title,
                "astrbot_task_id": task_id,
            }
        )
        return safe

    async def upload(
        self,
        *,
        session_key: str,
        task_id: str | None,
        staged_path: str,
        expected_sha256: str,
        source_filename: str,
        contract_date: str,
        contract_title: str,
        description: str,
        custom_meta: dict | None,
        duplicate_confirmation_id: str,
    ) -> str:
        config_error = self.settings.validation_error()
        if config_error:
            return json_result(
                success=False,
                status="blocked",
                upload_status="not_started",
                failure_stage="configuration",
                error=config_error,
            )

        identity, identity_error = self.files.normalize_identity(
            contract_date,
            contract_title,
        )
        if identity_error or identity is None:
            return json_result(
                success=False,
                status="blocked",
                upload_status="not_started",
                failure_stage="document_identity",
                error=identity_error,
                retry_safe=True,
            )

        source, actual_sha256, file_error = await self.files.validate(
            staged_path,
            expected_sha256,
            source_filename,
            identity,
        )
        if file_error or source is None or actual_sha256 is None:
            return json_result(
                success=False,
                status="blocked",
                upload_status="not_started",
                failure_stage="file_validation",
                error=file_error,
                source_sha256=actual_sha256,
                retry_safe=True,
            )

        confirmed = False
        if str(duplicate_confirmation_id or "").strip():
            confirmed = self.confirmations.validate(
                session_key,
                actual_sha256,
                duplicate_confirmation_id,
            )
            if not confirmed:
                return json_result(
                    success=False,
                    status="blocked",
                    upload_status="not_started",
                    failure_stage="confirmation_validation",
                    error="重新上传确认无效或已过期。",
                    original_filename=source.original_filename,
                    normalized_filename=source.source_filename,
                    source_sha256=actual_sha256,
                    retry_safe=True,
                )

        metadata = self._task_meta(
            task_id,
            actual_sha256,
            source.original_filename,
            source.source_filename,
            source.contract_date,
            source.contract_title,
            custom_meta,
        )
        data: dict[str, str] = {
            "title": source.title,
            "description": str(description or "")[:2000],
            "make_public": "true" if self.settings.default_make_public else "false",
            "custom_meta": json.dumps(metadata, ensure_ascii=False, default=str),
        }

        response = await self.client.upload(source, data)
        return self.results.map(
            response,
            source,
            task_id=task_id,
            confirmed=confirmed,
        )
