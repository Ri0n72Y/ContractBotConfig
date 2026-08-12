from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star
import astrbot.api.message_components as Comp


UPLOAD_MARKERS = {
    "manual_review": "[CONTRACT_UPLOAD:MANUAL_REVIEW]",
    "duplicate": "[CONTRACT_UPLOAD:DUPLICATE_CONFIRMATION_REQUIRED]",
    "blocked": "[CONTRACT_UPLOAD:BLOCKED]",
    "processing": "[CONTRACT_UPLOAD:PROCESSING]",
    "complete": "[CONTRACT_UPLOAD:COMPLETE]",
    "failed": "[CONTRACT_UPLOAD:FAILED]",
}

READ_MARKERS = {
    "ready": "[CONTRACT_READ:READY]",
    "partial": "[CONTRACT_READ:PARTIAL]",
    "pending": "[CONTRACT_READ:PENDING]",
    "failed": "[CONTRACT_READ:FAILED]",
}

BLOCKED_MISSING_DATE_TEXT = (
    "合同正文中未找到可靠的合同日期，因此没有执行上传。"
    "当前合同文件已保留，请直接回复合同日期（YYYY-MM-DD），我会继续上传；"
    "无需重新发送文件。需要放弃请回复“结束”。"
)
BLOCKED_MISSING_TITLE_TEXT = (
    "合同正文中未找到可靠的正式标题，因此没有执行上传。"
    "当前合同文件已保留，请直接回复正式合同标题，我会继续上传；"
    "无需重新发送文件。需要放弃请回复“结束”。"
)
BLOCKED_MISSING_IDENTITY_TEXT = (
    "合同正文中缺少可靠的合同日期和正式标题，因此没有执行上传。"
    "当前合同文件已保留，请补充这些信息后继续；"
    "无需重新发送文件。需要放弃请回复“结束”。"
)


