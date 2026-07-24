from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


RECEIPT_SCHEMA_VERSION = 3


class ReceiptStore:
    """Persist upload receipts for audit and support diagnostics."""

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
                    payload.setdefault("schema_version", RECEIPT_SCHEMA_VERSION)
                    payload.setdefault("receipts", [])
                    return payload
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
            json.dumps(self._payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def upsert(self, receipt: dict[str, Any]) -> None:
        records = self._payload.setdefault("receipts", [])
        source_sha256 = str(receipt.get("source_sha256") or "").lower()
        source_filename = str(receipt.get("source_filename") or "").strip()
        existing_index: int | None = None

        for index, current in enumerate(records):
            if not isinstance(current, dict):
                continue
            current_sha = str(current.get("source_sha256") or "").lower()
            current_name = str(current.get("source_filename") or "").strip()
            if source_sha256 and source_sha256 == current_sha:
                existing_index = index
                break
            if source_filename and source_filename == current_name:
                existing_index = index
                break

        normalized = dict(receipt)
        normalized["system"] = "opencontracts"
        normalized["role"] = "upload_audit"
        normalized["updated_at"] = time.time()

        if existing_index is None:
            normalized.setdefault("upload_count", 1)
            records.append(normalized)
        else:
            merged = dict(records[existing_index])
            merged.update(
                {key: value for key, value in normalized.items() if value is not None}
            )
            merged["upload_count"] = int(
                records[existing_index].get("upload_count", 0)
            ) + 1
            records[existing_index] = merged
        self._save()
