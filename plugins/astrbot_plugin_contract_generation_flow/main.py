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
BUILDER_PROTOCOL_MARKER = '<contract_generation_protocol version="6">'
GENERATION_POLICY_PROTOCOL = "1"
HISTORY_CORPUS_EVENT_KEY = "contract_opencontracts_corpus_slug"
ASSET_CORPUS_EVENT_KEY = "contract_generation_asset_corpus_slug_bound"
SEARCH_DEFAULT_LIMIT = 3
TEMPLATE_READ_DEFAULT_CHARS = 80000
REFERENCE_READ_DEFAULT_CHARS = 60000
LIST_DOCUMENTS_PAGE_SIZE = 100
FALLBACK_POLICY_ALLOW = "allow_ai_fallback"
FALLBACK_POLICY_REQUIRE_TEMPLATE = "require_specific_template"
GENERATION_BASES = (
    "specific_template",
    "history_reference",
    "ai_scaffold",
    "source_draft",
)

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

ASSET_READ_PARAMETERS = {
    "type": "object",
    "properties": {
        "document_slug": {"type": "string", "description": "文档 slug。"},
        "char_offset": {"type": "integer", "description": "字符起点。"},
        "max_chars": {"type": "integer", "description": "本次最多读取字符数。"},
        "use_as_template": {
            "type": "boolean",
            "description": "只有已经决定采用该资产作为本轮专用合同模板时才设为 true。",
        },
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
        "generation_basis": {
            "type": "string",
            "enum": list(GENERATION_BASES),
            "description": (
                "本轮最终实际采用的内容依据：专用模板 specific_template、"
                "历史参考 history_reference、AI 自组织 ai_scaffold；"
                "仅以上一版为主要依据时使用 source_draft。source_draft_id 只是版本来源，"
                "可与 specific_template/history_reference/ai_scaffold 同时使用。"
            ),
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
            "description": "修改上一版时传入已读取的 draft_id；它不替代 generation_basis。",
        },
    },
    "required": ["document_title", "document_markdown", "generation_basis"],
}

KNOWLEDGE_TOOL_SPECS = (
    (
        "find_generation_assets",
        "search_corpus",
        "asset",
        "在生成资产库中检索最匹配的合同模板、参数或规则。普通模式使用语义检索；指定模板模式由运行时按 slug/标题身份确定性解析。",
        SEARCH_PARAMETERS,
    ),
    (
        "read_generation_asset",
        "get_document_text",
        "asset",
        "读取生成资产正文。只有已经决定采用该资产作为专用模板时才传 use_as_template=true；普通参数/规则读取不要绑定为模板。",
        ASSET_READ_PARAMETERS,
    ),
    (
        "find_similar_contracts",
        "search_corpus",
        "history",
        "在历史合同库中语义检索与当前需求最相似的合同，用于结构、条款组合和企业措辞参考。Corpus 已由运行时绑定。",
        SEARCH_PARAMETERS,
    ),
    (
        "read_reference_contract",
        "get_document_text",
        "history",
        "仅当历史检索摘要不足时读取最相关的一份历史合同正文；不要默认迁移旧项目事实。",
        READ_PARAMETERS,
    ),
)

RUNTIME_SOURCE_NAMES = (
    "search_corpus",
    "list_documents",
    "get_document_text",
    "read_latest_contract_draft",
    "read_contract_draft",
    "generate_contract_docx",
    "finalize_contract_draft",
    "publish_contract_download",
)


def _json(**payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def _tool_json(payload: dict[str, Any]) -> str:
    """Compact UTF-8 JSON for model-facing tool results."""
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )


def _filter_args(parameters: dict[str, Any], tool_args: dict[str, Any]) -> dict[str, Any]:
    properties = parameters.get("properties", {}) if isinstance(parameters, dict) else {}
    allowed = set(properties) if isinstance(properties, dict) else set()
    return {key: value for key, value in tool_args.items() if key in allowed}


def _decode_json_dict(value: Any) -> dict[str, Any] | None:
    current = value
    for _ in range(3):
        if isinstance(current, dict):
            return dict(current)
        if not isinstance(current, str):
            return None
        text = current.strip()
        if not text:
            return None
        try:
            current = json.loads(text)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
    return dict(current) if isinstance(current, dict) else None


