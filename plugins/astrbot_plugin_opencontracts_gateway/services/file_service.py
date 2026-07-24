from __future__ import annotations

import asyncio
import hashlib
import mimetypes
import re
from pathlib import Path

from ..config.settings import GatewaySettings
from ..domain.models import ValidatedFile


class FileService:
    """Validate staged files and derive stable upload metadata."""

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
    def _source_filename(value: str, source: Path) -> str:
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
    def _title(value: str, source_filename: str) -> str:
        candidate = str(value or "").strip()
        if not candidate:
            candidate = Path(source_filename).stem
        return candidate[:512]

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
        title: str,
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

        logical_name = self._source_filename(source_filename, source)
        content_type = (
            mimetypes.guess_type(logical_name)[0]
            or "application/octet-stream"
        )
        return (
            ValidatedFile(
                path=source,
                sha256=actual,
                source_filename=logical_name,
                title=self._title(title, logical_name),
                content_type=content_type,
            ),
            actual,
            None,
        )
