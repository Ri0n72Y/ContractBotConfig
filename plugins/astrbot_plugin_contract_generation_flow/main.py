from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star
import astrbot.api.message_components as Comp
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor


GENERATION_TOOL = "transfer_to_docassemble_builder"
BUILDER_PROTOCOL_MARKER = '<contract_generation_protocol version="4">'
HISTORY_CORPUS_EVENT_KEY = "contract_opencontracts_corpus_slug"
ASSET_CORPUS_EVENT_KEY = "contract_generation_asset_corpus_slug_bound"
SEARCH_DEFAULT_LIMIT = 3
TEMPLATE_READ_DEFAULT_CHARS = 80000
REFERENCE_READ_DEFAULT_CHARS = 60000

SEARCH_PARAMETERS = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "检索语句。"},
        "limit": {"type": "integer", "description": "最多返回结果数量；默认 3。"},
        "granularity": {
            "type": "string",
            "enum": ["passage", "block", "both"],
            "description": "检索粒度。",
        },
    },
    "required": ["query"],
}

READ_PARAMETERS = {
    "type": "object",
    "properties": {
        "document_slug": {"type": "string", "description": "文档 slug。"},
        "char_offset": {"type": "integer", "description": "字符起点。"},
        "max_chars": {"type": "integer", "description": "本次最多读取字符数。"},
    },
    "required": ["document_slug"],
}

READ_LATEST_DRAFT_PARAMETERS = {
    "type": "object",
    "properties": {
        "max_chars": {
            "type": "integer",
            "description": "首次最多读取字符数，默认 60000。",
        }
    },
}

READ_DRAFT_PARAMETERS = {
    "type": "object",
    "properties": {
        "draft_id": {"type": "string", "description": "草稿 ID。"},
        "char_offset": {"type": "integer", "description": "字符起点。"},
        "max_chars": {
            "type": "integer",
            "description": "本次最多读取字符数，默认 60000。",
        },
    },
    "required": ["draft_id"],
}

GENERATE_AND_PUBLISH_PARAMETERS = {
    "type": "object",
    "properties": {
        "document_title": {"type": "string", "description": "合同标题。"},
        "document_markdown": {
            "type": "string",
            "description": "已经编制完成的完整合同 Markdown。",
        },
        "output_filename": {
            "type": "string",
            "description": "可选 DOCX 文件名。",
        },
        "render_profile": {
            "type": "string",
            "description": "排版 profile，通常使用 standard_contract。",
        },
        "source_draft_id": {
            "type": "string",
            "description": "修改上一版时传入已读取的 draft_id。",
        },
    },
    "required": ["document_title", "document_markdown"],
}

KNOWLEDGE_TOOL_SPECS = (
    (
        "find_generation_assets",
        "search_corpus",
        "asset",
        "在生成资产库中语义检索最匹配的合同模板、参数或规则。Corpus 已由运行时绑定。",
        SEARCH_PARAMETERS,
    ),
    (
        "read_generation_asset",
        "get_document_text",
        "asset",
        "读取生成资产正文。选定模板从 char_offset=0 开始，只有返回 next_offset 时才继续读取。",
        READ_PARAMETERS,
    ),
    (
        "find_similar_contracts",
        "search_corpus",
        "history",
        "在历史合同库中语义检索与当前需求最相似的合同。Corpus 已由运行时绑定。",
        SEARCH_PARAMETERS,
    ),
    (
        "read_reference_contract",
        "get_document_text",
        "history",
        "仅当历史检索摘要不足时，读取最相关的一份历史合同正文。",
        READ_PARAMETERS,
    ),
)

RUNTIME_SOURCE_NAMES = (
    "search_corpus",
    "get_document_text",
    "read_latest_contract_draft",
    "read_contract_draft",
    "generate_contract_docx",
    "finalize_contract_draft",
    "publish_contract_download",
)


