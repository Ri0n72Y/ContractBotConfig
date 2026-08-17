from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class ConfirmationService:
    """Validate Router-owned state used by upload confirmation and cancellation."""

    def __init__(self, state_path: Path, ttl_seconds: int) -> None:
        self.state_path = state_path
        self.ttl_seconds = ttl_seconds

    def _load_state(self) -> dict[str, Any] | None:
        try:
            payload: Any = json.loads(
                self.state_path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError, TypeError):
            return None
        return payload if isinstance(payload, dict) else None

    def validate(
        self,
        session_key: str,
        source_sha256: str,
        confirmation_id: str,
    ) -> bool:
        supplied_id = str(confirmation_id or "").strip()
        if not supplied_id:
            return False
        payload = self._load_state()
        if payload is None:
            return False
        try:
            record = payload.get(str(session_key))
            if not isinstance(record, dict):
                return False
            if record.get("state") != "duplicate_confirmed":
                return False
            if str(record.get("duplicate_confirmation_id") or "") != supplied_id:
                return False
            confirmed_at = float(record.get("duplicate_confirmed_at") or 0)
            if confirmed_at <= 0:
                return False
            if time.time() - confirmed_at > self.ttl_seconds:
                return False
            return any(
                isinstance(item, dict)
                and str(item.get("sha256") or "").lower()
                == source_sha256.lower()
                for item in record.get("files", [])
            )
        except (ValueError, TypeError):
            return False

    def task_still_active(
        self,
        session_key: str,
        task_id: str | None,
        source_sha256: str,
    ) -> bool:
        """Return False only when Router state proves this dispatched task ended.

        Direct/admin calls without a Router task id keep their existing behavior.
        If the Router state file itself is temporarily unreadable, this check does
        not introduce a new upload blocker; normal file and identity validation
        still applies.
        """

        expected_task_id = str(task_id or "").strip()
        if not expected_task_id:
            return True
        payload = self._load_state()
        if payload is None:
            return True

        record = payload.get(str(session_key))
        if not isinstance(record, dict):
            return False
        if str(record.get("dispatch_task_id") or "").strip() != expected_task_id:
            return False

        expected_sha = str(source_sha256 or "").strip().lower()
        if not expected_sha:
            return True
        return any(
            isinstance(item, dict)
            and str(item.get("sha256") or "").strip().lower() == expected_sha
            for item in record.get("files", [])
        )
