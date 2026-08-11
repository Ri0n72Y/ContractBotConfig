from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star


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
            max_file_bytes=max(1024, int(config.get("max_file_bytes", 30 * 1024 * 1024))),
            verify_tls=bool(config.get("verify_tls", True)),
            cleanup_sessions=bool(config.get("cleanup_sessions", True)),
        )

    def validation_error(self) -> str | None:
        if not self.base_url.startswith(("http://", "https://")):
            return "Docassemble base_url 必须以 http:// 或 https:// 开头。"
        if not self.api_key:
            return "Docassemble API Key 未配置。"
        if not self.allowed_interviews:
            return "allowed_interviews 为空；MVP 必须显式允许可执行 interview。"
        if self.default_interview and self.default_interview not in self.allowed_interviews:
            return "default_interview 不在 allowed_interviews 中。"
        return None


class DocassembleClient:
    def __init__(self, settings: GatewaySettings) -> None:
        self.settings = settings

    def _headers(self) -> dict[str, str]:
        return {
            "X-API-Key": self.settings.api_key,
            "Accept": "application/json",
            "User-Agent": "AstrBot-Docassemble-Gateway/0.1.0",
        }

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.settings.base_url,
            headers=self._headers(),
            timeout=httpx.Timeout(self.settings.timeout_seconds),
            verify=self.settings.verify_tls,
            follow_redirects=False,
        )

    @staticmethod
    def _safe_error(response: httpx.Response) -> str:
        text = (response.text or "").strip()
        text = re.sub(
            r"(?i)(x-api-key|authorization|api[_ -]?key)\s*[:=]\s*\S+",
            r"\1: [REDACTED]",
            text,
        )
        return text[:1200] or f"HTTP {response.status_code}"

    async def inspect_interview(self, interview: str) -> tuple[bool, str | None]:
        try:
            async with self._client() as client:
                response = await client.get(
                    "/api/interview_data",
                    params={"i": interview},
                )
        except httpx.TimeoutException:
            return False, "连接 Docassemble /api/interview_data 超时。"
        except httpx.RequestError as exc:
            return False, f"连接 Docassemble 失败：{str(exc)[:500]}"
        if response.status_code != 200:
            return False, self._safe_error(response)
        try:
            body = response.json()
        except ValueError:
            return False, "Docassemble /api/interview_data 未返回 JSON。"
        if not isinstance(body, dict) or "names" not in body:
            return False, "Docassemble /api/interview_data 返回结构异常。"
        return True, None

    async def start_session(self, interview: str) -> tuple[dict[str, Any] | None, str | None]:
        try:
            async with self._client() as client:
                response = await client.get(
                    "/api/session/new",
                    params={"i": interview},
                )
        except httpx.TimeoutException:
            return None, "创建 Docassemble session 超时。"
        except httpx.RequestError as exc:
            return None, f"创建 Docassemble session 失败：{str(exc)[:500]}"
        if response.status_code != 200:
            return None, self._safe_error(response)
        try:
            body = response.json()
        except ValueError:
            return None, "Docassemble /api/session/new 未返回 JSON。"
        if not isinstance(body, dict) or not body.get("session"):
            return None, "Docassemble session 响应缺少 session ID。"
        return body, None

    async def set_variables(
        self,
        interview: str,
        session: str,
        secret: str,
        variables: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str | None]:
        payload: dict[str, Any] = {
            "i": interview,
            "session": session,
            "variables": variables,
        }
        if secret:
            payload["secret"] = secret
        try:
            async with self._client() as client:
                response = await client.post("/api/session", json=payload)
        except httpx.TimeoutException:
            return None, "Docassemble 生成请求超时；禁止自动重试。"
        except httpx.RequestError as exc:
            return None, f"Docassemble 生成请求失败；禁止自动重试：{str(exc)[:500]}"
        if response.status_code != 200:
            return None, self._safe_error(response)
        try:
            body = response.json()
        except ValueError:
            return None, "Docassemble /api/session 未返回 JSON。"
        if not isinstance(body, dict):
            return None, "Docassemble /api/session 返回结构异常。"
        return body, None

    async def download_docx(self, file_number: int) -> tuple[bytes | None, str | None]:
        try:
            async with self._client() as client:
                response = await client.get(
                    f"/api/file/{file_number}",
                    params={"extension": "docx"},
                )
        except httpx.TimeoutException:
            return None, "下载 Docassemble DOCX 超时。"
        except httpx.RequestError as exc:
            return None, f"下载 Docassemble DOCX 失败：{str(exc)[:500]}"
        if response.status_code != 200:
            return None, self._safe_error(response)
        data = response.content
        if len(data) > self.settings.max_file_bytes:
            return None, "Docassemble 返回的 DOCX 超过大小限制。"
        if not data.startswith(b"PK\x03\x04"):
            return None, "Docassemble 返回内容不是有效 DOCX/ZIP 文件。"
        return data, None

    async def delete_session(self, interview: str, session: str, secret: str) -> None:
        del secret
        params: dict[str, str] = {"i": interview, "session": session}
        try:
            async with self._client() as client:
                await client.delete("/api/session", params=params)
        except httpx.HTTPError as exc:
            logger.warning("Docassemble session cleanup failed: %s", exc)


