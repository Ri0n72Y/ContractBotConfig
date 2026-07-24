from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from plugins.astrbot_plugin_opencontracts_gateway.services.confirmation_service import (
    ConfirmationService,
)


class ConfirmationServiceTests(unittest.TestCase):
    def test_confirmation_binds_session_hash_and_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            state_path = Path(temp) / "pending.json"
            sha256 = hashlib.sha256(b"contract-data").hexdigest()
            state_path.write_text(
                json.dumps(
                    {
                        "wecom:1": {
                            "state": "duplicate_confirmed",
                            "duplicate_confirmation_id": "confirmation-id",
                            "duplicate_confirmed_at": 4102444800,
                            "files": [{"sha256": sha256}],
                        }
                    }
                ),
                encoding="utf-8",
            )
            service = ConfirmationService(
                state_path,
                ttl_seconds=10_000_000_000,
            )
            self.assertTrue(
                service.validate(
                    "wecom:1",
                    sha256,
                    "confirmation-id",
                )
            )
            self.assertFalse(
                service.validate(
                    "wecom:2",
                    sha256,
                    "confirmation-id",
                )
            )
