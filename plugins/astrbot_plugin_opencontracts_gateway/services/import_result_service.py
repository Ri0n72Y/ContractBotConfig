from __future__ import annotations

from ..clients.import_client import is_document_conflict
from ..config.settings import GatewaySettings
from ..domain.models import ImportResponse, ValidatedFile
from ..domain.results import json_result
from ..storage.receipt_store import ReceiptStore
from .import_response_policy import classify_http, conflict_result


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
                server_status = body.get("status")
                if server_status == "updated" and not confirmed:
                    return self._unexpected_update(
                        source,
                        document_id=document_id,
                        task_id=task_id,
                        http_status=response.status_code,
                    )
                return self._accepted(
                    source,
                    document_id=document_id,
                    server_status=server_status,
                    task_id=task_id,
                    confirmed=confirmed,
                    http_status=response.status_code,
                )

        if is_document_conflict(response.status_code, body):
            return conflict_result(
                source,
                confirmed=confirmed,
                http_status=response.status_code,
            )

        status, stage = classify_http(response.status_code)
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

    def _unexpected_update(
        self,
        source: ValidatedFile,
        *,
        document_id: object,
        task_id: str | None,
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
                "server_import_status": "updated",
                "processing_status": "processing",
                "last_task_id": task_id,
                "reupload_confirmed": False,
                "manual_review_required": True,
            }
        )
        return json_result(
            success=False,
            status="failed",
            upload_status="accepted",
            processing_status="processing",
            failure_stage="unexpected_unconfirmed_update",
            write_committed=True,
            manual_review_required=True,
            error=(
                "OpenContracts 已写入新版本，但本次任务没有有效的重新上传确认。"
                "请人工核查，避免再次提交。"
            ),
            document_id=document_id,
            server_import_status="updated",
            source_filename=source.source_filename,
            source_sha256=source.sha256,
            http_status=http_status,
        )
