from __future__ import annotations

import hashlib
import json
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from ..config.settings import GeneratorSettings


DRAFT_ID_RE = re.compile(r"^[0-9a-f]{32}$")
OWNER_KEY_RE = re.compile(r"^[0-9a-f]{64}$")


class DraftWorkspaceError(RuntimeError):
    pass


class DraftWorkspaceService:
    """Thread-safe persistence for successfully generated contract Markdown.

    MVP design: the LLM does not manage draft transactions. A completed contract
    is saved as one body.md plus one atomic manifest. With fewer than a few dozen
    active users, scanning finalized manifests is simpler and more reliable than
    maintaining a separate latest-index transaction.
    """

    def __init__(self, settings: GeneratorSettings) -> None:
        self.settings = settings
        self.output_dir = settings.output_dir
        self.draft_dir = self.output_dir / "_drafts"
        self._lock = threading.RLock()

    def initialize(self) -> None:
        with self._lock:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self.draft_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def owner_key(unified_msg_origin: str) -> str:
        return hashlib.sha256(
            str(unified_msg_origin or "").encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _validate_owner(owner_key: str) -> str:
        value = str(owner_key or "").strip().lower()
        if not OWNER_KEY_RE.fullmatch(value):
            raise DraftWorkspaceError("invalid draft owner key")
        return value

    @staticmethod
    def _validate_draft_id(draft_id: str) -> str:
        value = str(draft_id or "").strip().lower()
        if not DRAFT_ID_RE.fullmatch(value):
            raise DraftWorkspaceError("invalid draft_id")
        return value

    def _draft_path(self, draft_id: str) -> Path:
        value = self._validate_draft_id(draft_id)
        root = self.draft_dir.resolve()
        path = (root / value).resolve()
        if path.parent != root:
            raise DraftWorkspaceError("unsafe draft path")
        return path

    def _manifest_path(self, draft_id: str) -> Path:
        return self._draft_path(draft_id) / "manifest.json"

    def _body_path(self, draft_id: str) -> Path:
        return self._draft_path(draft_id) / "body.md"

    def _load_manifest_unlocked(self, draft_id: str) -> dict[str, Any]:
        path = self._manifest_path(draft_id)
        if not path.is_file():
            raise DraftWorkspaceError("draft not found")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as exc:
            raise DraftWorkspaceError("draft manifest invalid") from exc
        if not isinstance(payload, dict):
            raise DraftWorkspaceError("draft manifest invalid")
        return payload

    @staticmethod
    def _atomic_write_text(path: Path, text: str) -> None:
        temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
        try:
            temporary.write_text(text, encoding="utf-8")
            temporary.replace(path)
        except OSError as exc:
            try:
                if temporary.is_file():
                    temporary.unlink()
            except OSError:
                pass
            raise DraftWorkspaceError("unable to persist draft") from exc

    @staticmethod
    def _assert_owner(manifest: dict[str, Any], owner_key: str) -> None:
        if str(manifest.get("owner_key") or "") != owner_key:
            raise DraftWorkspaceError("draft does not belong to this conversation")

    def save_finalized(
        self,
        *,
        owner_key: str,
        generation_id: str,
        generation_basis: str,
        source_draft_id: str,
        template_asset_id: str,
        template_document_slug: str,
        document_title: str,
        output_filename: str,
        render_profile: str,
        markdown: str,
        output: dict[str, Any],
    ) -> dict[str, Any]:
        owner = self._validate_owner(owner_key)
        text = str(markdown or "")
        if not text.strip():
            raise DraftWorkspaceError("cannot persist empty contract draft")
        if len(text) > self.settings.max_markdown_chars:
            raise DraftWorkspaceError("draft exceeds max_markdown_chars")

        source_id = str(source_draft_id or "").strip().lower()
        if source_id:
            self._validate_draft_id(source_id)

        draft_id = uuid.uuid4().hex
        now = time.time()
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        manifest: dict[str, Any] = {
            "draft_id": draft_id,
            "owner_key": owner,
            "generation_id": str(generation_id or ""),
            "generation_basis": str(generation_basis or ""),
            "source_draft_id": source_id or None,
            "template_asset_id": str(template_asset_id or ""),
            "template_document_slug": str(template_document_slug or ""),
            "document_title": str(document_title or ""),
            "output_filename": str(output_filename or ""),
            "render_profile": str(render_profile or ""),
            "created_at": now,
            "updated_at": now,
            "finalized": True,
            "markdown_sha256": digest,
            "markdown_chars": len(text),
            "output": dict(output),
        }

        with self._lock:
            directory = self._draft_path(draft_id)
            try:
                directory.mkdir(parents=True, exist_ok=False)
            except OSError as exc:
                raise DraftWorkspaceError("unable to create draft workspace") from exc
            try:
                self._atomic_write_text(self._body_path(draft_id), text)
                self._atomic_write_text(
                    self._manifest_path(draft_id),
                    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                )
            except Exception:
                try:
                    shutil.rmtree(directory)
                except OSError:
                    pass
                raise
        return dict(manifest)

    def _candidate_manifests_unlocked(self, owner_key: str) -> list[dict[str, Any]]:
        owner = self._validate_owner(owner_key)
        candidates: list[dict[str, Any]] = []
        if not self.draft_dir.is_dir():
            return candidates
        for directory in self.draft_dir.iterdir():
            if (
                not directory.is_dir()
                or directory.is_symlink()
                or not DRAFT_ID_RE.fullmatch(directory.name)
            ):
                continue
            try:
                manifest = self._load_manifest_unlocked(directory.name)
                self._assert_owner(manifest, owner)
                if not bool(manifest.get("finalized", False)):
                    continue
                updated_at = float(manifest.get("updated_at", 0) or 0)
                if updated_at <= 0:
                    continue
                body_path = self._body_path(directory.name)
                if not body_path.is_file():
                    continue
                candidates.append(manifest)
            except (DraftWorkspaceError, TypeError, ValueError, OSError):
                continue
        return candidates

    @staticmethod
    def _latest_manifest(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not candidates:
            return None
        candidates.sort(
            key=lambda item: (
                float(item.get("updated_at", 0) or 0),
                str(item.get("draft_id") or ""),
            ),
            reverse=True,
        )
        return dict(candidates[0])

    def latest_finalized(self, *, owner_key: str) -> dict[str, Any] | None:
        with self._lock:
            return self._latest_manifest(
                self._candidate_manifests_unlocked(owner_key)
            )

    def read_latest(
        self,
        *,
        owner_key: str,
        max_chars: int,
    ) -> dict[str, Any] | None:
        """Read the first slice of the latest finalized draft in one operation."""
        with self._lock:
            manifest = self._latest_manifest(
                self._candidate_manifests_unlocked(owner_key)
            )
            if manifest is None:
                return None
            draft_id = str(manifest.get("draft_id") or "")
            return self.read(
                owner_key=owner_key,
                draft_id=draft_id,
                char_offset=0,
                max_chars=max_chars,
            )

    def read(
        self,
        *,
        owner_key: str,
        draft_id: str,
        char_offset: int,
        max_chars: int,
    ) -> dict[str, Any]:
        owner = self._validate_owner(owner_key)
        offset = max(0, int(char_offset))
        limit = max(1000, min(int(max_chars), self.settings.max_chunk_chars))
        with self._lock:
            manifest = self._load_manifest_unlocked(draft_id)
            self._assert_owner(manifest, owner)
            if not bool(manifest.get("finalized", False)):
                raise DraftWorkspaceError("draft is not finalized")
            path = self._body_path(draft_id)
            if not path.is_file():
                raise DraftWorkspaceError("draft body missing")
            try:
                markdown = path.read_text(encoding="utf-8")
            except OSError as exc:
                raise DraftWorkspaceError("unable to read draft body") from exc
            expected_hash = str(manifest.get("markdown_sha256") or "")
            actual_hash = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
            if not expected_hash or expected_hash != actual_hash:
                raise DraftWorkspaceError("draft integrity check failed")

        total = len(markdown)
        offset = min(offset, total)
        text = markdown[offset : offset + limit]
        next_offset = offset + len(text)
        if next_offset >= total:
            next_offset = None
        return {
            "draft_id": draft_id,
            "char_offset": offset,
            "text": text,
            "total_chars": total,
            "next_offset": next_offset,
            "generation_id": manifest.get("generation_id"),
            "generation_basis": manifest.get("generation_basis"),
            "source_draft_id": manifest.get("source_draft_id"),
            "template_asset_id": manifest.get("template_asset_id"),
            "template_document_slug": manifest.get("template_document_slug"),
            "document_title": manifest.get("document_title"),
            "output_filename": manifest.get("output_filename"),
            "render_profile": manifest.get("render_profile"),
            "finalized": True,
        }

    def cleanup_expired(self) -> int:
        cutoff = time.time() - self.settings.output_retention_seconds
        removed = 0
        with self._lock:
            if self.output_dir.exists():
                for path in self.output_dir.glob("*.docx"):
                    try:
                        if path.is_file() and path.stat().st_mtime < cutoff:
                            path.unlink()
                            removed += 1
                    except OSError:
                        continue

            if self.draft_dir.exists():
                for directory in self.draft_dir.iterdir():
                    if (
                        not directory.is_dir()
                        or directory.is_symlink()
                        or not DRAFT_ID_RE.fullmatch(directory.name)
                    ):
                        continue
                    try:
                        manifest = self._load_manifest_unlocked(directory.name)
                        updated_at = float(manifest.get("updated_at", 0) or 0)
                        if updated_at <= 0:
                            updated_at = directory.stat().st_mtime
                        if updated_at < cutoff:
                            shutil.rmtree(directory)
                            removed += 1
                    except (DraftWorkspaceError, TypeError, ValueError, OSError):
                        try:
                            if directory.stat().st_mtime < cutoff:
                                shutil.rmtree(directory)
                                removed += 1
                        except OSError:
                            pass
                        continue
        return removed
