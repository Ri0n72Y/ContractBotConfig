from __future__ import annotations

import json
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star
import astrbot.api.message_components as Comp

try:
    from astrbot.core.agent.message import TextPart
except Exception:
    TextPart = None


BUILDER_PROMPT_MARKER = "<contract_docassemble_builder_policy>"
GENERATION_TOOL = "transfer_to_docassemble_builder"
REQUIRED_BUILDER_TOOLS = {
    "list_documents",
    "get_document_text",
    "docassemble_generate_document",
    "publish_contract_download",
}


class ContractGenerationFlow(Star):
    """Lean generation UX and Builder runtime guardrails."""

    def __init__(
        self,
        context: Context,
        config: AstrBotConfig | None = None,
    ) -> None:
        super().__init__(context, config)
        config = config or {}
        self.progress_enabled = bool(config.get("generation_progress_enabled", True))
        self.progress_text = str(
            config.get(
                "generation_progress_text",
                "正在读取合同库中的参考合同并生成 DOCX，完成后会返回下载链接。",
            )
        ).strip()

    async def initialize(self) -> None:
        logger.info("Contract generation flow 0.2.0 initialized.")

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

    @staticmethod
    def _resolve_tool_args(
        hook_args: tuple[Any, ...],
        hook_kwargs: dict[str, Any],
    ) -> tuple[Any | None, dict[str, Any] | None]:
        tool = hook_kwargs.get("tool")
        tool_args = hook_kwargs.get("tool_args")
        if tool is None:
            for candidate in hook_args:
                if hasattr(candidate, "name") and not isinstance(candidate, dict):
                    tool = candidate
                    break
        if tool_args is None:
            for candidate in hook_args:
                if isinstance(candidate, dict):
                    tool_args = candidate
                    break
        return tool, tool_args

    @staticmethod
    def _append_temp_instruction(req: ProviderRequest, text: str) -> None:
        if TextPart is not None and hasattr(req, "extra_user_content_parts"):
            part = TextPart(text=text)
            if hasattr(part, "mark_as_temp"):
                part = part.mark_as_temp()
            req.extra_user_content_parts.append(part)
        else:
            req.prompt = f"{req.prompt or ''}\n\n{text}"

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

    @filter.on_llm_request(priority=1150)
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
        tool_set = getattr(req, "func_tool", None)
        tools = getattr(tool_set, "tools", None)
        if isinstance(tools, list):
            names = {str(getattr(tool, "name", "")) for tool in tools}
            missing = sorted(REQUIRED_BUILDER_TOOLS - names)
            if missing:
                tool_set.tools = []
                self._append_temp_instruction(
                    req,
                    "<contract_generation_tool_guard>\n"
                    "Builder 核心运行工具绑定不完整，无法执行本次生成。"
                    f" missing_tools={json.dumps(missing, ensure_ascii=False)}。"
                    "直接返回 [CONTRACT_DOCASSEMBLE:BLOCKED]，"
                    "reason=builder_tool_binding_incomplete。"
                    "\n</contract_generation_tool_guard>",
                )
                logger.error(
                    "Contract generation flow: Builder core tools incomplete: %s",
                    missing,
                )
                return

        self._append_temp_instruction(
            req,
            "<contract_generation_execution_policy>\n"
            "这是已经进入执行阶段的合同草稿生成任务，不存在额外确认门。"
            "用户要求生成、起草、制作或按当前方案生成即视为执行授权。"
            "优先从本轮合同库参考正文补齐可复用信息；"
            "用户未提供且合同库也没有的信息默认保留【待填写】占位符并继续，"
            "除非用户明确要求缺失字段必须停止。"
            "不要为了缺少金额、付款日期、主体工商字段、质保或争议条款等普通草稿字段"
            "再次向用户提问。"
            "\n</contract_generation_execution_policy>",
        )

    @filter.on_using_llm_tool(priority=1050)
    async def mark_generation_execution(
        self,
        event: AstrMessageEvent,
        *hook_args: Any,
        **hook_kwargs: Any,
    ) -> None:
        tool, tool_args = self._resolve_tool_args(hook_args, hook_kwargs)
        if tool is None or tool_args is None:
            return

        tool_name = str(getattr(tool, "name", ""))
        if tool_name != GENERATION_TOOL:
            return

        event.set_extra("contract_docassemble_generation_task", True)
        event.set_extra("contract_generation_download_publication_verified", False)
        event.set_extra(
            "contract_generation_original_handoff_input",
            tool_args.get("input"),
        )
        tool_args["background_task"] = False
        await self._send_progress_once(event)

    @filter.on_using_llm_tool(priority=900)
    async def restore_generation_handoff_after_legacy_guards(
        self,
        event: AstrMessageEvent,
        *hook_args: Any,
        **hook_kwargs: Any,
    ) -> None:
        """Compatibility with older Handoff Policy configs that rewrite duplicates."""
        tool, tool_args = self._resolve_tool_args(hook_args, hook_kwargs)
        if tool is None or tool_args is None:
            return
        if str(getattr(tool, "name", "")) != GENERATION_TOOL:
            return

        raw = tool_args.get("input")
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            parsed = None
        if not isinstance(parsed, dict) or parsed.get("error") != "duplicate_handoff":
            return

        original = event.get_extra("contract_generation_original_handoff_input")
        if original is None:
            return
        tool_args["input"] = original
        tool_args["background_task"] = False
        logger.warning(
            "Contract generation flow: restored Builder handoff rewritten by "
            "legacy duplicate guard."
        )
