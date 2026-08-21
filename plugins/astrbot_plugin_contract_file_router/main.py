from __future__ import annotations

import asyncio
from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from .document_text import extract_staged_contract_text
from .runtime import ContractFileRouter as RuntimeContractFileRouter


_STAGED_TEXT_EVENT_KEY = "contract_staged_document_text"
_STAGED_TEXT_ATTACHED_EVENT_KEY = "contract_staged_document_text_attached"




class Main(RuntimeContractFileRouter):
    """AstrBot Star entrypoint with per-session Router serialization."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._intake_locks: dict[str, asyncio.Lock] = {}

    async def initialize(self) -> None:
        logger.info(
            "Contract file router 0.5.8 initialized: data_dir=%s",
            self.data_dir,
        )

    def _session_lock(self, event: AstrMessageEvent) -> asyncio.Lock:
        session = self._session_key(event)
        lock = self._intake_locks.get(session)
        if lock is None:
            lock = asyncio.Lock()
            self._intake_locks[session] = lock
        return lock

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
