from __future__ import annotations

import hashlib
import inspect
import json
import re
import shutil
import time
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context
import astrbot.api.message_components as Comp

try:
    from astrbot.core.agent.message import TextPart
except Exception:
    TextPart = None


MENU = """已收到合同文件。请选择需要执行的操作：

1. 上传进合同系统
2. 快速分析（提取关键信息 + 风险审查）
3. 自由提问（直接输入要查询的问题）

回复 1 或 2；需要查询条款时，直接输入问题。
需要放弃当前文件并开始其他任务，请回复“结束”。"""
QUESTION_PROMPT = "请直接输入你要查询的合同问题，例如：付款条件是什么？解除合同需要满足什么条件？"
DUPLICATE_PROMPT = """这份合同已经存在于合同系统中。

需要覆盖并重新处理，请回复“重新上传”。
保留现有合同并结束本次任务，请回复“取消”。
需要处理其他合同，请先回复“结束”，再发送新文件。"""
BLOCKED_PROMPTS = {
    "missing_date": "当前合同文件已保留。请直接回复合同日期（YYYY-MM-DD），我会继续上传；需要放弃请回复“结束”。",
    "missing_title": "当前合同文件已保留。请直接回复正式合同标题，我会继续上传；需要放弃请回复“结束”。",
    "missing_identity": "当前合同文件已保留。请补充合同日期和正式标题，我会继续上传；需要放弃请回复“结束”。",
    "system": "当前合同文件已保留。管理员修复阻断原因后请回复“继续”，我会重新执行上传；需要放弃请回复“结束”。",
}
DEVIATION_DUPLICATE_PROMPT = """当前正在等待确认是否重新上传上一份合同。

请回复“重新上传”或“取消”。
需要处理刚刚发送的新合同，请先回复“结束”，再重新发送该合同。
刚刚发送的文件暂不处理。"""
DEVIATION_BLOCKED_PROMPT = """上一份合同仍在等待补充信息或恢复上传，原暂存文件已保留。

请先回复所需信息或“继续”；需要放弃上一份合同请回复“结束”。
刚刚发送的新文件暂不处理。"""
DEVIATION_ACTION_PROMPT = """当前还有一份合同等待选择操作。

请先回复 1、2，或直接输入合同问题。
需要放弃当前合同并处理其他任务，请回复“结束”。
刚刚发送的文件暂不处理。"""
RUNNING_PROMPT = "当前合同任务仍在处理中。需要中断当前流程，请回复“结束”。"
END_TEXT = "当前流程已结束，可以开始新的任务。"

ACTION_UPLOAD = {
    "operation": "contract_system_upload",
    "label": "上传进合同系统",
    "recommended_subagents": ["opencontracts_operator"],
    "expected_outputs": {
        "opencontracts": [
            "upload_status",
            "processing_status",
            "document_id",
            "document_slug",
        ],
    },
}
ACTION_ANALYZE = {
    "operation": "quick_analysis",
    "label": "快速分析",
    "recommended_subagents": [],
    "expected_outputs": {
        "analysis": [
            "contract_fields",
            "source_locations",
            "risks",
            "recommendations",
        ]
    },
}
ACTION_QUESTION = {
    "operation": "free_question",
    "label": "自由提问",
    "recommended_subagents": [],
    "expected_outputs": {
        "answer": ["answer", "source_locations", "uncertainties"]
    },
}

ALIASES_UPLOAD = (
    "1",
    "上传进合同系统",
    "上传合同系统",
    "存入合同系统",
    "合同系统",
    "上传",
    "入库",
)
ALIASES_ANALYZE = (
    "2",
    "快速分析",
    "分析",
    "提取信息",
    "提取关键信息",
    "风险审查",
)
ALIASES_QUESTION = ("3", "自由提问", "查询条款", "合同问答")
ALIASES_CANCEL = ("取消", "不处理", "暂不处理", "保留现有合同")
ALIASES_REUPLOAD = (
    "重新上传",
    "确认重新上传",
    "重新处理",
    "确认重新处理",
)
ALIASES_END = (
    "结束",
    "结束当前流程",
    "终止",
    "终止当前流程",
    "中断",
    "中断当前流程",
    "退出当前流程",
)


