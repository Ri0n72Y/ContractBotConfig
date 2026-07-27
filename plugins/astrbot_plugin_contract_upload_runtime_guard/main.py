from __future__ import annotations

import json
import re
import zipfile
from datetime import date
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star

try:
    from astrbot.core.agent.message import TextPart
except Exception:
    TextPart = None

UPLOAD_OPERATIONS = {
    "contract_system_upload",
    "contract_system_reupload",
    "opencontracts_upload",
    "opencontracts_reupload",
}
HANDOFF_TOOL = "transfer_to_opencontracts_operator"
PUBLIC_MCP_TOOLS = [
    "list_public_corpuses",
    "list_documents",
    "opencontracts_gateway_status",
    "opencontracts_upload_document",
    "get_document_text",
    "search_corpus",
]
MAX_TEXT_CHARS = 180_000

DATE_PATTERNS = (
    re.compile(
        r"(?P<y>20\d{2})\s*[年./-]\s*(?P<m>0?[1-9]|1[0-2])"
        r"\s*[月./-]\s*(?P<d>0?[1-9]|[12]\d|3[01])\s*日?"
    ),
    re.compile(
        r"(?P<y>20\d{2})(?P<m>0[1-9]|1[0-2])"
        r"(?P<d>0[1-9]|[12]\d|3[01])"
    ),
)
DATE_LABELS = ("签订日期", "签订时间", "签署日期", "签署时间", "合同日期")
FALLBACK_DATE_LABELS = ("生效日期", "生效时间")
TITLE_SUFFIXES = ("合同", "合同书", "协议", "协议书", "承诺书", "确认书", "备忘录")
TITLE_EXCLUDES = (
    "合同编号",
    "目录",
    "附件",
    "补充条款",
    "工程概况",
    "签订日期",
    "签订时间",
)


def _clean_line(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(r"^[#*`>|\-–—\s]+", "", text).strip()
    return re.sub(r"[（(]?以下简称.*$", "", text).strip()


def _docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        raw = archive.read("word/document.xml")
    root = ElementTree.fromstring(raw)
    lines: list[str] = []
    size = 0
    for paragraph in root.iter():
        if not paragraph.tag.endswith("}p"):
            continue
        line = _clean_line(
            "".join(
                node.text or ""
                for node in paragraph.iter()
                if node.tag.endswith("}t")
            )
        )
        if line:
            lines.append(line)
            size += len(line)
        if size >= MAX_TEXT_CHARS:
            break
    return "\n".join(lines)


def _pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "当前环境缺少 pypdf，无法在不输出原文的条件下提取 PDF 合同身份。"
        ) from exc
    reader = PdfReader(str(path))
    parts: list[str] = []
    size = 0
    for page in reader.pages[:4]:
        text = page.extract_text() or ""
        parts.append(text)
        size += len(text)
        if size >= MAX_TEXT_CHARS:
            break
    return "\n".join(parts)


def _read_private_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return _docx_text(path)
    if suffix == ".pdf":
        return _pdf_text(path)
    if suffix in {".txt", ".md", ".markdown"}:
        return path.read_text(encoding="utf-8", errors="ignore")[:MAX_TEXT_CHARS]
    raise RuntimeError(f"暂不支持安全提取 {suffix or '无扩展名'} 合同身份。")


def _normalized_date(match: re.Match[str]) -> str | None:
    try:
        return date(
            int(match.group("y")),
            int(match.group("m")),
            int(match.group("d")),
        ).isoformat()
    except ValueError:
        return None


