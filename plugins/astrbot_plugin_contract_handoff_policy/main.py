from __future__ import annotations

import json
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star


HANDOFF_MAP = {
    "opencontracts_operator": "transfer_to_opencontracts_operator",
    "docassemble_builder": "transfer_to_docassemble_builder",
}


class ContractHandoffPolicy(Star):
    """Normalize contract handoffs and keep WeCom work in the current event."""

    def __init__(
        self,
        context: Context,
        config: AstrBotConfig | None = None,
    ):
        super().__init__(context, config)
        config = config or {}
        self.config = config
        self.force_synchronous_platforms = set(
            config.get(
                "force_synchronous_platforms",
                ["wecom"],
            )
        )
        self.max_calls_per_agent = int(
            config.get("max_calls_per_agent", 1)
        )
        self._counts: dict[str, dict[str, int]] = {}

    async def initialize(self) -> None:
        logger.info(
            "Contract handoff policy 0.4.4 initialized: instance_id=%s",
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
                if (
                    hasattr(candidate, "name")
                    and not isinstance(candidate, dict)
                ):
                    tool = candidate
                    break

        if tool_args is None:
            for candidate in hook_args:
                if isinstance(candidate, dict):
                    tool_args = candidate
                    break

        return tool, tool_args

    @staticmethod
    def _event_key(event: AstrMessageEvent) -> str:
        task_id = event.get_extra("contract_pending_task_id")
        return f"{event.unified_msg_origin}:{task_id or id(event)}"

    @staticmethod
    def _expected_agents(context: dict[str, Any]) -> list[str]:
        agents = context.get("recommended_subagents")
        if isinstance(agents, list):
            return [
                str(agent)
                for agent in agents
                if str(agent).strip()
            ]

        legacy = context.get("recommended_subagent")
        if legacy:
            return [str(legacy)]
        return []

    @staticmethod
    def _merge_constraints(
        existing: Any,
        additions: list[str],
    ) -> list[str]:
        merged: list[str] = []
        candidates = existing if isinstance(existing, list) else []
        for value in [*candidates, *additions]:
            text = str(value or "").strip()
            if text and text not in merged:
                merged.append(text)
        return merged

    @staticmethod
    def _preserve_agent_input(
        canonical: dict[str, Any],
        original_input: Any,
    ) -> None:
        if not isinstance(original_input, str) or not original_input.strip():
            return
        raw = original_input.strip()
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            canonical["main_agent_note"] = raw[:2000]
            return
        if not isinstance(parsed, dict):
            canonical["main_agent_note"] = raw[:2000]
            return

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
        canonical["main_agent_input"] = parsed

    @filter.on_using_llm_tool(priority=1000)
    async def normalize_handoff(
        self,
        event: AstrMessageEvent,
        *hook_args: Any,
        **hook_kwargs: Any,
    ):
        if self is None:
            logger.error(
                "Contract handoff policy invoked without an instance."
            )
            return

        tool, tool_args = self._resolve_tool_args(
            hook_args,
            hook_kwargs,
        )
        if tool is None or tool_args is None:
            return

        tool_name = str(getattr(tool, "name", ""))
        if not tool_name.startswith("transfer_to_"):
            return

        task_context = event.get_extra("contract_task_context")
        if not isinstance(task_context, dict):
            return

        expected_agents = self._expected_agents(task_context)
        expected_tools = {
            HANDOFF_MAP[agent]
            for agent in expected_agents
            if agent in HANDOFF_MAP
        }
        actual_agent = tool_name.removeprefix("transfer_to_")
        event_key = self._event_key(event)

        event_counts = self._counts.setdefault(event_key, {})
        current_count = event_counts.get(tool_name, 0)
        event_counts[tool_name] = current_count + 1

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
            logger.error(
                "Contract handoff policy: direct task attempted a handoff."
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
            logger.error(
                "Contract handoff policy: routing mismatch, "
                "expected=%s actual=%s",
                sorted(expected_tools),
                tool_name,
            )
            return

        if current_count >= self.max_calls_per_agent:
            tool_args["background_task"] = False
            tool_args["input"] = json.dumps(
                {
                    "delegated_agent": actual_agent,
                    "must_not_execute": True,
                    "error": "duplicate_handoff",
                    "task_context": task_context,
                },
                ensure_ascii=False,
            )
            logger.error(
                "Contract handoff policy: duplicate %s suppressed.",
                tool_name,
            )
            return

        original_input = tool_args.get("input")
        canonical = dict(task_context)
        canonical["delegated_agent"] = actual_agent
        canonical["document_read_channel"] = "opencontracts_mcp"
        canonical["document_write_channel"] = "worker_key_bound_document_import"
        canonical["receipt_role"] = "append_only_upload_audit"
        canonical["remaining_expected_subagents"] = [
            agent
            for agent in expected_agents
            if agent != actual_agent
        ]
        branch_tasks = task_context.get("branch_tasks")
        if isinstance(branch_tasks, dict):
            branch = branch_tasks.get(actual_agent)
            if isinstance(branch, dict):
                canonical["branch_task"] = branch
                canonical["operation"] = branch.get(
                    "operation", canonical.get("operation")
                )
                canonical["expected_outputs"] = branch.get(
                    "expected_outputs", canonical.get("expected_outputs")
                )
                canonical["required_tools"] = branch.get("required_tools", [])

        self._preserve_agent_input(canonical, original_input)

        if actual_agent == "opencontracts_operator":
            canonical["required_tools"] = [
                "get_corpus_info",
                "list_documents",
                "opencontracts_gateway_status",
                "opencontracts_upload_document",
                "get_document_text",
                "search_corpus",
            ]
            canonical["integration_sequence"] = [
                "validate_contract_identity",
                "discover_with_opencontracts_mcp",
                "write_to_worker_key_bound_corpus",
                "verify_with_opencontracts_mcp",
            ]
            canonical["identity_contract"] = {
                "required_fields": ["contract_date", "contract_title"],
                "document_title_format": "YYYY-MM-DD 合同标题",
                "normalized_filename_format": "YYYY-MM-DD_合同标题.原扩展名",
                "remote_duplicate_key": "exact_document_title",
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
                    "OpenContracts MCP 提供远端合同发现、正文读取和检索核验",
                    "合同日期和合同标题缺失时停止上传",
                    "远端查重使用规范化 document_title 精确匹配",
                    "上传网关使用 WorkerKey 写入其绑定的 Corpus，不传配置 Corpus ID",
                    "传输异常、服务端 5xx 或成功响应结构异常时禁止自动重试",
                    "manual_review_required 时首行输出人工核查标记",
                    "source_files.original_name 仅保留原扩展名和审计信息",
                    "receipt 只记录追加式上传审计",
                    "结果在当前企业微信事件中同步返回",
                ],
            )
        elif isinstance(original_input, str) and original_input.strip():
            canonical["main_agent_note"] = original_input.strip()[:1000]

        tool_args["input"] = json.dumps(
            canonical,
            ensure_ascii=False,
            indent=2,
        )

        platform_name = ""
        try:
            platform_name = event.get_platform_name()
        except Exception:
            pass

        if (
            platform_name in self.force_synchronous_platforms
            or task_context.get("background_task") is False
            or task_context.get("delivery_mode")
            == "current_event_response"
        ):
            tool_args["background_task"] = False

        logger.info(
            "Contract handoff policy: normalized %s "
            "task_id=%s background=%s",
            tool_name,
            task_context.get("task_id"),
            tool_args.get("background_task", False),
        )

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