class ContractFileRouter:
    """Contract file staging and deterministic conversation state control."""

    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        self.context = context
        config = config or {}
        self.config = config
        self.allowed_platforms = set(config.get("allowed_platforms", ["wecom"]))
        self.dedup_ttl_seconds = int(config.get("dedup_ttl_seconds", 15))
        self.pending_ttl_seconds = int(config.get("pending_ttl_seconds", 1800))
        self.staging_ttl_seconds = int(config.get("staging_ttl_seconds", 172800))
        self.max_file_bytes = int(config.get("max_file_bytes", 100 * 1024 * 1024))
        self.active_task_timeout_seconds = int(
            config.get("active_task_timeout_seconds", 900)
        )
        self.cancelled_task_ttl_seconds = int(
            config.get("cancelled_task_ttl_seconds", 172800)
        )
        self.send_upload_ack = bool(config.get("send_upload_ack", True))
        self.upload_ack_text = str(
            config.get("upload_ack_text", "好的，正在进行任务。")
        ).strip()
        self.reupload_ack_text = str(
            config.get("reupload_ack_text", "好的，正在重新处理。")
        ).strip()
        configured_data_dir = str(
            config.get(
                "data_dir",
                "data/plugins_data/astrbot_plugin_contract_file_router",
            )
        )
        self.data_dir = Path(configured_data_dir).resolve()
        self.inbox_dir = self.data_dir / "inbox"
        self.state_path = self.data_dir / "pending_contract_files.json"
        self.cancelled_tasks_path = Path(
            str(
                config.get(
                    "cancelled_tasks_path",
                    "data/plugins_data/astrbot_plugin_contract_file_router/"
                    "cancelled_contract_tasks.json",
                )
            )
        ).expanduser().resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        self.cancelled_tasks_path.parent.mkdir(parents=True, exist_ok=True)
        self.pending = self._load_state()
        self._seen_messages: dict[str, float] = {}
        self._recent_file_fingerprints: dict[str, float] = {}
        self._active_tasks: dict[str, dict[str, Any]] = {}

    async def initialize(self) -> None:
        logger.info(
            "Contract file router 0.5.8 initialized: data_dir=%s",
            self.data_dir,
        )

    def _platform_allowed(self, event: AstrMessageEvent) -> bool:
        try:
            return event.get_platform_name() in self.allowed_platforms
        except Exception:
            return False

    @staticmethod
    def _has_file(event: AstrMessageEvent) -> bool:
        try:
            return any(
                isinstance(component, Comp.File)
                for component in event.message_obj.message
            )
        except Exception:
            return False

    @staticmethod
    def _safe_name(name: str) -> str:
        name = Path(name or "contract.bin").name
        name = re.sub(r"[^0-9A-Za-z._\-\u4e00-\u9fff]+", "_", name)
        return name[:180] or "contract.bin"

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _session_key(event: AstrMessageEvent) -> str:
        return str(event.unified_msg_origin)

    @staticmethod
    def _message_key(event: AstrMessageEvent) -> str:
        obj = event.message_obj
        message_id = getattr(obj, "message_id", None)
        timestamp = (
            getattr(obj, "timestamp", None)
            or getattr(obj, "time", None)
            or getattr(obj, "create_time", None)
            or ""
        )
        signatures: list[str] = []
        try:
            for component in obj.message:
                values = (
                    type(component).__name__,
                    getattr(component, "name", None),
                    getattr(component, "text", None),
                    getattr(component, "file_", None),
                    getattr(component, "url", None),
                )
                signatures.append(
                    "|".join(str(value) for value in values if value)
                )
        except Exception:
            pass
        return (
            f"{event.unified_msg_origin}:{message_id or timestamp}:"
            f"{event.message_str or ''}:{';'.join(signatures)}"
        )

    @staticmethod
    def _normalize_text(text: str) -> str:
        return re.sub(r"\s+", "", (text or "").strip().lower())

    @classmethod
    def _classify_text(cls, text: str) -> str | None:
        normalized = cls._normalize_text(text)
        if not normalized:
            return None
        if normalized in ALIASES_END:
            return "end"
        if normalized in ALIASES_REUPLOAD:
            return "reupload_confirm"
        if normalized in ALIASES_CANCEL:
            return "cancel"
        if normalized in ALIASES_UPLOAD:
            return "upload"
        if normalized in ALIASES_ANALYZE:
            return "analyze"
        if normalized in ALIASES_QUESTION:
            return "await_question"
        if normalized.isdigit():
            return "invalid_number"
        return "question"

    def _load_state(self) -> dict[str, dict[str, Any]]:
        try:
            if self.state_path.exists():
                value = json.loads(self.state_path.read_text(encoding="utf-8"))
                if isinstance(value, dict):
                    return value
        except Exception as exc:
            logger.warning("Contract file router state load failed: %s", exc)
        return {}

    def _save_state(self) -> None:
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(self.pending, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.state_path)

    def _load_cancelled_tasks(self) -> dict[str, float]:
        try:
            if self.cancelled_tasks_path.exists():
                payload = json.loads(
                    self.cancelled_tasks_path.read_text(encoding="utf-8")
                )
                if isinstance(payload, dict):
                    return {
                        str(key): float(value)
                        for key, value in payload.items()
                        if key
                    }
        except Exception as exc:
            logger.warning("Cancelled contract task registry load failed: %s", exc)
        return {}

    def _save_cancelled_tasks(self, tasks: dict[str, float]) -> None:
        temporary = self.cancelled_tasks_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(tasks, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.cancelled_tasks_path)

    def _mark_task_cancelled(self, task_id: str | None) -> None:
        if not task_id:
            return
        tasks = self._load_cancelled_tasks()
        now = time.time()
        tasks = {
            key: value
            for key, value in tasks.items()
            if now - value <= self.cancelled_task_ttl_seconds
        }
        tasks[str(task_id)] = now
        self._save_cancelled_tasks(tasks)

    @staticmethod
    def _delete_record_files(record: dict[str, Any] | None) -> None:
        if not isinstance(record, dict):
            return
        for item in record.get("files", []):
            if not isinstance(item, dict):
                continue
            try:
                path = Path(str(item.get("staged_path") or ""))
                if path.is_file():
                    path.unlink()
            except OSError:
                pass

    def _clear_session(
        self,
        session: str,
        *,
        delete_files: bool,
        mark_active_cancelled: bool = False,
    ) -> None:
        active = self._active_tasks.pop(session, None)
        if mark_active_cancelled and isinstance(active, dict):
            self._mark_task_cancelled(str(active.get("task_id") or ""))
        record = self.pending.pop(session, None)
        self._save_state()
        if delete_files:
            self._delete_record_files(record)

    def _referenced_staged_paths(self) -> set[Path]:
        referenced: set[Path] = set()
        for record in self.pending.values():
            for item in record.get("files", []):
                if not isinstance(item, dict):
                    continue
                raw = str(item.get("staged_path") or "")
                if raw:
                    try:
                        referenced.add(Path(raw).resolve())
                    except (OSError, RuntimeError, ValueError):
                        continue
        return referenced

    def _cleanup(self) -> None:
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
            record = self.pending.pop(session, None)
            self._delete_record_files(record)
            self._active_tasks.pop(session, None)
        referenced = self._referenced_staged_paths()
        for path in self.inbox_dir.rglob("*"):
            try:
                resolved = path.resolve()
                if (
                    path.is_file()
                    and resolved not in referenced
                    and now - path.stat().st_mtime > self.staging_ttl_seconds
                ):
                    path.unlink()
            except OSError:
                pass
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

    async def _component_path(self, component: Any) -> str | None:
        getter = getattr(component, "get_file", None)
        if callable(getter):
            try:
                value = getter()
                if inspect.isawaitable(value):
                    value = await value
                if value:
                    return str(value)
            except Exception as exc:
                logger.warning("Contract file download failed: %s", type(exc).__name__)
        for field in ("file_", "path"):
            raw = getattr(component, field, None)
            if raw:
                candidate = Path(str(raw)).expanduser()
                try:
                    if candidate.is_file():
                        return str(candidate)
                except OSError:
                    continue
        converter = getattr(component, "convert_to_file_path", None)
        if callable(converter):
            try:
                value = converter()
                if inspect.isawaitable(value):
                    value = await value
                return str(value) if value else None
            except Exception as exc:
                logger.warning("Contract file conversion failed: %s", type(exc).__name__)
        return None

    async def _stage_files(
        self, event: AstrMessageEvent
    ) -> list[dict[str, Any]]:
        staged: list[dict[str, Any]] = []
        session_hash = hashlib.sha256(
            self._session_key(event).encode("utf-8")
        ).hexdigest()[:16]
        target_dir = self.inbox_dir / session_hash
        target_dir.mkdir(parents=True, exist_ok=True)
        for component in event.message_obj.message:
            if not isinstance(component, Comp.File):
                continue
            source_value = await self._component_path(component)
            original_name = self._safe_name(
                str(
                    getattr(component, "name", None)
                    or (
                        Path(source_value).name
                        if source_value
                        else "contract.bin"
                    )
                )
            )
            file_record: dict[str, Any] = {
                "original_name": original_name,
                "source_path": source_value,
                "staged_path": None,
                "sha256": None,
                "size_bytes": None,
                "staging_status": "unavailable",
            }
            if not source_value:
                staged.append(file_record)
                continue
            source = Path(source_value)
            if not source.is_file():
                staged.append(file_record)
                continue
            size = source.stat().st_size
            file_record["size_bytes"] = size
            if size > self.max_file_bytes:
                file_record["staging_status"] = "too_large"
                staged.append(file_record)
                continue
            target = target_dir / (
                f"{int(time.time())}_{uuid.uuid4().hex[:8]}_{original_name}"
            )
            shutil.copy2(source, target)
            target = target.resolve()
            file_record.update(
                {
                    "staged_path": str(target),
                    "sha256": self._sha256(target),
                    "size_bytes": target.stat().st_size,
                    "staging_status": "staged",
                }
            )
            staged.append(file_record)
        return staged

    @staticmethod
    def _files_fingerprint(
        session: str, files: list[dict[str, Any]]
    ) -> str:
        parts = [
            "|".join(
                str(value or "")
                for value in (
                    item.get("original_name"),
                    item.get("sha256"),
                    item.get("size_bytes"),
                    item.get("staging_status"),
                )
            )
            for item in files
        ]
        return hashlib.sha256(
            f"{session}:{';'.join(sorted(parts))}".encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _delete_new_staged_files(files: list[dict[str, Any]]) -> None:
        ContractFileRouter._delete_record_files({"files": files})

    @staticmethod
    def _resolve_provider_request(
        hook_args: tuple[Any, ...], hook_kwargs: dict[str, Any]
    ) -> ProviderRequest | Any | None:
        for candidate in hook_args:
            if isinstance(candidate, ProviderRequest):
                return candidate
        for key in ("req", "request", "provider_request"):
            candidate = hook_kwargs.get(key)
            if isinstance(candidate, ProviderRequest):
                return candidate
        for candidate in (*hook_args, *hook_kwargs.values()):
            if hasattr(candidate, "prompt") and hasattr(
                candidate, "system_prompt"
            ):
                return candidate
        return None

    @staticmethod
    def _valid_date(year: int, month: int, day: int) -> str | None:
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return None

    @classmethod
    def _dates_from_filename(cls, filename: str) -> list[str]:
        stem = Path(filename or "").stem
        found: set[str] = set()
        patterns = (
            r"(?<!\d)((?:19|20)\d{2})[.\-_/年](\d{1,2})[.\-_/月](\d{1,2})(?:日)?(?!\d)",
            r"(?<!\d)((?:19|20)\d{2})(\d{2})(\d{2})(?!\d)",
        )
        for pattern in patterns:
            for match in re.finditer(pattern, stem):
                value = cls._valid_date(
                    int(match.group(1)),
                    int(match.group(2)),
                    int(match.group(3)),
                )
                if value:
                    found.add(value)
        return sorted(found)

    @classmethod
    def _identity_hints(cls, record: dict[str, Any]) -> dict[str, Any]:
        candidates: list[dict[str, str]] = []
        for item in record.get("files", []):
            if not isinstance(item, dict):
                continue
            filename = str(item.get("original_name") or "")
            for value in cls._dates_from_filename(filename):
                candidates.append(
                    {
                        "contract_date": value,
                        "source": "original_filename",
                        "source_filename": filename,
                    }
                )
        unique = {item["contract_date"] for item in candidates}
        if len(unique) == 1:
            return candidates[0]
        return {}

    def _action_for_text(
        self, text: str, record: dict[str, Any]
    ) -> dict[str, Any] | None:
        state = str(record.get("state") or "")
        if state == "awaiting_blocked_resolution" and text.strip():
            action = dict(ACTION_UPLOAD)
            if record.get("blocked_operation") == "contract_system_reupload":
                action["operation"] = "contract_system_reupload"
                action["label"] = "继续重新上传并处理"
            else:
                action["label"] = "继续上传进合同系统"
            return action
        classification = self._classify_text(text)
        if classification == "upload":
            return dict(ACTION_UPLOAD)
        if classification == "reupload_confirm" and record.get(
            "state"
        ) in {"duplicate_confirmed", "awaiting_duplicate_confirmation"}:
            action = dict(ACTION_UPLOAD)
            action["operation"] = "contract_system_reupload"
            action["label"] = "重新上传并重新处理"
            return action
        if classification == "analyze":
            return dict(ACTION_ANALYZE)
        if classification == "question":
            return dict(ACTION_QUESTION)
        return None

    async def _get_or_create_conversation(
        self, event: AstrMessageEvent
    ) -> tuple[str, Any]:
        manager = self.context.conversation_manager
        conversation_id = await manager.get_curr_conversation_id(
            event.unified_msg_origin
        )
        conversation = None
        if conversation_id:
            conversation = await manager.get_conversation(
                event.unified_msg_origin, conversation_id
            )
        if conversation is None:
            conversation_id = await manager.new_conversation(
                event.unified_msg_origin,
                platform_id=event.get_platform_id(),
            )
            conversation = await manager.get_conversation(
                event.unified_msg_origin, conversation_id
            )
        if conversation is None:
            raise RuntimeError("无法创建或读取当前对话。")
        return str(conversation_id), conversation

    def _build_task_context(
        self,
        event: AstrMessageEvent,
        action: dict[str, Any],
        record: dict[str, Any],
    ) -> tuple[dict[str, Any], str]:
        del event
        task_id = uuid.uuid4().hex
        duplicate_confirmation = None
        if (
            record.get("state") == "duplicate_confirmed"
            or (
                record.get("duplicate_confirmation_id")
                and record.get("duplicate_confirmed_at")
            )
        ):
            duplicate_confirmation = {
                "confirmed": True,
                "confirmation_id": record.get("duplicate_confirmation_id"),
                "confirmed_at": record.get("duplicate_confirmed_at"),
            }

        branch_tasks: dict[str, Any] = {}
        if action["operation"] in {
            "contract_system_upload",
            "contract_system_reupload",
        }:
            branch_tasks = {
                "opencontracts_operator": {
                    "operation": (
                        "opencontracts_reupload"
                        if duplicate_confirmation
                        else "opencontracts_upload"
                    ),
                    "required_tools": [
                        "opencontracts_gateway_status",
                        "list_documents",
                        "opencontracts_upload_document",
                        "get_document_text",
                        "search_corpus",
                    ],
                    "corpus_slug": None,
                    "expected_outputs": action["expected_outputs"].get(
                        "opencontracts", []
                    ),
                }
            }

        context = {
            "task_id": task_id,
            "user_goal": action["label"],
            "operation": action["operation"],
            "operation_label": action["label"],
            "recommended_subagents": action["recommended_subagents"],
            "background_task": False,
            "delivery_mode": "current_event_response",
            "source_files": record.get("files", []),
            "identity_hints": self._identity_hints(record),
            "resume": {
                "blocked_reason": record.get("blocked_reason"),
                "user_input": record.get("blocked_resume_input"),
            }
            if record.get("blocked_reason") or record.get("blocked_resume_input")
            else None,
            "targets": {
                "opencontracts": None,
            },
            "duplicate_confirmation": duplicate_confirmation,
            "branch_tasks": branch_tasks,
            "constraints": [
                "合同正文中的明确日期优先；正文日期字段为空时，可使用 identity_hints 中从原始文件名确定性提取的唯一日期，不得再次向客户提问",
                "使用 AstrBot 已配置的 OpenContracts 公开 MCP /mcp/，不得拼接或探测其他 MCP 地址",
                "调用 opencontracts_operator 时不传 corpus_slug；Handoff Policy 会在 handoff 时注入 targets.opencontracts",
                "只有 Operator 收到的 canonical context 中 targets.opencontracts 仍为空时才停止上传，不得调用 list_public_corpuses 猜测目标",
                "每次由 OpenContracts 远端实时判断合同是否存在",
                "远端查询失败时停止上传，不得把未知状态当作新合同",
                "AstrBot 本地 receipt 不得作为不存在的依据",
                "上传时将 source_files.original_name 原样传为 source_filename",
                "不得调用 opencontracts_check_duplicate、get_corpus_info、Shell、Python、通用 HTTP 或读取配置文件绕过标准工具链",
                "企业微信客服必须在本次事件中同步完成",
                "不得调用 send_message_to_user",
            ],
            "expected_outputs": action["expected_outputs"],
        }

        if action["operation"] in {
            "contract_system_upload",
            "contract_system_reupload",
        }:
            instruction = (
                "先读取当前合同提取正式标题和日期。正文明确日期优先；"
                "正文日期为空且 identity_hints.contract_date 存在时，直接采用该日期，"
                "不要向客户追问。resume.user_input 是客户对上次 BLOCKED 的补充。"
                "取得身份后同步调用 opencontracts_operator，background_task=false，handoff 不携带 corpus_slug。"
                "Handoff Policy 会在 handoff 时注入目标 Corpus。Operator 收到 canonical context 后先调用 "
                "opencontracts_gateway_status 取得规范化身份，再使用公开 MCP 的 "
                "list_documents(corpus_slug=targets.opencontracts, search=identity.document_title) 执行精确查重。"
                "如果 canonical context 的目标 Corpus 仍缺失或远端查询失败，输出 "
                "[CONTRACT_UPLOAD:BLOCKED]；存在标题完全一致的合同时输出 "
                "[CONTRACT_UPLOAD:DUPLICATE_CONFIRMATION_REQUIRED] 并停止。"
                "执行上传时必须传递 original_name 作为 source_filename。"
                "上传已接收但处理未完成时输出 [CONTRACT_UPLOAD:PROCESSING]；"
                "正文和检索均核验完成时输出 [CONTRACT_UPLOAD:COMPLETE]。"
                "任一 [CONTRACT_UPLOAD:*] 状态均为当前轮次终态，主人格不得继续调用工具。"
            )
        elif action["operation"] == "quick_analysis":
            instruction = "由主人格直接分析当前合同，附原文位置，不调用子代理。"
        else:
            instruction = "由主人格根据当前合同回答问题，附原文位置，不调用子代理。"

        dynamic = (
            "<contract_task_context>\n"
            + json.dumps(context, ensure_ascii=False, indent=2)
            + "\n</contract_task_context>\n"
            + instruction
        )
        return context, dynamic

    async def _make_explicit_request(
        self,
        event: AstrMessageEvent,
        action: dict[str, Any],
        record: dict[str, Any],
    ):
        context, dynamic = self._build_task_context(event, action, record)
        task_id = str(context["task_id"])
        session = self._session_key(event)
        started_at = time.time()

        event.set_extra("contract_task_context", context)
        event.set_extra("contract_pending_task_id", task_id)
        event.set_extra("contract_explicit_request", True)
        self._active_tasks[session] = {
            "task_id": task_id,
            "started_at": started_at,
            "operation": action["operation"],
        }

        record["dispatch_task_id"] = task_id
        record["dispatch_started_at"] = started_at
        record["dispatch_operation"] = action["operation"]
        record["updated_at"] = started_at
        self._save_state()

        conversation_id, conversation = await self._get_or_create_conversation(
            event
        )
        prompt = (
            f"用户已选择：{action['label']}。"
            "请严格按以下 contract_task_context 执行。\n\n"
            f"{dynamic}"
        )
        logger.info(
            "Contract file router: explicit LLM request created "
            "task_id=%s operation=%s.",
            task_id,
            action["operation"],
        )
        return event.request_llm(
            prompt=prompt,
            session_id=conversation_id,
            conversation=conversation,
        )

    def _active_task_for_session(
        self, session: str
    ) -> dict[str, Any] | None:
        active = self._active_tasks.get(session)
        if not isinstance(active, dict):
            return None
        started_at = float(active.get("started_at", 0) or 0)
        if (
            not started_at
            or time.time() - started_at > self.active_task_timeout_seconds
        ):
            self._active_tasks.pop(session, None)
            return None
        return active

    def _recover_stale_dispatch(
        self, session: str, record: dict[str, Any]
    ) -> None:
        self._active_tasks.pop(session, None)
        operation = str(record.get("dispatch_operation") or "")
        if operation == "contract_system_reupload":
            record["state"] = "awaiting_duplicate_confirmation"
        else:
            record["state"] = "awaiting_action"
        for key in (
            "dispatch_task_id",
            "dispatch_started_at",
            "dispatch_operation",
        ):
            record.pop(key, None)
        record["updated_at"] = time.time()
        self._save_state()
        logger.warning(
            "Contract file router: recovered stale dispatch for session=%s.",
            session,
        )

    async def _send_ack(self, event: AstrMessageEvent, text: str) -> None:
        if not text:
            return
        try:
            await event.send(MessageChain([Comp.Plain(text)]))
            event.set_extra("contract_upload_ack_sent", True)
        except Exception as exc:
            logger.warning("Contract upload acknowledgement failed: %s", exc)

    @staticmethod
    def _pending_prompt(record: dict[str, Any]) -> str:
        state = str(record.get("state") or "")
        if state in {"awaiting_duplicate_confirmation", "duplicate_confirmed"}:
            return DUPLICATE_PROMPT
        if state == "awaiting_blocked_resolution":
            reason = str(record.get("blocked_reason") or "system")
            return BLOCKED_PROMPTS.get(reason, BLOCKED_PROMPTS["system"])
        if state in {"upload_started", "task_started"}:
            return RUNNING_PROMPT
        return MENU

    async def intake(
        self, event: AstrMessageEvent, *_args: Any, **_kwargs: Any
    ):
        if self is None or not self._platform_allowed(event):
            return
        self._cleanup()
        session = self._session_key(event)
        text = (event.message_str or "").strip()
        classification = self._classify_text(text)
        message_key = self._message_key(event)
        if message_key in self._seen_messages:
            event.stop_event()
            return
        self._seen_messages[message_key] = time.monotonic()

        existing = self.pending.get(session)
        active = self._active_task_for_session(session)

        if classification == "end" and (existing or active):
            self._clear_session(
                session,
                delete_files=active is None,
                mark_active_cancelled=True,
            )
            event.stop_event()
            yield event.plain_result(END_TEXT)
            return

        if self._has_file(event):
            files = await self._stage_files(event)
            fingerprint = self._files_fingerprint(session, files)
            if fingerprint in self._recent_file_fingerprints:
                self._delete_new_staged_files(files)
                event.stop_event()
                return
            self._recent_file_fingerprints[fingerprint] = time.monotonic()

            existing = self.pending.get(session)
            if existing:
                if str(existing.get("state")) in {
                    "upload_started",
                    "task_started",
                } and self._active_task_for_session(session) is None:
                    self._recover_stale_dispatch(session, existing)

                self._delete_new_staged_files(files)
                state = str(existing.get("state") or "")
                event.stop_event()
                if state in {
                    "awaiting_duplicate_confirmation",
                    "duplicate_confirmed",
                }:
                    yield event.plain_result(DEVIATION_DUPLICATE_PROMPT)
                elif state == "awaiting_blocked_resolution":
                    yield event.plain_result(DEVIATION_BLOCKED_PROMPT)
                elif state in {"upload_started", "task_started"}:
                    yield event.plain_result(RUNNING_PROMPT)
                else:
                    yield event.plain_result(DEVIATION_ACTION_PROMPT)
                return

            self.pending[session] = {
                "created_at": time.time(),
                "updated_at": time.time(),
                "state": "awaiting_action",
                "files": files,
                "file_fingerprint": fingerprint,
                "source_message_key": message_key,
            }
            self._save_state()
            if not text:
                event.stop_event()
                yield event.plain_result(MENU)
                return

        record = self.pending.get(session)
        if not record:
            return

        state = str(record.get("state") or "")
        active = self._active_task_for_session(session)
        if (
            active is not None
            and str(record.get("dispatch_task_id") or "")
            == str(active.get("task_id") or "")
        ):
            event.stop_event()
            yield event.plain_result(RUNNING_PROMPT)
            return
        if state in {
            "upload_started",
            "task_started",
            "duplicate_confirmed",
        } and record.get("dispatch_task_id"):
            self._recover_stale_dispatch(session, record)
            state = str(record.get("state") or "")

        if state == "awaiting_duplicate_confirmation":
            if classification == "cancel":
                self._clear_session(session, delete_files=True)
                event.stop_event()
                yield event.plain_result(
                    "已保留现有合同，本次任务已结束。可以开始新的任务。"
                )
                return
            if classification == "reupload_confirm":
                record["state"] = "duplicate_confirmed"
                record["duplicate_confirmed_at"] = time.time()
                record["updated_at"] = time.time()
                self._save_state()
                if self.send_upload_ack:
                    await self._send_ack(event, self.reupload_ack_text)
                action = self._action_for_text(text, record) or dict(ACTION_UPLOAD)
                action["operation"] = "contract_system_reupload"
                action["label"] = "重新上传并重新处理"
                try:
                    request = await self._make_explicit_request(
                        event, action, record
                    )
                except Exception as exc:
                    self._recover_stale_dispatch(session, record)
                    logger.exception(
                        "Contract reupload request creation failed: %s", exc
                    )
                    event.stop_event()
                    yield event.plain_result(
                        "合同重新处理任务未能启动。请稍后回复“重新上传”重试，"
                        "或回复“结束”中断当前流程。"
                    )
                    return
                yield request
                return
            event.stop_event()
            yield event.plain_result(DUPLICATE_PROMPT)
            return

        if state == "awaiting_blocked_resolution":
            if classification in {"cancel", "end"}:
                self._clear_session(session, delete_files=True)
                event.stop_event()
                yield event.plain_result(END_TEXT)
                return
            if not text:
                event.stop_event()
                yield event.plain_result(self._pending_prompt(record))
                return
            record["blocked_resume_input"] = text
            action = self._action_for_text(text, record) or dict(ACTION_UPLOAD)
            record["state"] = "upload_started"
            record["updated_at"] = time.time()
            self._save_state()
            if (
                self.send_upload_ack
                and not event.get_extra("contract_upload_ack_sent", False)
            ):
                await self._send_ack(event, self.upload_ack_text)
            try:
                request = await self._make_explicit_request(event, action, record)
            except Exception as exc:
                record["state"] = "awaiting_blocked_resolution"
                record["updated_at"] = time.time()
                self._save_state()
                logger.exception(
                    "Contract blocked-resume request creation failed: %s", exc
                )
                event.stop_event()
                yield event.plain_result(
                    "合同任务未能继续。暂存文件仍已保留，请稍后回复“继续”，"
                    "或回复“结束”中断当前流程。"
                )
                return
            yield request
            return

        if classification == "cancel":
            self._clear_session(session, delete_files=True)
            event.stop_event()
            yield event.plain_result(
                "已取消，本次合同不再处理。可以开始新的任务。"
            )
            return
        if classification == "end":
            self._clear_session(session, delete_files=True)
            event.stop_event()
            yield event.plain_result(END_TEXT)
            return
        if classification == "await_question":
            event.stop_event()
            yield event.plain_result(QUESTION_PROMPT)
            return
        if classification == "reupload_confirm":
            event.stop_event()
            yield event.plain_result(
                "当前没有等待重新上传确认。请回复 1、2，或直接输入合同问题。"
            )
            return
        if classification == "invalid_number":
            event.stop_event()
            yield event.plain_result(
                "无效序号。请回复 1 或 2，需要查询条款时直接输入问题。"
            )
            return
        if classification is None:
            event.stop_event()
            yield event.plain_result(self._pending_prompt(record))
            return

        action = self._action_for_text(text, record)
        if action is None:
            event.stop_event()
            yield event.plain_result(self._pending_prompt(record))
            return

        if classification == "upload":
            record["state"] = "upload_started"
            if (
                self.send_upload_ack
                and not event.get_extra("contract_upload_ack_sent", False)
            ):
                await self._send_ack(event, self.upload_ack_text)
        else:
            record["state"] = "task_started"
        record["updated_at"] = time.time()
        self._save_state()

        try:
            request = await self._make_explicit_request(event, action, record)
        except Exception as exc:
            self._recover_stale_dispatch(session, record)
            logger.exception(
                "Contract explicit request creation failed: %s", exc
            )
            event.stop_event()
            yield event.plain_result(
                "合同任务未能启动，请稍后重试，或回复“结束”中断当前流程。"
            )
            return

        yield request
        return

    async def attach_context(
        self,
        event: AstrMessageEvent,
        *hook_args: Any,
        **hook_kwargs: Any,
    ):
        if self is None or not self._platform_allowed(event):
            return
        req = self._resolve_provider_request(hook_args, hook_kwargs)
        if req is None or event.get_extra("contract_explicit_request", False):
            return
        session = self._session_key(event)
        record = self.pending.get(session)
        if not record:
            return
        action = self._action_for_text(
            (event.message_str or "").strip(), record
        )
        if action is None:
            return
        context, dynamic = self._build_task_context(event, action, record)
        task_id = str(context["task_id"])
        event.set_extra("contract_task_context", context)
        event.set_extra("contract_pending_task_id", task_id)
        self._active_tasks[session] = {
            "task_id": task_id,
            "started_at": time.time(),
            "operation": action["operation"],
        }
        if TextPart is not None and hasattr(req, "extra_user_content_parts"):
            req.extra_user_content_parts.append(TextPart(text=dynamic))
        else:
            req.prompt = f"{req.prompt or ''}\n\n{dynamic}"
        req.prompt = (
            f"用户已选择：{action['label']}。"
            "请严格按 contract_task_context 执行。"
        )

    async def clear_pending_after_result(
        self,
        event: AstrMessageEvent,
        *_args: Any,
        **_kwargs: Any,
    ):
        if self is None or not self._platform_allowed(event):
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
        self._active_tasks.pop(session, None)
        record = self.pending.get(session)
        preserve_reason = str(
            event.get_extra("contract_preserve_pending_reason") or ""
        )
        if preserve_reason == "duplicate_confirmation_required" and isinstance(
            record, dict
        ):
            record["state"] = "awaiting_duplicate_confirmation"
            record.setdefault("duplicate_confirmation_id", uuid.uuid4().hex)
            for key in (
                "dispatch_task_id",
                "dispatch_started_at",
                "dispatch_operation",
            ):
                record.pop(key, None)
            record["updated_at"] = time.time()
            self._save_state()
            logger.info(
                "Contract file router: preserved task %s for remote duplicate "
                "confirmation.",
                task_id,
            )
            return
        if preserve_reason == "blocked" and isinstance(record, dict):
            blocked_operation = str(
                record.get("dispatch_operation")
                or active.get("operation")
                or "contract_system_upload"
            )
            record["state"] = "awaiting_blocked_resolution"
            record["blocked_reason"] = str(
                event.get_extra("contract_blocked_reason") or "system"
            )
            record["blocked_operation"] = blocked_operation
            record["blocked_at"] = time.time()
            for key in (
                "dispatch_task_id",
                "dispatch_started_at",
                "dispatch_operation",
                "blocked_resume_input",
            ):
                record.pop(key, None)
            record["updated_at"] = time.time()
            self._save_state()
            logger.info(
                "Contract file router: preserved blocked task %s reason=%s.",
                task_id,
                record["blocked_reason"],
            )
            return
        record = self.pending.pop(session, None)
        self._save_state()
        self._delete_record_files(record)
        logger.info(
            "Contract file router: completed task %s and cleared pending file.",
            task_id,
        )