def _extract_identity(staged_path: str) -> dict[str, Any]:
    path = Path(staged_path).expanduser().resolve()
    if not path.is_file():
        return {"ok": False, "error": "合同暂存文件不存在。"}
    try:
        lines = [
            _clean_line(line)
            for line in _read_private_text(path).splitlines()
        ]
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    lines = [line for line in lines if line]
    if not lines:
        return {"ok": False, "error": "未能从合同文件提取可解析文本。"}

    dates: list[tuple[int, str]] = []
    for index, line in enumerate(lines[:240]):
        label_score = 0
        if any(label in line for label in DATE_LABELS):
            label_score = 100
        elif any(label in line for label in FALLBACK_DATE_LABELS):
            label_score = 50
        for pattern in DATE_PATTERNS:
            for match in pattern.finditer(line):
                normalized = _normalized_date(match)
                if normalized:
                    dates.append((label_score - index, normalized))

    titles: list[tuple[int, str]] = []
    for index, line in enumerate(lines[:80]):
        if len(line) < 4 or len(line) > 120:
            continue
        if any(value in line for value in TITLE_EXCLUDES):
            continue
        score = 100 - index
        if any(line.endswith(suffix) for suffix in TITLE_SUFFIXES):
            score += 120
        elif "合同" in line or "协议" in line:
            score += 70
        else:
            continue
        if "甲方" in line or "乙方" in line:
            score -= 80
        titles.append((score, line))

    if not dates or not titles:
        missing = []
        if not dates:
            missing.append("合同日期")
        if not titles:
            missing.append("合同标题")
        return {"ok": False, "error": "无法可靠提取" + "、".join(missing) + "。"}

    best_date = max(dates)
    best_title = max(titles)
    return {
        "ok": True,
        "contract_date": best_date[1],
        "contract_title": best_title[1],
        "confidence": "high" if best_date[0] >= 50 and best_title[0] >= 150 else "medium",
        "extractor": "local_private_identity_v1",
    }


