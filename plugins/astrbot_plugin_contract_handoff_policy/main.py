from __future__ import annotations

import json
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star
import astrbot.api.message_components as Comp


READ_STATUS_CONTRACT = {
    "ready": "[CONTRACT_READ:READY]",
    "partial": "[CONTRACT_READ:PARTIAL]",
    "pending": "[CONTRACT_READ:PENDING]",
    "failed": "[CONTRACT_READ:FAILED]",
}


class ContractHandoffPolicy(Star):
    """Normalize OpenContracts handoffs without rewriting Master tool availability."""

    def __init__(
        self,
        context: Context,
        config: AstrBotConfig | None = None,
    ) -> None:
        super().__init__(context, config)
        config = config or {}
        self.force_synchronous_platforms = set(
            config.get("force_synchronous_platforms", ["wecom"])
        )
        self.long_task_ack_enabled = bool(
            config.get("long_task_ack_enabled", True)
        )
        self.long_task_ack_text = str(
            config.get(
                "long_task_ack_text",
                "正在读取合同库中的相关合同，完成后会继续在当前会话返回结果。",
            )
        ).strip()
        self.default_opencontracts_corpus_slug = str(
            config.get("default_opencontracts_corpus_slug", "contracts")
        ).strip()

    async def initialize(self) -> None:
        logger.info(
            "Contract handoff policy 0.5.0 initialized: default_corpus=%s",
            self.default_opencontracts_corpus_slug or "<empty>",
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
    def _merge_constraints(existing: Any, additions: list[str]) -> list[str]:
        merged: list[str] = []
        for value in [
            *(existing if isinstance(existing, list) else []),
            *additions,
        ]:
            text = str(value or "").strip()
            if text and text not in merged:
                merged.append(text)
        return merged

    @staticmethod
    def _is_upload_operation(operation: str) -> bool:
        return operation.strip().lower() in {
            "contract_system_upload",
            "contract_system_reupload",
            "opencontracts_upload",
            "opencontracts_reupload",
        }

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

    def _corpus_slug(
        self,
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
            self.default_opencontracts_corpus_slug,
        ]
        for value in candidates:
            text = str(value or "").strip()
            if text:
                return text
        return ""

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

    def _build_read_context(
        self,
        parsed: dict[str, Any],
        task_context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        corpus_slug = self._corpus_slug(parsed, task_context)
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
            "operation": str(
                parsed.get("operation") or "opencontracts_database_analysis"
            ),
            "background_task": False,
            "delivery_mode": "current_event_response",
            "document_read_channel": "opencontracts_public_mcp",
            "targets": {"opencontracts": corpus_slug or None},
            "required_tools": [
                "list_documents",
                "get_document_text",
                "search_corpus",
            ],
            "documents_to_fetch": documents,
            "query": str(query or "").strip(),
            "read_contract": {
                "corpus_slug": corpus_slug or None,
                "chunk_tool": "get_document_text",
                "initial_char_offset": 0,
                "max_chars_per_call": 30000,
                "continue_until_next_offset_is_null": True,
                "empty_text_action": "return_pending_without_fallback",
                "status_contract": READ_STATUS_CONTRACT,
            },
            "constraints": [
                "只使用 AstrBot 已配置的 OpenContracts 公开 MCP 工具",
                "固定使用 targets.opencontracts 作为 corpus_slug，不调用 list_public_corpuses 猜库",
                "先 list_documents，再读取真正需要的文档；不要默认扫描整个 Corpus",
                "get_document_text 从 offset 0 开始，必要时按 next_offset 继续",
                "正文为空时返回 PENDING，不使用本地文件或历史内容补齐",
            ],
        }
        self._preserve_agent_input(canonical, parsed)
        return canonical

    def _build_upload_context(
        self,
        parsed: dict[str, Any],
        task_context: dict[str, Any],
    ) -> dict[str, Any]:
        canonical = dict(task_context)
        canonical["delegated_agent"] = "opencontracts_operator"
        canonical["document_read_channel"] = "opencontracts_public_mcp"
        canonical["document_write_channel"] = "worker_key_bound_document_import"
        canonical["receipt_role"] = "append_only_upload_audit"

        branch_tasks = task_context.get("branch_tasks")
        branch: dict[str, Any] | None = None
        if isinstance(branch_tasks, dict):
            candidate = branch_tasks.get("opencontracts_operator")
            if isinstance(candidate, dict):
                branch = dict(candidate)
                canonical["operation"] = branch.get(
                    "operation", canonical.get("operation")
                )
                canonical["expected_outputs"] = branch.get(
                    "expected_outputs", canonical.get("expected_outputs")
                )

        self._preserve_agent_input(canonical, parsed)
        corpus_slug = self._corpus_slug(parsed, canonical)
        canonical["targets"] = {"opencontracts": corpus_slug or None}
        required_tools = [
            "list_documents",
            "opencontracts_gateway_status",
            "opencontracts_upload_document",
            "get_document_text",
            "search_corpus",
        ]
        canonical["required_tools"] = required_tools
        canonical["integration_sequence"] = [
            "resolve_identity_with_gateway_status",
            "discover_in_target_corpus_with_public_mcp",
            "write_to_worker_key_bound_corpus",
            "verify_in_target_corpus_with_public_mcp",
        ]
        canonical["mcp_contract"] = {
            "endpoint": "/mcp/",
            "corpus_slug": corpus_slug or None,
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
                "使用 targets.opencontracts 作为所有 OpenContracts MCP 读取的 corpus_slug",
                "不得调用 list_public_corpuses 猜测目标 Corpus",
                "远端查重使用 Gateway 返回的 identity.document_title",
                "WorkerKey 决定写入 Corpus，不传配置 Corpus ID",
                "传输异常、服务端 5xx 或成功响应结构异常时禁止自动重试",
                "结果在当前企业微信事件中同步返回",
            ],
        )
        canonical["branch_task"] = {
            "operation": canonical.get("operation"),
            "required_tools": required_tools,
            "expected_outputs": canonical.get("expected_outputs", []),
            "corpus_slug": corpus_slug or None,
        }
        return canonical

    @filter.on_using_llm_tool(priority=1000)
    async def normalize_handoff(
        self,
        event: AstrMessageEvent,
        *hook_args: Any,
        **hook_kwargs: Any,
    ) -> None:
        tool, tool_args = self._resolve_tool_args(hook_args, hook_kwargs)
        if tool is None or tool_args is None:
            return
        if str(getattr(tool, "name", "")) != "transfer_to_opencontracts_operator":
            return

        parsed = self._parse_agent_input(tool_args.get("input"))
        task_context = event.get_extra("contract_task_context")
        if not isinstance(task_context, dict):
            task_context = None

        operation = str(
            parsed.get("operation")
            or ((task_context or {}).get("operation") or "")
        )
        if task_context is not None and self._is_upload_operation(operation):
            canonical = self._build_upload_context(parsed, task_context)
            logger.info(
                "Contract handoff policy: normalized upload task corpus=%s",
                (canonical.get("targets") or {}).get("opencontracts"),
            )
        else:
            canonical = self._build_read_context(parsed, task_context)
            await self._send_long_task_ack(event)
            logger.info(
                "Contract handoff policy: normalized read task corpus=%s",
                (canonical.get("targets") or {}).get("opencontracts"),
            )

        tool_args["input"] = json.dumps(canonical, ensure_ascii=False, indent=2)
        tool_args["background_task"] = False
