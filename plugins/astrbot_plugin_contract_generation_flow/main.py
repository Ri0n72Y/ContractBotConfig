from __future__ import annotations

import asyncio
import inspect
import json
import uuid
from pathlib import Path
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star
import astrbot.api.message_components as Comp
from astrbot.core.agent.mcp_client import MCPTool
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.skills.skill_manager import SkillInfo, SkillManager


GENERATION_TOOL = "transfer_to_docassemble_builder"
BUILDER_PERSONA_ID = "contract_docassemble_builder"
BUILDER_PROTOCOL_MARKER = '<contract_generation_protocol version="7">'
GENERATION_POLICY_PROTOCOL = "2"
HISTORY_CORPUS_EVENT_KEY = "contract_opencontracts_corpus_slug"
ASSET_CORPUS_EVENT_KEY = "contract_generation_asset_corpus_slug_bound"
DOCUMENT_SPEC_SKILL_NAME = "contract-document-specification"
MAX_BOUND_SKILL_CHARS = 128000
INTERNAL_TOOL_CALL_TIMEOUT_SECONDS = 120
BUILDER_BOUND_TOOL_NAMES = (
    "read_bound_skill",
    "find_generation_assets",
    "read_generation_asset",
    "find_similar_contracts",
    "read_reference_contract",
    "read_latest_contract_draft",
    "read_contract_draft",
    "generate_and_publish_contract",
)
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

BOUND_SKILL_READ_PARAMETERS = {
    "type": "object",
    "properties": {
        "skill_name": {
            "type": "string",
            "description": "要读取的、已绑定到 Builder Persona 的 Skill 名称。",
        }
    },
    "required": ["skill_name"],
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
        "读取生成资产正文。只有已经决定采用该资产作为专用合同模板时才传 use_as_template=true；模板绑定必须来自本轮生成资产检索候选。",
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


def _tool_result_retry_safe(tool_result: Any, default: bool = True) -> bool:
    if isinstance(tool_result, dict) and "retry_safe" in tool_result:
        return bool(tool_result.get("retry_safe"))
    value = getattr(tool_result, "retry_safe", None)
    return default if value is None else bool(value)


def _tool_result_commit_unknown(tool_result: Any) -> bool:
    if isinstance(tool_result, dict):
        return bool(tool_result.get("commit_unknown"))
    return bool(getattr(tool_result, "commit_unknown", False))


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
    status: str | None = None,
    **extra: Any,
) -> str:
    payload: dict[str, Any] = {
        "success": False,
        "status": status or ("blocked" if retry_safe else "failed"),
        "failure_stage": failure_stage,
        "error": error,
        "retry_safe": retry_safe,
    }
    payload.update(extra)
    return _tool_json(payload)


def _resolve_registered_tool(context: Context, name: str) -> FunctionTool | None:
    # Internal composition resolves the raw registered implementation. AstrBot
    # remains responsible for exposing and binding public tools to agents.
    return context.get_llm_tool_manager().get_func(name)


def _mark_terminal_failure(
    event: AstrMessageEvent,
    reason: str,
    *,
    stage: str = "",
    commit_unknown: bool = False,
) -> None:
    event.set_extra("contract_generation_terminal_failure", True)
    event.set_extra("contract_generation_terminal_failure_reason", str(reason or ""))
    if stage:
        event.set_extra("contract_generation_write_stage", stage)
    if commit_unknown:
        event.set_extra("contract_generation_write_commit_unknown", True)
        event.set_extra("contract_generation_write_commit_unknown_stage", stage)


class _EventToolContext:
    """Minimal context for deterministic composition of known registered tools."""

    class _EventView:
        def __init__(self, event: AstrMessageEvent) -> None:
            self.event = event

    def __init__(self, event: AstrMessageEvent) -> None:
        self.context = self._EventView(event)
        self.tool_call_timeout = INTERNAL_TOOL_CALL_TIMEOUT_SECONDS


async def _invoke_registered_tool(
    tool: FunctionTool,
    context: _EventToolContext,
    *,
    side_effecting: bool = False,
    **tool_args: Any,
) -> Any:
    """Call only a known local plugin handler or MCPTool for business composition."""
    try:
        if tool.handler is not None:
            result = tool.handler(context.context.event, **tool_args)
            if inspect.isasyncgen(result):
                last: Any = None
                async for item in result:
                    if item is not None:
                        last = item
                return last
            if inspect.isawaitable(result):
                return await result
            return result
        if isinstance(tool, MCPTool):
            return await tool.call(context, **tool_args)
        logger.error(
            "Contract generation flow: unsupported internal tool implementation: %s",
            getattr(tool, "name", type(tool).__name__),
        )
        return {
            "isError": True,
            "error": "unsupported internal tool implementation",
            "retry_safe": not side_effecting,
            "commit_unknown": side_effecting,
        }
    except asyncio.CancelledError:
        logger.error(
            "Contract generation flow: registered tool %s was cancelled during execution",
            getattr(tool, "name", type(tool).__name__),
        )
        raise
    except Exception:
        logger.exception(
            "Contract generation flow: registered tool %s raised during execution",
            getattr(tool, "name", type(tool).__name__),
        )
        return {
            "isError": True,
            "error": "registered tool execution failed",
            "retry_safe": not side_effecting,
            "commit_unknown": side_effecting,
        }


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


