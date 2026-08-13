from __future__ import annotations

import re
import time

from ..config.settings import GatewaySettings


class OutputRetentionService:
    """Delete only expired DOCX files created by this Gateway."""

    GENERATED_FILE_RE = re.compile(r"^[0-9a-f]{12}_.+\.docx$", re.IGNORECASE)

    def __init__(self, settings: GatewaySettings) -> None:
        self.settings = settings
        self.settings.output_dir.mkdir(parents=True, exist_ok=True)

    def cleanup_expired(self) -> dict[str, int]:
        root = self.settings.output_dir.resolve()
        now = time.time()
        removed = 0
        skipped_unsafe = 0
        try:
            entries = list(root.iterdir())
        except OSError:
            return {"removed": 0, "skipped_unsafe": 0}

        for entry in entries:
            if entry.is_symlink() or not entry.is_file():
                continue
            if not self.GENERATED_FILE_RE.fullmatch(entry.name):
                continue
            try:
                resolved = entry.resolve(strict=True)
            except (OSError, RuntimeError, ValueError):
                skipped_unsafe += 1
                continue
            if resolved.parent != root:
                skipped_unsafe += 1
                continue
            try:
                age = now - resolved.stat().st_mtime
            except OSError:
                continue
            if age <= self.settings.output_retention_seconds:
                continue
            try:
                resolved.unlink()
                removed += 1
            except OSError:
                skipped_unsafe += 1

        return {
            "removed": removed,
            "skipped_unsafe": skipped_unsafe,
        }
