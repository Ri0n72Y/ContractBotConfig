from __future__ import annotations

import json
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star
import astrbot.api.message_components as Comp
from astrbot.core.agent.tool import FunctionTool


GENERATION_TOOL = "transfer_to_docassemble_builder"
BUILDER_PERSONA_ID = "contract_docassemble_builder"
REQUIRED_BUILDER_TOOLS = (
    "list_documents",
    "get_document_text",
    "docassemble_generate_document",
    "publish_contract_download",
)
RUNTIME_GUARD_OPEN = "<contract_generation_runtime_guard>"
RUNTIME_GUARD_CLOSE = "</contract_generation_runtime_guard>"


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
    """Delegate a Builder read tool while recording real reference evidence."""

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
        listed_slugs = (
            {str(value).strip() for value in listed if str(value).strip()}
            if isinstance(listed, list)
            else set()
        )
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
    """Own Builder handoff runtime state and one generation progress message."""

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

    def _refresh_builder_prompt(self, agent: Any) -> bool:
        persona = self._context.persona_manager.get_persona_v3_by_id(
            BUILDER_PERSONA_ID
        )
        if not persona:
            return False
        prompt = str(persona.get("prompt") or "").strip()
        if not prompt:
            return False
        agent.instructions = prompt
        return True

    @staticmethod
    def _append_runtime_guard(agent: Any, missing: list[str]) -> None:
        instructions = str(getattr(agent, "instructions", "") or "").strip()
        guard = (
            RUNTIME_GUARD_OPEN
            + "Builder 运行时核心工具注册不完整。missing_tools="
            + json.dumps(missing, ensure_ascii=False)
            + "。不要调用其他工具补救；直接返回 "
            "[CONTRACT_DOCASSEMBLE:BLOCKED]，"
            "reason=builder_runtime_tool_unavailable。"
            + RUNTIME_GUARD_CLOSE
        )
        agent.instructions = f"{instructions}\n\n{guard}" if instructions else guard

    def _rebuild_handoff_agent(
        self,
        tool: Any,
    ) -> tuple[list[str], list[str], bool]:
        agent = getattr(tool, "agent", None)
        if agent is None:
            return [], list(REQUIRED_BUILDER_TOOLS), False

        prompt_refreshed = self._refresh_builder_prompt(agent)
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
            self._append_runtime_guard(agent, missing)
            return [], missing, prompt_refreshed

        agent.tools = runtime_tools
        return [runtime_tool.name for runtime_tool in runtime_tools], [], prompt_refreshed

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

        runtime_tools, missing, prompt_refreshed = self._rebuild_handoff_agent(tool)
        event.set_extra("contract_generation_builder_runtime_tools", runtime_tools)
        if missing:
            logger.error(
                "Contract generation flow: Builder runtime unavailable: "
                "prompt_refreshed=%s missing_tools=%s",
                prompt_refreshed,
                missing,
            )
        else:
            logger.info(
                "Contract generation flow: refreshed Builder handoff: "
                "prompt_refreshed=%s tools=%s",
                prompt_refreshed,
                runtime_tools,
            )
        await self._send_progress_once(event)
