from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


SUPPORTED_RENDER_PROFILES = ("standard_contract",)


@dataclass(frozen=True)
class GeneratorSettings:
    output_dir: Path
    body_font: str
    heading_font: str
    body_font_size: float
    heading_font_size: float
    line_spacing: float
    margin_cm: float
    max_markdown_chars: int
    max_chunk_chars: int
    max_file_bytes: int
    output_retention_seconds: int
    output_cleanup_interval_seconds: int

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "GeneratorSettings":
        max_markdown_chars = max(
            1000,
            int(config.get("max_markdown_chars", 180000)),
        )
        max_chunk_chars = max(
            1000,
            min(
                max_markdown_chars,
                int(config.get("max_chunk_chars", 60000)),
            ),
        )
        return cls(
            output_dir=Path(
                str(
                    config.get(
                        "output_dir",
                        "data/plugins_data/astrbot_plugin_contract_docx_generator/output",
                    )
                )
            ).expanduser().resolve(),
            body_font=str(config.get("body_font", "宋体")).strip() or "宋体",
            heading_font=str(config.get("heading_font", "黑体")).strip() or "黑体",
            body_font_size=max(8.0, float(config.get("body_font_size", 12))),
            heading_font_size=max(
                10.0,
                float(config.get("heading_font_size", 16)),
            ),
            line_spacing=max(1.0, float(config.get("line_spacing", 1.5))),
            margin_cm=max(1.0, float(config.get("margin_cm", 2.54))),
            max_markdown_chars=max_markdown_chars,
            max_chunk_chars=max_chunk_chars,
            max_file_bytes=max(
                1024,
                int(config.get("max_file_bytes", 30 * 1024 * 1024)),
            ),
            output_retention_seconds=max(
                300,
                int(config.get("output_retention_seconds", 86400)),
            ),
            output_cleanup_interval_seconds=max(
                30,
                int(config.get("output_cleanup_interval_seconds", 300)),
            ),
        )
