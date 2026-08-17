from __future__ import annotations

import asyncio
import io
from pathlib import Path
from typing import Any

from markitdown_no_magika import MarkItDown, StreamInfo
from pypdf import PdfReader


MAX_STAGED_TEXT_CHARS = 120_000
_TEXT_SUFFIXES = {".txt", ".md", ".markdown"}


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "utf-16"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _parse_pdf_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    parts: list[str] = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            parts.append(text)
    return "\n\n".join(parts).strip()


def _parse_docx_text(data: bytes, file_name: str) -> str:
    converter = MarkItDown(enable_plugins=False)
    stream_info = StreamInfo(extension=".docx", filename=file_name)
    result = converter.convert(io.BytesIO(data), stream_info=stream_info)
    return str(result.markdown or "").strip()


async def _parse_document(path: Path, original_name: str) -> str:
    data = await asyncio.to_thread(path.read_bytes)
    suffix = path.suffix.lower() or Path(original_name).suffix.lower()
    file_name = original_name or path.name

    if suffix == ".pdf":
        return await asyncio.to_thread(_parse_pdf_text, data)
    if suffix == ".docx":
        return await asyncio.to_thread(_parse_docx_text, data, file_name)
    if suffix in _TEXT_SUFFIXES:
        return _decode_text(data).strip()

    raise ValueError(f"暂不支持读取 {suffix or '未知格式'} 合同正文")


async def extract_staged_contract_text(
    files: list[dict[str, Any]],
    *,
    max_chars: int = MAX_STAGED_TEXT_CHARS,
) -> dict[str, Any]:
    """Parse Router-owned staged contract files for the current LLM request.

    The returned text is an in-memory snapshot. No model tool call and no
    persistent extracted-text sidecar are created.
    """

    remaining = max(1, int(max_chars))
    sections: list[str] = []
    parsed_files: list[str] = []
    errors: list[str] = []
    truncated = False

    for item in files:
        if not isinstance(item, dict):
            continue
        original_name = str(item.get("original_name") or "contract").strip() or "contract"
        staged_path = str(item.get("staged_path") or "").strip()
        if not staged_path or str(item.get("staging_status") or "") != "staged":
            errors.append(f"{original_name}: 暂存文件不可用")
            continue

        path = Path(staged_path)
        try:
            if not path.is_file():
                raise FileNotFoundError("暂存文件不存在")
            text = await _parse_document(path, original_name)
        except Exception as exc:  # noqa: BLE001 - convert parser failures into task context
            errors.append(f"{original_name}: {exc}")
            continue

        if not text:
            errors.append(f"{original_name}: 未解析到正文")
            continue

        header = f"[文件：{original_name}]\n"
        available = max(remaining - len(header), 0)
        if available <= 0:
            truncated = True
            break
        selected = text[:available]
        if len(selected) < len(text):
            truncated = True
        sections.append(header + selected)
        parsed_files.append(original_name)
        remaining -= len(header) + len(selected)
        if remaining <= 0:
            truncated = True
            break

    return {
        "text": "\n\n".join(sections),
        "parsed_files": parsed_files,
        "errors": errors,
        "truncated": truncated,
        "max_chars": int(max_chars),
    }