class DocassembleGateway(Star):
    """Allowlisted Docassemble API gateway for deterministic DOCX assembly."""

    def __init__(
        self,
        context: Context,
        config: AstrBotConfig | None = None,
    ) -> None:
        super().__init__(context, config)
        self.settings = GatewaySettings.from_config(config or {})
        self.settings.output_dir.mkdir(parents=True, exist_ok=True)
        self.client = DocassembleClient(self.settings)
        self._audit_lock = asyncio.Lock()
        self._audit_path = self.settings.output_dir.parent / "generation_audit.jsonl"

    async def initialize(self) -> None:
        logger.info(
            "Docassemble gateway 0.1.0 initialized: base_url=%s allowed_interviews=%d",
            self.settings.base_url,
            len(self.settings.allowed_interviews),
        )

    @staticmethod
    def _json(**payload: Any) -> str:
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    @staticmethod
    def _safe_filename(value: str) -> str:
        raw = Path(str(value or "contract.docx")).name
        raw = re.sub(r"[<>:\"/\\|?*\x00-\x1f\x7f]+", "_", raw).strip(" .")
        if not raw.lower().endswith(".docx"):
            raw += ".docx"
        encoded = raw.encode("utf-8")
        if len(encoded) <= 180:
            return raw
        stem = Path(raw).stem
        suffix = ".docx"
        out = ""
        for char in stem:
            candidate = f"{out}{char}{suffix}"
            if len(candidate.encode("utf-8")) > 180:
                break
            out += char
        return f"{out or 'contract'}{suffix}"

    def _resolve_interview(self, requested: str) -> tuple[str | None, str | None]:
        interview = str(requested or self.settings.default_interview).strip()
        if not interview:
            return None, "未指定 Docassemble interview，且 default_interview 为空。"
        if interview not in self.settings.allowed_interviews:
            return None, "请求的 Docassemble interview 不在 allowed_interviews 中。"
        return interview, None

    def _descriptor(self, response: dict[str, Any]) -> dict[str, Any] | None:
        value: Any = response
        for part in self.settings.result_descriptor_key.split("."):
            if not isinstance(value, dict):
                return None
            value = value.get(part)
        return value if isinstance(value, dict) else None

    async def _audit(self, payload: dict[str, Any]) -> None:
        record = {
            "timestamp": int(time.time()),
            **payload,
        }
        async with self._audit_lock:
            self._audit_path.parent.mkdir(parents=True, exist_ok=True)
            with self._audit_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    @filter.llm_tool(name="docassemble_gateway_status")
    async def docassemble_gateway_status(
        self,
        event: AstrMessageEvent,
        refresh_interviews: bool = False,
    ) -> str:
        """检查 Docassemble Gateway 配置和 allowlist interview 可用性。

        Args:
            refresh_interviews(boolean): 为 true 时逐个调用 /api/interview_data 核对 allowlist。
        """
        del event
        error = self.settings.validation_error()
        payload: dict[str, Any] = {
            "configured": error is None,
            "configuration_error": error,
            "base_url": self.settings.base_url,
            "default_interview": self.settings.default_interview,
            "allowed_interviews": list(self.settings.allowed_interviews),
            "result_descriptor_key": self.settings.result_descriptor_key,
            "api_key_configured": bool(self.settings.api_key),
        }
        if refresh_interviews and error is None:
            validated: list[str] = []
            invalid: dict[str, str] = {}
            for interview in self.settings.allowed_interviews:
                ok, inspect_error = await self.client.inspect_interview(interview)
                if ok:
                    validated.append(interview)
                else:
                    invalid[interview] = inspect_error or "interview validation failed"
            payload["validated_interviews"] = validated
            payload["invalid_interviews"] = invalid
        return self._json(**payload)

    @filter.llm_tool(name="docassemble_generate_document")
    async def docassemble_generate_document(
        self,
        event: AstrMessageEvent,
        variables: dict,
        interview: str = "",
        output_filename: str = "",
    ) -> str:
        """使用 allowlist 中的 Docassemble interview 生成并取回 DOCX。

        Args:
            variables(object): 一次性注入 interview 的完整变量；不得包含 API Key。
            interview(string): allowlist 中的完整 interview filename；为空时使用 default_interview。
            output_filename(string): 可选本地交付文件名，只接受文件名，不接受路径。
        """
        del event
        config_error = self.settings.validation_error()
        if config_error:
            return self._json(
                success=False,
                status="blocked",
                failure_stage="configuration",
                error=config_error,
                retry_safe=True,
            )
        if not isinstance(variables, dict):
            return self._json(
                success=False,
                status="blocked",
                failure_stage="variables",
                error="variables 必须是 JSON object。",
                retry_safe=True,
            )
        target, target_error = self._resolve_interview(interview)
        if target_error or target is None:
            return self._json(
                success=False,
                status="blocked",
                failure_stage="interview_allowlist",
                error=target_error,
                retry_safe=True,
            )

        session_data, start_error = await self.client.start_session(target)
        if start_error or session_data is None:
            await self._audit(
                {"status": "failed", "stage": "session_start", "interview": target}
            )
            return self._json(
                success=False,
                status="failed",
                failure_stage="session_start",
                error=start_error,
                retry_safe=True,
            )

        session = str(session_data.get("session") or "")
        secret = str(session_data.get("secret") or "")
        try:
            response, generation_error = await self.client.set_variables(
                target,
                session,
                secret,
                variables,
            )
            if generation_error or response is None:
                await self._audit(
                    {"status": "failed", "stage": "generation", "interview": target}
                )
                return self._json(
                    success=False,
                    status="failed",
                    failure_stage="generation",
                    error=generation_error,
                    retry_safe=False,
                )

            question_type = str(response.get("questionType") or "").strip()
            if question_type == "undefined_variable":
                missing = str(response.get("variable") or "").strip()
                await self._audit(
                    {
                        "status": "blocked",
                        "stage": "missing_variable",
                        "interview": target,
                        "missing_variable": missing,
                    }
                )
                return self._json(
                    success=False,
                    status="blocked",
                    failure_stage="missing_variable",
                    missing_variables=[missing] if missing else [],
                    retry_safe=True,
                )

            descriptor = self._descriptor(response)
            if descriptor is None:
                await self._audit(
                    {"status": "blocked", "stage": "result_contract", "interview": target}
                )
                return self._json(
                    success=False,
                    status="blocked",
                    failure_stage="result_contract",
                    error=(
                        "Interview 未返回约定的文件描述对象："
                        f"{self.settings.result_descriptor_key}"
                    ),
                    question_type=question_type or None,
                    question_name=response.get("questionName"),
                    retry_safe=True,
                )

            file_number = descriptor.get("file_number")
            try:
                file_number = int(file_number)
            except (TypeError, ValueError):
                file_number = 0
            extension = str(descriptor.get("extension") or "docx").lower().lstrip(".")
            if file_number <= 0 or extension != "docx":
                return self._json(
                    success=False,
                    status="failed",
                    failure_stage="result_contract",
                    error="Docassemble 文件描述缺少有效 DOCX file_number。",
                    retry_safe=True,
                )

            data, download_error = await self.client.download_docx(file_number)
            if download_error or data is None:
                await self._audit(
                    {"status": "failed", "stage": "download", "interview": target}
                )
                return self._json(
                    success=False,
                    status="failed",
                    failure_stage="download",
                    error=download_error,
                    retry_safe=True,
                )

            requested_name = output_filename or str(descriptor.get("filename") or "contract.docx")
            safe_name = self._safe_filename(requested_name)
            destination = self.settings.output_dir / f"{uuid.uuid4().hex[:12]}_{safe_name}"
            destination.write_bytes(data)
            await self._audit(
                {
                    "status": "ready",
                    "stage": "complete",
                    "interview": target,
                    "file_number": file_number,
                    "output_path": str(destination),
                    "size_bytes": len(data),
                }
            )
            return self._json(
                success=True,
                status="ready",
                interview=target,
                output_path=str(destination),
                output_filename=safe_name,
                source_file_number=file_number,
                size_bytes=len(data),
                delivery_format="docx",
            )
        finally:
            if self.settings.cleanup_sessions and session:
                await self.client.delete_session(target, session, secret)