def _tool_result_is_error(tool_result: Any) -> bool:
    if tool_result is None:
        return False
    if isinstance(tool_result, dict):
        return bool(tool_result.get("isError") or tool_result.get("is_error"))
    return bool(
        getattr(tool_result, "isError", False)
        or getattr(tool_result, "is_error", False)
    )


def _tool_result_texts(tool_result: Any) -> list[str]:
    texts: list[str] = []
    if isinstance(tool_result, str):
        return [tool_result]
    if isinstance(tool_result, dict):
        content = tool_result.get("content")
    else:
        content = getattr(tool_result, "content", None)
    if not isinstance(content, list):
        return texts
    for item in content:
        text = item.get("text") if isinstance(item, dict) else getattr(item, "text", None)
        if text is not None:
            texts.append(str(text))
    return texts


def _tool_error_detail(tool_result: Any, limit: int = 1000) -> str:
    pieces = _tool_result_texts(tool_result)
    if isinstance(tool_result, dict):
        direct_error = tool_result.get("error")
        if direct_error:
            pieces.append(str(direct_error))
        structured = tool_result.get("structuredContent")
        if structured is None:
            structured = tool_result.get("structured_content")
    else:
        structured = getattr(tool_result, "structuredContent", None)
        if structured is None:
            structured = getattr(tool_result, "structured_content", None)
    if structured is not None:
        pieces.append(str(structured))
    detail = " | ".join(piece.strip() for piece in pieces if piece.strip())
    return detail[:limit]


def _tool_result_payload(tool_result: Any) -> dict[str, Any] | None:
    if tool_result is None or _tool_result_is_error(tool_result):
        return None

    if isinstance(tool_result, dict):
        has_wrapper_shape = any(
            key in tool_result
            for key in (
                "content",
                "structuredContent",
                "structured_content",
                "isError",
                "is_error",
            )
        )
        structured = tool_result.get("structuredContent")
        if structured is None:
            structured = tool_result.get("structured_content")
        parsed = _decode_json_dict(structured)
        if parsed is not None:
            return parsed
        for piece in _tool_result_texts(tool_result):
            parsed = _decode_json_dict(piece)
            if parsed is not None:
                return parsed
        return None if has_wrapper_shape else dict(tool_result)

    structured = getattr(tool_result, "structuredContent", None)
    if structured is None:
        structured = getattr(tool_result, "structured_content", None)
    parsed = _decode_json_dict(structured)
    if parsed is not None:
        return parsed

    for piece in _tool_result_texts(tool_result):
        parsed = _decode_json_dict(piece)
        if parsed is not None:
            return parsed
    return None


def _normalized_tool_failure(
    *,
    failure_stage: str,
    error: str,
    retry_safe: bool = True,
) -> str:
    return _tool_json(
        {
            "success": False,
            "status": "blocked" if retry_safe else "failed",
            "failure_stage": failure_stage,
            "error": error,
            "retry_safe": retry_safe,
        }
    )


def _resolve_registered_tool(context: Context, name: str) -> FunctionTool | None:
    return context.get_llm_tool_manager().get_full_tool_set().get_tool(name)


async def _invoke_registered_tool(
    tool: FunctionTool,
    context: Any,
    **tool_args: Any,
) -> Any:
    """Execute a registered tool while keeping framework exceptions out of LLM context."""
    result: Any = None
    try:
        async for item in FunctionToolExecutor.execute(
            tool=tool,
            run_context=context,
            **tool_args,
        ):
            if item is not None:
                result = item
    except Exception:
        logger.exception(
            "Contract generation flow: registered tool %s raised during execution",
            getattr(tool, "name", type(tool).__name__),
        )
        return {
            "isError": True,
            "error": "registered tool execution failed",
        }
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


def _search_result_count(payload: dict[str, Any]) -> int:
    results = payload.get("results")
    return len(results) if isinstance(results, list) else 0


def _search_candidates(payload: dict[str, Any]) -> dict[str, dict[str, str]]:
    candidates: dict[str, dict[str, str]] = {}
    results = payload.get("results")
    if not isinstance(results, list):
        return candidates
    for item in results:
        if not isinstance(item, dict):
            continue
        slug = str(item.get("document_slug") or item.get("slug") or "").strip()
        if not slug:
            continue
        title = str(item.get("document_title") or item.get("title") or "").strip()
        candidates[slug] = {
            "document_slug": slug,
            "document_title": title,
        }
    return candidates


