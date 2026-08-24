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
_DELETE_FILE_ALIASES = {
    "删除文件",
    "删除当前文件",
    "删除这份文件",
    "删除当前合同文件",
    "删除这份合同文件",
}


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
        """Only clean transient dedup/cancel metadata; retain staged contract files."""
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

    def _clear_session(
        self,
        session: str,
        *,
        delete_files: bool,
        mark_active_cancelled: bool = False,
    ) -> None:
        """End session state without deleting staged files unless explicitly requested."""
        del delete_files
        RuntimeContractFileRouter._clear_session(
            self,
            session,
            delete_files=False,
            mark_active_cancelled=mark_active_cancelled,
        )

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
            session = self._session_key(event)
            normalized = self._normalize_text(event.message_str or "")

            if normalized in _DELETE_FILE_ALIASES:
                record = self.pending.get(session)
                active = self._active_task_for_session(session)
                if record is not None or active is not None:
                    RuntimeContractFileRouter._clear_session(
                        self,
                        session,
                        delete_files=True,
                        mark_active_cancelled=True,
                    )
                    event.stop_event()
                    results.append(event.plain_result("当前合同文件已删除，可以开始新的任务。"))
                else:
                    event.stop_event()
                    results.append(event.plain_result("当前没有可删除的合同文件。"))
            else:
                # A new file becomes the current file when no contract task is running.
                # The previous staged file remains on disk until explicit deletion or
                # the future maintenance cleanup policy removes it.
                if self._has_file(event):
                    existing = self.pending.get(session)
                    active = self._active_task_for_session(session)
                    if existing is not None and active is None:
                        self.pending.pop(session, None)
                        self._save_state()

                if not results:
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
            if not self._platform_allowed(event):
                return
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

            preserve_reason = str(
                event.get_extra("contract_preserve_pending_reason") or ""
            )
            if preserve_reason in {"duplicate_confirmation_required", "blocked"}:
                return await RuntimeContractFileRouter.clear_pending_after_result(
                    self,
                    event,
                    *args,
                    **kwargs,
                )

            self._active_tasks.pop(session, None)
            record = self.pending.get(session)
            if not isinstance(record, dict):
                return
            record["state"] = "awaiting_action"
            for key in (
                "dispatch_task_id",
                "dispatch_started_at",
                "dispatch_operation",
                "blocked_reason",
                "blocked_operation",
                "blocked_at",
                "blocked_resume_input",
            ):
                record.pop(key, None)
            record["updated_at"] = time.time()
            self._save_state()
            logger.info(
                "Contract file router: completed task %s and retained current file.",
                task_id,
            )


__all__ = ["Main"]
