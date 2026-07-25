from __future__ import annotations

import shutil
import uuid
from typing import Any

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

    @staticmethod
    def _source_fields(source: ValidatedFile) -> dict[str, Any]:
        return {
            "source_sha256": source.sha256,
            "original_filename": source.original_filename,
            "normalized_filename": source.source_filename,
            "document_title": source.title,
            "contract_date": source.contract_date,
            "contract_title": source.contract_title,
        }

    def _retain_manual_review_copy(
        self,
        source: ValidatedFile,
        task_id: str | None,
    ) -> tuple[str | None, str | None]:
        review_dir = self.settings.data_dir / "manual_review"
        try:
            review_dir.mkdir(parents=True, exist_ok=True)
            prefix = str(task_id or uuid.uuid4().hex)[:64]
            target = review_dir / (
                f"{prefix}_{uuid.uuid4().hex[:8]}_{source.source_filename}"
            )
            shutil.copy2(source.path, target)
            return str(target.resolve()), None
        except OSError as exc:
            return None, str(exc)[:500]

    def _append_receipt(
        self,
        source: ValidatedFile,
        *,
        task_id: str | None,
        state: str,
        document_id: object | None = None,
        server_status: object | None = None,
        confirmed: bool = False,
        write_committed: bool | str = False,
        manual_review_required: bool = False,
        failure_stage: str | None = None,
        http_status: int | None = None,
        error: str | None = None,
        review_copy_path: str | None = None,
        review_copy_error: str | None = None,
    ) -> None:
        self.receipts.append(
            {
                **self._source_fields(source),
                "document_id": document_id,
                "server_import_status": server_status,
                "last_task_id": task_id,
                "reupload_confirmed": confirmed,
                "state": state,
                "write_committed": write_committed,
                "manual_review_required": manual_review_required,
                "failure_stage": failure_stage,
                "http_status": http_status,
                "error": error,
                "review_copy_path": review_copy_path,
                "review_copy_error": review_copy_error,
            }
        )

    def map(
        self,
        response: ImportResponse,
        source: ValidatedFile,
        *,
        task_id: str | None,
        confirmed: bool,
    ) -> str:
        if response.transport_error:
            return self._commit_unknown(
                source,
                task_id=task_id,
                confirmed=confirmed,
                failure_stage="transport_commit_unknown",
                error=response.transport_error,
                http_status=None,
            )

        body = response.body
        if response.status_code == 201 and isinstance(body, dict):
            document_id = body.get("document_id")
            server_status = body.get("status")
            if (
                body.get("ok") is True
                and document_id is not None
                and server_status in {"created", "updated"}
            ):
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

        if response.status_code is not None and 200 <= response.status_code < 300:
            return self._commit_unknown(
                source,
                task_id=task_id,
                confirmed=confirmed,
                failure_stage="unexpected_success_response",
                error="OpenContracts 返回成功状态码，但响应结构不符合导入契约。",
                http_status=response.status_code,
                response=body,
            )

        if response.status_code is not None and response.status_code >= 500:
            return self._commit_unknown(
                source,
                task_id=task_id,
                confirmed=confirmed,
                failure_stage="upstream_commit_unknown",
                error="OpenContracts 服务端错误，无法确认写入是否已经提交。",
                http_status=response.status_code,
                response=body,
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
            retry_safe=True,
            **self._source_fields(source),
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
        self._append_receipt(
            source,
            task_id=task_id,
            state="processing",
            document_id=document_id,
            server_status=server_status,
            confirmed=confirmed,
            write_committed=True,
            http_status=http_status,
        )
        return json_result(
            success=True,
            status="processing",
            stored_in_opencontracts=True,
            upload_status="accepted",
            processing_status="processing",
            document_id=document_id,
            server_import_status=server_status,
            reupload_confirmed=confirmed,
            imported_as_new_version=(server_status == "updated"),
            write_committed=True,
            retry_safe=False,
            http_status=http_status,
            **self._source_fields(source),
        )

    def _unexpected_update(
        self,
        source: ValidatedFile,
        *,
        document_id: object,
        task_id: str | None,
        http_status: int,
    ) -> str:
        error = (
            "OpenContracts 已写入新版本，但本次任务没有有效的重新上传确认。"
            "请人工核查，禁止自动重试。"
        )
        review_copy_path, review_copy_error = self._retain_manual_review_copy(
            source,
            task_id,
        )
        self._append_receipt(
            source,
            task_id=task_id,
            state="manual_review_required",
            document_id=document_id,
            server_status="updated",
            confirmed=False,
            write_committed=True,
            manual_review_required=True,
            failure_stage="unexpected_unconfirmed_update",
            http_status=http_status,
            error=error,
            review_copy_path=review_copy_path,
            review_copy_error=review_copy_error,
        )
        return json_result(
            success=False,
            status="manual_review_required",
            upload_status="accepted",
            processing_status="processing",
            failure_stage="unexpected_unconfirmed_update",
            write_committed=True,
            manual_review_required=True,
            retry_safe=False,
            error=error,
            document_id=document_id,
            server_import_status="updated",
            review_copy_retained=review_copy_path is not None,
            review_copy_path=review_copy_path,
            review_copy_error=review_copy_error,
            http_status=http_status,
            **self._source_fields(source),
        )

    def _commit_unknown(
        self,
        source: ValidatedFile,
        *,
        task_id: str | None,
        confirmed: bool,
        failure_stage: str,
        error: str,
        http_status: int | None,
        response: Any = None,
    ) -> str:
        review_copy_path, review_copy_error = self._retain_manual_review_copy(
            source,
            task_id,
        )
        self._append_receipt(
            source,
            task_id=task_id,
            state="manual_review_required",
            confirmed=confirmed,
            write_committed="unknown",
            manual_review_required=True,
            failure_stage=failure_stage,
            http_status=http_status,
            error=error,
            review_copy_path=review_copy_path,
            review_copy_error=review_copy_error,
        )
        return json_result(
            success=False,
            status="manual_review_required",
            upload_status="unknown",
            processing_status="unknown",
            failure_stage=failure_stage,
            write_committed="unknown",
            manual_review_required=True,
            retry_safe=False,
            error=error,
            review_copy_retained=review_copy_path is not None,
            review_copy_path=review_copy_path,
            review_copy_error=review_copy_error,
            http_status=http_status,
            response=response,
            **self._source_fields(source),
        )
