from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ValidatedFile:
    path: Path
    sha256: str
    source_filename: str
    title: str
    content_type: str


@dataclass(frozen=True)
class ImportResponse:
    status_code: int | None
    body: Any
    transport_error: str | None = None

    @property
    def received(self) -> bool:
        return self.status_code is not None and self.transport_error is None