def _normalized_lookup(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def _template_identity_key(value: Any) -> str:
    text = "".join(
        char
        for char in str(value or "").strip().casefold()
        if char.isalnum()
    )
    for suffix in ("生成模板", "template", "模板"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    return text


def _template_identity_matches(query: str, slug: str, title: str) -> bool:
    query_lookup = _normalized_lookup(query)
    if query_lookup and query_lookup == _normalized_lookup(slug):
        return True
    query_key = _template_identity_key(query)
    title_key = _template_identity_key(title)
    return bool(query_key and title_key and query_key == title_key)


def _merge_candidate_maps(
    event: AstrMessageEvent,
    key: str,
    additions: dict[str, dict[str, str]],
) -> dict[str, dict[str, str]]:
    current = event.get_extra(key, {})
    merged = dict(current) if isinstance(current, dict) else {}
    for slug, metadata in additions.items():
        merged[str(slug)] = dict(metadata)
    event.set_extra(key, merged)
    return merged


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
            return _normalized_tool_failure(
                failure_stage="runtime_tool",
                error=f"运行工具 {self._source_name} 当前不可用。",
            )
        result = await _invoke_registered_tool(
            source,
            context,
            **_filter_args(self.parameters, tool_args),
        )
        if _tool_result_is_error(result):
            logger.warning(
                "Contract generation flow: runtime tool %s returned error: %s",
                self._source_name,
                _tool_error_detail(result),
            )
            return _normalized_tool_failure(
                failure_stage="runtime_tool",
                error=f"运行工具 {self._source_name} 调用失败。",
            )
        payload = _tool_result_payload(result)
        if payload is None:
            logger.warning(
                "Contract generation flow: runtime tool %s returned unparseable result",
                self._source_name,
            )
            return _normalized_tool_failure(
                failure_stage="runtime_result",
                error=f"运行工具 {self._source_name} 返回了无法解析的结果。",
            )
        return _tool_json(payload)


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

    @staticmethod
    def _record_search_attempt(event: AstrMessageEvent, tool_name: str) -> None:
        if tool_name == "find_generation_assets":
            event.set_extra("contract_generation_asset_search_attempted", True)
        elif tool_name == "find_similar_contracts":
            event.set_extra("contract_generation_history_search_attempted", True)

    @staticmethod
    def _strict_template_mode(event: AstrMessageEvent) -> bool:
        return bool(event.get_extra("contract_generation_require_specific_template", False))

    async def _resolve_required_template_identity(
        self,
        context: Any,
        *,
        corpus_slug: str,
        required_query: str,
    ) -> tuple[dict[str, Any] | None, str | None]:
        source = _resolve_registered_tool(self._context, "list_documents")
        if source is None or not getattr(source, "active", True):
            return None, "OpenContracts 工具 list_documents 当前不可用。"

        documents: list[dict[str, Any]] = []
        offset = 0
        total_count: int | None = None
        while total_count is None or offset < total_count:
            result = await _invoke_registered_tool(
                source,
                context,
                corpus_slug=corpus_slug,
                limit=LIST_DOCUMENTS_PAGE_SIZE,
                offset=offset,
                search="",
            )
            if _tool_result_is_error(result):
                logger.warning(
                    "Contract generation flow: list_documents failed during strict template resolution: %s",
                    _tool_error_detail(result),
                )
                return None, "指定模板身份解析失败。"
            payload = _tool_result_payload(result)
            if not isinstance(payload, dict):
                return None, "指定模板身份解析返回了无法解析的结果。"
            page = payload.get("documents")
            if not isinstance(page, list):
                return None, "指定模板身份解析缺少 documents。"
            try:
                total_count = max(0, int(payload.get("total_count", len(page)) or 0))
            except (TypeError, ValueError):
                return None, "指定模板身份解析返回了非法 total_count。"
            documents.extend(item for item in page if isinstance(item, dict))
            if not page:
                break
            offset += len(page)
            if offset <= 0:
                break

        matches: list[dict[str, Any]] = []
        for document in documents:
            slug = str(document.get("slug") or "").strip()
            title = str(document.get("title") or "").strip()
            if not slug or not _template_identity_matches(required_query, slug, title):
                continue
            matches.append(
                {
                    "type": "document_identity",
                    "document_slug": slug,
                    "document_title": title,
                    "description": str(document.get("description") or ""),
                    "identity_verified": True,
                }
            )

        return {
            "query": required_query,
            "identity_resolution": "slug_or_normalized_title",
            "identity_verified": bool(matches),
            "results": matches,
        }, None

    async def call(self, context: Any, **tool_args: Any) -> Any:
        event = context.context.event
        self._record_search_attempt(event, self.name)

        if not event.get_extra("contract_generation_policy_verified", False):
            return _normalized_tool_failure(
                failure_stage="generation_policy",
                error=str(
                    event.get_extra("contract_generation_policy_error", "")
                    or "生成策略无效。"
                ),
            )

        strict_template = self._strict_template_mode(event)
        if strict_template and self.name in {
            "find_similar_contracts",
            "read_reference_contract",
        }:
            return _normalized_tool_failure(
                failure_stage="generation_policy",
                error="指定模板模式不使用历史合同，请只检索并读取用户指定模板。",
            )

        corpus_slug = self._corpus_slug(event)
        if not corpus_slug:
            return _normalized_tool_failure(
                failure_stage=(
                    "generation_asset_corpus"
                    if self._role == "asset"
                    else "history_corpus"
                ),
                error="目标合同库未绑定。",
            )

        forwarded_args = _filter_args(self.parameters, tool_args)
        use_as_template = False
        if self.name == "read_generation_asset":
            use_as_template = bool(forwarded_args.pop("use_as_template", False))

        if strict_template and self.name == "find_generation_assets":
            required_query = str(
                event.get_extra("contract_generation_required_template_query", "") or ""
            ).strip()
            actual_query = str(forwarded_args.get("query") or "").strip()
            if not required_query or _normalized_lookup(actual_query) != _normalized_lookup(
                required_query
            ):
                return _normalized_tool_failure(
                    failure_stage="required_template_search",
                    error="指定模板模式必须使用 required_template_query 原样检索生成资产。",
                )
            payload, resolution_error = await self._resolve_required_template_identity(
                context,
                corpus_slug=corpus_slug,
                required_query=required_query,
            )
            if resolution_error or payload is None:
                return _normalized_tool_failure(
                    failure_stage="required_template_search",
                    error=resolution_error or "指定模板身份解析失败。",
                )
            candidates = _search_candidates(payload)
            event.set_extra("contract_generation_asset_search_verified", True)
            event.set_extra(
                "contract_generation_asset_search_result_count",
                len(candidates),
            )
            event.set_extra(
                "contract_generation_required_template_candidates",
                candidates,
            )
            event.set_extra(
                "contract_generation_required_template_search_verified", True
            )
            return _tool_json(payload)

        if strict_template and self.name == "read_generation_asset" and use_as_template:
            requested_slug = str(forwarded_args.get("document_slug") or "").strip()
            candidates = event.get_extra(
                "contract_generation_required_template_candidates", {}
            )
            candidates = dict(candidates) if isinstance(candidates, dict) else {}
            if not requested_slug or requested_slug not in candidates:
                return _normalized_tool_failure(
                    failure_stage="required_template_match",
                    error="只能把本轮 required_template_query 确定性解析出的模板候选绑定为指定模板。",
                )

        source = _resolve_registered_tool(self._context, self._source_name)
        if source is None or not getattr(source, "active", True):
            return _normalized_tool_failure(
                failure_stage="opencontracts_tool",
                error=f"OpenContracts 工具 {self._source_name} 当前不可用。",
            )

        self._defaults(forwarded_args)
        forwarded_args["corpus_slug"] = corpus_slug

        result = await _invoke_registered_tool(source, context, **forwarded_args)
        if _tool_result_is_error(result):
            logger.warning(
                "Contract generation flow: OpenContracts tool %s returned error: %s",
                self._source_name,
                _tool_error_detail(result),
            )
            return _normalized_tool_failure(
                failure_stage="opencontracts_tool",
                error=f"OpenContracts 工具 {self._source_name} 调用失败。",
            )

        payload = _tool_result_payload(result)
        if payload is None:
            logger.warning(
                "Contract generation flow: OpenContracts tool %s returned unparseable result",
                self._source_name,
            )
            return _normalized_tool_failure(
                failure_stage="opencontracts_result",
                error=f"OpenContracts 工具 {self._source_name} 返回了无法解析的结果。",
            )

        normalized = _tool_json(payload)
        if payload.get("error") or payload.get("success") is False:
            return normalized

        if self.name == "find_generation_assets":
            current_count = _search_result_count(payload)
            previous_count = int(
                event.get_extra("contract_generation_asset_search_result_count", 0) or 0
            )
            event.set_extra("contract_generation_asset_search_verified", True)
            event.set_extra(
                "contract_generation_asset_search_result_count",
                previous_count + current_count,
            )
        elif self.name == "find_similar_contracts":
            current_count = _search_result_count(payload)
            previous_count = int(
                event.get_extra("contract_generation_history_search_result_count", 0)
                or 0
            )
            event.set_extra("contract_generation_history_search_verified", True)
            event.set_extra(
                "contract_generation_history_search_result_count",
                previous_count + current_count,
            )
            if current_count > 0:
                event.set_extra("contract_generation_history_search_had_results", True)
            _merge_candidate_maps(
                event,
                "contract_generation_history_candidates",
                _search_candidates(payload),
            )
        elif self.name == "read_generation_asset":
            self._record_asset_text(
                event,
                payload,
                forwarded_args,
                use_as_template=use_as_template,
            )
        return normalized

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
        *,
        use_as_template: bool,
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
                "use_as_template": bool(use_as_template),
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
            state["use_as_template"] = bool(
                state.get("use_as_template", False) or use_as_template
            )

        states[slug] = state
        event.set_extra("contract_generation_asset_read_states", states)
        if not state.get("complete") or not state.get("use_as_template"):
            return

        manifest = state.get("manifest")
        manifest = dict(manifest) if isinstance(manifest, dict) else {}
        asset_type = str(manifest.get("asset_type") or "").strip().lower()
        status = str(manifest.get("status") or "").strip().lower()
        if status not in {"", "active"}:
            return
        if asset_type and asset_type != "contract_template":
            return

        strict_template = bool(
            event.get_extra("contract_generation_require_specific_template", False)
        )
        required_match_verified = False
        selected_title = ""
        if strict_template:
            candidates = event.get_extra(
                "contract_generation_required_template_candidates", {}
            )
            candidates = dict(candidates) if isinstance(candidates, dict) else {}
            candidate = candidates.get(slug)
            if not isinstance(candidate, dict):
                return
            required_match_verified = True
            selected_title = str(candidate.get("document_title") or "").strip()

        asset_id = str(manifest.get("asset_id") or slug).strip() or slug
        event.set_extra("contract_generation_template_selected_verified", True)
        event.set_extra("contract_generation_selected_template_document_slug", slug)
        event.set_extra("contract_generation_selected_template_asset_id", asset_id)
        event.set_extra("contract_generation_selected_template_document_title", selected_title)
        event.set_extra(
            "contract_generation_selected_template_required_match_verified",
            required_match_verified,
        )
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
                "必须显式声明本轮实际 generation_basis；source_draft_id 只是版本来源。"
            ),
            parameters=GENERATE_AND_PUBLISH_PARAMETERS,
        )
        self._context = context

    @staticmethod
    def _call_failure(
        result: Any,
        *,
        tool_name: str,
        failure_stage: str,
    ) -> str | None:
        if not _tool_result_is_error(result):
            return None
        logger.warning(
            "Contract generation: tool %s returned error: %s",
            tool_name,
            _tool_error_detail(result),
        )
        return _normalized_tool_failure(
            failure_stage=failure_stage,
            error=f"工具 {tool_name} 调用失败。",
        )

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
            return _normalized_tool_failure(
                failure_stage="generation_runtime",
                error="正式生成工具不可用：" + ", ".join(missing),
            )

        generated = await _invoke_registered_tool(
            generator,
            context,
            **_filter_args(self.parameters, tool_args),
        )
        generated_failure = self._call_failure(
            generated,
            tool_name="generate_contract_docx",
            failure_stage="docx_result",
        )
        if generated_failure:
            return generated_failure
        generated_payload = _tool_result_payload(generated)
        if not isinstance(generated_payload, dict):
            return _normalized_tool_failure(
                failure_stage="docx_result",
                error="DOCX 生成工具返回了无法解析的结果。",
            )
        if not (
            generated_payload.get("success") is True
            and str(generated_payload.get("status") or "").lower() == "ready"
        ):
            return _tool_json(generated_payload)

        source_path = str(generated_payload.get("output_path") or "").strip()
        filename = str(generated_payload.get("output_filename") or "").strip()
        if not source_path or not filename:
            return _normalized_tool_failure(
                failure_stage="docx_result",
                error="DOCX 生成成功但缺少 output_path 或 output_filename。",
            )

        published = await _invoke_registered_tool(
            publisher,
            context,
            source_path=source_path,
            filename=filename,
        )
        published_failure = self._call_failure(
            published,
            tool_name="publish_contract_download",
            failure_stage="publication_result",
        )
        if published_failure:
            return published_failure
        published_payload = _tool_result_payload(published)
        if not isinstance(published_payload, dict):
            return _normalized_tool_failure(
                failure_stage="publication_result",
                error="下载发布工具返回了无法解析的结果。",
            )
        if not (
            published_payload.get("success") is True
            and str(published_payload.get("status") or "").lower() == "ready"
        ):
            return _tool_json(published_payload)

        draft_id = generated_payload.get("draft_id")
        draft_saved = bool(generated_payload.get("draft_saved"))
        finalizer = _resolve_registered_tool(self._context, "finalize_contract_draft")
        if finalizer is not None and getattr(finalizer, "active", True):
            finalized = await _invoke_registered_tool(finalizer, context)
            if _tool_result_is_error(finalized):
                logger.warning(
                    "Contract generation: publication succeeded but draft finalize returned error: %s",
                    _tool_error_detail(finalized),
                )
            else:
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

        return _tool_json(
            {
                "success": True,
                "status": "ready",
                "generation_id": generated_payload.get("generation_id"),
                "generation_basis": generated_payload.get("generation_basis"),
                "renderer": generated_payload.get("renderer"),
                "render_profile": generated_payload.get("render_profile"),
                "draft_id": draft_id,
                "draft_saved": draft_saved,
                "filename": published_payload.get("filename") or filename,
                "size_bytes": published_payload.get("size_bytes")
                or generated_payload.get("size_bytes"),
                "download_url": published_payload.get("download_url"),
                "expires_at": published_payload.get("expires_at"),
                "expires_in_seconds": published_payload.get("expires_in_seconds"),
                "delivery_format": published_payload.get("delivery_format"),
                "publication_id": published_payload.get("publication_id"),
                "idempotent": bool(
                    generated_payload.get("idempotent")
                    or published_payload.get("idempotent")
                ),
            }
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
            "Contract generation flow 0.7.1 initialized: asset_corpus=%s",
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
    def _parse_generation_input(value: Any) -> tuple[dict[str, Any], str]:
        if isinstance(value, dict):
            return dict(value), ""
        if value is None or (isinstance(value, str) and not value.strip()):
            return {}, ""
        if not isinstance(value, str):
            return {}, "Builder handoff input 必须是 JSON 对象。"
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}, "Builder handoff input 不是有效 JSON。"
        if not isinstance(parsed, dict):
            return {}, "Builder handoff input 必须解析为 JSON 对象。"
        return dict(parsed), ""

    @staticmethod
    def _reset_generation_state(event: AstrMessageEvent) -> None:
        values: dict[str, Any] = {
            "contract_generation_generation_id": uuid.uuid4().hex,
            "contract_generation_policy_protocol": "",
            "contract_generation_policy_verified": False,
            "contract_generation_policy_error": "",
            "contract_generation_asset_search_attempted": False,
            "contract_generation_asset_search_verified": False,
            "contract_generation_asset_search_result_count": 0,
            "contract_generation_asset_read_states": {},
            "contract_generation_template_selected_verified": False,
            "contract_generation_selected_template_document_slug": "",
            "contract_generation_selected_template_document_title": "",
            "contract_generation_selected_template_asset_id": "",
            "contract_generation_selected_template_version": "",
            "contract_generation_selected_render_profile": "standard_contract",
            "contract_generation_template_hints": {},
            "contract_generation_history_search_attempted": False,
            "contract_generation_history_search_verified": False,
            "contract_generation_history_search_result_count": 0,
            "contract_generation_history_search_had_results": False,
            "contract_generation_history_candidates": {},
            "contract_generation_fallback_policy": "",
            "contract_generation_require_specific_template": False,
            "contract_generation_required_template_query": "",
            "contract_generation_required_template_search_verified": False,
            "contract_generation_required_template_candidates": {},
            "contract_generation_selected_template_required_match_verified": False,
            "contract_generation_basis_verified": False,
            "contract_generation_basis": "",
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
    def _apply_generation_policy(
        event: AstrMessageEvent,
        parsed_input: dict[str, Any],
        parse_error: str,
    ) -> None:
        if parse_error:
            event.set_extra("contract_generation_fallback_policy", "invalid")
            event.set_extra("contract_generation_policy_error", parse_error)
            return

        protocol = str(parsed_input.get("generation_policy_protocol") or "").strip()
        event.set_extra("contract_generation_policy_protocol", protocol)
        if protocol != GENERATION_POLICY_PROTOCOL:
            event.set_extra("contract_generation_fallback_policy", "invalid")
            event.set_extra(
                "contract_generation_policy_error",
                f"generation_policy_protocol 必须为 {GENERATION_POLICY_PROTOCOL}。",
            )
            return

        if "fallback_policy" not in parsed_input:
            event.set_extra("contract_generation_fallback_policy", "invalid")
            event.set_extra(
                "contract_generation_policy_error",
                "正式生成 handoff 必须显式提供 fallback_policy。",
            )
            return

        raw_policy = parsed_input.get("fallback_policy")
        policy = str(raw_policy or "").strip().lower()
        if policy not in {FALLBACK_POLICY_ALLOW, FALLBACK_POLICY_REQUIRE_TEMPLATE}:
            event.set_extra("contract_generation_fallback_policy", policy or "invalid")
            event.set_extra(
                "contract_generation_policy_error",
                "fallback_policy 只能是 allow_ai_fallback 或 require_specific_template。",
            )
            return

        required_template_query = str(
            parsed_input.get("required_template_query") or ""
        ).strip()
        if policy == FALLBACK_POLICY_REQUIRE_TEMPLATE and not required_template_query:
            event.set_extra("contract_generation_fallback_policy", policy)
            event.set_extra("contract_generation_require_specific_template", True)
            event.set_extra(
                "contract_generation_policy_error",
                "require_specific_template 必须提供 required_template_query。",
            )
            return

        event.set_extra("contract_generation_fallback_policy", policy)
        event.set_extra(
            "contract_generation_require_specific_template",
            policy == FALLBACK_POLICY_REQUIRE_TEMPLATE,
        )
        event.set_extra(
            "contract_generation_required_template_query",
            required_template_query,
        )
        event.set_extra("contract_generation_policy_verified", True)
        event.set_extra("contract_generation_policy_error", "")

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
        if (
            not event.get_extra("contract_generation_require_specific_template", False)
            and not str(event.get_extra(HISTORY_CORPUS_EVENT_KEY, "") or "").strip()
        ):
            missing.append("history_corpus_slug")
        return missing

    async def _ensure_runtime_tools(
        self,
        agent: Any,
        event: AstrMessageEvent,
    ) -> tuple[list[str], list[str]]:
        async with self._runtime_lock:
            if agent.tools is not self._runtime_tools:
                agent.tools = self._runtime_tools

        diagnostics = self._runtime_diagnostics(event)
        event.set_extra("contract_generation_builder_runtime_optional_missing", diagnostics)
        event.set_extra(ASSET_CORPUS_EVENT_KEY, self.asset_corpus_slug)

        if not self._builder_prompt_compatible(agent):
            return [tool.name for tool in self._runtime_tools], [
                "builder_persona_protocol_v6"
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

        parsed_input, parse_error = self._parse_generation_input(tool_args.get("input"))
        event.set_extra("contract_generation_task", True)
        self._reset_generation_state(event)
        self._apply_generation_policy(event, parsed_input, parse_error)
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
        elif not event.get_extra("contract_generation_policy_verified", False):
            logger.error(
                "Contract generation flow: invalid generation policy: %s",
                event.get_extra("contract_generation_policy_error", ""),
            )
        else:
            logger.info(
                "Contract generation flow: Builder runtime ready: generation_id=%s "
                "asset_corpus=%s history_corpus=%s policy_protocol=%s fallback_policy=%s diagnostics=%s tools=%s",
                event.get_extra("contract_generation_generation_id", ""),
                self.asset_corpus_slug,
                event.get_extra(HISTORY_CORPUS_EVENT_KEY, ""),
                event.get_extra("contract_generation_policy_protocol", ""),
                event.get_extra("contract_generation_fallback_policy", ""),
                event.get_extra(
                    "contract_generation_builder_runtime_optional_missing", []
                ),
                runtime_tools,
            )
        await self._send_progress_once(event)
