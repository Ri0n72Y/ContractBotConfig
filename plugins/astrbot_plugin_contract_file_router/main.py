from __future__ import annotations

import asyncio
import hashlib
import time
from pathlib import Path
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

from .document_text import extract_staged_contract_text
from .runtime import ContractFileRouter as RuntimeContractFileRouter


_STAGED_TEXT_EVENT_KEY = "contract_staged_document_text"
_STAGED_TEXT_ATTACHED_EVENT_KEY = "contract_staged_document_text_attached"


class Main(Star, RuntimeContractFileRouter):
    """Only AstrBot Star entrypoint; runtime.py owns the task state machine."""

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

    @staticmethod
    def _md5(path: Path) -> str:
        digest = hashlib.md5(usedforsecurity=False)
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    async def _stage_files(
        self, event: AstrMessageEvent
    ) -> list[dict[str, Any]]:
        files = await RuntimeContractFileRouter._stage_files(self, event)
        for item in files:
            if not isinstance(item, dict):
                continue
            raw_path = str(item.get("staged_path") or "")
            if not raw_path or item.get("staging_status") != "staged":
                continue
            path = Path(raw_path)
            try:
                if not path.is_file():
                    continue
                md5_value = self._md5(path)
                item["md5"] = md5_value
                renamed = path.with_name(f"{md5_value}_{path.name}")
                if renamed != path and not renamed.exists():
                    path.rename(renamed)
                    path = renamed
                item["staged_path"] = str(path.resolve())
            except OSError as exc:
                logger.warning(
                    "Contract file router MD5 staging rename failed: %s",
                    type(exc).__name__,
                )
        return files

    @staticmethod
    def _files_fingerprint(
        session: str, files: list[dict[str, Any]]
    ) -> str:
        parts: list[str] = []
        for item in files:
            if not isinstance(item, dict):
                continue
            md5_value = str(item.get("md5") or "").strip()
            if md5_value:
                parts.append(md5_value)
                continue
            parts.append(
                "|".join(
                    str(value or "")
                    for value in (
                        item.get("original_name"),
                        item.get("size_bytes"),
                        item.get("staging_status"),
                    )
                )
            )
        digest = hashlib.md5(usedforsecurity=False)
        digest.update(f"{session}:{';'.join(sorted(parts))}".encode("utf-8"))
        return digest.hexdigest()

    @staticmethod
    def _delete_record_files(record: dict[str, Any] | None) -> None:
        """Business flows never delete retained staged files."""
        del record

    @staticmethod
    def _delete_new_staged_files(files: list[dict[str, Any]]) -> None:
        """Business dedup/rejection never performs physical file cleanup."""
        del files

    def _cleanup(self) -> None:
        """Expire transient task state only; physical file cleanup is maintenance work."""
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
        expired = [
            session
            for session, record in self.pending.items()
            if str(record.get("state") or "") != "awaiting_blocked_resolution"
            and now
            - float(record.get("updated_at", record.get("created_at", 0)))
            > self.pending_ttl_seconds
        ]
        for session in expired:
            self.pending.pop(session, None)
            self._active_tasks.pop(session, None)
        if expired:
            self._save_state()

        cancelled = self._load_cancelled_tasks()
        filtered = {
            key: value
            for key, value in cancelled.items()
            if now - value <= self.cancelled_task_ttl_seconds
        }
        if filtered != cancelled:
            self._save_cancelled_tasks(filtered)

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
                "以下内容是本轮暂存合同的正文快照，直接据此执行本轮合同任务。\n"
                f"{text}\n"
                "</staged_contract_text>"
            )
        else:
            sections.append(
                "<staged_contract_parse_notes>未能从本轮暂存文件取得可读正文；"
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
                "<contract_question>\n"
                f"{user_query}\n"
                "</contract_question>"
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
            return await RuntimeContractFileRouter.clear_pending_after_result(
                self,
                event,
                *args,
                **kwargs,
            )


__all__ = ["Main"]
