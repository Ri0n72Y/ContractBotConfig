from __future__ import annotations

from ..clients.import_client import is_document_conflict
from ..config.settings import GatewaySettings
from ..domain.models import ImportResponse, ValidatedFile
from ..domain.results import json_result
from ..storage.receipt_store import ReceiptStore


class ImportResultService:
    """Map OpenContracts import responses to stable contract upload states."""

    def __init__(
        self,
        settings: GatewaySettings,
        receipts: ReceiptStore,
    ) -> None:
        self.settings = settings
        self.receipts = receipts

    def map(
        self,
        response: ImportResponse,
        source: ValidatedFile,
        *,
        task_id: str | None,
        confirmed: bool,
    ) -> str:
        if response.transport_error:
            return json_result(
                success=False,
                status="failed",
                upload_status="unknown",
                processing_status="unknown",
                failure_stage="transport",
                error=response.transport_error,
                source_filename=source.source_filename,
                source_sha256=source.sha256,
            )

        body = response.body
        if response.status_code == 201 and isinstance(body, dict):
            document_id = body.get("document_id")
            if body.get("ok") and document_id is not None:
                return self._accepted(
                    source,
                    document_id=document_id,
                    server_status=body.get("status"),
                    task_id=task_id,
                    confirmed=confirmed,
                    http_status=response.status_code,
                )

        if is_document_conflict(response.status_code, body):
            return self._conflict(
                source,
                confirmed=confirmed,
                http_status=response.status_code,
            )

        status, stage = self._classify_http(response.status_code)
        return json_result(
            success=False,
            status=status,
            upload_status="failed",
            processing_status="not_started",
            failure_stage=stage,
            http_status=response.status_code,
            response=body,
            source_filename=source.source_filename,
            source_sha256=source.sha256,
        )

    def _accepted(
        self,
        source: ValidatedFile,
        *,
        document_id: object,
        server_status: object,
        task_id: str | None,
        confirmed: bool,
        http_status: int,
    ) -> str:
        self.receipts.upsert(
            {
                "source_sha256": source.sha256,
                "source_filename": source.source_filename,
                "document_id": document_id,
                "document_title": source.title,
                "corpus_id": self.settings.default_corpus_id or None,
                "corpus_slug": self.settings.default_corpus_slug or None,
                "server_import_status": server_status,
                "processing_status": "processing",
                "last_task_id": task_id,
                "reupload_confirmed": confirmed,
            }
        )
        return json_result(
            success=True,
            status="processing",
            stored_in_opencontracts=True,
            upload_status="accepted",
            processing_status="processing",
            document_id=document_id,
            document_title=source.title,
            source_filename=source.source_filename,
            source_sha256=source.sha256,
            corpus_id=self.settings.default_corpus_id or None,
            corpus_slug=self.settings.default_corpus_slug or None,
            server_import_status=server_status,
            reupload_confirmed=confirmed,
            imported_as_new_version=(server_status == "updated"),
            http_status=http_status,
        )

    @staticmethod
    def _conflict(
        source: ValidatedFile,
        *,
        confirmed: bool,
        http_status: int | None,
    ) -> str:
        if not confirmed:
            return json_result(
                success=False,
                status="confirmation_required",
                duplicate=True,
                upload_status="not_started",
                processing_status="not_started",
                source_filename=source.source_filename,
                source_sha256=source.sha256,
                customer_action="confirm_reupload_or_cancel",
                conflict_detected_during_upload=True,
            )
        return json_result(
            success=False,
            status="failed",
            upload_status="failed",
            processing_status="not_started",
            failure_stage="version_write_conflict",
            error="已确认重新上传，但 OpenContracts 未接受同路径版本写入。",
            source_filename=source.source_filename,
            source_sha256=source.sha256,
            http_status=http_status,
        )

    @staticmethod
    def _classify_http(status_code: int | None) -> tuple[str, str]:
        if status_code in {401, 403}:
            return "blocked", "authentication_or_permission"
        if status_code == 404:
            return "blocked", "import_endpoint_missing"
        if status_code == 413:
            return "blocked", "upstream_file_limit"
        if status_code == 429:
            return "blocked", "rate_limit"
        if status_code is not None and 400 <= status_code < 500:
            return "failed", "request_validation"
        return "failed", "upstream_service"