class ContractUploadRuntimeGuard(Star):
    """Prevent contract plaintext logging and resolve public MCP corpus safely."""

    def __init__(self, context: Context):
        super().__init__(context)

    async def initialize(self) -> None:
        logger.info("Contract upload runtime guard 0.1.0 initialized.")

    @staticmethod
    def _resolve_request(
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
            if hasattr(candidate, "prompt") and hasattr(candidate, "system_prompt"):
                return candidate
        return None

    @staticmethod
    def _tool_names(tool_set: Any) -> list[str]:
        if tool_set is None:
            return []
        names = getattr(tool_set, "names", None)
        if callable(names):
            try:
                return [str(value) for value in names()]
            except Exception:
                pass
        return [
            str(getattr(tool, "name", ""))
            for tool in getattr(tool_set, "tools", [])
        ]

    @staticmethod
    def _retain_tools(tool_set: Any, allowed: set[str]) -> int:
        if tool_set is None:
            return 0
        names = ContractUploadRuntimeGuard._tool_names(tool_set)
        remover = getattr(tool_set, "remove_tool", None)
        removed = 0
        if callable(remover):
            for name in names:
                if name and name not in allowed:
                    remover(name)
                    removed += 1
            return removed
        tools = getattr(tool_set, "tools", None)
        if isinstance(tools, list):
            kept = []
            for tool in tools:
                if str(getattr(tool, "name", "")) in allowed:
                    kept.append(tool)
                else:
                    removed += 1
            tool_set.tools = kept
        return removed

    @staticmethod
    def _append_preflight(req: Any, payload: dict[str, Any]) -> None:
        block = (
            "<contract_private_preflight>\n"
            + json.dumps(payload, ensure_ascii=False, indent=2)
            + "\n</contract_private_preflight>\n"
            "该身份由插件在内存中提取。不得读取合同文件，直接按预检结果执行。"
        )
        if TextPart is not None and hasattr(req, "extra_user_content_parts"):
            req.extra_user_content_parts.append(TextPart(text=block))
        else:
            req.prompt = f"{req.prompt or ''}\n\n{block}"

    @filter.on_llm_request(priority=-1000)
    async def protect_master_upload(
        self,
        event: AstrMessageEvent,
        *hook_args: Any,
        **hook_kwargs: Any,
    ):
        context = event.get_extra("contract_task_context")
        if not isinstance(context, dict):
            return
        if str(context.get("operation") or "") not in UPLOAD_OPERATIONS:
            return
        req = self._resolve_request(hook_args, hook_kwargs)
        if req is None:
            return
        tool_set = getattr(req, "func_tool", None)
        if HANDOFF_TOOL not in self._tool_names(tool_set):
            return

        identity = context.get("contract_identity")
        result: dict[str, Any]
        if isinstance(identity, dict) and identity.get("contract_date") and identity.get("contract_title"):
            result = {"ok": True, **identity}
        else:
            source_files = context.get("source_files")
            source = source_files[0] if isinstance(source_files, list) and source_files else {}
            result = _extract_identity(str(source.get("staged_path") or ""))

        if result.get("ok"):
            identity = {
                "contract_date": result["contract_date"],
                "contract_title": result["contract_title"],
                "confidence": result.get("confidence"),
                "extractor": result.get("extractor"),
            }
            context["contract_identity"] = identity
            context.pop("contract_identity_error", None)
            allowed = {HANDOFF_TOOL}
            payload = {
                "status": "ready",
                "contract_identity": identity,
                "next_action": "call_transfer_to_opencontracts_operator_once",
            }
        else:
            error = str(result.get("error") or "合同身份提取失败。")
            context["contract_identity_error"] = error
            allowed = set()
            payload = {
                "status": "blocked",
                "error": error,
                "required_output": "[CONTRACT_UPLOAD:BLOCKED]",
            }
        event.set_extra("contract_task_context", context)
        removed = self._retain_tools(tool_set, allowed)
        self._append_preflight(req, payload)
        logger.info(
            "Contract upload privacy preflight: task_id=%s status=%s removed_tools=%d",
            context.get("task_id"),
            payload["status"],
            removed,
        )

    @filter.on_using_llm_tool(priority=900)
    async def add_public_corpus_resolution(
        self,
        event: AstrMessageEvent,
        *hook_args: Any,
        **hook_kwargs: Any,
    ):
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
        if str(getattr(tool, "name", "")) != HANDOFF_TOOL or not isinstance(tool_args, dict):
            return
        try:
            canonical = json.loads(str(tool_args.get("input") or "{}"))
        except (TypeError, ValueError):
            return
        if not isinstance(canonical, dict):
            return

        required = [
            name
            for name in canonical.get("required_tools", [])
            if str(name).strip()
        ]
        canonical["required_tools"] = list(dict.fromkeys([*PUBLIC_MCP_TOOLS, *required]))
        configured = str(
            (canonical.get("targets") or {}).get("opencontracts") or ""
        ).strip()
        canonical["mcp_contract"] = {
            "endpoint": "/mcp/",
            "configured_corpus_slug": configured or None,
            "resolver_tool": "list_public_corpuses",
            "resolution_rules": [
                "use exact configured slug when present",
                "if configured slug is absent or invalid and exactly one public corpus exists, use that sole corpus",
                "if resolution is still ambiguous, block without upload",
            ],
            "resolved_slug_usage": [
                "list_documents",
                "get_document_text",
                "search_corpus",
            ],
        }
        constraints = [
            str(value)
            for value in canonical.get("constraints", [])
            if "不得调用 list_public_corpuses" not in str(value)
            and "必须使用 targets.opencontracts" not in str(value)
        ]
        constraints.extend(
            [
                "先调用 list_public_corpuses，按 mcp_contract.resolution_rules 确定唯一目标 Corpus",
                "不得尝试常见 slug、不得拼接其他 MCP 地址",
                "解析后的 slug 必须用于 list_documents、get_document_text 和 search_corpus",
                "合同原文不得出现在工具返回、模型回复或日志中",
            ]
        )
        canonical["constraints"] = list(dict.fromkeys(constraints))
        branch = canonical.get("branch_task")
        if isinstance(branch, dict):
            branch["required_tools"] = canonical["required_tools"]
            branch["configured_corpus_slug"] = configured or None
            branch.pop("corpus_slug", None)
        canonical["contract_identity"] = event.get_extra(
            "contract_task_context", {}
        ).get("contract_identity", canonical.get("contract_identity"))
        tool_args["input"] = json.dumps(canonical, ensure_ascii=False, indent=2)
