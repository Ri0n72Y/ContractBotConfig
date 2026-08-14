from __future__ import annotations

from typing import Any

from astrbot.api.event import AstrMessageEvent


class GenerationIntegrityService:
    """Bind one generation event to the current Gateway output."""

    @staticmethod
    def formal_generation(event: AstrMessageEvent) -> bool:
        return bool(event.get_extra("contract_docassemble_generation_task", False))

    @staticmethod
    def clear_generation_output(event: AstrMessageEvent) -> None:
        event.set_extra("contract_generation_gateway_output_verified", False)
        event.set_extra("contract_generation_gateway_output", {})

    @classmethod
    def record_generation_output(
        cls,
        event: AstrMessageEvent,
        result: dict[str, Any],
    ) -> None:
        cls.clear_generation_output(event)
        output_path = str(result.get("output_path") or "").strip()
        output_filename = str(result.get("output_filename") or "").strip()
        if not (
            result.get("success") is True
            and str(result.get("status") or "").lower() == "ready"
            and output_path
            and output_filename
        ):
            return
        event.set_extra(
            "contract_generation_gateway_output",
            {
                "output_path": output_path,
                "output_filename": output_filename,
                "size_bytes": result.get("size_bytes"),
                "interview": result.get("interview"),
            },
        )
        event.set_extra("contract_generation_gateway_output_verified", True)
