from __future__ import annotations

import asyncio
import contextlib
import json
from pathlib import Path
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
import astrbot.api.message_components as Comp

from .config.settings import DeliverySettings
from .services.publication_service import PublicationService


GENERATION_HANDOFF_TOOL = "transfer_to_docassemble_builder"
GENERATION_READY_MARKER = "[CONTRACT_GENERATION:READY]"
PUBLICATION_VERIFIED_KEY = "contract_generation_download_publication_verified"
PUBLICATION_RECORD_KEY = "contract_generation_download_publication_record"


class ContractDownloadDelivery(Star):
    """Publish the current generated DOCX through an expiring HTTPS link."""

    def __init__(
        self,
        context: Context,
        config: AstrBotConfig | None = None,
    ) -> None:
        super().__init__(context, config)
        self.settings = DeliverySettings.from_config(config or {})
        self.publications = PublicationService(self.settings)
        self._cleanup_task: asyncio.Task | None = None

    async def initialize(self) -> None:
        result = await asyncio.to_thread(self.publications.cleanup_expired)
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info(
            "Contract download delivery 0.2.5 initialized: configured=%s "
            "ttl_seconds=%d cleanup_removed=%d",
            self.settings.validation_error() is None,
            self.settings.ttl_seconds,
            result.get("removed", 0),
        )

    async def terminate(self) -> None:
        task = self._cleanup_task
        self._cleanup_task = None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(self.settings.cleanup_interval_seconds)
            result = await asyncio.to_thread(self.publications.cleanup_expired)
            if result.get("skipped_unsafe"):
                logger.warning(
                    "Contract download cleanup skipped unsafe token directories: %d",
                    result["skipped_unsafe"],
                )

    @staticmethod
    def _json(**payload: Any) -> str:
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    @staticmethod
    def _canonical_path(value: str) -> Path | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return Path(text).expanduser().resolve(strict=False)
        except (OSError, RuntimeError, ValueError):
            return None

    @staticmethod
    def _generation_id(event: AstrMessageEvent) -> str:
        return str(
            event.get_extra("contract_generation_generation_id", "") or ""
        ).strip()

    @staticmethod
    def _resolve_tool_response(
        hook_args: tuple[Any, ...],
        hook_kwargs: dict[str, Any],
    ) -> tuple[Any | None, Any | None]:
        tool = hook_kwargs.get("tool")
        tool_result = hook_kwargs.get("tool_result")
        if tool is None:
            for candidate in hook_args:
                if hasattr(candidate, "name") and not isinstance(candidate, dict):
                    tool = candidate
                    break
        if tool_result is None:
            for candidate in hook_args:
                if candidate is tool or isinstance(candidate, dict):
                    continue
                if hasattr(candidate, "content") or isinstance(candidate, str):
                    tool_result = candidate
                    break
        return tool, tool_result

    @staticmethod
    def _tool_result_text(tool_result: Any) -> str:
        if tool_result is None:
            return ""
        if isinstance(tool_result, str):
            return tool_result
        content = getattr(tool_result, "content", None)
        if not isinstance(content, list):
            return ""
        parts: list[str] = []
        for item in content:
            text = (
                item.get("text")
                if isinstance(item, dict)
                else getattr(item, "text", None)
            )
            if text:
                parts.append(str(text))
        return "\n".join(parts).strip()

    @classmethod
    def _matches_current_generation_output(
        cls,
        event: AstrMessageEvent,
        source_path: str,
        filename: str,
    ) -> bool:
        if not event.get_extra("contract_generation_renderer_output_verified", False):
            return False
        expected = event.get_extra("contract_generation_renderer_output", {})
        if not isinstance(expected, dict):
            return False

        expected_generation_id = str(expected.get("generation_id") or "").strip()
        current_generation_id = cls._generation_id(event)
        if current_generation_id and expected_generation_id != current_generation_id:
            return False

        expected_path = cls._canonical_path(str(expected.get("output_path") or ""))
        actual_path = cls._canonical_path(source_path)
        expected_filename = str(expected.get("output_filename") or "").strip()
        actual_filename = str(filename or "").strip()
        return bool(
            expected_path is not None
            and actual_path is not None
            and actual_path == expected_path
            and expected_filename
            and actual_filename == expected_filename
        )

    @classmethod
    def _publication_matches_current_generation(
        cls,
        event: AstrMessageEvent,
    ) -> bool:
        if not event.get_extra(PUBLICATION_VERIFIED_KEY, False):
            return False
        record = event.get_extra(PUBLICATION_RECORD_KEY, {})
        if not isinstance(record, dict):
            return False
        current_generation_id = cls._generation_id(event)
        if current_generation_id:
            return str(record.get("generation_id") or "") == current_generation_id
        return True

    @classmethod
    def _current_publication(
        cls,
        event: AstrMessageEvent,
        source_path: str,
        filename: str,
    ) -> dict[str, Any] | None:
        if not cls._publication_matches_current_generation(event):
            return None
        record = event.get_extra(PUBLICATION_RECORD_KEY, {})
        if not isinstance(record, dict):
            return None
        expected_path = cls._canonical_path(str(record.get("source_path") or ""))
        actual_path = cls._canonical_path(source_path)
        if expected_path is None or actual_path is None or expected_path != actual_path:
            return None
        if str(record.get("requested_filename") or "") != str(filename or "").strip():
            return None
        if not str(record.get("download_url") or "").startswith("https://"):
            return None
        return dict(record)

    @filter.on_llm_tool_respond(priority=950)
    async def observe_builder_ready(
        self,
        event: AstrMessageEvent,
        *hook_args: Any,
        **hook_kwargs: Any,
    ) -> None:
        """Remember whether the current Builder handoff claimed READY."""
        tool, tool_result = self._resolve_tool_response(hook_args, hook_kwargs)
        if tool is None or str(getattr(tool, "name", "")) != GENERATION_HANDOFF_TOOL:
            return
        text = self._tool_result_text(tool_result)
        event.set_extra(
            "contract_generation_builder_ready_claimed",
            GENERATION_READY_MARKER in text,
        )

    @filter.on_decorating_result(priority=950)
    async def enforce_customer_delivery_result(
        self,
        event: AstrMessageEvent,
        *_hook_args: Any,
        **_hook_kwargs: Any,
    ) -> None:
        """Suppress only a false customer-facing READY outcome."""
        if not event.get_extra("contract_generation_builder_ready_claimed", False):
            return
        if self._publication_matches_current_generation(event):
            return
        result = event.get_result()
        chain = getattr(result, "chain", None) if result else None
        if not isinstance(chain, list):
            return
        result.chain = [
            Comp.Plain(
                "文档生成未完成本轮临时下载发布，因此本次不报告生成成功。"
                "请检查合同生成和下载交付配置后重新执行生成。"
            )
        ]
        logger.error(
            "Contract download delivery: suppressed READY without current-generation publication."
        )

    @filter.llm_tool(name="contract_download_delivery_status")
    async def contract_download_delivery_status(
        self,
        event: AstrMessageEvent,
    ) -> str:
        """管理员排障：检查临时合同下载发布配置和清理状态。"""
        del event
        cleanup = await asyncio.to_thread(self.publications.cleanup_expired)
        error = self.settings.validation_error()
        return self._json(
            configured=error is None,
            configuration_error=error,
            public_base_url=self.settings.public_base_url,
            ttl_seconds=self.settings.ttl_seconds,
            max_file_bytes=self.settings.max_file_bytes,
            allowed_source_dirs=[str(path) for path in self.settings.allowed_source_dirs],
            cleanup=cleanup,
        )

    @filter.llm_tool(name="publish_contract_download")
    async def publish_contract_download(
        self,
        event: AstrMessageEvent,
        source_path: str,
        filename: str = "",
    ) -> str:
        """将本轮正式生成的 DOCX 发布为临时 HTTPS 链接。

        Args:
            source_path(string): 本轮 DOCX 生成工具返回的 output_path。
            filename(string): 使用同一次生成结果返回的 output_filename。
        """
        current = self._current_publication(event, source_path, filename)
        if current is not None:
            current.update(success=True, status="ready", idempotent=True)
            return self._json(**current)

        event.set_extra(PUBLICATION_VERIFIED_KEY, False)
        event.set_extra(PUBLICATION_RECORD_KEY, {})

        formal_generation = bool(event.get_extra("contract_generation_task", False))
        if formal_generation and not self._matches_current_generation_output(
            event, source_path, filename
        ):
            return self._json(
                success=False,
                status="blocked",
                failure_stage="generation_output_binding",
                error=(
                    "正式合同下载发布只能使用本轮 DOCX 生成工具刚成功生成的 "
                    "output_path 和 output_filename。"
                ),
                retry_safe=True,
            )

        result = await asyncio.to_thread(
            self.publications.publish,
            source_path=source_path,
            filename=filename,
        )
        verified = bool(
            result.get("success") is True
            and str(result.get("status") or "").lower() == "ready"
            and str(result.get("download_url") or "").startswith("https://")
        )
        event.set_extra(PUBLICATION_VERIFIED_KEY, verified)
        if verified:
            record = {
                **result,
                "generation_id": self._generation_id(event),
                "source_path": source_path,
                "requested_filename": str(filename or "").strip(),
                "idempotent": False,
            }
            event.set_extra(PUBLICATION_RECORD_KEY, record)
            result = dict(result)
            result["generation_id"] = self._generation_id(event)
            result["idempotent"] = False
        return self._json(**result)
