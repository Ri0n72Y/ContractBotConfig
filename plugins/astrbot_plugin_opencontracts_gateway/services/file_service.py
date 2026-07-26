from __future__ import annotations

import asyncio
import hashlib
import mimetypes
import re
from datetime import date
from pathlib import Path

from ..config.settings import GatewaySettings
from ..domain.models import DocumentIdentity, ValidatedFile


class FileService:
    """Validate staged files and derive a stable contract document identity."""

    def __init__(self, settings: GatewaySettings) -> None:
        self.settings = settings

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _original_filename(value: str, source: Path) -> str:
        raw = str(value or "").strip() or source.name
        raw = raw.replace("\\", "/").split("/")[-1]
        legacy = re.fullmatch(r"\d+_[0-9a-fA-F]{8}_(.+)", raw)
        if legacy:
            raw = legacy.group(1)
        raw = "".join(
            char for char in raw if ord(char) >= 32 and ord(char) != 127
        ).strip()
        return raw[:240] or "contract.bin"

    @staticmethod
    def _normalize_date(value: str) -> str | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        match = re.fullmatch(
            r"(\d{4})\s*(?:年|[-/.])\s*(\d{1,2})\s*(?:月|[-/.])\s*(\d{1,2})\s*日?",
            raw,
        )
        if not match:
            match = re.fullmatch(r"(\d{4})(\d{2})(\d{2})", raw)
        if not match:
            return None
        try:
            parsed = date(*(int(part) for part in match.groups()))
        except ValueError:
            return None
        return parsed.isoformat()

    @staticmethod
    def _normalize_title(value: str) -> str:
        raw = str(value or "").strip()
        raw = re.sub(r"[<>:\"/\\|?*\x00-\x1f\x7f]+", "_", raw)
        raw = re.sub(r"\s+", " ", raw)
        raw = raw.strip(" ._-")
        return raw[:180]

    @staticmethod
    def _truncate_utf8(value: str, max_bytes: int) -> str:
        chars: list[str] = []
        size = 0
        for char in value:
            char_size = len(char.encode("utf-8"))
            if size + char_size > max_bytes:
                break
            chars.append(char)
            size += char_size
        return "".join(chars)

    @classmethod
    def normalize_identity(
        cls,
        contract_date: str,
        contract_title: str,
    ) -> tuple[DocumentIdentity | None, str | None]:
        normalized_date = cls._normalize_date(contract_date)
        if normalized_date is None:
            return None, "contract_date 必须是有效合同日期，例如 2026-07-25。"
        normalized_title = cls._normalize_title(contract_title)
        if not normalized_title:
            return None, "contract_title 不能为空。"
        return (
            DocumentIdentity(
                contract_date=normalized_date,
                contract_title=normalized_title,
                document_title=f"{normalized_date} {normalized_title}",
            ),
            None,
        )

    @classmethod
    def _normalized_filename(
        cls,
        identity: DocumentIdentity,
        original_filename: str,
        source: Path,
    ) -> str:
        suffix = Path(original_filename).suffix or source.suffix
        suffix = suffix.lower()
        if not re.fullmatch(r"\.[0-9a-z]{1,12}", suffix):
            suffix = ".bin"
        prefix = f"{identity.contract_date}_"
        available_bytes = max(
            1,
            240 - len(prefix.encode("utf-8")) - len(suffix.encode("utf-8")),
        )
        title = cls._truncate_utf8(
            identity.contract_title,
            available_bytes,
        ).rstrip(" ._-") or "合同"
        return f"{prefix}{title}{suffix}"

    def _resolve(self, staged_path: str) -> tuple[Path | None, str | None]:
        if not str(staged_path or "").strip():
            return None, "staged_path 不能为空。"
        source = Path(staged_path).expanduser()
        if source.is_symlink():
            return None, "暂存文件不能是符号链接。"
        try:
            resolved = source.resolve(strict=True)
        except FileNotFoundError:
            return None, "指定的暂存文件不存在。"
        except OSError as exc:
            return None, f"无法解析暂存文件路径：{exc}"
        if not resolved.is_file():
            return None, "staged_path 不是普通文件。"
        if not any(
            resolved == root or resolved.is_relative_to(root)
            for root in self.settings.allowed_roots
        ):
            return None, "文件不在 allowed_roots 范围内。"
        size = resolved.stat().st_size
        if size <= 0:
            return None, "文件为空。"
        if size > self.settings.max_file_bytes:
            return None, (
                f"文件超过最大大小：{size} > "
                f"{self.settings.max_file_bytes} bytes。"
            )
        return resolved, None

    async def validate(
        self,
        staged_path: str,
        expected_sha256: str,
        source_filename: str,
        identity: DocumentIdentity,
    ) -> tuple[ValidatedFile | None, str | None, str | None]:
        source, error = self._resolve(staged_path)
        if error or source is None:
            return None, None, error

        actual = await asyncio.to_thread(self._sha256, source)
        expected = str(expected_sha256 or "").strip().lower()
        if self.settings.require_expected_sha256 and not expected:
            return None, actual, "当前配置要求 expected_sha256。"
        if expected and expected != actual:
            return None, actual, "文件 SHA-256 与任务上下文不一致。"

        original_name = self._original_filename(source_filename, source)
        normalized_name = self._normalized_filename(
            identity,
            original_name,
            source,
        )
        content_type = (
            mimetypes.guess_type(normalized_name)[0]
            or "application/octet-stream"
        )
        return (
            ValidatedFile(
                path=source,
                sha256=actual,
                original_filename=original_name,
                source_filename=normalized_name,
                title=identity.document_title,
                contract_date=identity.contract_date,
                contract_title=identity.contract_title,
                content_type=content_type,
            ),
            actual,
            None,
        )
