from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class GatewaySettings:
    base_url: str
    api_key: str
    allowed_interviews: tuple[str, ...]
    default_interview: str
    result_descriptor_key: str
    output_dir: Path
    timeout_seconds: int
    max_file_bytes: int
    verify_tls: bool
    cleanup_sessions: bool
    output_retention_seconds: int
    output_cleanup_interval_seconds: int

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "GatewaySettings":
        allowed = tuple(
            str(item).strip()
            for item in config.get("allowed_interviews", [])
            if str(item).strip()
        )
        return cls(
            base_url=str(config.get("base_url", "http://docassemble")).rstrip("/"),
            api_key=str(config.get("api_key", "")).strip(),
            allowed_interviews=allowed,
            default_interview=str(config.get("default_interview", "")).strip(),
            result_descriptor_key=str(
                config.get("result_descriptor_key", "contractbot_document")
            ).strip()
            or "contractbot_document",
            output_dir=Path(
                str(
                    config.get(
                        "output_dir",
                        "data/plugins_data/astrbot_plugin_docassemble_gateway/output",
                    )
                )
            ).expanduser().resolve(),
            timeout_seconds=max(5, int(config.get("timeout_seconds", 90))),
            max_file_bytes=max(
                1024,
                int(config.get("max_file_bytes", 30 * 1024 * 1024)),
            ),
            verify_tls=bool(config.get("verify_tls", True)),
            cleanup_sessions=bool(config.get("cleanup_sessions", True)),
            output_retention_seconds=max(
                300,
                int(config.get("output_retention_seconds", 86400)),
            ),
            output_cleanup_interval_seconds=max(
                30,
                int(config.get("output_cleanup_interval_seconds", 300)),
            ),
        )

    def validation_error(self) -> str | None:
        if not self.base_url.startswith(("http://", "https://")):
            return "Docassemble base_url 必须以 http:// 或 https:// 开头。"
        if not self.api_key:
            return "Docassemble API Key 未配置。"
        if not self.allowed_interviews:
            return "allowed_interviews 为空；MVP 必须显式允许可执行 interview。"
        if (
            self.default_interview
            and self.default_interview not in self.allowed_interviews
        ):
            return "default_interview 不在 allowed_interviews 中。"
        return None