def _builder_bound_skill_names(context: Context) -> list[str]:
    persona_manager = getattr(context, "persona_manager", None)
    if persona_manager is None:
        return []
    persona = persona_manager.get_persona_v3_by_id(BUILDER_PERSONA_ID)
    if not isinstance(persona, dict):
        return []
    raw = persona.get("skills")
    if not isinstance(raw, list):
        return []
    names: list[str] = []
    for item in raw:
        name = str(item or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def _builder_bound_tool_names(context: Context) -> list[str]:
    persona_manager = getattr(context, "persona_manager", None)
    if persona_manager is None:
        return []
    persona = persona_manager.get_persona_v3_by_id(BUILDER_PERSONA_ID)
    if not isinstance(persona, dict):
        return []
    raw = persona.get("tools")
    if not isinstance(raw, list):
        return []
    names: list[str] = []
    for item in raw:
        name = str(item or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def _skill_id_matches_logical_name(skill_id: str, logical_name: str) -> bool:
    skill_id = str(skill_id or "").strip()
    logical_name = str(logical_name or "").strip()
    if not skill_id or not logical_name:
        return False
    if skill_id == logical_name:
        return True
    prefix = f"{logical_name}-"
    if not skill_id.startswith(prefix):
        return False
    version = skill_id[len(prefix):]
    parts = version.split(".")
    return bool(parts) and all(part.isdigit() and part for part in parts)


def _resolve_bound_skill_id(requested_name: str, bound_names: list[str]) -> str | None:
    requested_name = str(requested_name or "").strip()
    if requested_name in bound_names:
        return requested_name
    if requested_name != DOCUMENT_SPEC_SKILL_NAME:
        return None
    candidates = [
        name
        for name in bound_names
        if _skill_id_matches_logical_name(name, DOCUMENT_SPEC_SKILL_NAME)
    ]
    return candidates[0] if len(candidates) == 1 else None


def _skill_request_name(skill_id: str) -> str:
    if _skill_id_matches_logical_name(skill_id, DOCUMENT_SPEC_SKILL_NAME):
        return DOCUMENT_SPEC_SKILL_NAME
    return str(skill_id or "").strip()


def _runtime_name(context: Context, event: AstrMessageEvent) -> str:
    cfg = context.get_config(umo=event.unified_msg_origin) or {}
    provider_settings = cfg.get("provider_settings") or {}
    runtime = str(provider_settings.get("computer_use_runtime", "local") or "local")
    return runtime if runtime in {"local", "sandbox"} else "local"


class _BoundSkillReadTool(FunctionTool):
    def __init__(self, context: Context, skill_manager: SkillManager) -> None:
        super().__init__(
            name="read_bound_skill",
            description=(
                "读取当前 Builder Persona 已绑定且处于启用状态的 Skill 的完整 SKILL.md。"
                "正式合同生成遇到匹配 Skill 时必须先调用本工具完成 grounding；"
                "本工具不允许读取任意本地文件。"
            ),
            parameters=BOUND_SKILL_READ_PARAMETERS,
        )
        self._context = context
        self._skill_manager = skill_manager

    def _resolve_skill(
        self,
        event: AstrMessageEvent,
        skill_name: str,
    ) -> SkillInfo | None:
        bound_names = _builder_bound_skill_names(self._context)
        resolved_name = _resolve_bound_skill_id(skill_name, bound_names)
        if resolved_name is None:
            return None
        runtime = _runtime_name(self._context, event)
        active = self._skill_manager.list_skills(
            active_only=True,
            runtime=runtime,
            show_sandbox_path=False,
        )
        return next((skill for skill in active if skill.name == resolved_name), None)

    async def call(self, context: Any, **tool_args: Any) -> Any:
        event = context.context.event
        event.set_extra("contract_generation_skill_grounding_attempted", True)
        skill_name = str(tool_args.get("skill_name") or "").strip()
        if not skill_name:
            return _normalized_tool_failure(
                failure_stage="skill_grounding",
                error="skill_name 不能为空。",
            )
        try:
            skill = self._resolve_skill(event, skill_name)
        except Exception:
            logger.exception(
                "Contract generation flow: failed to resolve bound Skill %s",
                skill_name,
            )
            return _normalized_tool_failure(
                failure_stage="skill_grounding",
                error=f"Skill {skill_name} 的运行时状态读取失败。",
            )
        if skill is None:
            return _normalized_tool_failure(
                failure_stage="skill_grounding",
                error=f"Skill {skill_name} 未绑定到 Builder、未启用或当前不可读取。",
            )
        if not skill.local_exists:
            return _normalized_tool_failure(
                failure_stage="skill_grounding",
                error=f"Skill {skill_name} 仅存在于隔离运行时，当前受限读取入口无法读取。",
            )
        if (
            _skill_id_matches_logical_name(skill.name, DOCUMENT_SPEC_SKILL_NAME)
            and event.get_extra("contract_generation_document_spec_loaded", False)
            and str(event.get_extra("contract_generation_document_spec_skill_id", "") or "").strip() == skill.name
        ):
            return _tool_json(
                {
                    "success": True,
                    "status": "already_grounded",
                    "skill": DOCUMENT_SPEC_SKILL_NAME,
                    "runtime_id": skill.name,
                    "retry_safe": True,
                }
            )
        try:
            path = Path(skill.path).expanduser().resolve(strict=True)
            if not path.is_file() or path.name != "SKILL.md":
                raise ValueError("invalid skill path")
            content = await asyncio.to_thread(path.read_text, encoding="utf-8")
        except (OSError, RuntimeError, ValueError, UnicodeError) as exc:
            logger.warning(
                "Contract generation flow: failed to read bound Skill %s: %s",
                skill_name,
                exc,
            )
            return _normalized_tool_failure(
                failure_stage="skill_grounding",
                error=f"Skill {skill_name} 的 SKILL.md 读取失败。",
            )
        if not content.strip() or len(content) > MAX_BOUND_SKILL_CHARS:
            return _normalized_tool_failure(
                failure_stage="skill_grounding",
                error=f"Skill {skill_name} 内容为空或超过受限读取上限。",
            )
        loaded = event.get_extra("contract_generation_skill_grounding_loaded", [])
        loaded_names = list(loaded) if isinstance(loaded, list) else []
        if skill_name not in loaded_names:
            loaded_names.append(skill_name)
        event.set_extra("contract_generation_skill_grounding_loaded", loaded_names)
        if _skill_id_matches_logical_name(skill.name, DOCUMENT_SPEC_SKILL_NAME):
            event.set_extra("contract_generation_document_spec_loaded", True)
            event.set_extra("contract_generation_document_spec_skill_id", skill.name)
        logger.info(
            "Contract generation flow: Builder Skill grounded: requested=%s resolved=%s",
            skill_name,
            skill.name,
        )
        return content


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

        query_slug = _normalized_lookup(required_query)
        query_title = _template_identity_key(required_query)
        exact_slug_matches: list[dict[str, Any]] = []
        title_matches: list[dict[str, Any]] = []
        for document in documents:
            slug = str(document.get("slug") or "").strip()
            title = str(document.get("title") or "").strip()
            if not slug:
                continue
            candidate = {
                "type": "document_identity",
                "document_slug": slug,
                "document_title": title,
                "description": str(document.get("description") or ""),
                "identity_verified": True,
            }
            if query_slug and query_slug == _normalized_lookup(slug):
                exact_slug_matches.append(candidate)
            elif query_title and query_title == _template_identity_key(title):
                title_matches.append(candidate)

        if exact_slug_matches:
            matches = exact_slug_matches[:1]
            resolution = "exact_slug"
        elif len(title_matches) == 1:
            matches = title_matches
            resolution = "normalized_title"
        elif len(title_matches) > 1:
            logger.warning(
                "Contract generation flow: required template title is ambiguous: query=%s candidates=%s",
                required_query,
                [item.get("document_slug") for item in title_matches],
            )
            return None, "指定模板标题匹配到多个文档，请使用 document slug 明确指定。"
        else:
            matches = []
            resolution = "not_found"

        return {
            "query": required_query,
            "identity_resolution": resolution,
            "identity_verified": bool(matches),
            "results": matches,
        }, None

    @staticmethod
    def _candidate_set(event: AstrMessageEvent, strict_template: bool) -> dict[str, Any]:
        key = (
            "contract_generation_required_template_candidates"
            if strict_template
            else "contract_generation_asset_candidates"
        )
        value = event.get_extra(key, {})
        return dict(value) if isinstance(value, dict) else {}

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
            _merge_candidate_maps(
                event,
                "contract_generation_asset_candidates",
                candidates,
            )
            event.set_extra(
                "contract_generation_required_template_search_verified", True
            )
            return _tool_json(payload)

        if self.name == "read_generation_asset" and use_as_template:
            requested_slug = str(forwarded_args.get("document_slug") or "").strip()
            candidates = self._candidate_set(event, strict_template)
            if not requested_slug or requested_slug not in candidates:
                return _normalized_tool_failure(
                    failure_stage=(
                        "required_template_match"
                        if strict_template
                        else "generation_template_match"
                    ),
                    error=(
                        "只能把本轮 required_template_query 确定性解析出的模板候选绑定为指定模板。"
                        if strict_template
                        else "只能把本轮 find_generation_assets 实际返回的模板候选绑定为专用模板。"
                    ),
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
                retry_safe=_tool_result_retry_safe(result),
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
            _merge_candidate_maps(
                event,
                "contract_generation_asset_candidates",
                _search_candidates(payload),
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
        candidates = cls._candidate_set(event, strict_template)
        candidate = candidates.get(slug)
        if not isinstance(candidate, dict):
            return

        asset_id = str(manifest.get("asset_id") or slug).strip() or slug
        event.set_extra("contract_generation_template_selected_verified", True)
        event.set_extra("contract_generation_selected_template_document_slug", slug)
        event.set_extra("contract_generation_selected_template_asset_id", asset_id)
        event.set_extra(
            "contract_generation_selected_template_document_title",
            str(candidate.get("document_title") or "").strip(),
        )
        event.set_extra(
            "contract_generation_selected_template_search_match_verified",
            True,
        )
        event.set_extra(
            "contract_generation_selected_template_required_match_verified",
            strict_template,
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
                "把完整合同 Markdown 生成 DOCX、发布临时 HTTPS 下载链接并持久化本轮草稿。"
                "必须显式声明 generation_basis；写操作异常/取消后禁止自动重试。"
            ),
            parameters=GENERATE_AND_PUBLISH_PARAMETERS,
        )
        self._context = context

    @staticmethod
    def _event(context: Any) -> AstrMessageEvent:
        return context.context.event

    @staticmethod
    def _terminal_response(event: AstrMessageEvent) -> str | None:
        if not event.get_extra("contract_generation_terminal_failure", False):
            return None
        reason = str(
            event.get_extra("contract_generation_terminal_failure_reason", "")
            or "本轮生成已经进入不可自动重试状态。"
        )
        return _normalized_tool_failure(
            failure_stage="terminal_failure",
            error=reason,
            retry_safe=False,
            commit_unknown=bool(
                event.get_extra("contract_generation_write_commit_unknown", False)
            ),
        )

    @staticmethod
    def _set_write_stage(event: AstrMessageEvent, stage: str) -> None:
        event.set_extra("contract_generation_write_stage", stage)

    @staticmethod
    def _write_error_response(
        event: AstrMessageEvent,
        result: Any,
        *,
        tool_name: str,
        failure_stage: str,
    ) -> str | None:
        if not _tool_result_is_error(result):
            return None
        retry_safe = _tool_result_retry_safe(result, default=False)
        commit_unknown = _tool_result_commit_unknown(result) or not retry_safe
        detail = _tool_error_detail(result)
        logger.warning(
            "Contract generation: write tool %s returned error: %s",
            tool_name,
            detail,
        )
        if not retry_safe:
            reason = (
                f"写操作 {tool_name} 执行异常，提交状态无法安全确认；"
                "本轮禁止自动重试，请先核查实际生成/发布状态。"
            )
            _mark_terminal_failure(
                event,
                reason,
                stage=failure_stage,
                commit_unknown=commit_unknown,
            )
            return _normalized_tool_failure(
                failure_stage=failure_stage,
                error=reason,
                retry_safe=False,
                commit_unknown=commit_unknown,
            )
        return _normalized_tool_failure(
            failure_stage=failure_stage,
            error=f"工具 {tool_name} 调用失败。",
            retry_safe=True,
        )

    @staticmethod
    def _unsafe_unparseable_write(
        event: AstrMessageEvent,
        *,
        tool_name: str,
        failure_stage: str,
    ) -> str:
        reason = (
            f"写操作 {tool_name} 返回了无法解析的结果，无法确认是否已经产生副作用；"
            "本轮禁止自动重试。"
        )
        _mark_terminal_failure(
            event,
            reason,
            stage=failure_stage,
            commit_unknown=True,
        )
        return _normalized_tool_failure(
            failure_stage=failure_stage,
            error=reason,
            retry_safe=False,
            commit_unknown=True,
        )

    @staticmethod
    def _observe_payload_failure(
        event: AstrMessageEvent,
        payload: dict[str, Any],
        *,
        failure_stage: str,
    ) -> str:
        retry_safe = bool(payload.get("retry_safe", True))
        if not retry_safe:
            _mark_terminal_failure(
                event,
                str(payload.get("error") or "本轮写操作失败且禁止自动重试。"),
                stage=failure_stage,
                commit_unknown=bool(payload.get("commit_unknown", False)),
            )
        return _tool_json(payload)

    @staticmethod
    def _partial_after_publication(
        event: AstrMessageEvent,
        *,
        generated_payload: dict[str, Any],
        published_payload: dict[str, Any],
        filename: str,
        error: str,
        commit_unknown: bool = False,
    ) -> str:
        reason = (
            "合同 DOCX 已完成 HTTPS 发布，但本轮可继续编辑草稿未能可靠持久化。"
            "不要重新执行整条生成链；请保留已发布文件并进行草稿恢复。"
        )
        _mark_terminal_failure(
            event,
            reason,
            stage="draft_finalize",
            commit_unknown=commit_unknown,
        )
        return _normalized_tool_failure(
            failure_stage="draft_finalize",
            error=error or reason,
            retry_safe=False,
            status="partial",
            delivery_committed=True,
            draft_saved=False,
            manual_recovery_required=True,
            generation_id=generated_payload.get("generation_id"),
            generation_basis=generated_payload.get("generation_basis"),
            source_draft_id=generated_payload.get("source_draft_id"),
            filename=published_payload.get("filename") or filename,
            size_bytes=(
                published_payload.get("size_bytes")
                or generated_payload.get("size_bytes")
            ),
            download_url=published_payload.get("download_url"),
            expires_at=published_payload.get("expires_at"),
            expires_in_seconds=published_payload.get("expires_in_seconds"),
            delivery_format=published_payload.get("delivery_format"),
            publication_id=published_payload.get("publication_id"),
            commit_unknown=commit_unknown,
        )

    async def _call_impl(self, context: Any, **tool_args: Any) -> Any:
        event = self._event(context)
        terminal = self._terminal_response(event)
        if terminal is not None:
            return terminal

        if event.get_extra("contract_generation_document_spec_required", True) and not event.get_extra(
            "contract_generation_document_spec_loaded", False
        ):
            return _normalized_tool_failure(
                failure_stage="document_spec_skill",
                error=(
                    "正式合同生成前必须先调用 read_bound_skill 读取并应用 "
                    f"{DOCUMENT_SPEC_SKILL_NAME} Skill。"
                ),
                retry_safe=True,
                required_skill=DOCUMENT_SPEC_SKILL_NAME,
            )

        generator = _resolve_registered_tool(self._context, "generate_contract_docx")
        publisher = _resolve_registered_tool(self._context, "publish_contract_download")
        finalizer = _resolve_registered_tool(self._context, "finalize_contract_draft")
        missing = [
            name
            for name, tool in (
                ("generate_contract_docx", generator),
                ("publish_contract_download", publisher),
                ("finalize_contract_draft", finalizer),
            )
            if tool is None or not getattr(tool, "active", True)
        ]
        if missing:
            return _normalized_tool_failure(
                failure_stage="generation_runtime",
                error="正式生成工具不可用：" + ", ".join(missing),
            )

        assert generator is not None
        assert publisher is not None
        assert finalizer is not None

        self._set_write_stage(event, "docx_generation")
        generated = await _invoke_registered_tool(
            generator,
            context,
            side_effecting=True,
            **_filter_args(self.parameters, tool_args),
        )
        generated_failure = self._write_error_response(
            event,
            generated,
            tool_name="generate_contract_docx",
            failure_stage="docx_result",
        )
        if generated_failure:
            return generated_failure
        generated_payload = _tool_result_payload(generated)
        if not isinstance(generated_payload, dict):
            return self._unsafe_unparseable_write(
                event,
                tool_name="generate_contract_docx",
                failure_stage="docx_result",
            )
        if not (
            generated_payload.get("success") is True
            and str(generated_payload.get("status") or "").lower() == "ready"
        ):
            return self._observe_payload_failure(
                event,
                generated_payload,
                failure_stage="docx_result",
            )

        source_path = str(generated_payload.get("output_path") or "").strip()
        filename = str(generated_payload.get("output_filename") or "").strip()
        if not source_path or not filename:
            return self._unsafe_unparseable_write(
                event,
                tool_name="generate_contract_docx",
                failure_stage="docx_result",
            )

        self._set_write_stage(event, "publication")
        published = await _invoke_registered_tool(
            publisher,
            context,
            side_effecting=True,
            source_path=source_path,
            filename=filename,
        )
        published_failure = self._write_error_response(
            event,
            published,
            tool_name="publish_contract_download",
            failure_stage="publication_result",
        )
        if published_failure:
            return published_failure
        published_payload = _tool_result_payload(published)
        if not isinstance(published_payload, dict):
            return self._unsafe_unparseable_write(
                event,
                tool_name="publish_contract_download",
                failure_stage="publication_result",
            )
        if not (
            published_payload.get("success") is True
            and str(published_payload.get("status") or "").lower() == "ready"
        ):
            return self._observe_payload_failure(
                event,
                published_payload,
                failure_stage="publication_result",
            )

        self._set_write_stage(event, "draft_finalize")
        finalized = await _invoke_registered_tool(
            finalizer,
            context,
            side_effecting=True,
        )
        if _tool_result_is_error(finalized):
            logger.warning(
                "Contract generation: publication succeeded but draft finalize returned error: %s",
                _tool_error_detail(finalized),
            )
            return self._partial_after_publication(
                event,
                generated_payload=generated_payload,
                published_payload=published_payload,
                filename=filename,
                error="HTTPS 已发布，但草稿持久化工具执行异常。",
                commit_unknown=(
                    _tool_result_commit_unknown(finalized)
                    or not _tool_result_retry_safe(finalized, default=False)
                ),
            )

        finalized_payload = _tool_result_payload(finalized)
        if not isinstance(finalized_payload, dict):
            return self._partial_after_publication(
                event,
                generated_payload=generated_payload,
                published_payload=published_payload,
                filename=filename,
                error="HTTPS 已发布，但草稿持久化结果无法解析。",
                commit_unknown=True,
            )
        if not (
            finalized_payload.get("success") is True
            and str(finalized_payload.get("status") or "").lower() == "ready"
            and bool(finalized_payload.get("draft_saved"))
            and str(finalized_payload.get("draft_id") or "").strip()
        ):
            return self._partial_after_publication(
                event,
                generated_payload=generated_payload,
                published_payload=published_payload,
                filename=filename,
                error=str(
                    finalized_payload.get("error")
                    or "HTTPS 已发布，但草稿持久化没有返回可验证的 draft_id。"
                ),
                commit_unknown=bool(finalized_payload.get("commit_unknown", False)),
            )

        event.set_extra("contract_generation_write_stage", "complete")
        return _tool_json(
            {
                "success": True,
                "status": "ready",
                "generation_id": generated_payload.get("generation_id"),
                "generation_basis": generated_payload.get("generation_basis"),
                "source_draft_id": generated_payload.get("source_draft_id"),
                "renderer": generated_payload.get("renderer"),
                "render_profile": generated_payload.get("render_profile"),
                "draft_id": finalized_payload.get("draft_id"),
                "draft_saved": True,
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
                    or finalized_payload.get("idempotent")
                ),
            }
        )

    async def call(self, context: Any, **tool_args: Any) -> Any:
        event = self._event(context)
        try:
            return await self._call_impl(context, **tool_args)
        except asyncio.CancelledError:
            stage = str(
                event.get_extra("contract_generation_write_stage", "")
                or "write_operation"
            )
            reason = (
                "正式合同写操作在执行期间被取消或超时，底层线程/文件写入可能仍已提交；"
                "当前提交状态未知，本轮禁止自动重试。"
            )
            _mark_terminal_failure(
                event,
                reason,
                stage=stage,
                commit_unknown=True,
            )
            logger.error(
                "Contract generation: write operation cancelled at stage=%s; marked commit-unknown",
                stage,
            )
            raise


class ContractGenerationFlow(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None) -> None:
        super().__init__(context, config)
        self._context = context
        self._skill_manager = SkillManager()
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
        self._business_tools = {tool.name: tool for tool in self._build_business_tools()}

    async def initialize(self) -> None:
        logger.info(
            "Contract generation flow 0.8.0 initialized: asset_corpus=%s",
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
            "contract_generation_reference_value_fields": [],
            "contract_generation_asset_search_attempted": False,
            "contract_generation_asset_search_verified": False,
            "contract_generation_asset_search_result_count": 0,
            "contract_generation_asset_candidates": {},
            "contract_generation_asset_read_states": {},
            "contract_generation_template_selected_verified": False,
            "contract_generation_selected_template_document_slug": "",
            "contract_generation_selected_template_document_title": "",
            "contract_generation_selected_template_asset_id": "",
            "contract_generation_selected_template_version": "",
            "contract_generation_selected_render_profile": "standard_contract",
            "contract_generation_selected_template_search_match_verified": False,
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
            "contract_generation_document_spec_required": True,
            "contract_generation_document_spec_available": False,
            "contract_generation_document_spec_loaded": False,
            "contract_generation_document_spec_skill_id": "",
            "contract_generation_skill_grounding_attempted": False,
            "contract_generation_skill_grounding_loaded": [],
            "contract_generation_skill_runtime_error": "",
            "contract_generation_write_stage": "",
            "contract_generation_write_commit_unknown": False,
            "contract_generation_write_commit_unknown_stage": "",
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

        raw_reference_fields = parsed_input.get("reference_value_fields", [])
        if raw_reference_fields is None:
            raw_reference_fields = []
        if not isinstance(raw_reference_fields, list):
            event.set_extra("contract_generation_fallback_policy", "invalid")
            event.set_extra(
                "contract_generation_policy_error",
                "reference_value_fields 提供时必须是字符串数组。",
            )
            return
        reference_fields: list[str] = []
        for item in raw_reference_fields:
            value = str(item or "").strip()
            if value and value not in reference_fields:
                reference_fields.append(value)
        event.set_extra("contract_generation_reference_value_fields", reference_fields)

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

    def _builder_prompt_compatible(self) -> bool:
        persona_manager = getattr(self._context, "persona_manager", None)
        if persona_manager is None:
            return False
        persona = persona_manager.get_persona_v3_by_id(BUILDER_PERSONA_ID)
        if not isinstance(persona, dict):
            return False
        prompt = str(persona.get("prompt") or persona.get("system_prompt") or "").strip()
        return bool(prompt and BUILDER_PROTOCOL_MARKER in prompt)

    def _bound_skill_infos(
        self,
        event: AstrMessageEvent,
    ) -> tuple[list[str], list[SkillInfo], list[str]]:
        bound_names = _builder_bound_skill_names(self._context)
        runtime = _runtime_name(self._context, event)
        active = self._skill_manager.list_skills(
            active_only=True,
            runtime=runtime,
            show_sandbox_path=False,
        )
        active_by_name = {skill.name: skill for skill in active}
        selected = [
            active_by_name[name]
            for name in bound_names
            if name in active_by_name and active_by_name[name].local_exists
        ]
        missing = [
            name
            for name in bound_names
            if name not in active_by_name or not active_by_name[name].local_exists
        ]
        return bound_names, selected, missing

    def _prepare_builder_skill_state(
        self,
        event: AstrMessageEvent,
    ) -> list[str]:
        bound_names, skill_infos, missing_skills = self._bound_skill_infos(event)
        runtime_missing: list[str] = []
        document_spec_bindings = [
            name for name in bound_names
            if _skill_id_matches_logical_name(name, DOCUMENT_SPEC_SKILL_NAME)
        ]
        if not document_spec_bindings:
            runtime_missing.append("builder_document_spec_binding")
        elif len(document_spec_bindings) > 1:
            runtime_missing.append("builder_document_spec_binding_ambiguous")
        readable_skill_ids = {skill.name for skill in skill_infos if skill.local_exists}
        resolved_id = document_spec_bindings[0] if len(document_spec_bindings) == 1 else ""
        available = bool(resolved_id and resolved_id in readable_skill_ids)
        event.set_extra("contract_generation_document_spec_available", available)
        event.set_extra("contract_generation_document_spec_skill_id", resolved_id if available else "")
        if len(document_spec_bindings) == 1 and not available:
            runtime_missing.append("builder_document_spec_skill")
        for name in missing_skills:
            marker = f"builder_skill:{name}"
            if marker not in runtime_missing:
                runtime_missing.append(marker)
        return runtime_missing

    def _build_business_tools(self) -> list[FunctionTool]:
        tools: list[FunctionTool] = [
            _BoundSkillReadTool(self._context, self._skill_manager)
        ]
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
        tools.append(_GenerateAndPublishTool(self._context))
        return tools

    def _runtime_diagnostics(self, event: AstrMessageEvent) -> list[str]:
        manager = self._context.get_llm_tool_manager()
        missing: list[str] = []
        for name in RUNTIME_SOURCE_NAMES:
            tool = manager.get_func(name)
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

    def _validate_builder_runtime(
        self,
        event: AstrMessageEvent,
    ) -> tuple[list[str], list[str]]:
        try:
            missing = self._prepare_builder_skill_state(event)
            event.set_extra("contract_generation_skill_runtime_error", "")
        except Exception:
            logger.exception("Contract generation flow: failed to inspect Builder Skill binding")
            event.set_extra("contract_generation_document_spec_available", False)
            event.set_extra("contract_generation_skill_runtime_error", "builder skill binding inspection failed")
            missing = ["builder_skill_runtime", "builder_document_spec_skill"]
        bound_tools = _builder_bound_tool_names(self._context)
        for name in BUILDER_BOUND_TOOL_NAMES:
            if name not in bound_tools:
                missing.append(f"builder_tool_binding:{name}")
        manager = self._context.get_llm_tool_manager()
        for name in BUILDER_BOUND_TOOL_NAMES:
            tool = manager.get_func(name)
            if tool is None or not getattr(tool, "active", True):
                missing.append(f"builder_tool:{name}")
        diagnostics = self._runtime_diagnostics(event)
        event.set_extra("contract_generation_builder_runtime_optional_missing", diagnostics)
        event.set_extra(ASSET_CORPUS_EVENT_KEY, self.asset_corpus_slug)
        if not self._builder_prompt_compatible():
            missing.append("builder_persona_protocol_v7")
        deduped: list[str] = []
        for item in missing:
            if item not in deduped:
                deduped.append(item)
        return list(BUILDER_BOUND_TOOL_NAMES), deduped

    async def _call_business_tool(self, event: AstrMessageEvent, name: str, **tool_args: Any) -> Any:
        if event.get_extra("contract_generation_terminal_failure", False):
            return _normalized_tool_failure(
                failure_stage="generation_terminal",
                error=str(event.get_extra("contract_generation_terminal_failure_reason", "") or "当前 generation 已进入 terminal 状态。"),
                retry_safe=False,
                handoff_terminal=True,
                write_started=bool(event.get_extra("contract_generation_write_stage", "")),
            )
        tool = self._business_tools.get(name)
        if tool is None:
            return _normalized_tool_failure(failure_stage="runtime_tool", error=f"业务工具 {name} 未注册。", retry_safe=False, handoff_terminal=True)
        return await tool.call(_EventToolContext(event), **tool_args)

    @filter.llm_tool(name="read_bound_skill")
    async def read_bound_skill(self, event: AstrMessageEvent, skill_name: str) -> Any:
        """读取 Builder 当前实际绑定的指定 Skill。

        Args:
            skill_name(string): 要读取的、已绑定到 Builder Persona 的 Skill 逻辑名；正式合同使用 contract-document-specification。
        """
        return await self._call_business_tool(event, "read_bound_skill", skill_name=skill_name)

    @filter.llm_tool(name="find_generation_assets")
    async def find_generation_assets(self, event: AstrMessageEvent, query: str, limit: int = SEARCH_DEFAULT_LIMIT, granularity: str = "passage") -> Any:
        """在受限生成资产 Corpus 中检索合同模板、参数或规则。

        Args:
            query(string): 检索语句；指定模板模式必须使用 handoff 的 required_template_query 原文。
            limit(int): 最多返回结果数量，默认 3。
            granularity(string): 检索粒度，使用 passage、block 或 both。
        """
        return await self._call_business_tool(event, "find_generation_assets", query=query, limit=limit, granularity=granularity)

    @filter.llm_tool(name="read_generation_asset")
    async def read_generation_asset(self, event: AstrMessageEvent, document_slug: str, char_offset: int = 0, max_chars: int = TEMPLATE_READ_DEFAULT_CHARS, use_as_template: bool = False) -> Any:
        """读取本轮生成资产候选；模板绑定必须来自本轮搜索证据。

        Args:
            document_slug(string): 本轮生成资产搜索返回的文档 slug。
            char_offset(int): 字符起点，首次读取使用 0。
            max_chars(int): 本次最多读取字符数，默认 80000。
            use_as_template(bool): 已决定把该资产作为本轮专用合同模板时才设为 true。
        """
        return await self._call_business_tool(event, "read_generation_asset", document_slug=document_slug, char_offset=char_offset, max_chars=max_chars, use_as_template=use_as_template)

    @filter.llm_tool(name="find_similar_contracts")
    async def find_similar_contracts(self, event: AstrMessageEvent, query: str, limit: int = SEARCH_DEFAULT_LIMIT, granularity: str = "passage") -> Any:
        """在当前 handoff 绑定的历史合同 Corpus 中检索相似合同。

        Args:
            query(string): 与当前交易/合同目标相关的检索语句。
            limit(int): 最多返回结果数量，默认 3。
            granularity(string): 检索粒度，使用 passage、block 或 both。
        """
        return await self._call_business_tool(event, "find_similar_contracts", query=query, limit=limit, granularity=granularity)

    @filter.llm_tool(name="read_reference_contract")
    async def read_reference_contract(self, event: AstrMessageEvent, document_slug: str, char_offset: int = 0, max_chars: int = REFERENCE_READ_DEFAULT_CHARS) -> Any:
        """读取本轮历史合同候选正文。

        Args:
            document_slug(string): 本轮历史检索返回的文档 slug。
            char_offset(int): 字符起点，首次读取使用 0。
            max_chars(int): 本次最多读取字符数，默认 60000。
        """
        return await self._call_business_tool(event, "read_reference_contract", document_slug=document_slug, char_offset=char_offset, max_chars=max_chars)

    @filter.llm_tool(name="generate_and_publish_contract")
    async def generate_and_publish_contract(self, event: AstrMessageEvent, document_title: str, document_markdown: str, generation_basis: str, output_filename: str = "", render_profile: str = "standard_contract", source_draft_id: str = "") -> Any:
        """一次完成 DOCX 生成、HTTPS 发布和成功草稿持久化。

        Args:
            document_title(string): 合同标题。
            document_markdown(string): 已按文档规范整理完成的完整最终合同 Markdown。
            generation_basis(string): 本轮实际主要依据：specific_template、history_reference、ai_scaffold 或 source_draft。
            output_filename(string): 可选 DOCX 文件名。
            render_profile(string): 排版 profile，通常使用 standard_contract。
            source_draft_id(string): 修改上一版时传入已读取的 draft_id；不替代 generation_basis。
        """
        return await self._call_business_tool(event, "generate_and_publish_contract", document_title=document_title, document_markdown=document_markdown, generation_basis=generation_basis, output_filename=output_filename, render_profile=render_profile, source_draft_id=source_draft_id)

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
        if not event.get_extra("contract_generation_policy_verified", False):
            _mark_terminal_failure(
                event,
                str(event.get_extra("contract_generation_policy_error", "") or "生成策略无效。"),
                stage="generation_policy",
                commit_unknown=False,
            )
        runtime_tools, missing = self._validate_builder_runtime(event)
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
                "asset_corpus=%s history_corpus=%s policy_protocol=%s fallback_policy=%s "
                "diagnostics=%s document_spec_required=%s document_spec_available=%s "
                "document_spec_skill_id=%s document_spec_loaded=%s tools=%s",
                event.get_extra("contract_generation_generation_id", ""),
                self.asset_corpus_slug,
                event.get_extra(HISTORY_CORPUS_EVENT_KEY, ""),
                event.get_extra("contract_generation_policy_protocol", ""),
                event.get_extra("contract_generation_fallback_policy", ""),
                event.get_extra(
                    "contract_generation_builder_runtime_optional_missing", []
                ),
                event.get_extra("contract_generation_document_spec_required", True),
                event.get_extra("contract_generation_document_spec_available", False),
                event.get_extra("contract_generation_document_spec_skill_id", ""),
                event.get_extra("contract_generation_document_spec_loaded", False),
                runtime_tools,
            )
        await self._send_progress_once(event)
