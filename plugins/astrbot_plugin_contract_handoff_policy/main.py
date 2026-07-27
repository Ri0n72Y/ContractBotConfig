from __future__ import annotations

import json
import re
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


HANDOFF_MAP = {
    "opencontracts_operator": "transfer_to_opencontracts_operator",
    "docassemble_builder": "transfer_to_docassemble_builder",
}

READ_OPERATIONS = {
    "opencontracts_get_documents_text",
    "opencontracts_database_analysis",
    "opencontracts_compare_contracts",
    "opencontracts_contract_summary",
    "opencontracts_contract_question",
    "contract_database_analysis",
    "contract_database_question",
    "contract_comparison",
}

READ_STATUS_CONTRACT = {
    "ready": "[CONTRACT_READ:READY]",
    "partial": "[CONTRACT_READ:PARTIAL]",
    "pending": "[CONTRACT_READ:PENDING]",
    "failed": "[CONTRACT_READ:FAILED]",
}

DATABASE_INTENT_PATTERNS = (
    r"合同库",
    r"数据库.*合同",
    r"系统中.*合同",
    r"现有合同",
    r"这两(?:个|份)合同",
    r"两(?:个|份)合同",
    r"多个合同",
    r"合同.*(?:对比|比较|总体分析|整体分析|综合分析|汇总|总结)",
    r"(?:对比|比较|总体分析|整体分析|综合分析|汇总|总结).*合同",
)


