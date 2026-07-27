from __future__ import annotations

import asyncio
import hashlib
import json
import re
import socket
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
import astrbot.api.message_components as Comp


DOC_CONVERSION_FAILED_TEXT = (
    "该旧版 Word 文件无法转换。请将文件另存为 DOCX 或 PDF 后重新上传。"
)
DOC_CONVERTER_UNAVAILABLE_TEXT = (
    "旧版 Word 转换服务当前不可用。请稍后重试，或将文件另存为 DOCX 或 PDF 后重新上传。"
)
PDF_MAGIC = b"%PDF"
UNAVAILABLE_ERROR_CODES = {
    "converter_dns_failed",
    "converter_connection_refused",
    "converter_timeout",
    "converter_unreachable",
    "converter_request_error",
}


class DocConversionError(RuntimeError):
    """Safe conversion failure carrying a non-sensitive machine-readable code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class ContractDocPreconverter(Star):
    """Convert legacy Word .doc uploads to PDF before Contract File Router runs."""

    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context, config)
        config = config or {}
        self.allowed_platforms = set(config.get("allowed_platforms", ["wecom"]))
        self.enabled = bool(config.get("enabled", True))
        self.converter_url = str(
            config.get(
                "converter_url",
                "http://gotenberg:3000/forms/libreoffice/convert",
            )
        ).strip()
        self.request_timeout_seconds = int(
            config.get("request_timeout_seconds", 90)
        )
        self.max_file_bytes = int(
            config.get("max_file_bytes", 100 * 1024 * 1024)
        )
        self.staging_ttl_seconds = int(
            config.get("staging_ttl_seconds", 172800)
        )
        data_dir = str(
            config.get(
                "data_dir",
                "data/plugins_data/astrbot_plugin_contract_doc_preconverter",
            )
        )
        self.data_dir = Path(data_dir).expanduser().resolve()
        self.output_dir = self.data_dir / "converted"
        self.audit_path = self.data_dir / "conversion_audit.jsonl"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)

    async def initialize(self) -> None:
        logger.info(
            "Contract DOC preconverter 0.1.2 initialized: enabled=%s endpoint=%s",
            self.enabled,
            self._endpoint_label(),
        )

    def _platform_allowed(self, event: AstrMessageEvent) -> bool:
        try:
            return event.get_platform_name() in self.allowed_platforms
        except Exception:
            return False

    @staticmethod
    def _is_doc_component(component: Any) -> bool:
        if not isinstance(component, Comp.File):
            return False
        name = str(getattr(component, "name", None) or "").strip()
        if not name:
            raw = getattr(component, "file", None)
            name = Path(str(raw or "")).name
        return Path(name).suffix.lower() == ".doc"

    @staticmethod
    async def _component_path(component: Any) -> str | None:
        raw = getattr(component, "file", None)
        if raw:
            candidate = Path(str(raw)).expanduser()
            try:
                if candidate.is_file():
                    return str(candidate)
            except OSError:
                pass

        converter = getattr(component, "convert_to_file_path", None)
        if callable(converter):
            try:
                value = converter()
                if hasattr(value, "__await__"):
                    value = await value
                if value:
                    return str(value)
            except Exception as exc:
                raise DocConversionError("source_path_resolve_failed") from exc

        return str(raw) if raw else None

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        try:
            with path.open("rb") as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(block)
        except OSError as exc:
            raise DocConversionError("source_read_failed") from exc
        return digest.hexdigest()

    @staticmethod
    def _safe_pdf_name(original_name: str) -> str:
        source = Path(original_name or "contract.doc").name
        stem = source[: -len(Path(source).suffix)] or "contract"
        return f"{stem}.pdf"

    def _endpoint_label(self) -> str:
        try:
            parsed = urlsplit(self.converter_url)
            host = parsed.hostname or "unknown"
            default_port = 443 if parsed.scheme == "https" else 80
            port = parsed.port or default_port
            path = parsed.path or "/"
            return f"{parsed.scheme or 'http'}://{host}:{port}{path}"
        except Exception:
            return "invalid-converter-url"

    def _cleanup_expired(self) -> None:
        now = time.time()
        for path in self.output_dir.glob("*.pdf"):
            try:
                if now - path.stat().st_mtime > self.staging_ttl_seconds:
                    path.unlink()
            except OSError:
                continue

    @staticmethod
    def _connect_error_code(exc: httpx.ConnectError) -> str:
        current: BaseException | None = exc
        for _ in range(8):
            current = getattr(current, "__cause__", None)
            if current is None:
                break
            if isinstance(current, socket.gaierror):
                return "converter_dns_failed"
            if isinstance(current, ConnectionRefusedError):
                return "converter_connection_refused"
            if isinstance(current, (socket.timeout, TimeoutError)):
                return "converter_timeout"
        return "converter_unreachable"

    def _convert_sync(self, source: Path, original_name: str) -> bytes:
        try:
            source_size = source.stat().st_size
        except OSError as exc:
            raise DocConversionError("source_stat_failed") from exc
        if source_size <= 0 or source_size > self.max_file_bytes:
            raise DocConversionError("source_size_invalid")
        if not self.converter_url:
            raise DocConversionError("converter_url_missing")

        timeout = httpx.Timeout(self.request_timeout_seconds)
        try:
            with source.open("rb") as file_handle:
                with httpx.Client(
                    timeout=timeout,
                    follow_redirects=False,
                    trust_env=False,
                ) as client:
                    response = client.post(
                        self.converter_url,
                        headers={"Accept": "application/pdf"},
                        files={
                            "files": (
                                Path(original_name or "contract.doc").name,
                                file_handle,
                                "application/msword",
                            )
                        },
                    )
        except httpx.TimeoutException as exc:
            raise DocConversionError("converter_timeout") from exc
        except httpx.ConnectError as exc:
            raise DocConversionError(self._connect_error_code(exc)) from exc
        except httpx.RequestError as exc:
            raise DocConversionError("converter_request_error") from exc
        except OSError as exc:
            raise DocConversionError("source_read_failed") from exc

        if response.status_code >= 400:
            raise DocConversionError(f"converter_http_{response.status_code}")

        result = response.content
        if len(result) > self.max_file_bytes:
            raise DocConversionError("converted_file_too_large")
        if not result.startswith(PDF_MAGIC):
            raise DocConversionError("converter_returned_non_pdf")
        return result

    def _write_audit(self, payload: dict[str, Any]) -> None:
        record = {
            "recorded_at": time.time(),
            **payload,
        }
        try:
            with self.audit_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("Contract DOC conversion audit write failed: %s", exc)

    async def _convert_component(self, component: Any) -> dict[str, Any]:
        source_value = await self._component_path(component)
        if not source_value:
            raise DocConversionError("source_path_missing")
        source = Path(source_value).expanduser().resolve()
        if not source.is_file():
            raise DocConversionError("source_file_missing")

        original_name = str(
            getattr(component, "name", None) or source.name or "contract.doc"
        )
        source_sha256 = self._sha256(source)
        pdf_bytes = await asyncio.to_thread(
            self._convert_sync,
            source,
            original_name,
        )

        output_name = self._safe_pdf_name(original_name)
        output = self.output_dir / (
            f"{int(time.time())}_{uuid.uuid4().hex[:10]}_{output_name}"
        )
        temporary = output.with_suffix(".tmp")
        try:
            temporary.write_bytes(pdf_bytes)
            temporary.replace(output)
            output = output.resolve()
        except OSError as exc:
            try:
                if temporary.is_file():
                    temporary.unlink()
            except OSError:
                pass
            raise DocConversionError("converted_file_write_failed") from exc
        output_sha256 = self._sha256(output)

        setattr(component, "file", str(output))
        setattr(component, "name", output_name)

        result = {
            "source_name": Path(original_name).name,
            "source_sha256": source_sha256,
            "working_name": output_name,
            "working_path": str(output),
            "working_sha256": output_sha256,
            "source_format": "doc",
            "target_format": "pdf",
            "backend": "gotenberg",
            "status": "complete",
        }
        self._write_audit(result)
        return result

    @staticmethod
    def _failure_code(exc: Exception) -> str:
        if isinstance(exc, DocConversionError):
            return exc.code
        safe_name = re.sub(r"[^0-9A-Za-z_]+", "_", type(exc).__name__)
        return f"unexpected_{safe_name[:48] or 'error'}"

    @staticmethod
    def _failure_text(code: str) -> str:
        if code in UNAVAILABLE_ERROR_CODES:
            return DOC_CONVERTER_UNAVAILABLE_TEXT
        return DOC_CONVERSION_FAILED_TEXT

    @filter.event_message_type(filter.EventMessageType.ALL, priority=1100)
    async def preconvert(
        self,
        event: AstrMessageEvent,
        *_args: Any,
        **_kwargs: Any,
    ):
        if self is None or not self._platform_allowed(event):
            return
        self._cleanup_expired()

        components = [
            component
            for component in getattr(event.message_obj, "message", [])
            if self._is_doc_component(component)
        ]
        if not components:
            return

        if not self.enabled:
            event.stop_event()
            yield event.plain_result(DOC_CONVERSION_FAILED_TEXT)
            return

        converted: list[dict[str, Any]] = []
        try:
            for component in components:
                converted.append(await self._convert_component(component))
        except Exception as exc:
            for item in converted:
                try:
                    path = Path(str(item.get("working_path") or ""))
                    if path.is_file():
                        path.unlink()
                except OSError:
                    pass
            code = self._failure_code(exc)
            event.set_extra("contract_doc_conversion_error", code)
            self._write_audit(
                {
                    "source_format": "doc",
                    "target_format": "pdf",
                    "backend": "gotenberg",
                    "status": "failed",
                    "error_code": code,
                }
            )
            logger.warning(
                "Contract DOC preconversion failed before routing: "
                "code=%s endpoint=%s",
                code,
                self._endpoint_label(),
            )
            event.stop_event()
            yield event.plain_result(self._failure_text(code))
            return

        event.set_extra("contract_doc_conversions", converted)
        logger.info(
            "Contract DOC preconversion completed for %s file(s).",
            len(converted),
        )
