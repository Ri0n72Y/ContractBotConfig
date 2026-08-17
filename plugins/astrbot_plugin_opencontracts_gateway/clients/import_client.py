from __future__ import annotations

import json
import re
from typing import Any

import httpx

from ..config.settings import GatewaySettings
from ..domain.models import ImportResponse, ValidatedFile


class ImportClient:
    """Call OpenContracts' official document import endpoint with WorkerKey."""

    def __init__(self, settings: GatewaySettings) -> None:
        self.settings = settings

    @staticmethod
    def safe_error_text(value: Any, max_chars: int = 1200) -> str:
        text = str(value or "").strip()
        text = re.sub(
            r"(?i)(authorization|token|workerkey|bearer)\s*[:=]\s*\S+",
            r"\1: [REDACTED]",
            text,
        )
        return text[:max_chars]

    async def upload(
        self,
        source: ValidatedFile,
        data: dict[str, str],
    ) -> ImportResponse:
        try:
            with source.path.open("rb") as file_handle:
                async with httpx.AsyncClient(
                    base_url=self.settings.base_url,
                    timeout=httpx.Timeout(self.settings.timeout_seconds),
                    verify=self.settings.verify_tls,
                    follow_redirects=False,
                ) as client:
                    response = await client.post(
                        self.settings.import_path,
                        headers={
                            "Authorization": (
                                f"WorkerKey {self.settings.worker_key}"
                            ),
                            "Accept": "application/json",
                            "User-Agent": (
                                "AstrBot-OpenContracts-Upload-Gateway/0.6.2"
                            ),
                        },
                        data={**data, "filename": source.source_filename},
                        files={
                            "file": (
                                source.source_filename,
                                file_handle,
                                source.content_type,
                            )
                        },
                    )
        except httpx.TimeoutException:
            return ImportResponse(
                status_code=None,
                body=None,
                transport_error="连接 OpenContracts 导入接口超时。",
            )
        except (httpx.RequestError, OSError) as exc:
            return ImportResponse(
                status_code=None,
                body=None,
                transport_error=self.safe_error_text(exc),
            )

        try:
            body: Any = response.json()
        except ValueError:
            body = {"raw_text": self.safe_error_text(response.text)}
        return ImportResponse(status_code=response.status_code, body=body)


def is_document_conflict(status_code: int | None, body: Any) -> bool:
    if status_code not in {400, 409}:
        return False
    text = json.dumps(body, ensure_ascii=False, default=str).lower()
    signals = (
        "document_path_exists",
        "unique_active_path_per_corpus",
        "duplicate key value violates unique constraint",
        "existing path",
        "path already exists",
        "slug already exists",
    )
    return any(signal in text for signal in signals)
