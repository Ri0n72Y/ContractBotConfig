from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
import astrbot.api.message_components as Comp


UPLOAD_MARKERS = {
    "complete": "[CONTRACT_UPLOAD:COMPLETE]",
    "processing": "[CONTRACT_UPLOAD:PROCESSING]",
    "blocked": "[CONTRACT_UPLOAD:BLOCKED]",
    "failed": "[CONTRACT_UPLOAD:FAILED]",
    "duplicate": "[CONTRACT_UPLOAD:DUPLICATE_CONFIRMATION_REQUIRED]",
}


class WecomFinalResultGuard(Star):
    """Collapse output into one WeCom-safe customer result."""

    def __init__(
        self,
        context: Context,
        config: AstrBotConfig | None = None,
    ):
        super().__init__(context, config)
        config = config or {}
        self.max_text_bytes = int(config.get("max_text_bytes", 1800))
        self.max_non_text_components = int(
            config.get("max_non_text_components", 1)
        )
        self.customer_facing_upload_results = bool(
            config.get("customer_facing_upload_results", True)
        )
        self.cancelled_task_ttl_seconds = int(
            config.get("cancelled_task_ttl_seconds", 172800)
        )
        self.cancelled_tasks_path = Path(
            str(
                config.get(
                    "cancelled_tasks_path",
                    "data/plugins_data/astrbot_plugin_contract_file_router/"
                    "cancelled_contract_tasks.json",
                )
            )
        ).expanduser().resolve()
        self.upload_processing_text = str(
            config.get(
                "upload_processing_text",
                "合同文件已接收，文档精读、标注和检索仍在处理中。\n\n"
                "当前流程已经结束，您可以继续上传合同或提出其他问题。",
            )
        ).strip()
        self.upload_complete_text = str(
            config.get(
                "upload_complete_text",
                "合同已完成上传、精读和标注。\n\n"
                "您可以继续上传合同或提出其他问题。",
            )
        ).strip()
        self.upload_blocked_text = str(
            config.get(
                "upload_blocked_text",
                "暂时无法确认合同系统中的文件状态，因此没有执行上传。"
                "请检查 OpenContracts REST 路径查询端点及容器服务后重试。",
            )
        ).strip()
        self.upload_failed_text = str(
            config.get(
                "upload_failed_text",
                "合同暂时无法完成上传。本次流程已结束，请稍后重试或联系工作人员。",
            )
        ).strip()
        self.upload_duplicate_text = str(
            config.get(
                "upload_duplicate_text",
                "这份合同已经存在于合同系统中。\n\n"
                "需要覆盖并重新处理，请回复“重新上传”。\n"
                "保留现有合同并结束任务，请回复“取消”。\n"
                "需要处理其他合同，请先回复“结束”，再发送新文件。",
            )
        ).strip()

    async def initialize(self) -> None:
        logger.info(
            "WeCom final result guard 0.2.3 initialized: instance_id=%s",
            id(self),
        )

    @staticmethod
    def _is_wecom(event: AstrMessageEvent) -> bool:
        try:
            return event.get_platform_name() == "wecom"
        except Exception:
            return False

    @staticmethod
    def _truncate_utf8(text: str, max_bytes: int) -> tuple[str, bool]:
        chars: list[str] = []
        size = 0
        truncated = False
        for char in (text or "").strip():
            char_size = len(char.encode("utf-8"))
            if chars and size + char_size > max_bytes:
                truncated = True
                break
            chars.append(char)
            size += char_size
        return "".join(chars), truncated

    @staticmethod
    def _upload_operation(event: AstrMessageEvent) -> bool:
        context = event.get_extra("contract_task_context", {})
        return (
            isinstance(context, dict)
            and context.get("operation")
            in {"contract_system_upload", "contract_system_reupload"}
        )

    @staticmethod
    def _classify_upload_result(text: str) -> str | None:
        value = text or ""
        lowered = value.lower()
        for status, marker in UPLOAD_MARKERS.items():
            if marker in value:
                return status

        if (
            "confirmation_required" in lowered
            or "duplicate_confirmation_required" in lowered
            or "document_path_exists" in lowered
            or "unique_active_path_per_corpus" in lowered
            or "duplicate key value violates unique constraint" in lowered
            or "这份合同已经上传过" in value
            or "这份合同已经存在" in value
        ):
            return "duplicate"

        if (
            '"status": "unknown"' in lowered
            or "remote_duplicate_check" in lowered
            or "lookup_path" in lowered
            or "remote_rest_path" in lowered
            or "rest_endpoint_missing" in lowered
            or "remote_duplicate_check" in lowered
            or "路径重复检查" in value
            or "rest 路径查询" in lowered
            or "无法确认合同系统" in value
        ):
            return "blocked"

        accepted_count = lowered.count("accepted") + value.count("成功接收")
        processing_signals = (
            "processing",
            "后台处理",
            "仍在处理",
            "尚未完成",
            "精读和标注",
        )
        if accepted_count >= 1 and any(
            signal in lowered or signal in value
            for signal in processing_signals
        ):
            return "processing"

        if (
            ("处理完成" in value or "检索验证完成" in value)
            and "processing" not in lowered
            and "尚未完成" not in value
        ):
            return "complete"

        failed_signals = (
            '"status": "failed"',
            "上传失败",
            "reupload_path_resolution",
            "request_validation",
            "upstream_service",
        )
        if any(
            signal in lowered or signal in value
            for signal in failed_signals
        ):
            return "failed"

        blocked_signals = (
            '"status": "blocked"',
            "not_started",
            "未配置",
            "无法执行上传",
            "上传被阻止",
        )
        if any(
            signal in lowered or signal in value
            for signal in blocked_signals
        ):
            return "blocked"
        return None

    def _customer_upload_text(self, status: str) -> str:
        if status == "complete":
            return self.upload_complete_text
        if status == "processing":
            return self.upload_processing_text
        if status == "duplicate":
            return self.upload_duplicate_text
        if status == "blocked":
            return self.upload_blocked_text
        return self.upload_failed_text

    def _consume_cancelled_task(self, task_id: str | None) -> bool:
        if not task_id or not self.cancelled_tasks_path.exists():
            return False
        try:
            payload = json.loads(
                self.cancelled_tasks_path.read_text(encoding="utf-8")
            )
            if not isinstance(payload, dict):
                return False
            now = time.time()
            filtered = {
                str(key): float(value)
                for key, value in payload.items()
                if now - float(value) <= self.cancelled_task_ttl_seconds
            }
            found = str(task_id) in filtered
            filtered.pop(str(task_id), None)
            temporary = self.cancelled_tasks_path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(filtered, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary.replace(self.cancelled_tasks_path)
            return found
        except Exception as exc:
            logger.warning(
                "Cancelled contract task registry read failed: %s", exc
            )
            return False

    @filter.on_decorating_result(priority=-999)
    async def normalize_result(
        self,
        event: AstrMessageEvent,
        *_hook_args: Any,
        **_hook_kwargs: Any,
    ):
        if self is None or not self._is_wecom(event):
            return

        result = event.get_result()
        chain = getattr(result, "chain", None) if result else None
        if not isinstance(chain, list):
            return

        task_id = event.get_extra("contract_pending_task_id")
        if self._consume_cancelled_task(str(task_id or "")):
            result.chain = []
            logger.info(
                "WeCom final result guard: suppressed cancelled contract task %s.",
                task_id,
            )
            return

        plains = [
            component.text.strip()
            for component in chain
            if (
                isinstance(component, Comp.Plain)
                and component.text
                and component.text.strip()
            )
        ]
        non_text = [
            component
            for component in chain
            if not isinstance(component, Comp.Plain)
        ]

        if not plains:
            if self._upload_operation(event):
                result.chain = [Comp.Plain(self.upload_failed_text)]
                logger.error(
                    "WeCom final result guard: upload operation returned no text; "
                    "inserted deterministic failure response."
                )
            return

        raw_final_text = plains[-1]
        if self.customer_facing_upload_results and self._upload_operation(event):
            upload_status = self._classify_upload_result(raw_final_text)
            if upload_status is not None:
                raw_final_text = self._customer_upload_text(upload_status)
                if upload_status == "duplicate":
                    event.set_extra(
                        "contract_preserve_pending_reason",
                        "duplicate_confirmation_required",
                    )
                logger.info(
                    "WeCom final result guard: normalized contract upload "
                    "result for customer, status=%s.",
                    upload_status,
                )

        final_text, truncated = self._truncate_utf8(
            raw_final_text, self.max_text_bytes
        )
        if truncated:
            suffix = "\n\n（结果过长，已截断；详细结果应作为附件交付。）"
            allowed = max(
                1,
                self.max_text_bytes - len(suffix.encode("utf-8")),
            )
            final_text, _ = self._truncate_utf8(raw_final_text, allowed)
            final_text += suffix

        result.chain = [
            Comp.Plain(final_text),
            *non_text[: self.max_non_text_components],
        ]
        if len(plains) > 1:
            logger.info(
                "WeCom final result guard: removed %d intermediate Plain "
                "components.",
                len(plains) - 1,
            )
