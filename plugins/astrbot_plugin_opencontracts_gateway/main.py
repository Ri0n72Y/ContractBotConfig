from __future__ import annotations

import asyncio
import hashlib
import json
import mimetypes
import re
import time
from pathlib import Path
from typing import Any

import httpx

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star


IMPORT_PATH = "/api/imports/documents/"
LOOKUP_PATH = "/api/imports/documents/lookup/"
RECEIPT_SCHEMA_VERSION = 2
RESERVED_META_KEYS = {
    "source",
    "source_sha256",
    "source_filename",
    "astrbot_task_id",
}


class OpenContractsGateway(Star):
    """OpenContracts gateway with authoritative remote duplicate checks."""

    def __init__(
        self,
        context: Context,
        config: AstrBotConfig | None = None,
    ) -> None:
        super().__init__(context, config)
        config = config or {}
        self.config = config
        self.base_url = str(
            config.get("base_url", "http://opencontracts-api:8000")
        ).strip().rstrip("/")
        self.auth_mode = str(config.get("auth_mode", "worker_key")).strip().lower()
        self.auth_token = str(config.get("auth_token", "")).strip()
        self.lookup_path = str(
            config.get("lookup_path", LOOKUP_PATH)
        ).strip() or LOOKUP_PATH
        if not self.lookup_path.startswith("/"):
            self.lookup_path = "/" + self.lookup_path

        self.default_corpus_id = str(
            config.get("default_corpus_id", "")
        ).strip()
        self.default_corpus_slug = str(
            config.get("default_corpus_slug", "")
        ).strip()
        self.default_make_public = bool(config.get("default_make_public", False))
        self.require_expected_sha256 = bool(
            config.get("require_expected_sha256", True)
        )
        self.max_file_bytes = int(
            config.get("max_file_bytes", 100 * 1024 * 1024)
        )
        self.timeout_seconds = float(config.get("timeout_seconds", 120))
        self.remote_timeout_seconds = float(
            config.get("remote_timeout_seconds", 30)
        )
        self.verify_tls = bool(config.get("verify_tls", True))
        self.confirmation_ttl_seconds = int(
            config.get("confirmation_ttl_seconds", 3600)
        )
        self.use_receipt_path_hints = bool(
            config.get("use_receipt_path_hints", True)
        )

        data_dir = Path(
            str(
                config.get(
                    "data_dir",
                    "data/plugins_data/astrbot_plugin_opencontracts_gateway",
                )
            )
        ).expanduser().resolve()
        data_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir = data_dir
        self.receipts_path = data_dir / "receipts.json"
        self.router_state_path = Path(
            str(
                config.get(
                    "router_state_path",
                    "data/plugins_data/astrbot_plugin_contract_file_router/"
                    "pending_contract_files.json",
                )
            )
        ).expanduser().resolve()
        self.bootstrap_receipts_json = str(
            config.get("bootstrap_receipts_json", "")
        ).strip()

        allowed_roots = config.get(
            "allowed_roots",
            [
                "/AstrBot/data/plugins_data/"
                "astrbot_plugin_contract_file_router/inbox"
            ],
        )
        if not isinstance(allowed_roots, list):
            allowed_roots = [str(allowed_roots)]
        self.allowed_roots = [
            Path(str(root)).expanduser().resolve()
            for root in allowed_roots
            if str(root).strip()
        ]
        self.receipts = self._load_receipts()
        self._merge_bootstrap_receipts()
        self._remote_query_lock = asyncio.Lock()

    async def initialize(self) -> None:
        logger.info(
            "OpenContracts gateway 0.5.1 initialized: base_url=%s "
            "auth_mode=%s receipts=%s rest_lookup=%s",
            self.base_url,
            self.auth_mode,
            len(self.receipts.get("receipts", [])),
            self.lookup_path,
        )

    @staticmethod
    def _json_result(**payload: Any) -> str:
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    @staticmethod
    def _safe_error_text(value: Any, max_chars: int = 1200) -> str:
        text = str(value or "").strip()
        text = re.sub(
            r"(?i)(authorization|token|workerkey|bearer)\s*[:=]\s*\S+",
            r"\1: [REDACTED]",
            text,
        )
        return text[:max_chars]

    def _write_configuration_error(self) -> str | None:
        if not self.base_url.startswith(("http://", "https://")):
            return "base_url 必须以 http:// 或 https:// 开头。"
        if self.auth_mode not in {"worker_key", "bearer"}:
            return "auth_mode 只能是 worker_key 或 bearer。"
        if not self.auth_token:
            return "尚未在插件 GUI 中配置 auth_token。"
        if not self.allowed_roots:
            return "allowed_roots 不能为空。"
        if self.max_file_bytes <= 0:
            return "max_file_bytes 必须大于 0。"
        if self.timeout_seconds <= 0:
            return "timeout_seconds 必须大于 0。"
        return None

    def _read_configuration_error(self) -> str | None:
        if not self.base_url.startswith(("http://", "https://")):
            return "base_url 必须以 http:// 或 https:// 开头。"
        if self.auth_mode != "worker_key":
            return "路径查重 REST 端点仅接受现有 WorkerKey；请将 auth_mode 设置为 worker_key。"
        if not self.auth_token:
            return "REST 路径查重与上传复用 auth_token，但当前 auth_token 为空。"
        if self.remote_timeout_seconds <= 0:
            return "remote_timeout_seconds 必须大于 0。"
        return None

    def _authorization_header(self) -> str:
        if self.auth_mode == "worker_key":
            return f"WorkerKey {self.auth_token}"
        return f"Bearer {self.auth_token}"

    def _rest_headers(self) -> dict[str, str]:
        return {
            "Authorization": self._authorization_header(),
            "Accept": "application/json",
            "User-Agent": "AstrBot-OpenContracts-Gateway/0.5.1",
        }

    @staticmethod
    def _calculate_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _normalise_title(title: str, source: Path) -> str:
        return ((title or "").strip() or source.stem)[:512]

    @staticmethod
    def _safe_filename(value: str, source: Path) -> str:
        raw = str(value or "").strip()
        if not raw:
            raw = source.name
        raw = raw.replace("\\", "/").split("/")[-1]
        legacy = re.fullmatch(r"\d+_[0-9a-fA-F]{8}_(.+)", raw)
        if legacy:
            raw = legacy.group(1)
        # Preserve the original visible filename. OpenContracts applies its own
        # path sanitiser; the gateway only removes path/control characters.
        raw = "".join(char for char in raw if ord(char) >= 32 and ord(char) != 127)
        raw = raw.strip()
        return raw[:240] or "contract.bin"

    def _resolve_allowed_file(
        self, staged_path: str
    ) -> tuple[Path | None, str | None]:
        if not staged_path or not staged_path.strip():
            return None, "staged_path 不能为空。"
        source = Path(staged_path).expanduser()
        if source.is_symlink():
            return None, "不允许上传符号链接。"
        try:
            resolved = source.resolve(strict=True)
        except FileNotFoundError:
            return None, "指定的暂存文件不存在。"
        except OSError as exc:
            return None, f"无法解析暂存文件路径：{exc}"
        if not resolved.is_file():
            return None, "staged_path 不是普通文件。"
        if not any(
            resolved == root or resolved.is_relative_to(root)
            for root in self.allowed_roots
        ):
            return None, "文件不在 allowed_roots 范围内。"
        size = resolved.stat().st_size
        if size <= 0:
            return None, "文件为空。"
        if size > self.max_file_bytes:
            return None, (
                f"文件超过最大大小：{size} > {self.max_file_bytes} bytes。"
            )
        return resolved, None

    def _load_receipts(self) -> dict[str, Any]:
        try:
            if self.receipts_path.exists():
                payload = json.loads(
                    self.receipts_path.read_text(encoding="utf-8")
                )
                if isinstance(payload, dict):
                    payload.setdefault("schema_version", RECEIPT_SCHEMA_VERSION)
                    payload.setdefault("receipts", [])
                    return payload
        except Exception as exc:
            logger.warning("OpenContracts receipt registry load failed: %s", exc)
        return {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "updated_at": time.time(),
            "receipts": [],
        }

    def _save_receipts(self) -> None:
        self.receipts["schema_version"] = RECEIPT_SCHEMA_VERSION
        self.receipts["updated_at"] = time.time()
        temporary = self.receipts_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(self.receipts, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.receipts_path)

    def _merge_bootstrap_receipts(self) -> None:
        if not self.bootstrap_receipts_json:
            return
        try:
            parsed = json.loads(self.bootstrap_receipts_json)
            if isinstance(parsed, dict):
                parsed = [parsed]
            if not isinstance(parsed, list):
                raise ValueError("bootstrap_receipts_json must be a list")
            changed = False
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                sha = str(item.get("source_sha256", "")).strip().lower()
                filename = str(
                    item.get("source_filename")
                    or item.get("import_filename")
                    or item.get("document_path")
                    or ""
                ).strip()
                if not sha and not filename:
                    continue
                receipt = dict(item)
                receipt.setdefault("source", "bootstrap")
                self._upsert_receipt(receipt, save=False)
                changed = True
            if changed:
                self._save_receipts()
        except Exception as exc:
            logger.warning("OpenContracts bootstrap receipts ignored: %s", exc)

    def _upsert_receipt(
        self, receipt: dict[str, Any], *, save: bool = True
    ) -> None:
        records = self.receipts.setdefault("receipts", [])
        sha = str(receipt.get("source_sha256", "")).lower()
        filename = str(
            receipt.get("source_filename")
            or receipt.get("import_filename")
            or receipt.get("document_path")
            or ""
        ).strip()
        index = None
        for idx, current in enumerate(records):
            current_sha = str(current.get("source_sha256", "")).lower()
            current_filename = str(
                current.get("source_filename")
                or current.get("import_filename")
                or current.get("document_path")
                or ""
            ).strip()
            if sha and current_sha == sha:
                index = idx
                break
            if filename and current_filename == filename:
                index = idx
                break
        receipt = dict(receipt)
        receipt["system"] = "opencontracts"
        receipt["updated_at"] = time.time()
        if index is None:
            records.append(receipt)
        else:
            merged = dict(records[index])
            merged.update({k: v for k, v in receipt.items() if v is not None})
            records[index] = merged
        if save:
            self._save_receipts()

    def _receipt_hints(
        self, sha256_value: str, logical_filename: str
    ) -> list[dict[str, Any]]:
        hints: list[dict[str, Any]] = []
        wanted_filename = str(logical_filename or "").strip()
        for item in self.receipts.get("receipts", []):
            if not isinstance(item, dict):
                continue
            current_sha = str(item.get("source_sha256", "")).lower()
            prefix = str(item.get("sha256_prefix", "")).lower()
            filenames = {
                str(item.get("source_filename") or "").strip(),
                str(item.get("import_filename") or "").strip(),
            }
            if (
                (current_sha and current_sha == sha256_value)
                or (prefix and sha256_value.startswith(prefix))
                or (wanted_filename and wanted_filename in filenames)
            ):
                hints.append(dict(item))
        return hints

    @staticmethod
    def _normalise_lookup_body(body: Any) -> tuple[dict[str, Any] | None, str | None]:
        if not isinstance(body, dict):
            return None, "REST 路径查询返回了无法识别的数据结构。"
        if body.get("ok") is not True:
            return None, str(body.get("error") or "REST 路径查询返回 ok=false。")
        if not isinstance(body.get("exists"), bool):
            return None, "REST 路径查询缺少布尔字段 exists。"
        return {
            "exists": bool(body.get("exists")),
            "same_content": bool(body.get("same_content", False)),
            "document_id": body.get("document_id"),
            "document_title": body.get("document_title"),
            "document_path": body.get("path"),
            "version_number": body.get("version_number"),
            "processing_status": body.get("processing_status"),
            "corpus_id": body.get("corpus_id"),
            "source": "remote_rest_path_lookup",
        }, None

    async def _remote_lookup_by_filename(
        self, logical_filename: str, sha256_value: str
    ) -> dict[str, Any]:
        read_error = self._read_configuration_error()
        if read_error:
            return {
                "attempted": False,
                "ok": False,
                "complete": False,
                "error": read_error,
            }
        params = {
            "filename": logical_filename,
            "sha256": sha256_value,
        }
        if self.default_corpus_id:
            params["corpus_id"] = self.default_corpus_id
        async with self._remote_query_lock:
            try:
                async with httpx.AsyncClient(
                    base_url=self.base_url,
                    timeout=httpx.Timeout(self.remote_timeout_seconds),
                    verify=self.verify_tls,
                    follow_redirects=False,
                ) as client:
                    response = await client.get(
                        self.lookup_path,
                        headers=self._rest_headers(),
                        params=params,
                    )
                if response.status_code != 200:
                    return {
                        "attempted": True,
                        "ok": False,
                        "complete": False,
                        "http_status": response.status_code,
                        "error": self._safe_error_text(response.text),
                    }
                try:
                    body = response.json()
                except ValueError:
                    return {
                        "attempted": True,
                        "ok": False,
                        "complete": False,
                        "http_status": response.status_code,
                        "error": "REST 路径查询未返回 JSON。",
                    }
                normalized, parse_error = self._normalise_lookup_body(body)
                if parse_error or normalized is None:
                    return {
                        "attempted": True,
                        "ok": False,
                        "complete": False,
                        "http_status": response.status_code,
                        "error": parse_error,
                    }
                return {
                    "attempted": True,
                    "ok": True,
                    "complete": True,
                    **normalized,
                }
            except httpx.TimeoutException:
                return {
                    "attempted": True,
                    "ok": False,
                    "complete": False,
                    "error": "REST 路径查询 OpenContracts 超时。",
                }
            except (httpx.RequestError, OSError) as exc:
                return {
                    "attempted": True,
                    "ok": False,
                    "complete": False,
                    "error": self._safe_error_text(exc),
                }

    def _valid_confirmation(
        self,
        event: AstrMessageEvent,
        sha256_value: str,
        confirmation_id: str,
    ) -> bool:
        try:
            payload = json.loads(
                self.router_state_path.read_text(encoding="utf-8")
            )
            record = payload.get(str(event.unified_msg_origin))
            if not isinstance(record, dict):
                return False
            if record.get("state") != "duplicate_confirmed":
                return False
            stored_id = str(record.get("duplicate_confirmation_id", ""))
            supplied_id = str(confirmation_id or "")
            if not supplied_id or supplied_id != stored_id:
                return False
            confirmed_at = float(record.get("duplicate_confirmed_at", 0))
            if confirmed_at <= 0:
                return False
            if time.time() - confirmed_at > self.confirmation_ttl_seconds:
                return False
            return any(
                str(item.get("sha256", "")).lower() == sha256_value
                for item in record.get("files", [])
                if isinstance(item, dict)
            )
        except Exception:
            return False

    @staticmethod
    def _task_id(event: AstrMessageEvent) -> str | None:
        for key in ("contract_pending_task_id", "contract_task_id"):
            value = event.get_extra(key)
            if value:
                return str(value)
        context = event.get_extra("contract_task_context")
        if isinstance(context, dict) and context.get("task_id"):
            return str(context["task_id"])
        return None

    async def _validated_file(
        self, staged_path: str, expected_sha256: str
    ) -> tuple[Path | None, str | None, str | None]:
        source, error = self._resolve_allowed_file(staged_path)
        if error or source is None:
            return None, None, error
        actual = await asyncio.to_thread(self._calculate_sha256, source)
        expected = (expected_sha256 or "").strip().lower()
        if self.require_expected_sha256 and not expected:
            return None, actual, (
                "当前配置要求 expected_sha256，但调用参数为空。"
            )
        if expected and expected != actual:
            return None, actual, "文件 SHA-256 与任务上下文不一致。"
        return source, actual, None

    @staticmethod
    def _is_path_conflict(status_code: int, body: Any) -> bool:
        if status_code not in {400, 409}:
            return False
        text = json.dumps(body, ensure_ascii=False, default=str).lower()
        signals = (
            "document_path_exists",
            "unique_active_path_per_corpus",
            "duplicate key value violates unique constraint",
            "existing path",
            "path already exists",
        )
        return any(signal in text for signal in signals)

    def _import_filename_candidates(
        self,
        source: Path,
        source_filename: str,
        sha256_value: str,
        *,
        include_hints: bool,
    ) -> list[str]:
        candidates: list[str] = []
        if include_hints and self.use_receipt_path_hints:
            for hint in self._receipt_hints(sha256_value, source_filename):
                for key in ("import_filename", "source_filename"):
                    value = str(hint.get(key) or "").strip()
                    if value:
                        candidates.append(self._safe_filename(value, source))
        candidates.append(self._safe_filename(source_filename, source))
        unique: list[str] = []
        for candidate in candidates:
            if candidate and candidate not in unique:
                unique.append(candidate)
        return unique

    async def _post_import(
        self,
        source: Path,
        import_filename: str,
        data: dict[str, str],
        content_type: str,
    ) -> tuple[httpx.Response | None, Any, str | None]:
        request_data = dict(data)
        request_data["filename"] = import_filename
        try:
            with source.open("rb") as file_handle:
                async with httpx.AsyncClient(
                    base_url=self.base_url,
                    timeout=httpx.Timeout(self.timeout_seconds),
                    verify=self.verify_tls,
                    follow_redirects=False,
                ) as client:
                    response = await client.post(
                        IMPORT_PATH,
                        headers={
                            "Authorization": self._authorization_header(),
                            "Accept": "application/json",
                            "User-Agent": (
                                "AstrBot-OpenContracts-Gateway/0.5.1"
                            ),
                        },
                        data=request_data,
                        files={
                            "file": (
                                import_filename,
                                file_handle,
                                content_type,
                            )
                        },
                    )
        except httpx.TimeoutException:
            return None, None, "连接 OpenContracts 上传接口超时。"
        except (httpx.RequestError, OSError) as exc:
            return None, None, self._safe_error_text(exc)
        try:
            body: Any = response.json()
        except ValueError:
            body = {"raw_text": self._safe_error_text(response.text)}
        return response, body, None

    @filter.llm_tool(name="opencontracts_gateway_status")
    async def opencontracts_gateway_status(
        self,
        event: AstrMessageEvent,
        check: str = "configuration",
    ) -> str:
        """检查 REST 写入配置和路径查重配置。

        Args:
            check(string): 固定填写 configuration。
        """
        del event, check
        write_error = self._write_configuration_error()
        read_error = self._read_configuration_error()
        return self._json_result(
            configured=write_error is None and read_error is None,
            write_configuration_error=write_error,
            read_configuration_error=read_error,
            duplicate_authority="opencontracts_remote_rest_path",
            local_receipts_authoritative=False,
            base_url=self.base_url,
            import_path=IMPORT_PATH,
            lookup_path=self.lookup_path,
            auth_mode=self.auth_mode,
            auth_token_configured=bool(self.auth_token),
            lookup_uses_existing_worker_key=True,
            default_corpus_id=self.default_corpus_id or None,
            default_corpus_slug=self.default_corpus_slug or None,
            receipt_count=len(self.receipts.get("receipts", [])),
            allowed_roots=[str(root) for root in self.allowed_roots],
        )

    @filter.llm_tool(name="opencontracts_check_duplicate")
    async def opencontracts_check_duplicate(
        self,
        event: AstrMessageEvent,
        staged_path: str,
        expected_sha256: str,
        source_filename: str = "",
    ) -> str:
        """通过 OpenContracts REST 路径端点实时判断原始文件路径是否存在。

        Args:
            staged_path(string): 合同路由插件返回的绝对暂存路径。
            expected_sha256(string): 路由任务上下文中的 SHA-256。
            source_filename(string): source_files.original_name；留空时从暂存名恢复。
        """
        del event
        source, actual, error = await self._validated_file(
            staged_path, expected_sha256
        )
        if error or source is None or actual is None:
            return self._json_result(
                success=False,
                status="blocked",
                duplicate=None,
                error=error,
                source_sha256=actual,
                no_request_sent=True,
            )
        logical_filename = self._safe_filename(source_filename, source)
        remote = await self._remote_lookup_by_filename(logical_filename, actual)
        if not remote.get("ok") or not remote.get("complete"):
            return self._json_result(
                success=False,
                status="unknown",
                duplicate=None,
                source_sha256=actual,
                source_filename=logical_filename,
                error=remote.get("error")
                or "无法通过 OpenContracts REST 完成路径重复检查。",
                remote_lookup=remote,
                local_receipts_ignored_for_negative_result=True,
                side_effects=False,
            )
        exists = bool(remote.get("exists"))
        match = {
            key: remote.get(key)
            for key in (
                "document_id",
                "document_title",
                "document_path",
                "version_number",
                "processing_status",
                "same_content",
                "corpus_id",
            )
            if remote.get(key) is not None
        }
        return self._json_result(
            success=True,
            status="duplicate" if exists else "new",
            duplicate=exists,
            same_content=bool(remote.get("same_content")),
            source_sha256=actual,
            source_filename=logical_filename,
            matches=[match] if exists else [],
            remote_lookup={"attempted": True, "complete": True},
            duplicate_authority="opencontracts_remote_rest_path",
            local_receipts_authoritative=False,
            side_effects=False,
        )

    @filter.llm_tool(name="opencontracts_upload_document")
    async def opencontracts_upload_document(
        self,
        event: AstrMessageEvent,
        staged_path: str,
        expected_sha256: str,
        source_filename: str = "",
        title: str = "",
        description: str = "",
        custom_meta: dict | None = None,
        duplicate_confirmation_id: str = "",
    ) -> str:
        """上传新合同，或在客户确认后向同一 OpenContracts 路径写入新版本。

        Args:
            staged_path(string): 合同路由插件返回的绝对暂存路径。
            expected_sha256(string): 路由任务上下文中的 SHA-256。
            source_filename(string): source_files.original_name，禁止使用暂存文件名。
            title(string): 文档标题；留空时使用文件名。
            description(string): 可选文档说明。
            custom_meta(object): 可选非敏感业务元数据。
            duplicate_confirmation_id(string): 路由插件生成的重复确认编号；新文件留空。
        """
        write_error = self._write_configuration_error()
        read_error = self._read_configuration_error()
        if write_error or read_error:
            return self._json_result(
                success=False,
                status="blocked",
                upload_status="not_started",
                failure_stage="configuration",
                error=write_error or read_error,
            )
        source, actual_sha256, error = await self._validated_file(
            staged_path, expected_sha256
        )
        if error or source is None or actual_sha256 is None:
            return self._json_result(
                success=False,
                status="blocked",
                upload_status="not_started",
                failure_stage="file_validation",
                error=error,
                source_sha256=actual_sha256,
            )

        logical_filename = self._safe_filename(source_filename, source)
        remote = await self._remote_lookup_by_filename(
            logical_filename, actual_sha256
        )
        if not remote.get("ok") or not remote.get("complete"):
            return self._json_result(
                success=False,
                status="blocked",
                upload_status="not_started",
                processing_status="not_started",
                failure_stage="remote_duplicate_check",
                error=remote.get("error")
                or "无法通过 OpenContracts REST 完成路径重复检查。",
                source_filename=logical_filename,
                source_sha256=actual_sha256,
                remote_lookup=remote,
                no_request_sent=True,
            )
        duplicate = bool(remote.get("exists"))
        confirmed = self._valid_confirmation(
            event, actual_sha256, duplicate_confirmation_id
        )
        if duplicate and not confirmed:
            return self._json_result(
                success=False,
                status="confirmation_required",
                duplicate=True,
                same_content=bool(remote.get("same_content")),
                upload_status="not_started",
                processing_status="not_started",
                source_sha256=actual_sha256,
                source_filename=logical_filename,
                document_path=remote.get("document_path"),
                matches=[
                    {
                        key: remote.get(key)
                        for key in (
                            "document_id",
                            "document_title",
                            "document_path",
                            "version_number",
                            "processing_status",
                            "same_content",
                            "corpus_id",
                        )
                        if remote.get(key) is not None
                    }
                ],
                customer_action="confirm_reupload_or_cancel",
                no_request_sent=True,
            )

        final_title = self._normalise_title(title, Path(logical_filename))
        content_type = (
            mimetypes.guess_type(logical_filename)[0]
            or "application/octet-stream"
        )
        safe_custom_meta: dict[str, Any] = {}
        if isinstance(custom_meta, dict):
            safe_custom_meta.update(
                {
                    str(key): value
                    for key, value in custom_meta.items()
                    if str(key) not in RESERVED_META_KEYS
                }
            )
        safe_custom_meta.update(
            {
                "source": "astrbot",
                "source_sha256": actual_sha256,
                "source_filename": logical_filename,
                "astrbot_task_id": self._task_id(event),
            }
        )
        data: dict[str, str] = {
            "title": final_title,
            "description": (description or "")[:2000],
            "make_public": "true" if self.default_make_public else "false",
            "custom_meta": json.dumps(
                safe_custom_meta, ensure_ascii=False
            ),
        }
        if self.default_corpus_id:
            data["add_to_corpus_id"] = self.default_corpus_id

        candidates = self._import_filename_candidates(
            source,
            logical_filename,
            actual_sha256,
            include_hints=bool(duplicate and confirmed),
        )
        last_response: httpx.Response | None = None
        last_body: Any = None
        attempted_filenames: list[str] = []
        for import_filename in candidates:
            attempted_filenames.append(import_filename)
            response, body, transport_error = await self._post_import(
                source,
                import_filename,
                data,
                content_type,
            )
            if transport_error:
                return self._json_result(
                    success=False,
                    status="failed",
                    upload_status="unknown",
                    processing_status="unknown",
                    failure_stage="transport",
                    error=transport_error,
                    source_sha256=actual_sha256,
                    source_filename=logical_filename,
                )
            if response is None:
                return self._json_result(
                    success=False,
                    status="failed",
                    upload_status="unknown",
                    failure_stage="transport",
                    error="OpenContracts 未返回响应。",
                    source_sha256=actual_sha256,
                    source_filename=logical_filename,
                )
            last_response, last_body = response, body
            if response.status_code == 201 and isinstance(body, dict):
                if body.get("ok") and body.get("document_id") is not None:
                    document_id = body.get("document_id")
                    server_status = body.get("status")
                    previous_hints = self._receipt_hints(
                        actual_sha256, logical_filename
                    )
                    previous = previous_hints[0] if previous_hints else {}
                    receipt = {
                        "source_sha256": actual_sha256,
                        "sha256_prefix": actual_sha256[:20],
                        "source_filename": logical_filename,
                        "import_filename": import_filename,
                        "document_id": document_id,
                        "document_title": final_title,
                        "document_path": remote.get("document_path"),
                        "corpus_id": self.default_corpus_id or None,
                        "corpus_slug": self.default_corpus_slug or None,
                        "server_import_status": server_status,
                        "processing_status": "processing",
                        "upload_count": int(previous.get("upload_count", 0)) + 1,
                        "last_task_id": self._task_id(event),
                        "reupload_confirmed": bool(duplicate and confirmed),
                        "source": "gateway_upload",
                    }
                    self._upsert_receipt(receipt)
                    return self._json_result(
                        success=True,
                        status="processing",
                        stored_in_opencontracts=True,
                        upload_status="accepted",
                        processing_status="processing",
                        document_id=document_id,
                        document_title=final_title,
                        source_filename=logical_filename,
                        corpus_id=self.default_corpus_id or None,
                        corpus_slug=self.default_corpus_slug or None,
                        server_import_status=server_status,
                        source_sha256=actual_sha256,
                        duplicate_replaced=bool(duplicate and confirmed),
                        imported_as_new_version=(server_status == "updated"),
                        import_filename=import_filename,
                        path_versioning_enforced=True,
                        duplicate_authority="opencontracts_remote_rest_path",
                        http_status=response.status_code,
                    )

            if self._is_path_conflict(response.status_code, body):
                refreshed = await self._remote_lookup_by_filename(
                    logical_filename, actual_sha256
                )
                return self._json_result(
                    success=False,
                    status="confirmation_required",
                    duplicate=True,
                    upload_status="not_started",
                    processing_status="not_started",
                    source_sha256=actual_sha256,
                    source_filename=logical_filename,
                    document_path=refreshed.get("document_path"),
                    customer_action="confirm_reupload_or_cancel",
                    conflict_detected_during_upload=True,
                    no_retry_with_alternate_path=True,
                )

            if response.status_code in {401, 403}:
                classification = "blocked"
                stage = "authentication_or_permission"
            elif response.status_code == 404:
                classification = "blocked"
                stage = "rest_endpoint_missing"
            elif response.status_code == 413:
                classification = "blocked"
                stage = "upstream_file_limit"
            elif response.status_code == 429:
                classification = "blocked"
                stage = "rate_limit"
            elif 400 <= response.status_code < 500:
                classification = "failed"
                stage = "request_validation"
            else:
                classification = "failed"
                stage = "upstream_service"
            return self._json_result(
                success=False,
                status=classification,
                upload_status="failed",
                processing_status="not_started",
                failure_stage=stage,
                http_status=response.status_code,
                response=body,
                source_filename=logical_filename,
                source_sha256=actual_sha256,
                import_filename=import_filename,
            )

        return self._json_result(
            success=False,
            status="failed",
            upload_status="failed",
            processing_status="not_started",
            failure_stage="reupload_path_resolution",
            error=(
                "已确认重新上传，但无法恢复原有导入文件名。"
                "为避免在 OpenContracts 中创建另一条逻辑路径，本次未继续。"
            ),
            http_status=(
                last_response.status_code if last_response is not None else None
            ),
            response=last_body,
            attempted_filenames=attempted_filenames,
            source_filename=logical_filename,
            source_sha256=actual_sha256,
            no_retry_with_alternate_path=True,
        )