class ContractHandoffPolicy(Star):
    """Normalize contract handoffs and enforce database-read boundaries."""

    def __init__(
        self,
        context: Context,
        config: AstrBotConfig | None = None,
    ):
        super().__init__(context, config)
        config = config or {}
        self.config = config
        self.force_synchronous_platforms = set(
            config.get("force_synchronous_platforms", ["wecom"])
        )
        self.max_calls_per_agent = int(config.get("max_calls_per_agent", 1))
        self.long_task_ack_enabled = bool(
            config.get("long_task_ack_enabled", True)
        )
        self.long_task_ack_text = str(
            config.get(
                "long_task_ack_text",
                "正在读取合同库中的相关合同并进行分析，内容较多，需要一些处理时间。完成后会继续在当前会话发送结果。",
            )
        ).strip()
        self.restrict_database_master_tools = bool(
            config.get("restrict_database_master_tools", True)
        )
        self._counts: dict[str, dict[str, int]] = {}

    async def initialize(self) -> None:
        logger.info(
            "Contract handoff policy 0.4.6 initialized: instance_id=%s",
            id(self),
        )

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
    def _event_key(event: AstrMessageEvent) -> str:
        task_id = event.get_extra("contract_pending_task_id")
        return f"{event.unified_msg_origin}:{task_id or id(event)}"

    @staticmethod
    def _expected_agents(context: dict[str, Any]) -> list[str]:
        agents = context.get("recommended_subagents")
        if isinstance(agents, list):
            return [str(agent) for agent in agents if str(agent).strip()]
        legacy = context.get("recommended_subagent")
        return [str(legacy)] if legacy else []

    @staticmethod
    def _merge_constraints(existing: Any, additions: list[str]) -> list[str]:
        merged: list[str] = []
        candidates = existing if isinstance(existing, list) else []
        for value in [*candidates, *additions]:
            text = str(value or "").strip()
            if text and text not in merged:
                merged.append(text)
        return merged

    @staticmethod
    def _parse_agent_input(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        if not isinstance(value, str) or not value.strip():
            return {}
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {"query": value.strip()}
        return parsed if isinstance(parsed, dict) else {"query": value.strip()}

    @staticmethod
    def _preserve_agent_input(
        canonical: dict[str, Any],
        parsed: dict[str, Any],
    ) -> None:
        identity_source = parsed.get("contract_identity")
        if not isinstance(identity_source, dict):
            identity_source = parsed
        contract_date = str(identity_source.get("contract_date") or "").strip()
        contract_title = str(identity_source.get("contract_title") or "").strip()
        if contract_date or contract_title:
            canonical["contract_identity"] = {
                "contract_date": contract_date,
                "contract_title": contract_title,
            }
        if parsed:
            canonical["main_agent_input"] = parsed

    @staticmethod
    def _upload_tools() -> list[str]:
        return [
            "list_documents",
            "opencontracts_gateway_status",
            "opencontracts_upload_document",
            "get_document_text",
            "search_corpus",
        ]

    @staticmethod
    def _read_tools() -> list[str]:
        return ["list_documents", "get_document_text", "search_corpus"]

    @staticmethod
    def _is_upload_operation(operation: str) -> bool:
        return operation in {
            "contract_system_upload",
            "contract_system_reupload",
            "opencontracts_upload",
            "opencontracts_reupload",
        }

    @classmethod
    def _is_read_operation(cls, operation: str) -> bool:
        value = operation.strip().lower()
        if value in READ_OPERATIONS:
            return True
        return (
            "opencontracts" in value
            and any(
                token in value
                for token in ("read", "text", "analysis", "compare", "summary", "question")
            )
        )

    @classmethod
    def _looks_like_database_read_request(
        cls,
        event: AstrMessageEvent,
        req: ProviderRequest | None,
    ) -> bool:
        context = event.get_extra("contract_task_context")
        if isinstance(context, dict):
            operation = str(context.get("operation") or "")
            if cls._is_upload_operation(operation):
                return False
            if operation in {"quick_analysis", "free_question"} and context.get(
                "source_files"
            ):
                return False
            if cls._is_read_operation(operation):
                return True
        if event.get_extra("contract_database_read_task", False):
            return True
        text = " ".join(
            part
            for part in (
                str(getattr(event, "message_str", "") or ""),
                str(getattr(req, "prompt", "") or "") if req else "",
            )
            if part
        )
        compact = re.sub(r"\s+", "", text)
        return any(re.search(pattern, compact, re.IGNORECASE) for pattern in DATABASE_INTENT_PATTERNS)

    @staticmethod
    def _append_temp_instruction(req: ProviderRequest, text: str) -> None:
        if TextPart is not None and hasattr(req, "extra_user_content_parts"):
            part = TextPart(text=text)
            if hasattr(part, "mark_as_temp"):
                part = part.mark_as_temp()
            req.extra_user_content_parts.append(part)
        else:
            req.prompt = f"{req.prompt or ''}\n\n{text}"

    @filter.on_llm_request(priority=1100)
    async def restrict_database_tools(
        self,
        event: AstrMessageEvent,
        *hook_args: Any,
        **hook_kwargs: Any,
    ):
        if self is None or not self.restrict_database_master_tools:
            return
        req = self._resolve_provider_request(hook_args, hook_kwargs)
        if req is None or not self._looks_like_database_read_request(event, req):
            return
        tool_set = getattr(req, "func_tool", None)
        if tool_set is None or not hasattr(tool_set, "tools"):
            return
        before = [str(getattr(tool, "name", "")) for tool in tool_set.tools]
        if "transfer_to_opencontracts_operator" not in before:
            # Sub-agent requests share the same event extras; only restrict the Master tool set.
            return
        event.set_extra("contract_database_read_task", True)
        if tool_set is not None and hasattr(tool_set, "tools"):
            tool_set.tools = [
                tool
                for tool in tool_set.tools
                if str(getattr(tool, "name", ""))
                == "transfer_to_opencontracts_operator"
            ]
            after = [str(getattr(tool, "name", "")) for tool in tool_set.tools]
            logger.info(
                "Contract handoff policy: restricted database task tools, before=%s after=%s",
                before,
                after,
            )
        self._append_temp_instruction(
            req,
            "<contract_database_read_policy>\n"
            "这是合同库读取或总体分析任务。主人格只能调用 transfer_to_opencontracts_operator。"
            "不得使用 Shell、Grep、Python、通用 HTTP、本地文件搜索或历史会话内容补齐正文。"
            "子人格返回 [CONTRACT_READ:READY]、[CONTRACT_READ:PARTIAL]、"
            "[CONTRACT_READ:PENDING] 或 [CONTRACT_READ:FAILED] 后，立即停止工具调用并据实回复。\n"
            "</contract_database_read_policy>",
        )

    @staticmethod
    def _read_corpus_slug(
        parsed: dict[str, Any],
        context: dict[str, Any] | None,
    ) -> str:
        candidates = [
            parsed.get("corpus_slug"),
            (parsed.get("targets") or {}).get("opencontracts")
            if isinstance(parsed.get("targets"), dict)
            else None,
            (parsed.get("branch_task") or {}).get("corpus_slug")
            if isinstance(parsed.get("branch_task"), dict)
            else None,
            ((context or {}).get("targets") or {}).get("opencontracts")
            if isinstance((context or {}).get("targets"), dict)
            else None,
        ]
        for value in candidates:
            text = str(value or "").strip()
            if text:
                return text
        return ""

    def _build_read_context(
        self,
        parsed: dict[str, Any],
        task_context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        corpus_slug = self._read_corpus_slug(parsed, task_context)
        operation = str(parsed.get("operation") or "opencontracts_database_analysis")
        query = parsed.get("query")
        main_input = parsed.get("main_agent_input")
        if not query and isinstance(main_input, dict):
            query = main_input.get("query")
        documents = parsed.get("documents_to_fetch")
        if not isinstance(documents, list):
            documents = parsed.get("documents")
        if not isinstance(documents, list):
            documents = []
        canonical: dict[str, Any] = {
            "delegated_agent": "opencontracts_operator",
            "operation": operation,
            "operation_label": str(
                parsed.get("operation_label") or "读取合同库并进行分析"
            ),
            "background_task": False,
            "delivery_mode": "current_event_response",
            "document_read_channel": "opencontracts_public_mcp",
            "targets": {"opencontracts": corpus_slug or None},
            "required_tools": self._read_tools(),
            "documents_to_fetch": documents,
            "query": str(query or "").strip(),
            "read_contract": {
                "corpus_slug": corpus_slug or None,
                "chunk_tool": "get_document_text",
                "initial_char_offset": 0,
                "max_chars_per_call": 10000,
                "continue_until_next_offset_is_null": True,
                "empty_text_action": "return_pending_without_fallback",
                "status_contract": READ_STATUS_CONTRACT,
            },
            "constraints": [
                "只使用 AstrBot 已配置的 OpenContracts 公开 MCP 工具读取远端合同",
                "先调用 list_documents 确认目标文档，再调用 get_document_text",
                "get_document_text 返回 next_offset 时继续分片，直到 next_offset 为 null",
                "page_count=0、total_chars=0 或正文为空时返回 CONTRACT_READ:PENDING",
                "多文档中仅部分正文可读时返回 CONTRACT_READ:PARTIAL，并限定结论覆盖范围",
                "不得使用 Shell、Grep、Python、通用 HTTP、本地文件搜索或历史上下文补齐正文",
                "不得以 search_corpus 或 list_annotations 的空结果替代正文读取结论",
                "任一 CONTRACT_READ 状态均为当前轮次终态",
            ],
        }
        self._preserve_agent_input(canonical, parsed)
        return canonical

    async def _send_long_task_ack(self, event: AstrMessageEvent) -> None:
        if (
            not self.long_task_ack_enabled
            or not self.long_task_ack_text
            or event.get_extra("contract_long_task_ack_sent", False)
        ):
            return
        try:
            await event.send(MessageChain([Comp.Plain(self.long_task_ack_text)]))
            event.set_extra("contract_long_task_ack_sent", True)
        except Exception as exc:
            logger.warning("Contract long-task acknowledgement failed: %s", exc)

    @filter.on_using_llm_tool(priority=1000)
    async def normalize_handoff(
        self,
        event: AstrMessageEvent,
        *hook_args: Any,
        **hook_kwargs: Any,
    ):
        if self is None:
            logger.error("Contract handoff policy invoked without an instance.")
            return
        tool, tool_args = self._resolve_tool_args(hook_args, hook_kwargs)
        if tool is None or tool_args is None:
            return
        tool_name = str(getattr(tool, "name", ""))
        if tool_name != "transfer_to_opencontracts_operator" and not tool_name.startswith(
            "transfer_to_"
        ):
            return

        original_input = tool_args.get("input")
        parsed = self._parse_agent_input(original_input)
        task_context = event.get_extra("contract_task_context")
        if not isinstance(task_context, dict):
            task_context = None
        operation = str(
            parsed.get("operation")
            or ((task_context or {}).get("operation") or "")
        )
        read_task = (
            event.get_extra("contract_database_read_task", False)
            or self._is_read_operation(operation)
            or isinstance(parsed.get("documents_to_fetch"), list)
        )

        event_key = self._event_key(event)
        event_counts = self._counts.setdefault(event_key, {})
        current_count = event_counts.get(tool_name, 0)
        event_counts[tool_name] = current_count + 1
        if current_count >= self.max_calls_per_agent:
            tool_args["background_task"] = False
            tool_args["input"] = json.dumps(
                {
                    "delegated_agent": tool_name.removeprefix("transfer_to_"),
                    "must_not_execute": True,
                    "error": "duplicate_handoff",
                    "terminal_status": READ_STATUS_CONTRACT["failed"]
                    if read_task
                    else None,
                },
                ensure_ascii=False,
            )
            logger.error("Contract handoff policy: duplicate %s suppressed.", tool_name)
            return

        if read_task and tool_name == "transfer_to_opencontracts_operator":
            event.set_extra("contract_database_read_task", True)
            await self._send_long_task_ack(event)
            canonical = self._build_read_context(parsed, task_context)
            tool_args["input"] = json.dumps(canonical, ensure_ascii=False, indent=2)
            tool_args["background_task"] = False
            logger.info(
                "Contract handoff policy: normalized read-only OpenContracts task operation=%s corpus=%s",
                canonical.get("operation"),
                (canonical.get("targets") or {}).get("opencontracts"),
            )
            return

        if task_context is None:
            return
        expected_agents = self._expected_agents(task_context)
        expected_tools = {
            HANDOFF_MAP[agent] for agent in expected_agents if agent in HANDOFF_MAP
        }
        actual_agent = tool_name.removeprefix("transfer_to_")
        if not expected_tools:
            tool_args["background_task"] = False
            tool_args["input"] = json.dumps(
                {
                    "delegated_agent": actual_agent,
                    "must_not_execute": True,
                    "error": "handoff_not_required",
                    "task_context": task_context,
                },
                ensure_ascii=False,
            )
            return
        if tool_name not in expected_tools:
            tool_args["background_task"] = False
            tool_args["input"] = json.dumps(
                {
                    "delegated_agent": actual_agent,
                    "must_not_execute": True,
                    "error": "routing_mismatch",
                    "expected_tools": sorted(expected_tools),
                    "actual_tool": tool_name,
                    "task_context": task_context,
                },
                ensure_ascii=False,
            )
            return

        canonical = dict(task_context)
        canonical["delegated_agent"] = actual_agent
        canonical["document_read_channel"] = "opencontracts_public_mcp"
        canonical["document_write_channel"] = "worker_key_bound_document_import"
        canonical["receipt_role"] = "append_only_upload_audit"
        canonical["remaining_expected_subagents"] = [
            agent for agent in expected_agents if agent != actual_agent
        ]
        branch_tasks = task_context.get("branch_tasks")
        branch: dict[str, Any] | None = None
        if isinstance(branch_tasks, dict):
            candidate = branch_tasks.get(actual_agent)
            if isinstance(candidate, dict):
                branch = dict(candidate)
                canonical["operation"] = branch.get(
                    "operation", canonical.get("operation")
                )
                canonical["expected_outputs"] = branch.get(
                    "expected_outputs", canonical.get("expected_outputs")
                )
        self._preserve_agent_input(canonical, parsed)

        if actual_agent == "opencontracts_operator":
            required_tools = self._upload_tools()
            corpus_slug = str(
                (canonical.get("targets") or {}).get("opencontracts") or ""
            ).strip()
            canonical["required_tools"] = required_tools
            canonical["integration_sequence"] = [
                "resolve_identity_with_gateway_status",
                "discover_in_target_corpus_with_public_mcp",
                "write_to_worker_key_bound_corpus",
                "verify_in_target_corpus_with_public_mcp",
            ]
            canonical["mcp_contract"] = {
                "endpoint": "/mcp/",
                "corpus_slug": corpus_slug,
                "corpus_slug_source": "targets.opencontracts",
                "document_discovery_tool": "list_documents",
                "missing_corpus_slug_action": "block_without_upload",
                "forbidden_tools": [
                    "get_corpus_info",
                    "opencontracts_check_duplicate",
                    "list_public_corpuses",
                ],
            }
            canonical["identity_contract"] = {
                "required_fields": ["contract_date", "contract_title"],
                "canonical_identity_tool": "opencontracts_gateway_status",
                "document_title_source": "gateway_status.identity.document_title",
                "normalized_filename_source": "gateway_status.identity.normalized_filename",
                "remote_duplicate_key": "gateway_status.identity.document_title",
                "missing_identity_action": "block_without_upload",
            }
            canonical["status_contract"] = {
                "duplicate": "[CONTRACT_UPLOAD:DUPLICATE_CONFIRMATION_REQUIRED]",
                "blocked": "[CONTRACT_UPLOAD:BLOCKED]",
                "processing": "[CONTRACT_UPLOAD:PROCESSING]",
                "complete": "[CONTRACT_UPLOAD:COMPLETE]",
                "manual_review": "[CONTRACT_UPLOAD:MANUAL_REVIEW]",
                "failed": "[CONTRACT_UPLOAD:FAILED]",
            }
            canonical["constraints"] = self._merge_constraints(
                canonical.get("constraints"),
                [
                    "使用 AstrBot 已配置的 OpenContracts 公开 MCP /mcp/，不得拼接或探测其他 MCP 地址",
                    "必须使用 targets.opencontracts 作为 list_documents、get_document_text 和 search_corpus 的 corpus_slug",
                    "远端查重使用 opencontracts_gateway_status 返回的 identity.document_title",
                    "不得调用 opencontracts_check_duplicate、get_corpus_info、Shell、Python、通用 HTTP 或读取配置文件绕过标准工具链",
                    "上传网关使用 WorkerKey 写入其绑定的 Corpus，不传配置 Corpus ID",
                    "传输异常、服务端 5xx 或成功响应结构异常时禁止自动重试",
                    "结果在当前企业微信事件中同步返回",
                ],
            )
            canonical["branch_task"] = {
                "operation": canonical.get("operation"),
                "required_tools": required_tools,
                "expected_outputs": canonical.get("expected_outputs", []),
                "corpus_slug": corpus_slug,
            }
        elif branch is not None:
            canonical["branch_task"] = branch
            canonical["required_tools"] = branch.get("required_tools", [])

        tool_args["input"] = json.dumps(canonical, ensure_ascii=False, indent=2)
        platform_name = ""
        try:
            platform_name = event.get_platform_name()
        except Exception:
            pass
        if (
            platform_name in self.force_synchronous_platforms
            or task_context.get("background_task") is False
            or task_context.get("delivery_mode") == "current_event_response"
        ):
            tool_args["background_task"] = False

    @filter.after_message_sent(priority=-998)
    async def clear_event_counts(
        self,
        event: AstrMessageEvent,
        *_hook_args: Any,
        **_hook_kwargs: Any,
    ):
        if self is None:
            return
        self._counts.pop(self._event_key(event), None)
