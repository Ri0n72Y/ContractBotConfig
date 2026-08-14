from __future__ import annotations

import json
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star
import astrbot.api.message_components as Comp
from astrbot.core.agent.tool import ToolSet


BUILDER_PROMPT_MARKER = "<contract_docassemble_builder_policy>"
GENERATION_TOOL = "transfer_to_docassemble_builder"
REQUIRED_BUILDER_TOOLS = (
    "list_documents",
    "get_document_text",
    "docassemble_generate_document",
    "publish_contract_download",
)


class ContractGenerationFlow(Star):
    """Own the Builder execution path and rebuild its runtime toolset."""

    def __init__(self, context: Context, config: AstrBotConfig | None = None) -> None:
        super().__init__(context, config)
        self._context = context
        config = config or {}
        self.progress_enabled = bool(config.get("generation_progress_enabled", True))
        self.progress_text = str(
            config.get(
                "generation_progress_text",
                "正在读取合同库中的参考合同并生成 DOCX，完成后会返回下载链接。",
            )
        ).strip()

    async def initialize(self) -> None:
        logger.info("Contract generation flow 0.2.1 initialized.")

    @staticmethod
    def _resolve_provider_request(
        hook_args: tuple[Any, ...], hook_kwargs: dict[str, Any]
    ) -> ProviderRequest | None:
        candidate = hook_kwargs.get("req") or hook_kwargs.get("request")
        if isinstance(candidate, ProviderRequest):
            return candidate
        for value in hook_args:
            if isinstance(value, ProviderRequest) or (
                hasattr(value, "func_tool") and hasattr(value, "prompt")
            ):
                return value
        return None

    @staticmethod
    def _resolve_tool(
        hook_args: tuple[Any, ...], hook_kwargs: dict[str, Any]
    ) -> Any | None:
        tool = hook_kwargs.get("tool")
        if tool is not None:
            return tool
        for candidate in hook_args:
            if hasattr(candidate, "name") and not isinstance(candidate, dict):
                return candidate
        return None

    @classmethod
    def _resolve_tool_args(
        cls,
        hook_args: tuple[Any, ...],
        hook_kwargs: dict[str, Any],
    ) -> tuple[Any | None, dict[str, Any] | None]:
        tool = cls._resolve_tool(hook_args, hook_kwargs)
        tool_args = hook_kwargs.get("tool_args")
        if tool_args is None:
            for candidate in hook_args:
                if isinstance(candidate, dict):
                    tool_args = candidate
                    break
        return tool, tool_args

    @staticmethod
    def _tool_names(tool_set: Any) -> list[str]:
        tools = getattr(tool_set, "tools", None)
        if not isinstance(tools, list):
            return []
        return [str(getattr(tool, "name", "")) for tool in tools]

    @staticmethod
    def _append_runtime_system_policy(req: ProviderRequest, text: str) -> None:
        existing = str(getattr(req, "system_prompt", "") or "").strip()
        req.system_prompt = f"{existing}\n\n{text}" if existing else text

    def _rebuild_builder_toolset(
        self,
        req: ProviderRequest,
    ) -> tuple[list[str], list[str], list[str]]:
        before = self._tool_names(getattr(req, "func_tool", None))
        registered = self._context.get_llm_tool_manager().get_full_tool_set()
        rebuilt = ToolSet()
        missing: list[str] = []

        for name in REQUIRED_BUILDER_TOOLS:
            tool = registered.get_tool(name)
            if tool is None or not getattr(tool, "active", True):
                missing.append(name)
                continue
            rebuilt.add_tool(tool)

        if missing:
            req.func_tool = None
            return before, [], missing

        req.func_tool = rebuilt
        return before, self._tool_names(rebuilt), []

    @staticmethod
    def _reset_reference_state(event: AstrMessageEvent) -> None:
        event.set_extra("contract_gateway_reference_documents", [])
        event.set_extra("contract_gateway_reference_list_verified", False)
        event.set_extra("contract_gateway_reference_text_documents", [])
        event.set_extra("contract_gateway_reference_text_verified", False)

    async def _send_progress_once(self, event: AstrMessageEvent) -> None:
        if (
            not self.progress_enabled
            or not self.progress_text
            or event.get_extra("contract_generation_progress_sent", False)
        ):
            return
        try:
            await event.send(MessageChain([Comp.Plain(self.progress_text)]))
            event.set_extra("contract_generation_progress_sent", True)
        except Exception as exc:
            logger.warning("Generation progress message failed: %s", exc)

    @filter.on_llm_request(priority=1200)
    async def prepare_builder_request(
        self,
        event: AstrMessageEvent,
        *hook_args: Any,
        **hook_kwargs: Any,
    ) -> None:
        req = self._resolve_provider_request(hook_args, hook_kwargs)
        if req is None:
            return
        system_prompt = str(getattr(req, "system_prompt", "") or "")
        if BUILDER_PROMPT_MARKER not in system_prompt:
            return

        event.set_extra("contract_docassemble_generation_task", True)
        event.set_extra("contract_generation_builder_active", True)
        self._reset_reference_state(event)

        before, after, missing = self._rebuild_builder_toolset(req)
        event.set_extra("contract_generation_builder_runtime_tools", after)

        if missing:
            self._append_runtime_system_policy(
                req,
                "<contract_generation_runtime_guard>"
                "Builder 运行时核心工具注册不完整。"
                "missing_tools=" + json.dumps(missing, ensure_ascii=False)
                + "。不要调用其他工具补救；直接返回 "
                "[CONTRACT_DOCASSEMBLE:BLOCKED]，"
                "reason=builder_runtime_tool_unavailable。"
                "</contract_generation_runtime_guard>",
            )
            logger.error(
                "Contract generation flow: Builder runtime tools unavailable: "
                "before=%s missing=%s",
                before,
                missing,
            )
            return

        if before != after:
            logger.info(
                "Contract generation flow: rebuilt Builder runtime tools: "
                "before=%s after=%s",
                before,
                after,
            )

        self._append_runtime_system_policy(
            req,
            "<contract_generation_runtime_policy>"
            "本段为当前运行时生成规则，覆盖 Persona 中任何过期的生成前置说明。"
            "只使用 list_documents、get_document_text、"
            "docassemble_generate_document、publish_contract_download 四个工具。"
            "不要调用 docassemble_gateway_status、"
            "contract_download_delivery_status，也不要委派 Operator。"
            "合同库数据源由已绑定 MCP 连接决定；不要要求、猜测或自行构造 corpus_slug。"
            "先 list_documents 获取本轮真实文档列表，再从其中选择最相关 document_slug，"
            "用 get_document_text 从 char_offset=0 读取非空正文。"
            "用户明确信息优先；参考库仍没有的普通草稿字段保留【待填写】并继续，"
            "除非用户明确要求字段不完整就停止。"
            "随后直接形成 document_title 和完整 document_body，调用一次 "
            "docassemble_generate_document；成功后立即调用一次 publish_contract_download。"
            "任何 BLOCKED/FAILED/READY 终态后停止工具调用。"
            "</contract_generation_runtime_policy>",
        )

    @filter.on_using_llm_tool(priority=1050)
    async def mark_generation_execution(
        self,
        event: AstrMessageEvent,
        *hook_args: Any,
        **hook_kwargs: Any,
    ) -> None:
        tool, tool_args = self._resolve_tool_args(hook_args, hook_kwargs)
        if (
            tool is None
            or tool_args is None
            or str(getattr(tool, "name", "")) != GENERATION_TOOL
        ):
            return
        event.set_extra("contract_docassemble_generation_task", True)
        event.set_extra("contract_generation_download_publication_verified", False)
        tool_args["background_task"] = False
        await self._send_progress_once(event)

    @filter.on_llm_tool_respond(priority=900)
    async def finish_builder_execution(
        self,
        event: AstrMessageEvent,
        *hook_args: Any,
        **hook_kwargs: Any,
    ) -> None:
        tool = self._resolve_tool(hook_args, hook_kwargs)
        if tool is None or str(getattr(tool, "name", "")) != GENERATION_TOOL:
            return
        event.set_extra("contract_generation_builder_active", False)
