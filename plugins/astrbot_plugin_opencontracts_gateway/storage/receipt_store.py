from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any


RECEIPT_SCHEMA_VERSION = 4


class ReceiptStore:
    """Persist append-only upload receipts for audit and diagnostics."""

    def __init__(self, data_dir: Path) -> None:
        data_dir.mkdir(parents=True, exist_ok=True)
        self.path = data_dir / "receipts.json"
        self._payload = self._load()

    @property
    def count(self) -> int:
        return len(self._payload.get("receipts", []))

    def _load(self) -> dict[str, Any]:
        try:
            if self.path.exists():
                payload = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    receipts = payload.get("receipts")
                    if not isinstance(receipts, list):
                        receipts = []
                    return {
                        "schema_version": RECEIPT_SCHEMA_VERSION,
                        "updated_at": float(payload.get("updated_at") or time.time()),
                        "receipts": receipts,
                    }
        except (OSError, ValueError, TypeError):
            pass
        return {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "updated_at": time.time(),
            "receipts": [],
        }

    def _save(self) -> None:
        self._payload["schema_version"] = RECEIPT_SCHEMA_VERSION
        self._payload["updated_at"] = time.time()
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(self._payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def append(self, receipt: dict[str, Any]) -> None:
        records = self._payload.setdefault("receipts", [])
        normalized = dict(receipt)
        normalized["receipt_id"] = uuid.uuid4().hex
        normalized["system"] = "opencontracts"
        normalized["role"] = "upload_audit"
        normalized["recorded_at"] = time.time()
        records.append(normalized)
        self._save()
