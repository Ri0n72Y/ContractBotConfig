from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


DEFAULT_IMPORT_PATH = "/api/imports/documents/"
DEFAULT_DATA_DIR = "data/plugins_data/astrbot_plugin_opencontracts_gateway"
DEFAULT_ROUTER_STATE_PATH = (
    "data/plugins_data/astrbot_plugin_contract_file_router/"
    "pending_contract_files.json"
)
DEFAULT_ALLOWED_ROOT = (
    "/AstrBot/data/plugins_data/astrbot_plugin_contract_file_router/inbox"
)


@dataclass(frozen=True)
class GatewaySettings:
    """Configuration for the WorkerKey-authenticated import boundary."""

    base_url: str
    worker_key: str
    import_path: str
    default_corpus_id: str
    default_corpus_slug: str
    default_make_public: bool
    allowed_roots: tuple[Path, ...]
    data_dir: Path
    router_state_path: Path
    require_expected_sha256: bool
    max_file_bytes: int
    timeout_seconds: float
    confirmation_ttl_seconds: int
    verify_tls: bool

    @classmethod
    def from_config(cls, config: Mapping[str, Any] | None) -> "GatewaySettings":
        values = config or {}
        roots_value = values.get("allowed_roots", [DEFAULT_ALLOWED_ROOT])
        if not isinstance(roots_value, list):
            roots_value = [str(roots_value)]
        allowed_roots = tuple(
            Path(str(root)).expanduser().resolve()
            for root in roots_value
            if str(root).strip()
        )

        import_path = str(
            values.get("import_path", DEFAULT_IMPORT_PATH)
        ).strip() or DEFAULT_IMPORT_PATH
        if not import_path.startswith("/"):
            import_path = "/" + import_path

        worker_key = str(
            values.get("worker_key") or values.get("auth_token") or ""
        ).strip()

        return cls(
            base_url=str(
                values.get("base_url", "http://opencontracts-api:8000")
            ).strip().rstrip("/"),
            worker_key=worker_key,
            import_path=import_path,
            default_corpus_id=str(
                values.get("default_corpus_id", "")
            ).strip(),
            default_corpus_slug=str(
                values.get("default_corpus_slug", "")
            ).strip(),
            default_make_public=bool(
                values.get("default_make_public", False)
            ),
            allowed_roots=allowed_roots,
            data_dir=Path(
                str(values.get("data_dir", DEFAULT_DATA_DIR))
            ).expanduser().resolve(),
            router_state_path=Path(
                str(
                    values.get(
                        "router_state_path",
                        DEFAULT_ROUTER_STATE_PATH,
                    )
                )
            ).expanduser().resolve(),
            require_expected_sha256=bool(
                values.get("require_expected_sha256", True)
            ),
            max_file_bytes=int(
                values.get("max_file_bytes", 100 * 1024 * 1024)
            ),
            timeout_seconds=float(values.get("timeout_seconds", 120)),
            confirmation_ttl_seconds=int(
                values.get("confirmation_ttl_seconds", 3600)
            ),
            verify_tls=bool(values.get("verify_tls", True)),
        )

    def validation_error(self) -> str | None:
        if not self.base_url.startswith(("http://", "https://")):
            return "base_url 必须以 http:// 或 https:// 开头。"
        if not self.worker_key:
            return "尚未在插件配置中填写 OpenContracts WorkerKey。"
        if not self.allowed_roots:
            return "allowed_roots 不能为空。"
        if self.max_file_bytes <= 0:
            return "max_file_bytes 必须大于 0。"
        if self.timeout_seconds <= 0:
            return "timeout_seconds 必须大于 0。"
        if self.confirmation_ttl_seconds <= 0:
            return "confirmation_ttl_seconds 必须大于 0。"
        return None
