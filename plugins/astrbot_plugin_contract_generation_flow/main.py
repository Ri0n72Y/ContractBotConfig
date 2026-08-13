from __future__ import annotations

import json
import re
import time
from pathlib import Path
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


BUILDER_PROMPT_MARKER = "<contract_docassemble_builder_policy>"
GENERATION_TOOL = "transfer_to_docassemble_builder"
REQUIRED_BUILDER_TOOLS = {
    "list_documents",
    "get_document_text",
    "search_corpus",
    "docassemble_gateway_status",
    "docassemble_generate_document",
    "contract_download_delivery_status",
    "publish_contract_download",
}
CONFIRM_ALIASES = {
    "确认",
    "确认生成",
    "确认并生成",
    "按以上信息生成",
    "按上述信息生成",
    "就按这个生成",
    "就按这些生成",
    "开始生成",
    "可以生成",
}
CANCEL_ALIASES = {
    "取消",
    "取消生成",
    "不生成了",
    "结束",
    "结束生成",
}


class ContractGenerationFlow(Star):
    """Deterministic confirmation and progress UX for contract generation."""

    def __init__(
        self,
        context: Context,
        config: AstrBotConfig | None = None,
    ) -> None:
        super().__init__(context, config)
        config = config or {}
        self.config = config
        self.confirmation_ttl_seconds = int(
            config.get("confirmation_ttl_seconds", 1800)
        )
        self.ack_enabled = bool(config.get("generation_ack_enabled", True))
        self.ack_text = str(
            config.get(
                "generation_ack_text",
                "收到了。我先整理你提供的信息和需要补充的项目，"
                "确认无误后再读取合同库并开始生成。",
            )
        ).strip()
        self.start_text = str(
            config.get(
                "generation_start_text",
                "信息已确认，我现在开始读取合同库中的参考合同并生成文档。",
            )
        ).strip()
        self.document_stage_text = str(
            config.get(
                "document_stage_text",
                "参考合同读取已进入生成阶段，正在通过 Docassemble 生成 DOCX。",
            )
        ).strip()
        self.delivery_stage_text = str(
            config.get(
                "delivery_stage_text",
                "DOCX 已生成，正在准备临时 HTTPS 下载链接。",
            )
        ).strip()
        self.confirmation_fallback_text = str(
            config.get(
                "confirmation_fallback_text",
                "我已经整理了本次合同生成需求，但正式生成前需要你确认。"
                "如需补充或修改，请直接回复；如果按当前信息生成，请回复“确认生成”。",
            )
        ).strip()
        self.cancel_text = str(
            config.get("generation_cancel_text", "已取消本次合同生成。")
        ).strip()
        self.state_path = Path(
            str(
                config.get(
                    "state_path",
                    "data/plugins_data/astrbot_plugin_contract_generation_flow/"
                    "pending_generation.json",
                )
            )
        ).expanduser().resolve()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.pending = self._load_state()
        self._cleanup_pending()

    async def initialize(self) -> None:
        logger.info(
            "Contract generation flow 0.1.1 initialized: pending=%d",
            len(self.pending),
        )

    @staticmethod
    def _session_key(event: AstrMessageEvent) -> str:
        return str(event.unified_msg_origin)

    @staticmethod
    def _normalize_text(text: str) -> str:
        return re.sub(r"\s+", "", (text or "").strip().lower())

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
    def _parse_input(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        if not isinstance(value, str) or not value.strip():
            return {}
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {"request_text": value.strip()}
        return parsed if isinstance(parsed, dict) else {"request_text": value.strip()}

    @staticmethod
    def _append_temp_instruction(req: ProviderRequest, text: str) -> None:
        if TextPart is not None and hasattr(req, "extra_user_content_parts"):
            part = TextPart(text=text)
            if hasattr(part, "mark_as_temp"):
                part = part.mark_as_temp()
            req.extra_user_content_parts.append(part)
        else:
            req.prompt = f"{req.prompt or ''}\n\n{text}"

    def _load_state(self) -> dict[str, dict[str, Any]]:
        try:
            if self.state_path.is_file():
                payload = json.loads(self.state_path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    return {
                        str(key): value
                        for key, value in payload.items()
                        if isinstance(value, dict)
                    }
        except Exception as exc:
            logger.warning("Generation confirmation state load failed: %s", exc)
        return {}

    def _save_state(self) -> None:
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(self.pending, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.state_path)

    def _cleanup_pending(self) -> None:
        now = time.time()
        expired = [
            key
            for key, value in self.pending.items()
            if now
            - float(value.get("updated_at", value.get("created_at", 0)) or 0)
            > self.confirmation_ttl_seconds
        ]
        for key in expired:
            self.pending.pop(key, None)
        if expired:
            self._save_state()

    async def _send_once(
        self,
        event: AstrMessageEvent,
        extra_key: str,
        text: str,
    ) -> None:
        if not text or event.get_extra(extra_key, False):
            return
        try:
            await event.send(MessageChain([Comp.Plain(text)]))
            event.set_extra(extra_key, True)
        except Exception as exc:
            logger.warning("Generation progress message failed: %s", exc)

    def _store_pending(
        self,
        event: AstrMessageEvent,
        original_input: Any,
        parsed: dict[str, Any],
    ) -> None:
        session = self._session_key(event)
        now = time.time()
        existing = self.pending.get(session, {})
        self.pending[session] = {
            "created_at": float(existing.get("created_at", now) or now),
            "updated_at": now,
            "input": original_input,
            "parsed": parsed,
        }
        self._save_state()

    def _clear_pending(self, event: AstrMessageEvent) -> None:
        if self.pending.pop(self._session_key(event), None) is not None:
            self._save_state()

    @filter.event_message_type(filter.EventMessageType.ALL, priority=1150)
    async def mark_pending_generation(
        self,
        event: AstrMessageEvent,
        *_args: Any,
        **_kwargs: Any,
    ) -> None:
        self._cleanup_pending()
        pending = self.pending.get(self._session_key(event))
        if not pending:
            return
        normalized = self._normalize_text(str(event.message_str or ""))
        if normalized in CANCEL_ALIASES:
            self._clear_pending(event)
            event.set_extra("contract_generation_confirmation_cancelled", True)
            event.stop_event()
            await self._send_once(
                event,
                "contract_generation_cancel_sent",
                self.cancel_text,
            )
            return
        event.set_extra("contract_docassemble_generation_task", True)
        event.set_extra("contract_generation_pending", True)
        if normalized in CONFIRM_ALIASES:
            event.set_extra("contract_generation_confirmation_approved", True)

    @filter.on_llm_request(priority=1150)
    async def prepare_generation_request(
        self,
        event: AstrMessageEvent,
        *hook_args: Any,
        **hook_kwargs: Any,
    ) -> None:
        req = self._resolve_provider_request(hook_args, hook_kwargs)
        if req is None:
            return

        system_prompt = str(getattr(req, "system_prompt", "") or "")
        tool_set = getattr(req, "func_tool", None)
        tools = getattr(tool_set, "tools", None)

        if BUILDER_PROMPT_MARKER in system_prompt:
            prompt_text = str(getattr(req, "prompt", "") or "")
            if (
                "generation_confirmation_required" in prompt_text
                and "must_not_execute" in prompt_text
            ):
                if isinstance(tools, list):
                    tool_set.tools = []
                self._append_temp_instruction(
                    req,
                    "<contract_generation_confirmation_guard>\n"
                    "本次只是生成前确认门。input 中 must_not_execute=true。"
                    "工具集已被运行时清空，不得执行任何生成或读取。"
                    "立即返回 [CONTRACT_DOCASSEMBLE:BLOCKED]，"
                    "reason=generation_confirmation_required，"
                    "confirmation_prompt_sent=true。\n"
                    "</contract_generation_confirmation_guard>",
                )
                return

            if isinstance(tools, list):
                names = {str(getattr(tool, "name", "")) for tool in tools}
                missing = sorted(REQUIRED_BUILDER_TOOLS - names)
                if missing:
                    tool_set.tools = []
                    self._append_temp_instruction(
                        req,
                        "<contract_generation_tool_guard>\n"
                        "Builder 的 WebUI 工具绑定不完整，禁止开始任何合同生成。"
                        f"缺少工具：{json.dumps(missing, ensure_ascii=False)}。"
                        "立即返回 [CONTRACT_DOCASSEMBLE:BLOCKED]，"
                        "reason=builder_tool_binding_incomplete，并列出 missing_tools。"
                        "不得调用 Docassemble、Shell、Python、HTTP 或本地文件工具补救。\n"
                        "</contract_generation_tool_guard>",
                    )
                    logger.error(
                        "Contract generation flow: Builder tools incomplete: %s",
                        missing,
                    )
                    return

            self._append_temp_instruction(
                req,
                "<contract_generation_runtime_guard>\n"
                "正式客户合同生成不得使用文件名包含 smoke 的 Docassemble interview；"
                "Gateway 会再次确定性拒绝。"
                "必须先实时使用 list_documents/get_document_text 读取本轮合同库参考正文，"
                "不能把主人格转述或历史会话内容当作已核验来源。"
                "只有 publish_contract_download 返回有效 HTTPS download_url 后才能返回 "
                "[CONTRACT_DOCASSEMBLE:READY]。\n"
                "</contract_generation_runtime_guard>",
            )
            return

        if not event.get_extra("contract_docassemble_generation_task", False):
            return

        pending = self.pending.get(self._session_key(event))
        approved = event.get_extra(
            "contract_generation_confirmation_approved", False
        )

        if self.ack_enabled and not pending and not approved:
            await self._send_once(
                event,
                "contract_generation_ack_sent",
                self.ack_text,
            )

        if pending:
            stored_input = pending.get("input")
            current_text = str(event.message_str or "").strip()
            if approved:
                instruction = (
                    "<contract_generation_confirmation_state>\n"
                    "用户已明确确认上一轮合同生成方案。不要再次询问确认。"
                    "请基于下面 stored_generation_request 调用 "
                    "transfer_to_docassemble_builder，并保持 background_task=false。"
                    "不得改写用户已确认的关键事实；未补充项按确认方案中的处理方式保留。"
                    "\nstored_generation_request:\n"
                    + json.dumps(stored_input, ensure_ascii=False, default=str)
                    + "\n</contract_generation_confirmation_state>"
                )
            else:
                instruction = (
                    "<contract_generation_confirmation_state>\n"
                    "当前会话正在等待合同生成确认。用户本轮输入不是确认指令，"
                    "应视为对上一版方案的补充或修改。"
                    "结合 current_user_update 更新生成方案，再调用 "
                    "transfer_to_docassemble_builder；Generation Flow 会再次拦截并发送确认，"
                    "本轮不得实际生成。"
                    "\nprevious_generation_request:\n"
                    + json.dumps(stored_input, ensure_ascii=False, default=str)
                    + "\ncurrent_user_update:\n"
                    + current_text
                    + "\n</contract_generation_confirmation_state>"
                )
            self._append_temp_instruction(req, instruction)
        else:
            self._append_temp_instruction(
                req,
                "<contract_generation_confirmation_policy>\n"
                "这是新的合同文书生成请求。首次不得实际生成。"
                "先整理用户已提供信息、关键缺失项和需要确认的假设。"
                "随后调用 transfer_to_docassemble_builder，input 必须是 JSON，至少包含："
                "operation='contract_generation'、generation_request、missing_fields、"
                "confirmation_message。confirmation_message 应为简短客户可读文本，"
                "列出已确认信息和仍缺失/待确认信息，并明确："
                "如需修改请直接回复；若按当前方案生成请回复“确认生成”。"
                "不要在 confirmation_message 中声称已经实时读取或核验合同库。"
                "Generation Flow 会拦截首次委派，不会真正执行 Builder。\n"
                "</contract_generation_confirmation_policy>",
            )

    @filter.on_using_llm_tool(priority=1050)
    async def control_generation_tools(
        self,
        event: AstrMessageEvent,
        *hook_args: Any,
        **hook_kwargs: Any,
    ) -> None:
        tool, tool_args = self._resolve_tool_args(hook_args, hook_kwargs)
        if tool is None or tool_args is None:
            return
        tool_name = str(getattr(tool, "name", ""))

        if tool_name == GENERATION_TOOL:
            original_input = tool_args.get("input")
            parsed = self._parse_input(original_input)
            approved = event.get_extra(
                "contract_generation_confirmation_approved", False
            )
            if not approved:
                self._store_pending(event, original_input, parsed)
                confirmation_message = str(
                    parsed.get("confirmation_message")
                    or self.confirmation_fallback_text
                ).strip()
                if len(confirmation_message) > 3000:
                    confirmation_message = (
                        confirmation_message[:3000].rstrip() + "…"
                    )
                await self._send_once(
                    event,
                    "contract_generation_confirmation_prompt_sent",
                    confirmation_message,
                )
                tool_args["background_task"] = False
                tool_args["input"] = json.dumps(
                    {
                        "delegated_agent": "docassemble_builder",
                        "must_not_execute": True,
                        "error": "generation_confirmation_required",
                        "confirmation_prompt_sent": True,
                    },
                    ensure_ascii=False,
                )
                return

            await self._send_once(
                event,
                "contract_generation_start_sent",
                self.start_text,
            )
            self._clear_pending(event)
            tool_args["background_task"] = False
            return

        if not event.get_extra(
            "contract_generation_confirmation_approved", False
        ):
            return

        if tool_name == "list_documents":
            event.set_extra("contract_generation_reference_list_requested", True)
            return

        if tool_name == "get_document_text":
            event.set_extra("contract_generation_reference_text_requested", True)
            return

        if tool_name == "docassemble_generate_document":
            if (
                event.get_extra(
                    "contract_generation_reference_list_requested", False
                )
                and event.get_extra(
                    "contract_generation_reference_text_requested", False
                )
            ):
                event.set_extra("contract_generation_docassemble_requested", True)
                await self._send_once(
                    event,
                    "contract_generation_document_stage_sent",
                    self.document_stage_text,
                )
            return

        if tool_name == "publish_contract_download":
            if event.get_extra("contract_generation_docassemble_requested", False):
                await self._send_once(
                    event,
                    "contract_generation_delivery_stage_sent",
                    self.delivery_stage_text,
                )
