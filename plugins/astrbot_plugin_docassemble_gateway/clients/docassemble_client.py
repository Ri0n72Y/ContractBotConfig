from __future__ import annotations

import re
from typing import Any

import httpx

from astrbot.api import logger

from ..config.settings import GatewaySettings


class DocassembleClient:
    """Small HTTP adapter for the Docassemble session and file APIs."""

    def __init__(self, settings: GatewaySettings) -> None:
        self.settings = settings

    def _headers(self) -> dict[str, str]:
        return {
            "X-API-Key": self.settings.api_key,
            "Accept": "application/json",
            "User-Agent": "AstrBot-Docassemble-Gateway/0.2.0",
        }

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.settings.base_url,
            headers=self._headers(),
            timeout=httpx.Timeout(self.settings.timeout_seconds),
            verify=self.settings.verify_tls,
            follow_redirects=False,
        )

    def _safe_error(self, response: httpx.Response) -> str:
        text = (response.text or "").strip()
        if self.settings.api_key:
            text = text.replace(self.settings.api_key, "[REDACTED]")
        text = re.sub(
            r"(?i)(x-api-key|authorization|api[_ -]?key)\s*[:=]\s*\S+",
            r"\1: [REDACTED]",
            text,
        )
        return text[:1200] or f"HTTP {response.status_code}"

    async def inspect_interview(
        self,
        interview: str,
    ) -> tuple[bool, str | None]:
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

    async def start_session(
        self,
        interview: str,
    ) -> tuple[dict[str, Any] | None, str | None]:
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
            "raw": 0,
        }
        if secret:
            payload["secret"] = secret
        try:
            async with self._client() as client:
                response = await client.post("/api/session", json=payload)
        except httpx.TimeoutException:
            return None, "Docassemble 生成请求超时；禁止自动重试。"
        except httpx.RequestError as exc:
            return (
                None,
                f"Docassemble 生成请求失败；禁止自动重试：{str(exc)[:500]}",
            )
        if response.status_code != 200:
            return None, self._safe_error(response)
        try:
            body = response.json()
        except ValueError:
            return None, "Docassemble /api/session 未返回 JSON。"
        if not isinstance(body, dict):
            return None, "Docassemble /api/session 返回结构异常。"
        return body, None

    async def download_docx(
        self,
        file_number: int,
    ) -> tuple[bytes | None, str | None]:
        try:
            async with self._client() as client:
                response = await client.get(
                    f"/api/file/{file_number}",
                    params={"extension": "docx"},
                    headers={
                        "Accept": (
                            "application/vnd.openxmlformats-officedocument."
                            "wordprocessingml.document, application/octet-stream"
                        )
                    },
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

    async def delete_session(
        self,
        interview: str,
        session: str,
    ) -> None:
        try:
            async with self._client() as client:
                await client.delete(
                    "/api/session",
                    params={"i": interview, "session": session},
                )
        except httpx.HTTPError as exc:
            logger.warning("Docassemble session cleanup failed: %s", exc)
