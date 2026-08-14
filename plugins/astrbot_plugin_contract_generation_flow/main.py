from __future__ import annotations

import json
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star
import astrbot.api.message_components as Comp
from astrbot.core.agent.tool import FunctionTool


GENERATION_TOOL = "transfer_to_docassemble_builder"
REQUIRED_BUILDER_TOOLS = (
    "list_documents",
    "get_document_text",
    "docassemble_generate_document",
    "publish_contract_download",
)
RUNTIME_POLICY_MARKER = "<contract_generation_runtime_policy>"
RUNTIME_GUARD_MARKER = "<contract_generation_runtime_guard>"


def _tool_result_payload(tool_result: Any) -> dict[str, Any] | None:
    if tool_result is None:
        return None
    if isinstance(tool_result, dict):
        return dict(tool_result)
    if bool(
        getattr(tool_result, "isError", False)
        or getattr(tool_result, "is_error", False)
    ):
        return None

    structured = getattr(tool_result, "structuredContent", None)
    if structured is None:
        structured = getattr(tool_result, "structured_content", None)
    if isinstance(structured, dict):
        return dict(structured)

    pieces: list[str] = []
    if isinstance(tool_result, str):
        pieces.append(tool_result)
    else:
        content = getattr(tool_result, "content", None)
        if isinstance(content, list):
            for item in content:
                text = (
                    item.get("text")
                    if isinstance(item, dict)
                    else getattr(item, "text", None)
                )
                if text is not None:
                    pieces.append(str(text))
    for piece in pieces:
        value = piece.strip()
        if not value:
            continue
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


class _ObservedReferenceTool(FunctionTool):
    """Delegate a Builder MCP read tool while recording real reference evidence."""

    def __init__(self, wrapped: FunctionTool) -> None:
        super().__init__(
            name=wrapped.name,
            description=wrapped.description,
            parameters=wrapped.parameters,
        )
        self._wrapped = wrapped
        self.active = bool(getattr(wrapped, "active", True))

    async def call(self, context: Any, **tool_args: Any) -> Any:
        result = await self._wrapped.call(context, **tool_args)
        event = context.context.event
        payload = _tool_result_payload(result)
        if payload is None:
            logger.warning(
                "Contract generation flow: reference tool result unparseable: %s",
                self.name,
            )
            return result

        if self.name == "list_documents":
            self._record_listing(event, payload)
        elif self.name == "get_document_text":
            self._record_text(event, payload, tool_args)
        return result

    @staticmethod
    def _record_listing(event: AstrMessageEvent, payload: dict[str, Any]) -> None:
        if payload.get("error"):
            return
        documents = payload.get("documents")
        if not isinstance(documents, list):
            return
        try:
            total_count = int(payload.get("total_count", len(documents)) or 0)
        except (TypeError, ValueError):
            return
        if total_count <= 0 or not documents:
            return

        slugs: list[str] = []
        for document in documents:
            if not isinstance(document, dict):
                continue
            slug = str(
                document.get("slug") or document.get("document_slug") or ""
            ).strip()
            if slug and slug not in slugs:
                slugs.append(slug)
        if not slugs:
            return

        event.set_extra("contract_gateway_reference_documents", slugs)
        event.set_extra("contract_gateway_reference_list_verified", True)
        logger.info(
            "Contract generation flow: Builder reference list verified: documents=%d",
            len(slugs),
        )

    @staticmethod
    def _record_text(
        event: AstrMessageEvent,
        payload: dict[str, Any],
        tool_args: dict[str, Any],
    ) -> None:
        if payload.get("error"):
            return
        document_slug = str(tool_args.get("document_slug") or "").strip()
        listed = event.get_extra("contract_gateway_reference_documents", [])
        listed_slugs = {
            str(value).strip()
            for value in listed
            if isinstance(listed, list) and str(value).strip()
        }
        if not document_slug or document_slug not in listed_slugs:
            return

        returned_slug = str(payload.get("document_slug") or "").strip()
        if returned_slug != document_slug:
            return
        try:
            requested_offset = int(tool_args.get("char_offset", 0) or 0)
            returned_offset = int(payload.get("char_offset", 0) or 0)
            total_chars = int(payload.get("total_chars", 0) or 0)
        except (TypeError, ValueError):
            return
        text = str(payload.get("text") or "")
        if (
            requested_offset != 0
            or returned_offset != requested_offset
            or total_chars <= 0
            or not text.strip()
        ):
            return

        verified = event.get_extra("contract_gateway_reference_text_documents", [])
        verified_slugs = (
            [str(value).strip() for value in verified if str(value).strip()]
            if isinstance(verified, list)
            else []
        )
        if document_slug not in verified_slugs:
            verified_slugs.append(document_slug)
        event.set_extra("contract_gateway_reference_text_documents", verified_slugs)
        event.set_extra("contract_gateway_reference_text_verified", True)
        logger.info(
            "Contract generation flow: Builder reference text verified: document=%s",
            document_slug,
        )


