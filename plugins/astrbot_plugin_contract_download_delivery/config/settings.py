from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


@dataclass(frozen=True)
class DeliverySettings:
    public_root: Path
    public_base_url: str
    allowed_source_dirs: tuple[Path, ...]
    ttl_seconds: int
    cleanup_interval_seconds: int
    max_file_bytes: int
    audit_path: Path

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "DeliverySettings":
        public_root = Path(
            str(config.get("public_root", "data/public_downloads"))
        ).expanduser().resolve()
        allowed_source_dirs = tuple(
            Path(str(item)).expanduser().resolve()
            for item in config.get(
                "allowed_source_dirs",
                [
                    "data/plugins_data/astrbot_plugin_contract_docx_generator/output",
                    "data/plugins_data/astrbot_plugin_docassemble_gateway/output",
                ],
            )
            if str(item).strip()
        )
        audit_path = Path(
            str(
                config.get(
                    "audit_path",
                    "data/plugins_data/astrbot_plugin_contract_download_delivery/"
                    "publication_audit.jsonl",
                )
            )
        ).expanduser().resolve()
        return cls(
            public_root=public_root,
            public_base_url=str(
                config.get(
                    "public_base_url",
                    "https://download.ri0n72y.top/contracts",
                )
            ).rstrip("/"),
            allowed_source_dirs=allowed_source_dirs,
            ttl_seconds=max(60, int(config.get("ttl_seconds", 1800))),
            cleanup_interval_seconds=max(
                15, int(config.get("cleanup_interval_seconds", 60))
            ),
            max_file_bytes=max(
                1024, int(config.get("max_file_bytes", 30 * 1024 * 1024))
            ),
            audit_path=audit_path,
        )

    def validation_error(self) -> str | None:
        parsed = urlsplit(self.public_base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            return "public_base_url 必须是 HTTPS 公网地址。"
        if parsed.query or parsed.fragment:
            return "public_base_url 不得包含 query 或 fragment。"
        if not self.allowed_source_dirs:
            return "allowed_source_dirs 不能为空。"
        if self.public_root.parent == self.public_root:
            return "public_root 不能是文件系统根目录。"
        if any(root == self.public_root for root in self.allowed_source_dirs):
            return "public_root 不能与 allowed_source_dirs 相同。"
        return None
