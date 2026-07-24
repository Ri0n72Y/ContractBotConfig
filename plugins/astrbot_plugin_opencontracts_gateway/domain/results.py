from __future__ import annotations

import json
from typing import Any


def json_result(**payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)