class WecomFinalResultGuard(Star):
    """Normalize contract results and split long WeCom text responses."""

    def __init__(
        self,
        context: Context,
        config: AstrBotConfig | None = None,
    ):
        super().__init__(context, config)
        config = config or {}
        self.max_text_bytes = max(512, int(config.get("max_text_bytes", 1800)))
        self.enable_text_segmentation = bool(
            config.get("enable_text_segmentation", True)
        )
        self.max_text_segments = max(
            2, int(config.get("max_text_segments", 12))
        )
        self.segment_title = str(
            config.get("segment_title", "合同分析")
        ).strip() or "合同分析"
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
                "合同文件已写入，正文解析或检索仍在处理中。\n\n"
                "当前流程已经结束，您可以稍后查询处理状态。",
            )
        ).strip()
        self.upload_complete_text = str(
            config.get(
                "upload_complete_text",
                "合同已完成上传，正文可以读取并已进入检索。\n\n"
                "您可以继续上传合同或提出其他问题。",
            )
        ).strip()
        self.upload_manual_review_text = str(
            config.get(
                "upload_manual_review_text",
                "合同系统可能已经接收了本次写入，但当前无法安全确认最终状态。"
                "已记录审计信息，请工作人员核查；请勿重复上传。",
            )
        ).strip()
        self.upload_blocked_text = str(
            config.get(
                "upload_blocked_text",
                "本次没有执行上传，当前合同文件已保留。"
                "请管理员检查 OpenContracts 公开 MCP、目标 Corpus slug、"
                "工具绑定或文件访问条件；修复后请回复“继续”。"
                "需要放弃当前合同请回复“结束”。",
            )
        ).strip()
        self.upload_failed_text = str(
            config.get(
                "upload_failed_text",
                "合同暂时无法完成上传，本次流程已结束。"
                "请重新上传合同文件，或联系工作人员。",
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
            "WeCom final result guard 0.3.5 initialized: instance_id=%s",
            id(self),
        )

    @staticmethod
    def _is_wecom(event: AstrMessageEvent) -> bool:
        try:
            return event.get_platform_name() == "wecom"
        except Exception:
            return False

    @staticmethod
    def _utf8_size(text: str) -> int:
        return len((text or "").encode("utf-8"))

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

    @classmethod
    def _hard_split_utf8(cls, text: str, max_bytes: int) -> list[str]:
        remaining = (text or "").strip()
        chunks: list[str] = []
        while remaining:
            chunk, truncated = cls._truncate_utf8(remaining, max_bytes)
            if not chunk:
                chunk = remaining[0]
            chunks.append(chunk.strip())
            if not truncated or len(chunk) >= len(remaining):
                break
            remaining = remaining[len(chunk) :].lstrip()
        return [chunk for chunk in chunks if chunk]

    @classmethod
    def _split_utf8(cls, text: str, max_bytes: int) -> list[str]:
        value = (text or "").strip()
        if not value:
            return []
        if cls._utf8_size(value) <= max_bytes:
            return [value]
        paragraphs = [part.strip() for part in re.split(r"\n{2,}", value) if part.strip()]
        chunks: list[str] = []
        current = ""
        for paragraph in paragraphs:
            candidate = paragraph if not current else f"{current}\n\n{paragraph}"
            if cls._utf8_size(candidate) <= max_bytes:
                current = candidate
                continue
            if current:
                chunks.append(current)
                current = ""
            if cls._utf8_size(paragraph) <= max_bytes:
                current = paragraph
                continue
            lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
            line_buffer = ""
            for line in lines or [paragraph]:
                line_candidate = line if not line_buffer else f"{line_buffer}\n{line}"
                if cls._utf8_size(line_candidate) <= max_bytes:
                    line_buffer = line_candidate
                    continue
                if line_buffer:
                    chunks.append(line_buffer)
                    line_buffer = ""
                if cls._utf8_size(line) <= max_bytes:
                    line_buffer = line
                else:
                    chunks.extend(cls._hard_split_utf8(line, max_bytes))
            if line_buffer:
                current = line_buffer
        if current:
            chunks.append(current)
        return [chunk for chunk in chunks if chunk]

    @staticmethod
    def _upload_operation(event: AstrMessageEvent) -> bool:
        context = event.get_extra("contract_task_context", {})
        return (
            isinstance(context, dict)
            and context.get("operation")
            in {"contract_system_upload", "contract_system_reupload"}
        )

    @classmethod
    def _classify_upload_result(cls, text: str) -> str | None:
        value = text or ""
        lowered = value.lower()
        for status, marker in UPLOAD_MARKERS.items():
            if marker in value:
                return status
        manual_review_signals = (
            '"status": "manual_review_required"',
            '"manual_review_required": true',
            "unexpected_unconfirmed_update",
            "transport_commit_unknown",
            "upstream_commit_unknown",
            "unexpected_success_response",
            "write_committed=unknown",
            "需要人工核查",
            "请勿重复上传",
        )
        if any(signal in lowered or signal in value for signal in manual_review_signals):
            return "manual_review"
        duplicate_signals = (
            "confirmation_required",
            "duplicate_confirmation_required",
            "document_path_exists",
            "unique_active_path_per_corpus",
            "duplicate key value violates unique constraint",
            "这份合同已经上传过",
            "这份合同已经存在",
        )
        if any(signal in lowered or signal in value for signal in duplicate_signals):
            return "duplicate"
        blocked_read_signals = (
            '"status": "unknown"',
            "mcp_document_discovery",
            "mcp_query_incomplete",
            "mcp_unavailable",
            "opencontracts mcp",
            "无法确认合同系统",
        )
        if any(signal in lowered or signal in value for signal in blocked_read_signals):
            return "blocked"
        if cls._blocked_reason(value) != "system":
            return "blocked"
        accepted_count = lowered.count("accepted") + value.count("成功接收")
        processing_signals = (
            "processing",
            "后台处理",
            "仍在处理",
            "尚未完成",
            "正文解析",
            "检索仍在处理",
        )
        if accepted_count >= 1 and any(
            signal in lowered or signal in value for signal in processing_signals
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
            "version_write_conflict",
            "request_validation",
            "import_endpoint_missing",
        )
        if any(signal in lowered or signal in value for signal in failed_signals):
            return "failed"
        blocked_signals = (
            '"status": "blocked"',
            "not_started",
            "未配置",
            "无法执行上传",
            "上传被阻止",
            "document_identity",
        )
        if any(signal in lowered or signal in value for signal in blocked_signals):
            return "blocked"
        return None

    @staticmethod
    def _term_missing(text: str, terms: tuple[str, ...]) -> bool:
        lowered = (text or "").lower()
        missing = (
            "无法提取",
            "无法可靠提取",
            "无法可靠取得",
            "未找到可靠",
            "缺少",
            "字段为空",
            "为空白",
            "未填写",
            "需要补充",
            "请补充",
            "请您补充",
            "missing",
            "required",
            "empty",
            "null",
        )
        clauses = [
            clause.strip()
            for clause in re.split(r"[\n。；;]", lowered)
            if clause.strip()
        ]
        for clause in clauses:
            if not any(term.lower() in clause for term in terms):
                continue
            if any(signal.lower() in clause for signal in missing):
                return True
        return False

    @classmethod
    def _blocked_reason(cls, text: str) -> str:
        date_missing = cls._term_missing(
            text,
            ("合同日期", "签订日期", "签署日期", "生效日期", "contract_date"),
        )
        title_missing = cls._term_missing(
            text,
            ("合同正式标题", "正式标题", "合同标题", "contract_title"),
        )
        if date_missing and title_missing:
            return "missing_identity"
        if date_missing:
            return "missing_date"
        if title_missing:
            return "missing_title"
        return "system"

    def _customer_upload_text(self, status: str, raw_text: str = "") -> str:
        if status == "complete":
            return self.upload_complete_text
        if status == "processing":
            return self.upload_processing_text
        if status == "manual_review":
            return self.upload_manual_review_text
        if status == "duplicate":
            return self.upload_duplicate_text
        if status == "blocked":
            reason = self._blocked_reason(raw_text)
            if reason == "missing_date":
                return BLOCKED_MISSING_DATE_TEXT
            if reason == "missing_title":
                return BLOCKED_MISSING_TITLE_TEXT
            if reason == "missing_identity":
                return BLOCKED_MISSING_IDENTITY_TEXT
            return self.upload_blocked_text
        return self.upload_failed_text

    @staticmethod
    def _read_status(text: str) -> str | None:
        value = text or ""
        for status, marker in READ_MARKERS.items():
            if marker in value:
                return status
        return None

    @staticmethod
    def _strip_read_markers(text: str) -> str:
        value = text or ""
        for marker in READ_MARKERS.values():
            value = value.replace(marker, "")
        return value.strip()

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
            logger.warning("Cancelled contract task registry read failed: %s", exc)
            return False

    def _segment_prefix(self, index: int, total: int) -> str:
        return f"{self.segment_title}（{index}/{total}）\n\n"

    async def _send_segmented_text(
        self,
        event: AstrMessageEvent,
        text: str,
    ) -> str:
        if not self.enable_text_segmentation:
            truncated, _ = self._truncate_utf8(text, self.max_text_bytes)
            return truncated + "\n\n（结果超过单条消息限制，请缩小分析范围后重试。）"
        payload_limit = max(256, self.max_text_bytes - 96)
        segments = self._split_utf8(text, payload_limit)
        if len(segments) <= 1:
            return segments[0] if segments else ""
        limited = False
        if len(segments) > self.max_text_segments:
            segments = segments[: self.max_text_segments]
            limited = True
            tail = "\n\n（结果已达到消息分段上限；未发送部分请缩小分析范围后重新查询。）"
            allowed = max(64, payload_limit - self._utf8_size(tail))
            segments[-1], _ = self._truncate_utf8(segments[-1], allowed)
            segments[-1] += tail
        total = len(segments)
        sent = 0
        for index, segment in enumerate(segments[:-1], start=1):
            message = self._segment_prefix(index, total) + segment
            try:
                await event.send(MessageChain([Comp.Plain(message)]))
                sent += 1
            except Exception as exc:
                logger.exception(
                    "WeCom final result guard: segment send failed index=%s: %s",
                    index,
                    exc,
                )
                fallback = segment + "\n\n（后续分段发送失败，请稍后缩小范围重试。）"
                fallback, _ = self._truncate_utf8(fallback, self.max_text_bytes)
                return fallback
        logger.info(
            "WeCom final result guard: sent %d intermediate segments, total=%d limited=%s.",
            sent,
            total,
            limited,
        )
        return self._segment_prefix(total, total) + segments[-1]

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
            if isinstance(component, Comp.Plain)
            and component.text
            and component.text.strip()
        ]
        non_text = [component for component in chain if not isinstance(component, Comp.Plain)]
        if not plains:
            if self._upload_operation(event):
                result.chain = [Comp.Plain(self.upload_failed_text)]
                logger.error(
                    "WeCom final result guard: upload operation returned no text; inserted deterministic failure response."
                )
            return
        raw_final_text = plains[-1]
        if self.customer_facing_upload_results and self._upload_operation(event):
            upload_status = self._classify_upload_result(raw_final_text)
            if upload_status is not None:
                blocked_reason = None
                if upload_status == "duplicate":
                    event.set_extra(
                        "contract_preserve_pending_reason",
                        "duplicate_confirmation_required",
                    )
                elif upload_status == "blocked":
                    blocked_reason = self._blocked_reason(raw_final_text)
                    event.set_extra("contract_preserve_pending_reason", "blocked")
                    event.set_extra("contract_blocked_reason", blocked_reason)
                raw_final_text = self._customer_upload_text(
                    upload_status,
                    raw_final_text,
                )
                logger.info(
                    "WeCom final result guard: normalized contract upload result for customer, status=%s blocked_reason=%s.",
                    upload_status,
                    blocked_reason,
                )
        read_status = self._read_status(raw_final_text)
        if read_status is not None:
            event.set_extra("contract_read_status", read_status)
            raw_final_text = self._strip_read_markers(raw_final_text)
            logger.info(
                "WeCom final result guard: observed contract read terminal status=%s.",
                read_status,
            )
        final_text = await self._send_segmented_text(event, raw_final_text)
        result.chain = [
            Comp.Plain(final_text),
            *non_text[: self.max_non_text_components],
        ]
        if len(plains) > 1:
            logger.info(
                "WeCom final result guard: removed %d intermediate Plain components.",
                len(plains) - 1,
            )
