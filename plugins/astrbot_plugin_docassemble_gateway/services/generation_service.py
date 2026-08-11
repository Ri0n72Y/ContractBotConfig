from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

from ..clients.docassemble_client import DocassembleClient
from ..config.settings import GatewaySettings


class GenerationService:
    """Validate generation input and map Docassemble output to a local DOCX."""

    SAFE_VARIABLE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
    MAX_VARIABLES_BYTES = 256 * 1024

    def __init__(
        self,
        settings: GatewaySettings,
        client: DocassembleClient,
    ) -> None:
        self.settings = settings
        self.client = client
        self.settings.output_dir.mkdir(parents=True, exist_ok=True)
        self._audit_lock = asyncio.Lock()
        self._audit_path = (
            self.settings.output_dir.parent / "generation_audit.jsonl"
        )

    @staticmethod
    def _safe_filename(value: str) -> str:
        raw = Path(str(value or "contract.docx")).name
        raw = re.sub(
            r"[<>:\"/\\|?*\x00-\x1f\x7f]+",
            "_",
            raw,
        ).strip(" .")
        if not raw.lower().endswith(".docx"):
            raw += ".docx"
        if len(raw.encode("utf-8")) <= 180:
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

    def resolve_interview(
        self,
        requested: str,
    ) -> tuple[str | None, str | None]:
        interview = str(
            requested or self.settings.default_interview
        ).strip()
        if not interview:
            return None, "未指定 Docassemble interview，且 default_interview 为空。"
        if interview not in self.settings.allowed_interviews:
            return (
                None,
                "请求的 Docassemble interview 不在 allowed_interviews 中。",
            )
        return interview, None

    def validate_variables(
        self,
        variables: Any,
    ) -> tuple[dict[str, Any] | None, str | None]:
        if not isinstance(variables, dict):
            return None, "variables 必须是 JSON object。"
        invalid = [
            str(name)
            for name in variables
            if not isinstance(name, str)
            or not self.SAFE_VARIABLE_NAME.fullmatch(name)
        ]
        if invalid:
            return (
                None,
                "variables 只能使用安全的顶层标识符；"
                f"不允许的变量名：{', '.join(invalid[:10])}",
            )
        try:
            encoded = json.dumps(
                variables,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError):
            return None, "variables 必须是可 JSON 序列化的数据。"
        if len(encoded) > self.MAX_VARIABLES_BYTES:
            return None, "variables 超过 256 KiB 限制。"
        return variables, None

    def _descriptor(
        self,
        response: dict[str, Any],
    ) -> dict[str, Any] | None:
        value: Any = response
        for part in self.settings.result_descriptor_key.split("."):
            if not isinstance(value, dict):
                return None
            value = value.get(part)
        return value if isinstance(value, dict) else None

    async def _audit(self, payload: dict[str, Any]) -> None:
        record = {"timestamp": int(time.time()), **payload}
        async with self._audit_lock:
            self._audit_path.parent.mkdir(parents=True, exist_ok=True)
            with self._audit_path.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        record,
                        ensure_ascii=False,
                        default=str,
                    )
                    + "\n"
                )

    async def generate(
        self,
        *,
        variables: Any,
        interview: str,
        output_filename: str,
    ) -> dict[str, Any]:
        config_error = self.settings.validation_error()
        if config_error:
            return {
                "success": False,
                "status": "blocked",
                "failure_stage": "configuration",
                "error": config_error,
                "retry_safe": True,
            }

        safe_variables, variable_error = self.validate_variables(variables)
        if variable_error or safe_variables is None:
            return {
                "success": False,
                "status": "blocked",
                "failure_stage": "variables",
                "error": variable_error,
                "retry_safe": True,
            }

        target, target_error = self.resolve_interview(interview)
        if target_error or target is None:
            return {
                "success": False,
                "status": "blocked",
                "failure_stage": "interview_allowlist",
                "error": target_error,
                "retry_safe": True,
            }

        session_data, start_error = await self.client.start_session(target)
        if start_error or session_data is None:
            await self._audit(
                {
                    "status": "failed",
                    "stage": "session_start",
                    "interview": target,
                }
            )
            return {
                "success": False,
                "status": "failed",
                "failure_stage": "session_start",
                "error": start_error,
                "retry_safe": True,
            }

        session = str(session_data.get("session") or "")
        secret = str(session_data.get("secret") or "")
        try:
            response, generation_error = await self.client.set_variables(
                target,
                session,
                secret,
                safe_variables,
            )
            if generation_error or response is None:
                await self._audit(
                    {
                        "status": "failed",
                        "stage": "generation",
                        "interview": target,
                    }
                )
                return {
                    "success": False,
                    "status": "failed",
                    "failure_stage": "generation",
                    "error": generation_error,
                    "retry_safe": False,
                }

            question_type = str(
                response.get("questionType") or ""
            ).strip()
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
                return {
                    "success": False,
                    "status": "blocked",
                    "failure_stage": "missing_variable",
                    "missing_variables": [missing] if missing else [],
                    "retry_safe": True,
                }

            descriptor = self._descriptor(response)
            if descriptor is None:
                await self._audit(
                    {
                        "status": "blocked",
                        "stage": "result_contract",
                        "interview": target,
                    }
                )
                return {
                    "success": False,
                    "status": "blocked",
                    "failure_stage": "result_contract",
                    "error": (
                        "Interview 未返回约定的文件描述对象："
                        f"{self.settings.result_descriptor_key}"
                    ),
                    "question_type": question_type or None,
                    "question_name": response.get("questionName"),
                    "retry_safe": True,
                }

            descriptor_status = str(
                descriptor.get("status") or ""
            ).strip().lower()
            file_number = descriptor.get("file_number")
            try:
                file_number = int(file_number)
            except (TypeError, ValueError):
                file_number = 0
            extension = str(
                descriptor.get("extension") or ""
            ).lower().lstrip(".")
            if (
                descriptor_status != "complete"
                or file_number <= 0
                or extension != "docx"
            ):
                return {
                    "success": False,
                    "status": "failed",
                    "failure_stage": "result_contract",
                    "error": (
                        "Docassemble 文件描述必须声明 status=complete，"
                        "并包含有效 DOCX file_number。"
                    ),
                    "retry_safe": True,
                }

            data, download_error = await self.client.download_docx(
                file_number
            )
            if download_error or data is None:
                await self._audit(
                    {
                        "status": "failed",
                        "stage": "download",
                        "interview": target,
                    }
                )
                return {
                    "success": False,
                    "status": "failed",
                    "failure_stage": "download",
                    "error": download_error,
                    "retry_safe": True,
                }

            requested_name = output_filename or str(
                descriptor.get("filename") or "contract.docx"
            )
            safe_name = self._safe_filename(requested_name)
            destination = (
                self.settings.output_dir
                / f"{uuid.uuid4().hex[:12]}_{safe_name}"
            )
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
            return {
                "success": True,
                "status": "ready",
                "interview": target,
                "output_path": str(destination),
                "output_filename": safe_name,
                "source_file_number": file_number,
                "size_bytes": len(data),
                "delivery_format": "docx",
            }
        finally:
            if self.settings.cleanup_sessions and session:
                await self.client.delete_session(target, session)
