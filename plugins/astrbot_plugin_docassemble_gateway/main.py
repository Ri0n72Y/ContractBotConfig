from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

from .clients.docassemble_client import DocassembleClient
from .config.settings import GatewaySettings
from .services.generation_integrity_service import GenerationIntegrityService
from .services.generation_service import GenerationService
from .services.output_retention_service import OutputRetentionService


class DocassembleGateway(Star):
    """AstrBot adapter for allowlisted Docassemble document generation."""

    def __init__(
        self,
        context: Context,
        config: AstrBotConfig | None = None,
    ) -> None:
        super().__init__(context, config)
        self.settings = GatewaySettings.from_config(config or {})
        self.client = DocassembleClient(self.settings)
        self.generation = GenerationService(self.settings, self.client)
        self.integrity = GenerationIntegrityService()
        self.retention = OutputRetentionService(self.settings)
        self._cleanup_task: asyncio.Task | None = None

    async def initialize(self) -> None:
        cleanup = await asyncio.to_thread(self.retention.cleanup_expired)
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info(
            "Docassemble gateway 0.2.1 initialized: base_url=%s "
            "allowed_interviews=%d output_retention_seconds=%d cleanup_removed=%d",
            self.settings.base_url,
            len(self.settings.allowed_interviews),
            self.settings.output_retention_seconds,
            cleanup.get("removed", 0),
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
            await asyncio.sleep(self.settings.output_cleanup_interval_seconds)
            cleanup = await asyncio.to_thread(self.retention.cleanup_expired)
            if cleanup.get("skipped_unsafe"):
                logger.warning(
                    "Docassemble output cleanup skipped unsafe files: %d",
                    cleanup["skipped_unsafe"],
                )

    @staticmethod
    def _formal_generation(event: AstrMessageEvent) -> bool:
        return GenerationIntegrityService.formal_generation(event)

    @filter.on_llm_tool_respond(priority=1000)
    async def verify_generation_reference_results(
        self,
        event: AstrMessageEvent,
        *hook_args: Any,
        **hook_kwargs: Any,
    ) -> None:
        tool, tool_args, tool_result = self.integrity.resolve_tool_response(
            hook_args,
            hook_kwargs,
        )
        if tool is None:
            return
        self.integrity.verify_reference_result(
            event,
            tool,
            tool_args,
            tool_result,
        )

    @staticmethod
    def _json(**payload: Any) -> str:
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    @filter.llm_tool(name="docassemble_gateway_status")
    async def docassemble_gateway_status(
        self,
        event: AstrMessageEvent,
        refresh_interviews: bool = False,
    ) -> str:
        """管理员排障：检查 Gateway 配置和 allowlist interview 可用性。

        Args:
            refresh_interviews(boolean): 为 true 时逐个调用
                /api/interview_data 核对 allowlist。
        """
        del event
        error = self.settings.validation_error()
        payload: dict[str, Any] = {
            "configured": error is None,
            "configuration_error": error,
            "base_url": self.settings.base_url,
            "default_interview": self.settings.default_interview,
            "allowed_interviews": list(self.settings.allowed_interviews),
            "result_descriptor_key": self.settings.result_descriptor_key,
            "api_key_configured": bool(self.settings.api_key),
            "output_retention_seconds": self.settings.output_retention_seconds,
            "output_cleanup_interval_seconds": self.settings.output_cleanup_interval_seconds,
        }
        if refresh_interviews and error is None:
            validated: list[str] = []
            invalid: dict[str, str] = {}
            for interview in self.settings.allowed_interviews:
                ok, inspect_error = await self.client.inspect_interview(interview)
                if ok:
                    validated.append(interview)
                else:
                    invalid[interview] = inspect_error or "interview validation failed"
            payload["validated_interviews"] = validated
            payload["invalid_interviews"] = invalid
        return self._json(**payload)

    @filter.llm_tool(name="docassemble_generate_document")
    async def docassemble_generate_document(
        self,
        event: AstrMessageEvent,
        variables: dict,
        interview: str = "",
        output_filename: str = "",
    ) -> str:
        """使用 allowlist interview 生成并取回真实 DOCX。

        Args:
            variables(object): 一次性注入 interview 的完整变量对象。
            interview(string): allowlist 中的完整 interview filename；为空时使用 default_interview。
            output_filename(string): 可选本地交付文件名，只接受文件名。
        """
        formal_generation = self._formal_generation(event)
        if formal_generation:
            self.integrity.clear_generation_output(event)
            if not (
                event.get_extra("contract_gateway_reference_list_verified", False)
                and event.get_extra("contract_gateway_reference_text_verified", False)
            ):
                return self._json(
                    success=False,
                    status="blocked",
                    failure_stage="reference_contract_read",
                    error=(
                        "正式合同生成前必须在本轮 Builder 中先通过 list_documents "
                        "取得真实参考文档，再通过 get_document_text 从 offset 0 "
                        "成功读取其中一份非空正文。"
                    ),
                    retry_safe=True,
                )

            selected_interview = str(
                interview or self.settings.default_interview or ""
            ).strip()
            if "smoke" in selected_interview.lower():
                return self._json(
                    success=False,
                    status="blocked",
                    failure_stage="smoke_interview_forbidden",
                    error="正式客户合同生成禁止使用 smoke interview。",
                    interview=selected_interview or None,
                    retry_safe=True,
                )

        result = await self.generation.generate(
            variables=variables,
            interview=interview,
            output_filename=output_filename,
        )
        if formal_generation:
            self.integrity.record_generation_output(event, result)
        return self._json(**result)
