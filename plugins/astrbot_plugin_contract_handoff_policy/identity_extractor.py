from __future__ import annotations

import re
import zipfile
from datetime import date
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

MAX_TEXT_CHARS = 180_000
MAX_SCAN_LINES = 240

_DATE_PATTERNS = (
    re.compile(r"(?P<y>20\d{2})\s*[年./-]\s*(?P<m>0?[1-9]|1[0-2])\s*[月./-]\s*(?P<d>0?[1-9]|[12]\d|3[01])\s*日?"),
    re.compile(r"(?P<y>20\d{2})(?P<m>0[1-9]|1[0-2])(?P<d>0[1-9]|[12]\d|3[01])"),
)
_DATE_LABELS = ("签订日期", "签订时间", "签署日期", "签署时间", "合同日期")
_FALLBACK_DATE_LABELS = ("生效日期", "生效时间")
_TITLE_SUFFIXES = (
    "合同",
    "合同书",
    "协议",
    "协议书",
    "承诺书",
    "确认书",
    "备忘录",
)
_TITLE_EXCLUDES = (
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
    text = re.sub(r"[（(]?以下简称.*$", "", text).strip()
    return text


def _docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        raw = archive.read("word/document.xml")
    root = ElementTree.fromstring(raw)
    lines: list[str] = []
    for paragraph in root.iter():
        if not paragraph.tag.endswith("}p"):
            continue
        values = [
            node.text or ""
            for node in paragraph.iter()
            if node.tag.endswith("}t")
        ]
        line = _clean_line("".join(values))
        if line:
            lines.append(line)
        if sum(len(item) for item in lines) >= MAX_TEXT_CHARS:
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
    for page in reader.pages[:4]:
        parts.append(page.extract_text() or "")
        if sum(len(item) for item in parts) >= MAX_TEXT_CHARS:
            break
    return "\n".join(parts)


def _read_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return _docx_text(path)
    if suffix == ".pdf":
        return _pdf_text(path)
    if suffix in {".txt", ".md", ".markdown"}:
        return path.read_text(encoding="utf-8", errors="ignore")[:MAX_TEXT_CHARS]
    raise RuntimeError(
        f"暂不支持从 {suffix or '无扩展名'} 文件安全提取合同身份。"
    )


def _normalize_date(match: re.Match[str]) -> str | None:
    try:
        value = date(
            int(match.group("y")),
            int(match.group("m")),
            int(match.group("d")),
        )
    except ValueError:
        return None
    return value.isoformat()


def _find_dates(lines: list[str]) -> list[tuple[int, int, str]]:
    candidates: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines[:MAX_SCAN_LINES]):
        label_score = 0
        if any(label in line for label in _DATE_LABELS):
            label_score = 100
        elif any(label in line for label in _FALLBACK_DATE_LABELS):
            label_score = 50
        for pattern in _DATE_PATTERNS:
            for match in pattern.finditer(line):
                normalized = _normalize_date(match)
                if normalized:
                    candidates.append((label_score - index, index, normalized))
    return candidates


def _title_score(line: str, index: int) -> int:
    if not line or len(line) < 4 or len(line) > 120:
        return -10_000
    if any(value in line for value in _TITLE_EXCLUDES):
        return -10_000
    if re.fullmatch(r"[\d\s._-]+", line):
        return -10_000
    score = 100 - index
    if any(line.endswith(suffix) for suffix in _TITLE_SUFFIXES):
        score += 120
    elif "合同" in line or "协议" in line:
        score += 70
    else:
        return -10_000
    if "项目" in line:
        score += 8
    if "甲方" in line or "乙方" in line:
        score -= 80
    return score


def extract_contract_identity(
    staged_path: str,
    original_name: str = "",
) -> dict[str, Any]:
    path = Path(str(staged_path or "")).expanduser().resolve()
    if not path.is_file():
        return {
            "ok": False,
            "error": "合同暂存文件不存在。",
            "extractor": "local_private_identity_v1",
        }
    try:
        text = _read_text(path)
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "extractor": "local_private_identity_v1",
        }

    lines = [_clean_line(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return {
            "ok": False,
            "error": "未能从合同文件提取可解析文本。",
            "extractor": "local_private_identity_v1",
        }

    dates = _find_dates(lines)
    contract_date = max(dates, default=None)
    title_candidates = [
        (_title_score(line, index), index, line)
        for index, line in enumerate(lines[:80])
    ]
    title = max(title_candidates, default=None)

    if contract_date is None or title is None or title[0] < 0:
        missing: list[str] = []
        if contract_date is None:
            missing.append("合同日期")
        if title is None or title[0] < 0:
            missing.append("合同标题")
        return {
            "ok": False,
            "error": "无法可靠提取" + "、".join(missing) + "。",
            "extractor": "local_private_identity_v1",
        }

    return {
        "ok": True,
        "contract_date": contract_date[2],
        "contract_title": title[2],
        "confidence": (
            "high"
            if contract_date[0] >= 50 and title[0] >= 150
            else "medium"
        ),
        "extractor": "local_private_identity_v1",
        "source_filename": Path(original_name or path.name).name,
    }