class ContractGenerationFlow(Star):
    """Own Builder handoff execution, runtime tools, and one progress message."""

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
    def _resolve_tool_args(
        hook_args: tuple[Any, ...], hook_kwargs: dict[str, Any]
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
    def _reset_reference_state(event: AstrMessageEvent) -> None:
        event.set_extra("contract_gateway_reference_documents", [])
        event.set_extra("contract_gateway_reference_list_verified", False)
        event.set_extra("contract_gateway_reference_text_documents", [])
        event.set_extra("contract_gateway_reference_text_verified", False)

    @staticmethod
    def _runtime_policy() -> str:
        return (
            RUNTIME_POLICY_MARKER
            + "本段为当前运行时生成规则，覆盖 Persona 中任何过期的生成前置说明。"
            "只使用 list_documents、get_document_text、"
            "docassemble_generate_document、publish_contract_download 四个工具。"
            "不要调用 docassemble_gateway_status、contract_download_delivery_status，"
            "也不要委派 Operator。合同库数据源由已绑定 MCP 连接决定；"
            "不要要求、猜测或自行构造 corpus_slug。"
            "先 list_documents 获取本轮真实文档列表，再从其中选择最相关 document_slug，"
            "用 get_document_text 从 char_offset=0 读取非空正文。"
            "用户明确信息优先；参考库仍没有的普通草稿字段保留【待填写】并继续，"
            "除非用户明确要求字段不完整就停止。"
            "随后直接形成 document_title 和完整 document_body，调用一次 "
            "docassemble_generate_document；成功后立即调用一次 publish_contract_download。"
            "任何 BLOCKED/FAILED/READY 终态后停止工具调用。"
            "</contract_generation_runtime_policy>"
        )

    @staticmethod
    def _append_instruction_once(agent: Any, text: str, marker: str) -> None:
        instructions = str(getattr(agent, "instructions", "") or "").strip()
        if marker in instructions:
            return
        agent.instructions = f"{instructions}\n\n{text}" if instructions else text

    def _rebuild_handoff_agent(self, tool: Any) -> tuple[list[str], list[str]]:
        agent = getattr(tool, "agent", None)
        if agent is None:
            return [], list(REQUIRED_BUILDER_TOOLS)

        registered = self._context.get_llm_tool_manager().get_full_tool_set()
        runtime_tools: list[FunctionTool] = []
        missing: list[str] = []
        for name in REQUIRED_BUILDER_TOOLS:
            runtime_tool = registered.get_tool(name)
            if runtime_tool is None or not getattr(runtime_tool, "active", True):
                missing.append(name)
                continue
            if name in {"list_documents", "get_document_text"}:
                runtime_tool = _ObservedReferenceTool(runtime_tool)
            runtime_tools.append(runtime_tool)

        if missing:
            agent.tools = []
            guard = (
                RUNTIME_GUARD_MARKER
                + "Builder 运行时核心工具注册不完整。missing_tools="
                + json.dumps(missing, ensure_ascii=False)
                + "。不要调用其他工具补救；直接返回 "
                "[CONTRACT_DOCASSEMBLE:BLOCKED]，"
                "reason=builder_runtime_tool_unavailable。"
                "</contract_generation_runtime_guard>"
            )
            self._append_instruction_once(agent, guard, RUNTIME_GUARD_MARKER)
            return [], missing

        agent.tools = runtime_tools
        self._append_instruction_once(
            agent,
            self._runtime_policy(),
            RUNTIME_POLICY_MARKER,
        )
        return [tool.name for tool in runtime_tools], []

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
        self._reset_reference_state(event)
        tool_args["background_task"] = False

        runtime_tools, missing = self._rebuild_handoff_agent(tool)
        event.set_extra("contract_generation_builder_runtime_tools", runtime_tools)
        if missing:
            logger.error(
                "Contract generation flow: Builder runtime tools unavailable: %s",
                missing,
            )
        else:
            logger.info(
                "Contract generation flow: rebuilt Builder handoff tools: %s",
                runtime_tools,
            )
        await self._send_progress_once(event)
