from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class ConfirmationService:
    """Validate the router-issued confirmation for a specific staged file."""

    def __init__(self, state_path: Path, ttl_seconds: int) -> None:
        self.state_path = state_path
        self.ttl_seconds = ttl_seconds

    def validate(
        self,
        session_key: str,
        source_sha256: str,
        confirmation_id: str,
    ) -> bool:
        supplied_id = str(confirmation_id or "").strip()
        if not supplied_id:
            return False
        try:
            payload: Any = json.loads(
                self.state_path.read_text(encoding="utf-8")
            )
            if not isinstance(payload, dict):
                return False
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
        except (OSError, ValueError, TypeError):
            return False
