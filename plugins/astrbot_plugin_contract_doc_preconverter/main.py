from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
import astrbot.api.message_components as Comp


DOC_CONVERSION_FAILED_TEXT = (
    "暂时无法读取该旧版 Word 文件。请将文件另存为 DOCX 或 PDF 后重新上传。"
)
PDF_MAGIC = b"%PDF"


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
            "Contract DOC preconverter 0.1.0 initialized: enabled=%s",
            self.enabled,
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
            return str(raw)
        converter = getattr(component, "convert_to_file_path", None)
        if callable(converter):
            value = converter()
            if hasattr(value, "__await__"):
                value = await value
            return str(value) if value else None
        return None

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _safe_pdf_name(original_name: str) -> str:
        source = Path(original_name or "contract.doc").name
        stem = source[: -len(Path(source).suffix)] or "contract"
        return f"{stem}.pdf"

    def _cleanup_expired(self) -> None:
        now = time.time()
        for path in self.output_dir.glob("*.pdf"):
            try:
                if now - path.stat().st_mtime > self.staging_ttl_seconds:
                    path.unlink()
            except OSError:
                continue

    @staticmethod
    def _multipart_body(file_bytes: bytes, filename: str) -> tuple[bytes, str]:
        boundary = f"contractbot-{uuid.uuid4().hex}"
        safe_filename = filename.replace('"', "_").replace("\r", "_").replace("\n", "_")
        prefix = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="files"; '
            f'filename="{safe_filename}"\r\n'
            "Content-Type: application/msword\r\n\r\n"
        ).encode("utf-8")
        suffix = f"\r\n--{boundary}--\r\n".encode("ascii")
        return prefix + file_bytes + suffix, boundary

    def _convert_sync(self, source: Path, original_name: str) -> bytes:
        source_size = source.stat().st_size
        if source_size <= 0 or source_size > self.max_file_bytes:
            raise ValueError("source_size_invalid")
        if not self.converter_url:
            raise ValueError("converter_url_missing")

        file_bytes = source.read_bytes()
        body, boundary = self._multipart_body(file_bytes, original_name)
        request = Request(
            self.converter_url,
            data=body,
            method="POST",
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Accept": "application/pdf",
            },
        )
        try:
            with urlopen(request, timeout=self.request_timeout_seconds) as response:
                result = response.read(self.max_file_bytes + 1)
        except HTTPError as exc:
            raise RuntimeError(f"converter_http_{exc.code}") from exc
        except URLError as exc:
            raise RuntimeError("converter_unreachable") from exc
        except TimeoutError as exc:
            raise RuntimeError("converter_timeout") from exc

        if len(result) > self.max_file_bytes:
            raise ValueError("converted_file_too_large")
        if not result.startswith(PDF_MAGIC):
            raise ValueError("converter_returned_non_pdf")
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
            raise ValueError("source_path_missing")
        source = Path(source_value).expanduser().resolve()
        if not source.is_file():
            raise ValueError("source_file_missing")

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
        output = self.output_dir / f"{int(time.time())}_{uuid.uuid4().hex[:10]}_{output_name}"
        temporary = output.with_suffix(".tmp")
        temporary.write_bytes(pdf_bytes)
        temporary.replace(output)
        output = output.resolve()
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
            logger.warning(
                "Contract DOC preconversion failed before routing: %s",
                type(exc).__name__,
            )
            event.stop_event()
            yield event.plain_result(DOC_CONVERSION_FAILED_TEXT)
            return

        event.set_extra("contract_doc_conversions", converted)
        logger.info(
            "Contract DOC preconversion completed for %s file(s).",
            len(converted),
        )
