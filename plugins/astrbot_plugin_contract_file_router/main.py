from __future__ import annotations

import asyncio
import time
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

from .document_text import extract_staged_contract_text
from .runtime import ContractFileRouter as RuntimeContractFileRouter


_STAGED_TEXT_EVENT_KEY = "contract_staged_document_text"
_STAGED_TEXT_ATTACHED_EVENT_KEY = "contract_staged_document_text_attached"
_DELETE_FILE_ALIASES = frozenset(
    {
        "删除文件",
        "删除当前文件",
        "删除这份文件",
        "删除合同文件",
        "清理当前文件",
    }
)


class Main(Star, RuntimeContractFileRouter):
    """Only AstrBot Star entrypoint; runtime.py is a plain implementation base."""

    def __init__(
        self,
        context: Context,
        config: AstrBotConfig | None = None,
    ) -> None:
        Star.__init__(self, context, config)
        RuntimeContractFileRouter.__init__(self, context, config)
        self._intake_locks: dict[str, asyncio.Lock] = {}

    async def initialize(self) -> None:
        logger.info(
            "Contract file router 0.5.9 initialized: data_dir=%s",
            self.data_dir,
        )

    def _session_lock(self, event: AstrMessageEvent) -> asyncio.Lock:
        session = self._session_key(event)
        lock = self._intake_locks.get(session)
        if lock is None:
            lock = asyncio.Lock()
            self._intake_locks[session] = lock
        return lock

    def _cleanup(self) -> None:
        """Prune transient registries without deleting retained contract files."""
        now_mono = time.monotonic()
        self._seen_messages = {
            key: value
            for key, value in self._seen_messages.items()
            if now_mono - value <= self.dedup_ttl_seconds
        }
        self._recent_file_fingerprints = {
            key: value
            for key, value in self._recent_file_fingerprints.items()
            if now_mono - value <= self.dedup_ttl_seconds
        }
        now = time.time()
        cancelled = self._load_cancelled_tasks()
        filtered = {
            key: value
            for key, value in cancelled.items()
            if now - value <= self.cancelled_task_ttl_seconds
        }
        if filtered != cancelled:
            self._save_cancelled_tasks(filtered)

    @staticmethod
    def _clear_dispatch_fields(record: dict[str, Any]) -> None:
        for key in (
            "dispatch_task_id",
            "dispatch_started_at",
            "dispatch_operation",
            "blocked_resume_input",
        ):
            record.pop(key, None)

    def _reset_record_for_followup(self, record: dict[str, Any]) -> None:
        record["state"] = "awaiting_action"
        self._clear_dispatch_fields(record)
        for key in (
            "blocked_reason",
            "blocked_operation",
            "blocked_at",
            "duplicate_confirmation_id",
            "duplicate_confirmed_at",
        ):
            record.pop(key, None)
        record["updated_at"] = time.time()

    def _end_file_session(self, session: str) -> None:
        active = self._active_tasks.pop(session, None)
        if isinstance(active, dict):
            self._mark_task_cancelled(str(active.get("task_id") or ""))
        record = self.pending.get(session)
        if isinstance(record, dict):
            record["state"] = "ended"
            self._clear_dispatch_fields(record)
            record["updated_at"] = time.time()
            self._save_state()

    def _cancel_operation_preserve_file(self, session: str) -> None:
        active = self._active_tasks.pop(session, None)
        if isinstance(active, dict):
            self._mark_task_cancelled(str(active.get("task_id") or ""))
        record = self.pending.get(session)
        if isinstance(record, dict):
            self._reset_record_for_followup(record)
            self._save_state()

    def _replace_current_file_context(self, session: str) -> None:
        active = self._active_tasks.pop(session, None)
        if isinstance(active, dict):
            self._mark_task_cancelled(str(active.get("task_id") or ""))
        old_record = self.pending.pop(session, None)
        if isinstance(old_record, dict):
            old_fingerprint = str(old_record.get("file_fingerprint") or "")
            if old_fingerprint:
                self._recent_file_fingerprints.pop(old_fingerprint, None)
        if old_record is not None:
            self._save_state()
            logger.info(
                "Contract file router: switched to a newly uploaded file; "
                "previous staged file retained for maintenance cleanup."
            )

    def _build_task_context(
        self,
        event: AstrMessageEvent,
        action: dict[str, Any],
        record: dict[str, Any],
    ) -> tuple[dict[str, Any], str]:
        context, dynamic = RuntimeContractFileRouter._build_task_context(
            self,
            event,
            action,
            record,
        )
        operation = str(context.get("operation") or "")
        if operation == "quick_analysis":
            dynamic += (
                "\n快速分析默认只输出最重要的4至6个风险，最多8个。"
                "每个风险用一条简短表述同时给出风险、原文位置和修改建议；"
                "不要机械遍历全部条款，不重复总体结论、法律背景、待确认清单或修改优先级。"
                "低重要度的措辞、排版和一般性提示除非会影响合同效力或履约，否则省略。"
            )
        elif operation == "free_question":
            dynamic += (
                "\n只回答用户当前问题，优先直接结论和原文位置；"
                "除非问题本身需要，不扩展成完整合同审查。"
            )
        dynamic += (
            "\n本次任务回复完成后，当前合同文件仍保留。"
            "答复末尾用一句话询问用户是否还需要继续处理这份合同；"
            "用户可以继续提问、要求修改、上传下一份文件，或回复“结束”。"
        )
        return context, dynamic

    async def _snapshot_staged_text(self, event: AstrMessageEvent) -> None:
        if event.get_extra(_STAGED_TEXT_EVENT_KEY) is not None:
            return
        context = event.get_extra("contract_task_context")
        if not isinstance(context, dict):
            return
        operation = str(context.get("operation") or "").strip()
        if operation not in {
            "contract_system_upload",
            "contract_system_reupload",
            "quick_analysis",
            "free_question",
        }:
            return
        files = context.get("source_files")
        if not isinstance(files, list):
            files = []
        payload = await extract_staged_contract_text(files)
        if operation == "free_question":
            payload["user_query"] = (event.message_str or "").strip()
        event.set_extra(_STAGED_TEXT_EVENT_KEY, payload)

    @staticmethod
    def _append_staged_text(req: Any, event: AstrMessageEvent) -> None:
        if event.get_extra(_STAGED_TEXT_ATTACHED_EVENT_KEY, False):
            return
        payload = event.get_extra(_STAGED_TEXT_EVENT_KEY)
        if not isinstance(payload, dict):
            return

        sections: list[str] = []
        text = str(payload.get("text") or "").strip()
        if text:
            sections.append(
                "<staged_contract_text>\n"
                "以下内容是本轮暂存合同的正文快照，直接据此执行当前合同任务。\n"
                f"{text}\n"
                "</staged_contract_text>"
            )
        else:
            sections.append(
                "<staged_contract_parse_notes>未能从当前暂存文件取得可读正文；"
                "不得凭空推测合同标题、日期或条款。</staged_contract_parse_notes>"
            )
        errors = payload.get("errors")
        if isinstance(errors, list) and errors:
            error_text = "\n".join(
                f"- {str(value)}" for value in errors if str(value).strip()
            )
            if error_text:
                sections.append(
                    "<staged_contract_parse_notes>\n"
                    f"{error_text}\n"
                    "</staged_contract_parse_notes>"
                )
        if payload.get("truncated"):
            sections.append(
                "<staged_contract_parse_notes>合同正文超过本轮直接注入上限，"
                "当前上下文包含前部正文。</staged_contract_parse_notes>"
            )
        user_query = str(payload.get("user_query") or "").strip()
        if user_query:
            sections.append(
                "<current_contract_question>\n"
                f"{user_query}\n"
                "</current_contract_question>"
            )

        content = "\n\n".join(sections)
        contexts = getattr(req, "contexts", None)
        if not isinstance(contexts, list):
            contexts = []
            req.contexts = contexts
        contexts.append(
            {
                "role": "user",
                "content": content,
                "_no_save": True,
            }
        )
        event.set_extra(_STAGED_TEXT_ATTACHED_EVENT_KEY, True)

    @filter.event_message_type(filter.EventMessageType.ALL, priority=1000)
    async def intake(
        self,
        event: AstrMessageEvent,
        *args: Any,
        **kwargs: Any,
    ):
        if not self._platform_allowed(event):
            return

        results: list[Any] = []
        async with self._session_lock(event):
            self._cleanup()
            session = self._session_key(event)
            text = (event.message_str or "").strip()
            normalized = self._normalize_text(text)
            classification = self._classify_text(text)
            existing = self.pending.get(session)
            active = self._active_task_for_session(session)

            if normalized in _DELETE_FILE_ALIASES:
                if existing or active:
                    self._clear_session(
                        session,
                        delete_files=True,
                        mark_active_cancelled=True,
                    )
                    message = "当前暂存合同文件已删除。"
                else:
                    message = "当前没有待删除的合同文件。"
                event.stop_event()
                results.append(event.plain_result(message))
            elif classification == "end" and (existing or active):
                self._end_file_session(session)
                event.stop_event()
                results.append(
                    event.plain_result(
                        "当前文件会话已结束，暂存文件仍保留。"
                        "发送新文件可开始处理下一份；如需物理删除请回复“删除文件”。"
                    )
                )
            elif classification == "cancel" and (existing or active):
                self._cancel_operation_preserve_file(session)
                event.stop_event()
                results.append(
                    event.plain_result(
                        "已取消当前操作，合同文件仍保留。"
                        "可以继续提问、选择其他操作，或回复“结束”。"
                    )
                )
            else:
                if self._has_file(event) and (existing or active):
                    self._replace_current_file_context(session)
                    existing = None
                    active = None
                elif isinstance(existing, dict) and str(existing.get("state") or "") == "ended":
                    return

                async for result in RuntimeContractFileRouter.intake(
                    self,
                    event,
                    *args,
                    **kwargs,
                ):
                    results.append(result)
                if event.get_extra("contract_explicit_request", False):
                    await self._snapshot_staged_text(event)

        for result in results:
            yield result

    @filter.on_llm_request(priority=1000)
    async def attach_context(
        self,
        event: AstrMessageEvent,
        *args: Any,
        **kwargs: Any,
    ):
        async with self._session_lock(event):
            session = self._session_key(event)
            record = self.pending.get(session)
            if (
                isinstance(record, dict)
                and str(record.get("state") or "") == "ended"
                and not event.get_extra("contract_explicit_request", False)
            ):
                return
            await RuntimeContractFileRouter.attach_context(
                self,
                event,
                *args,
                **kwargs,
            )
            await self._snapshot_staged_text(event)

        req = self._resolve_provider_request(args, kwargs)
        if req is not None:
            self._append_staged_text(req, event)

    @filter.after_message_sent(priority=-999)
    async def clear_pending_after_result(
        self,
        event: AstrMessageEvent,
        *args: Any,
        **kwargs: Any,
    ):
        async with self._session_lock(event):
            preserve_reason = str(
                event.get_extra("contract_preserve_pending_reason") or ""
            )
            if preserve_reason in {
                "duplicate_confirmation_required",
                "blocked",
            }:
                return await RuntimeContractFileRouter.clear_pending_after_result(
                    self,
                    event,
                    *args,
                    **kwargs,
                )

            session = self._session_key(event)
            task_id = event.get_extra("contract_pending_task_id")
            if not task_id:
                return
            active = self._active_tasks.get(session)
            if (
                not isinstance(active, dict)
                or active.get("task_id") != task_id
            ):
                return
            self._active_tasks.pop(session, None)
            record = self.pending.get(session)
            if not isinstance(record, dict):
                return
            self._reset_record_for_followup(record)
            self._save_state()
            logger.info(
                "Contract file router: completed task %s; staged file retained "
                "for follow-up.",
                task_id,
            )


__all__ = ["Main"]
