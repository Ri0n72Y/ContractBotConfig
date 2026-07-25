from __future__ import annotations

from ..domain.models import ValidatedFile
from ..domain.results import json_result


def conflict_result(
    source: ValidatedFile,
    *,
    confirmed: bool,
    http_status: int | None,
) -> str:
    """Map an import-path conflict to confirmation or failure."""
    source_fields = {
        "original_filename": source.original_filename,
        "normalized_filename": source.source_filename,
        "document_title": source.title,
        "contract_date": source.contract_date,
        "contract_title": source.contract_title,
        "source_sha256": source.sha256,
    }
    if not confirmed:
        return json_result(
            success=False,
            status="confirmation_required",
            duplicate=True,
            upload_status="not_started",
            processing_status="not_started",
            customer_action="confirm_reupload_or_cancel",
            conflict_detected_during_upload=True,
            retry_safe=True,
            **source_fields,
        )
    return json_result(
        success=False,
        status="failed",
        upload_status="failed",
        processing_status="not_started",
        failure_stage="version_write_conflict",
        error="已确认重新上传，但 OpenContracts 未接受同路径版本写入。",
        http_status=http_status,
        retry_safe=True,
        **source_fields,
    )


def classify_http(status_code: int | None) -> tuple[str, str]:
    """Classify non-success HTTP responses known not to have committed."""
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