def _json(**payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def _filter_args(parameters: dict[str, Any], tool_args: dict[str, Any]) -> dict[str, Any]:
    properties = parameters.get("properties", {}) if isinstance(parameters, dict) else {}
    allowed = set(properties) if isinstance(properties, dict) else set()
    return {key: value for key, value in tool_args.items() if key in allowed}


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
        try:
            parsed = json.loads(piece.strip())
        except (TypeError, ValueError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _resolve_registered_tool(context: Context, name: str) -> FunctionTool | None:
    return context.get_llm_tool_manager().get_full_tool_set().get_tool(name)


async def _invoke_registered_tool(
    tool: FunctionTool,
    context: Any,
    **tool_args: Any,
) -> Any:
    """Execute a registered tool through AstrBot's native executor.

    AstrBot 4.23.x decorator tools keep their implementation in ``handler`` and
    inherit the base ``FunctionTool.call`` that raises ``NotImplementedError``.
    The native executor is the compatibility boundary that dispatches handler,
    MCPTool and custom ``call`` implementations with the correct event/context.
    """
    result: Any = None
    async for item in FunctionToolExecutor.execute(
        tool=tool,
        run_context=context,
        **tool_args,
    ):
        if item is not None:
            result = item
    return result


def _scalar(value: str) -> str:
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def _parse_frontmatter(text: str) -> dict[str, Any]:
    lines = str(text or "").lstrip("\ufeff").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    try:
        end = next(
            index
            for index, line in enumerate(lines[1:], start=1)
            if line.strip() == "---"
        )
    except StopIteration:
        return {}

    manifest: dict[str, Any] = {}
    active_list: str | None = None
    for raw in lines[1:end]:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        stripped = raw.strip()
        if stripped.startswith("- ") and active_list:
            value = _scalar(stripped[2:])
            if value:
                current = manifest.setdefault(active_list, [])
                if isinstance(current, list):
                    current.append(value)
            continue
        if raw[:1].isspace() or ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if value:
            manifest[key] = _scalar(value)
            active_list = None
        else:
            manifest[key] = []
            active_list = key
    return manifest


def _list_field(manifest: dict[str, Any], key: str) -> list[str]:
    value = manifest.get(key)
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


class _DynamicRegisteredTool(FunctionTool):
    def __init__(
        self,
        context: Context,
        source_name: str,
        public_name: str,
        description: str,
        parameters: dict[str, Any],
    ) -> None:
        super().__init__(
            name=public_name,
            description=description,
            parameters=parameters,
        )
        self._context = context
        self._source_name = source_name

    async def call(self, context: Any, **tool_args: Any) -> Any:
        source = _resolve_registered_tool(self._context, self._source_name)
        if source is None or not getattr(source, "active", True):
            return _json(
                success=False,
                status="blocked",
                failure_stage="runtime_tool",
                error=f"运行工具 {self._source_name} 当前不可用。",
                retry_safe=True,
            )
        return await _invoke_registered_tool(
            source,
            context,
            **_filter_args(self.parameters, tool_args),
        )


class _BoundCorpusTool(FunctionTool):
    def __init__(
        self,
        context: Context,
        source_name: str,
        public_name: str,
        role: str,
        description: str,
        parameters: dict[str, Any],
        asset_corpus_slug: str,
    ) -> None:
        super().__init__(
            name=public_name,
            description=description,
            parameters=parameters,
        )
        self._context = context
        self._source_name = source_name
        self._role = role
        self._asset_corpus_slug = str(asset_corpus_slug or "").strip()

    def _corpus_slug(self, event: AstrMessageEvent) -> str:
        if self._role == "asset":
            return self._asset_corpus_slug
        return str(event.get_extra(HISTORY_CORPUS_EVENT_KEY, "") or "").strip()

    def _defaults(self, forwarded_args: dict[str, Any]) -> None:
        if self.name in {"find_generation_assets", "find_similar_contracts"}:
            forwarded_args.setdefault("limit", SEARCH_DEFAULT_LIMIT)
        elif self.name == "read_generation_asset":
            forwarded_args.setdefault("char_offset", 0)
            forwarded_args.setdefault("max_chars", TEMPLATE_READ_DEFAULT_CHARS)
        elif self.name == "read_reference_contract":
            forwarded_args.setdefault("char_offset", 0)
            forwarded_args.setdefault("max_chars", REFERENCE_READ_DEFAULT_CHARS)

    async def call(self, context: Any, **tool_args: Any) -> Any:
        event = context.context.event
        corpus_slug = self._corpus_slug(event)
        if not corpus_slug:
            return _json(
                success=False,
                status="blocked",
                failure_stage=(
                    "generation_asset_corpus"
                    if self._role == "asset"
                    else "history_corpus"
                ),
                error="目标合同库未绑定。",
                retry_safe=True,
            )

        source = _resolve_registered_tool(self._context, self._source_name)
        if source is None or not getattr(source, "active", True):
            return _json(
                success=False,
                status="blocked",
                failure_stage="opencontracts_tool",
                error=f"OpenContracts 工具 {self._source_name} 当前不可用。",
                retry_safe=True,
            )

        forwarded_args = _filter_args(self.parameters, tool_args)
        self._defaults(forwarded_args)
        forwarded_args["corpus_slug"] = corpus_slug
        result = await _invoke_registered_tool(source, context, **forwarded_args)
        payload = _tool_result_payload(result)
        if payload is None or payload.get("error") or payload.get("success") is False:
            return result

        if self.name == "find_generation_assets":
            event.set_extra("contract_generation_asset_search_verified", True)
        elif self.name == "find_similar_contracts":
            event.set_extra("contract_generation_history_search_verified", True)
        elif self.name == "read_generation_asset":
            self._record_asset_text(event, payload, forwarded_args)
        return result

    @staticmethod
    def _text_identity(
        payload: dict[str, Any],
        tool_args: dict[str, Any],
    ) -> tuple[str, int, int, str, int | None] | None:
        requested_slug = str(tool_args.get("document_slug") or "").strip()
        returned_slug = str(payload.get("document_slug") or "").strip()
        if not requested_slug or requested_slug != returned_slug:
            return None
        try:
            requested_offset = int(tool_args.get("char_offset", 0) or 0)
            returned_offset = int(payload.get("char_offset", 0) or 0)
            total_chars = int(payload.get("total_chars", 0) or 0)
        except (TypeError, ValueError):
            return None
        text = str(payload.get("text") or "")
        if (
            requested_offset != returned_offset
            or requested_offset < 0
            or total_chars <= 0
            or requested_offset >= total_chars
            or not text
        ):
            return None

        end_offset = returned_offset + len(text)
        if end_offset > total_chars:
            return None
        raw_next = payload.get("next_offset")
        if raw_next is None:
            if end_offset != total_chars:
                return None
            next_offset = None
        else:
            try:
                next_offset = int(raw_next)
            except (TypeError, ValueError):
                return None
            if next_offset != end_offset:
                return None
        return requested_slug, returned_offset, total_chars, text, next_offset

    @classmethod
    def _record_asset_text(
        cls,
        event: AstrMessageEvent,
        payload: dict[str, Any],
        tool_args: dict[str, Any],
    ) -> None:
        identity = cls._text_identity(payload, tool_args)
        if identity is None:
            return
        slug, offset, total_chars, text, next_offset = identity

        states = event.get_extra("contract_generation_asset_read_states", {})
        states = dict(states) if isinstance(states, dict) else {}
        if offset == 0:
            state: dict[str, Any] = {
                "document_slug": slug,
                "manifest": _parse_frontmatter(text),
                "total_chars": total_chars,
                "expected_offset": next_offset,
                "complete": next_offset is None,
            }
        else:
            previous = states.get(slug)
            if not isinstance(previous, dict):
                return
            try:
                if int(previous.get("expected_offset")) != offset:
                    return
                if int(previous.get("total_chars", 0)) != total_chars:
                    return
            except (TypeError, ValueError):
                return
            state = dict(previous)
            state["expected_offset"] = next_offset
            state["complete"] = next_offset is None

        states[slug] = state
        event.set_extra("contract_generation_asset_read_states", states)
        if not state.get("complete"):
            return

        manifest = state.get("manifest")
        manifest = dict(manifest) if isinstance(manifest, dict) else {}
        asset_type = str(manifest.get("asset_type") or "").strip().lower()
        status = str(manifest.get("status") or "").strip().lower()
        if status not in {"", "active"}:
            return
        if asset_type and asset_type != "contract_template":
            return
        if not asset_type and event.get_extra(
            "contract_generation_template_selected_verified", False
        ):
            return

        asset_id = str(manifest.get("asset_id") or slug).strip() or slug
        event.set_extra("contract_generation_template_selected_verified", True)
        event.set_extra("contract_generation_selected_template_document_slug", slug)
        event.set_extra("contract_generation_selected_template_asset_id", asset_id)
        event.set_extra(
            "contract_generation_selected_template_version",
            str(manifest.get("version") or "").strip(),
        )
        event.set_extra(
            "contract_generation_selected_render_profile",
            str(manifest.get("render_profile") or "standard_contract").strip()
            or "standard_contract",
        )
        event.set_extra(
            "contract_generation_template_hints",
            {
                "required_headings": _list_field(manifest, "required_headings"),
                "parameter_assets": _list_field(manifest, "parameter_assets"),
                "rule_assets": _list_field(manifest, "rule_assets"),
            },
        )


class _GenerateAndPublishTool(FunctionTool):
    def __init__(self, context: Context) -> None:
        super().__init__(
            name="generate_and_publish_contract",
            description=(
                "把完整合同 Markdown 生成 DOCX 并立即发布临时 HTTPS 下载链接。"
                "这是正式生成的最后一个工具，不需要再单独调用发布工具。"
            ),
            parameters=GENERATE_AND_PUBLISH_PARAMETERS,
        )
        self._context = context

    async def call(self, context: Any, **tool_args: Any) -> Any:
        generator = _resolve_registered_tool(self._context, "generate_contract_docx")
        publisher = _resolve_registered_tool(self._context, "publish_contract_download")
        missing = [
            name
            for name, tool in (
                ("generate_contract_docx", generator),
                ("publish_contract_download", publisher),
            )
            if tool is None or not getattr(tool, "active", True)
        ]
        if missing:
            return _json(
                success=False,
                status="blocked",
                failure_stage="generation_runtime",
                error="正式生成工具不可用：" + ", ".join(missing),
                retry_safe=True,
            )

        generated = await _invoke_registered_tool(
            generator,
            context,
            **_filter_args(self.parameters, tool_args),
        )
        generated_payload = _tool_result_payload(generated)
        if not isinstance(generated_payload, dict):
            return _json(
                success=False,
                status="failed",
                failure_stage="docx_result",
                error="DOCX 生成工具返回了无法解析的结果。",
                retry_safe=True,
            )
        if not (
            generated_payload.get("success") is True
            and str(generated_payload.get("status") or "").lower() == "ready"
        ):
            return generated

        source_path = str(generated_payload.get("output_path") or "").strip()
        filename = str(generated_payload.get("output_filename") or "").strip()
        if not source_path or not filename:
            return _json(
                success=False,
                status="failed",
                failure_stage="docx_result",
                error="DOCX 生成成功但缺少 output_path 或 output_filename。",
                retry_safe=True,
            )

        published = await _invoke_registered_tool(
            publisher,
            context,
            source_path=source_path,
            filename=filename,
        )
        published_payload = _tool_result_payload(published)
        if not isinstance(published_payload, dict):
            return _json(
                success=False,
                status="failed",
                failure_stage="publication_result",
                error="下载发布工具返回了无法解析的结果。",
                retry_safe=True,
            )
        if not (
            published_payload.get("success") is True
            and str(published_payload.get("status") or "").lower() == "ready"
        ):
            return published

        draft_id = generated_payload.get("draft_id")
        draft_saved = bool(generated_payload.get("draft_saved"))
        finalizer = _resolve_registered_tool(self._context, "finalize_contract_draft")
        if finalizer is not None and getattr(finalizer, "active", True):
            try:
                finalized = await _invoke_registered_tool(finalizer, context)
                finalized_payload = _tool_result_payload(finalized)
                if isinstance(finalized_payload, dict) and (
                    finalized_payload.get("success") is True
                    and str(finalized_payload.get("status") or "").lower() == "ready"
                ):
                    draft_id = finalized_payload.get("draft_id") or draft_id
                    draft_saved = bool(finalized_payload.get("draft_saved"))
                else:
                    logger.warning(
                        "Contract generation: publication succeeded but draft finalize did not complete."
                    )
            except Exception:
                logger.exception(
                    "Contract generation: publication succeeded but draft finalize raised."
                )

        return _json(
            success=True,
            status="ready",
            generation_id=generated_payload.get("generation_id"),
            renderer=generated_payload.get("renderer"),
            render_profile=generated_payload.get("render_profile"),
            draft_id=draft_id,
            draft_saved=draft_saved,
            filename=published_payload.get("filename") or filename,
            size_bytes=published_payload.get("size_bytes")
            or generated_payload.get("size_bytes"),
            download_url=published_payload.get("download_url"),
            expires_at=published_payload.get("expires_at"),
            expires_in_seconds=published_payload.get("expires_in_seconds"),
            delivery_format=published_payload.get("delivery_format"),
            publication_id=published_payload.get("publication_id"),
            idempotent=bool(
                generated_payload.get("idempotent")
                or published_payload.get("idempotent")
            ),
        )


class ContractGenerationFlow(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None) -> None:
        super().__init__(context, config)
        self._context = context
        config = config or {}
        self.asset_corpus_slug = str(
            config.get("generation_asset_corpus_slug", "contract-templates")
        ).strip()
        self.progress_enabled = bool(config.get("generation_progress_enabled", True))
        self.progress_text = str(
            config.get(
                "generation_progress_text",
                "正在匹配合同模板和历史参考合同，并生成可编辑 DOCX。",
            )
        ).strip()
        self._runtime_lock = asyncio.Lock()
        self._runtime_tools = self._build_runtime_tools()

    async def initialize(self) -> None:
        logger.info(
            "Contract generation flow 0.6.2 initialized: asset_corpus=%s",
            self.asset_corpus_slug or "<empty>",
        )

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
    def _reset_generation_state(event: AstrMessageEvent) -> None:
        values: dict[str, Any] = {
            "contract_generation_generation_id": uuid.uuid4().hex,
            "contract_generation_asset_search_verified": False,
            "contract_generation_asset_read_states": {},
            "contract_generation_template_selected_verified": False,
            "contract_generation_selected_template_document_slug": "",
            "contract_generation_selected_template_asset_id": "",
            "contract_generation_selected_template_version": "",
            "contract_generation_selected_render_profile": "standard_contract",
            "contract_generation_template_hints": {},
            "contract_generation_history_search_verified": False,
            "contract_generation_renderer_output_verified": False,
            "contract_generation_renderer_output": {},
            "contract_generation_pending_draft": {},
            "contract_generation_download_publication_verified": False,
            "contract_generation_download_publication_record": {},
            "contract_generation_builder_ready_claimed": False,
            "contract_generation_builder_runtime_optional_missing": [],
            "contract_generation_gateway_output_verified": False,
            "contract_generation_gateway_output": {},
            "contract_generation_terminal_failure": False,
            "contract_generation_terminal_failure_reason": "",
        }
        for key, value in values.items():
            event.set_extra(key, value)

    @staticmethod
    def _builder_prompt_compatible(agent: Any) -> bool:
        prompt = str(getattr(agent, "instructions", "") or "").strip()
        return bool(prompt and BUILDER_PROTOCOL_MARKER in prompt)

    def _build_runtime_tools(self) -> list[FunctionTool]:
        tools: list[FunctionTool] = []
        for public_name, source_name, role, description, parameters in KNOWLEDGE_TOOL_SPECS:
            tools.append(
                _BoundCorpusTool(
                    context=self._context,
                    source_name=source_name,
                    public_name=public_name,
                    role=role,
                    description=description,
                    parameters=parameters,
                    asset_corpus_slug=self.asset_corpus_slug,
                )
            )
        tools.extend(
            [
                _DynamicRegisteredTool(
                    context=self._context,
                    source_name="read_latest_contract_draft",
                    public_name="read_latest_contract_draft",
                    description=(
                        "一次取得当前会话最近成功交付合同草稿的元数据和首段正文。"
                        "修改上一版时优先调用。"
                    ),
                    parameters=READ_LATEST_DRAFT_PARAMETERS,
                ),
                _DynamicRegisteredTool(
                    context=self._context,
                    source_name="read_contract_draft",
                    public_name="read_contract_draft",
                    description="仅在上一版草稿返回 next_offset 时继续读取后续正文。",
                    parameters=READ_DRAFT_PARAMETERS,
                ),
                _GenerateAndPublishTool(self._context),
            ]
        )
        return tools

    def _runtime_diagnostics(self, event: AstrMessageEvent) -> list[str]:
        registered = self._context.get_llm_tool_manager().get_full_tool_set()
        missing: list[str] = []
        for name in RUNTIME_SOURCE_NAMES:
            tool = registered.get_tool(name)
            if tool is None or not getattr(tool, "active", True):
                missing.append(name)
        if not self.asset_corpus_slug:
            missing.append("generation_asset_corpus_slug")
        if not str(event.get_extra(HISTORY_CORPUS_EVENT_KEY, "") or "").strip():
            missing.append("history_corpus_slug")
        return missing

    async def _ensure_runtime_tools(
        self,
        agent: Any,
        event: AstrMessageEvent,
    ) -> tuple[list[str], list[str]]:
        # Always bind the same request-neutral wrapper list first. In AstrBot,
        # tools=None means all tools, so leaving an incompatible/new Agent
        # untouched would be less safe than binding the restricted wrappers.
        async with self._runtime_lock:
            if agent.tools is not self._runtime_tools:
                agent.tools = self._runtime_tools

        diagnostics = self._runtime_diagnostics(event)
        event.set_extra("contract_generation_builder_runtime_optional_missing", diagnostics)
        event.set_extra(ASSET_CORPUS_EVENT_KEY, self.asset_corpus_slug)

        if not self._builder_prompt_compatible(agent):
            return [tool.name for tool in self._runtime_tools], [
                "builder_persona_protocol_v4"
            ]
        return [tool.name for tool in self._runtime_tools], []

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

        event.set_extra("contract_generation_task", True)
        self._reset_generation_state(event)
        tool_args["background_task"] = False

        agent = getattr(tool, "agent", None)
        if agent is None:
            runtime_tools, missing = [], ["builder_agent"]
        else:
            runtime_tools, missing = await self._ensure_runtime_tools(agent, event)

        event.set_extra("contract_generation_builder_runtime_tools", runtime_tools)
        event.set_extra("contract_generation_builder_runtime_missing", missing)
        if missing:
            logger.error(
                "Contract generation flow: Builder runtime unavailable: missing=%s",
                missing,
            )
        else:
            logger.info(
                "Contract generation flow: Builder runtime ready: generation_id=%s "
                "asset_corpus=%s history_corpus=%s diagnostics=%s tools=%s",
                event.get_extra("contract_generation_generation_id", ""),
                self.asset_corpus_slug,
                event.get_extra(HISTORY_CORPUS_EVENT_KEY, ""),
                event.get_extra(
                    "contract_generation_builder_runtime_optional_missing", []
                ),
                runtime_tools,
            )
        await self._send_progress_once(event)