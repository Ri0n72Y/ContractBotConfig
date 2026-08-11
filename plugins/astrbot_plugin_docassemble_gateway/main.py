from __future__ import annotations

import json
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star

from .clients.docassemble_client import DocassembleClient
from .config.settings import GatewaySettings
from .services.generation_service import GenerationService


class DocassembleGateway(Star):
    """AstrBot adapter for allowlisted Docassemble document generation."""

    BUILDER_PROMPT_MARKER = "<contract_docassemble_builder_policy>"
    BUILDER_ALLOWED_TOOLS = {
        "list_documents",
        "get_document_text",
        "search_corpus",
        "docassemble_gateway_status",
        "docassemble_generate_document",
    }

    def __init__(
        self,
        context: Context,
        config: AstrBotConfig | None = None,
    ) -> None:
        super().__init__(context, config)
        self.settings = GatewaySettings.from_config(config or {})
        self.client = DocassembleClient(self.settings)
        self.generation = GenerationService(self.settings, self.client)

    async def initialize(self) -> None:
        logger.info(
            "Docassemble gateway 0.1.0 initialized: base_url=%s "
            "allowed_interviews=%d",
            self.settings.base_url,
            len(self.settings.allowed_interviews),
        )

    @staticmethod
    def _resolve_provider_request(
        hook_args: tuple[Any, ...],
        hook_kwargs: dict[str, Any],
    ) -> ProviderRequest | None:
        candidate = hook_kwargs.get("req") or hook_kwargs.get("request")
        if isinstance(candidate, ProviderRequest):
            return candidate
        for value in hook_args:
            if isinstance(value, ProviderRequest):
                return value
            if hasattr(value, "func_tool") and hasattr(value, "prompt"):
                return value
        return None

    @filter.on_llm_request(priority=1200)
    async def restrict_builder_tools(
        self,
        event: AstrMessageEvent,
        *hook_args: Any,
        **hook_kwargs: Any,
    ) -> None:
        """Remove fallback tools from the marked Docassemble Builder."""
        del event
        req = self._resolve_provider_request(hook_args, hook_kwargs)
        if req is None:
            return
        system_prompt = str(getattr(req, "system_prompt", "") or "")
        if self.BUILDER_PROMPT_MARKER not in system_prompt:
            return

        tool_set = getattr(req, "func_tool", None)
        tools = getattr(tool_set, "tools", None)
        if not isinstance(tools, list):
            return
        before = [str(getattr(tool, "name", "")) for tool in tools]
        tool_set.tools = [
            tool
            for tool in tools
            if str(getattr(tool, "name", ""))
            in self.BUILDER_ALLOWED_TOOLS
        ]
        after = [
            str(getattr(tool, "name", "")) for tool in tool_set.tools
        ]
        if after != before:
            logger.info(
                "Docassemble gateway: restricted Builder tools, "
                "before=%s after=%s",
                before,
                after,
            )
        if "docassemble_generate_document" not in after:
            logger.error(
                "Docassemble gateway: marked Builder request is missing "
                "docassemble_generate_document; fallback tools remain removed."
            )

    @staticmethod
    def _json(**payload: Any) -> str:
        return json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            default=str,
        )

    @filter.llm_tool(name="docassemble_gateway_status")
    async def docassemble_gateway_status(
        self,
        event: AstrMessageEvent,
        refresh_interviews: bool = False,
    ) -> str:
        """检查 Gateway 配置和 allowlist interview 可用性。

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
        }
        if refresh_interviews and error is None:
            validated: list[str] = []
            invalid: dict[str, str] = {}
            for interview in self.settings.allowed_interviews:
                ok, inspect_error = await self.client.inspect_interview(
                    interview
                )
                if ok:
                    validated.append(interview)
                else:
                    invalid[interview] = (
                        inspect_error or "interview validation failed"
                    )
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
            interview(string): allowlist 中的完整 interview filename；
                为空时使用 default_interview。
            output_filename(string): 可选本地交付文件名，只接受文件名。
        """
        del event
        result = await self.generation.generate(
            variables=variables,
            interview=interview,
            output_filename=output_filename,
        )
        return self._json(**result)
