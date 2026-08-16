from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import threading
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from ..config.settings import DeliverySettings


class PublicationError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class PublicationService:
    TOKEN_RE = re.compile(r"^[0-9a-f]{48}$")
    INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]+')
    REQUIRED_DOCX_MEMBERS = {"[Content_Types].xml", "word/document.xml"}

    def __init__(self, settings: DeliverySettings) -> None:
        self.settings = settings
        self._audit_lock = threading.Lock()
        self.settings.public_root.mkdir(parents=True, exist_ok=True)
        self.settings.audit_path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _is_within(candidate: Path, root: Path) -> bool:
        return candidate != root and root in candidate.parents

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @classmethod
    def _safe_filename(cls, value: str) -> str:
        raw = Path(str(value or "contract.docx")).name
        raw = cls.INVALID_FILENAME.sub("_", raw).strip(" .")
        if not raw:
            raw = "contract.docx"
        elif not raw.lower().endswith(".docx"):
            raw += ".docx"
        if len(raw.encode("utf-8")) <= 180:
            return raw
        suffix = ".docx"
        stem = Path(raw).stem.strip(" .") or "contract"
        output = ""
        for char in stem:
            candidate = f"{output}{char}{suffix}"
            if len(candidate.encode("utf-8")) > 180:
                break
            output += char
        return f"{output or 'contract'}{suffix}"

    def _resolve_source(self, source_path: str) -> Path:
        raw = Path(str(source_path or "")).expanduser()
        if not str(source_path or "").strip():
            raise PublicationError("source_path_missing", "未提供待发布文件路径。")
        try:
            if raw.is_symlink():
                raise PublicationError(
                    "source_symlink_forbidden", "不允许发布符号链接。"
                )
            source = raw.resolve(strict=True)
        except PublicationError:
            raise
        except (OSError, RuntimeError, ValueError) as exc:
            raise PublicationError(
                "source_path_invalid", "待发布文件路径无效。"
            ) from exc
        if not source.is_file():
            raise PublicationError("source_file_missing", "待发布文件不存在。")
        if not any(
            self._is_within(source, root)
            for root in self.settings.allowed_source_dirs
        ):
            raise PublicationError(
                "source_not_allowlisted",
                "待发布文件不在允许的生成输出目录中。",
            )
        if source.suffix.lower() != ".docx":
            raise PublicationError(
                "source_extension_forbidden", "当前只允许发布 DOCX 文件。"
            )
        try:
            size = source.stat().st_size
        except OSError as exc:
            raise PublicationError(
                "source_stat_failed", "无法读取待发布文件信息。"
            ) from exc
        if size <= 0 or size > self.settings.max_file_bytes:
            raise PublicationError(
                "source_size_invalid", "待发布 DOCX 文件大小不符合限制。"
            )
        try:
            with zipfile.ZipFile(source, "r") as archive:
                names = set(archive.namelist())
        except (OSError, zipfile.BadZipFile) as exc:
            raise PublicationError(
                "source_docx_invalid", "待发布文件不是有效 DOCX。"
            ) from exc
        if not self.REQUIRED_DOCX_MEMBERS.issubset(names):
            raise PublicationError(
                "source_docx_invalid", "待发布文件缺少 DOCX 必需结构。"
            )
        return source

    def _new_token_dir(self) -> tuple[str, Path]:
        for _ in range(8):
            token = secrets.token_hex(24)
            target_dir = self.settings.public_root / token
            try:
                target_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
                return token, target_dir
            except FileExistsError:
                continue
        raise PublicationError(
            "token_allocation_failed", "无法分配临时下载目录。"
        )

    def _delete_token_dir(self, directory: Path) -> bool:
        root = self.settings.public_root.resolve()
        try:
            if directory.is_symlink():
                return False
            resolved = directory.resolve(strict=True)
        except OSError:
            return False
        if resolved.parent != root or not self.TOKEN_RE.fullmatch(resolved.name):
            return False
        try:
            children = list(resolved.iterdir())
        except OSError:
            return False
        for child in children:
            try:
                if child.is_symlink() or child.is_file():
                    child.unlink()
                else:
                    return False
            except OSError:
                return False
        try:
            resolved.rmdir()
            return True
        except OSError:
            return False

    def _audit(self, payload: dict[str, Any]) -> None:
        record = {"recorded_at": int(time.time()), **payload}
        line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
        try:
            with self._audit_lock:
                with self.settings.audit_path.open("a", encoding="utf-8") as handle:
                    handle.write(line)
        except OSError:
            pass

    def cleanup_expired(self) -> dict[str, int]:
        now = time.time()
        removed = 0
        skipped_unsafe = 0
        try:
            entries = list(self.settings.public_root.iterdir())
        except OSError:
            return {"removed": 0, "skipped_unsafe": 0}
        for entry in entries:
            if entry.is_symlink() or not entry.is_dir():
                continue
            if not self.TOKEN_RE.fullmatch(entry.name):
                continue
            try:
                age = now - entry.stat().st_mtime
            except OSError:
                continue
            if age <= self.settings.ttl_seconds:
                continue
            if self._delete_token_dir(entry):
                removed += 1
            else:
                skipped_unsafe += 1
        return {"removed": removed, "skipped_unsafe": skipped_unsafe}

    def publish(self, *, source_path: str, filename: str = "") -> dict[str, Any]:
        configuration_error = self.settings.validation_error()
        if configuration_error:
            return {
                "success": False,
                "status": "blocked",
                "failure_stage": "configuration",
                "error": configuration_error,
                "retry_safe": True,
            }
        self.cleanup_expired()
        try:
            source = self._resolve_source(source_path)
            source_size = source.stat().st_size
            safe_name = self._safe_filename(filename or source.name)
            publication_id = uuid.uuid4().hex
            token, target_dir = self._new_token_dir()
            temporary = target_dir / f".{uuid.uuid4().hex}.part"
            destination = target_dir / safe_name
            try:
                source_hash = hashlib.sha256()
                with source.open("rb") as source_handle, temporary.open(
                    "xb"
                ) as target_handle:
                    while True:
                        block = source_handle.read(1024 * 1024)
                        if not block:
                            break
                        source_hash.update(block)
                        target_handle.write(block)
                    target_handle.flush()
                    os.fsync(target_handle.fileno())
                temporary.replace(destination)
                destination_hash = self._sha256(destination)
                source_digest = source_hash.hexdigest()
                if destination_hash != source_digest:
                    raise PublicationError(
                        "published_hash_mismatch",
                        "临时下载文件复制校验失败。",
                    )
                now = time.time()
                os.utime(target_dir, (now, now))
                expires_at = datetime.fromtimestamp(
                    now + self.settings.ttl_seconds,
                    tz=timezone.utc,
                ).isoformat()
                download_url = (
                    f"{self.settings.public_base_url}/{token}/"
                    f"{quote(safe_name, safe='')}"
                )
                self._audit(
                    {
                        "publication_id": publication_id,
                        "status": "published",
                        "source_name": source.name,
                        "output_filename": safe_name,
                        "size_bytes": source_size,
                        "sha256": source_digest,
                        "expires_at": expires_at,
                    }
                )
                return {
                    "success": True,
                    "status": "ready",
                    "publication_id": publication_id,
                    "filename": safe_name,
                    "size_bytes": source_size,
                    "sha256": source_digest,
                    "download_url": download_url,
                    "expires_at": expires_at,
                    "expires_in_seconds": self.settings.ttl_seconds,
                    "delivery_format": "https_download",
                }
            except Exception:
                try:
                    if temporary.is_file():
                        temporary.unlink()
                except OSError:
                    pass
                self._delete_token_dir(target_dir)
                raise
        except PublicationError as exc:
            self._audit(
                {
                    "publication_id": uuid.uuid4().hex,
                    "status": "failed",
                    "error_code": exc.code,
                }
            )
            return {
                "success": False,
                "status": "failed",
                "failure_stage": exc.code,
                "error": exc.message,
                "retry_safe": True,
            }
        except OSError:
            return {
                "success": False,
                "status": "failed",
                "failure_stage": "filesystem",
                "error": "临时下载文件发布失败。",
                "retry_safe": True,
            }
