from __future__ import annotations

import json
from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent


class GenerationIntegrityService:
    """Bind one generation event to a real reference document and output."""

    @staticmethod
    def formal_generation(event: AstrMessageEvent) -> bool:
        return bool(event.get_extra("contract_docassemble_generation_task", False))

    @staticmethod
    def resolve_tool_response(
        hook_args: tuple[Any, ...],
        hook_kwargs: dict[str, Any],
    ) -> tuple[Any | None, dict[str, Any] | None, Any | None]:
        tool = hook_kwargs.get("tool")
        tool_args = hook_kwargs.get("tool_args")
        tool_result = hook_kwargs.get("tool_result")
        if tool is None:
            for candidate in hook_args:
                if hasattr(candidate, "name") and not isinstance(candidate, dict):
                    tool = candidate
                    break
        if tool_args is None:
            for candidate in hook_args:
                if isinstance(candidate, dict):
                    tool_args = candidate
                    break
        if tool_result is None:
            for candidate in hook_args:
                if candidate is tool or candidate is tool_args:
                    continue
                if hasattr(candidate, "content") or isinstance(candidate, str):
                    tool_result = candidate
                    break
        return tool, tool_args, tool_result

    @staticmethod
    def tool_result_payload(tool_result: Any) -> dict[str, Any] | None:
        if tool_result is None:
            return None
        if isinstance(tool_result, dict):
            return dict(tool_result)
        if bool(
            getattr(tool_result, "isError", False)
            or getattr(tool_result, "is_error", False)
        ):
            return None

        structured = getattr(tool_result, "structuredContent", None)
        if structured is None:
            structured = getattr(tool_result, "structured_content", None)
        if isinstance(structured, dict):
            return dict(structured)

        pieces: list[str] = []
        if isinstance(tool_result, str):
            pieces.append(tool_result)
        else:
            content = getattr(tool_result, "content", None)
            if isinstance(content, list):
                for item in content:
                    text = (
                        item.get("text")
                        if isinstance(item, dict)
                        else getattr(item, "text", None)
                    )
                    if text is not None:
                        pieces.append(str(text))
        for piece in pieces:
            value = piece.strip()
            if not value:
                continue
            try:
                parsed = json.loads(value)
            except (TypeError, ValueError):
                continue
            if isinstance(parsed, dict):
                return parsed
        return None

    @staticmethod
    def verified_document_listing(
        payload: dict[str, Any],
        tool_args: dict[str, Any] | None,
    ) -> tuple[str, list[str]] | None:
        if payload.get("error") or not isinstance(tool_args, dict):
            return None
        corpus_slug = str(tool_args.get("corpus_slug") or "").strip()
        if not corpus_slug:
            return None
        returned_corpus = str(payload.get("corpus_slug") or "").strip()
        if returned_corpus and returned_corpus != corpus_slug:
            return None
        documents = payload.get("documents")
        if not isinstance(documents, list):
            return None
        try:
            total_count = int(payload.get("total_count", len(documents)) or 0)
        except (TypeError, ValueError):
            return None
        if total_count <= 0 or not documents:
            return None
        slugs: list[str] = []
        for document in documents:
            if not isinstance(document, dict):
                continue
            slug = str(document.get("slug") or document.get("document_slug") or "").strip()
            if slug and slug not in slugs:
                slugs.append(slug)
        return (corpus_slug, slugs) if slugs else None

    @staticmethod
    def verified_document_text(
        payload: dict[str, Any],
        tool_args: dict[str, Any] | None,
        listed_documents: dict[str, list[str]],
    ) -> tuple[str, str] | None:
        if payload.get("error") or not isinstance(tool_args, dict):
            return None
        corpus_slug = str(tool_args.get("corpus_slug") or "").strip()
        document_slug = str(tool_args.get("document_slug") or "").strip()
        if not corpus_slug or not document_slug:
            return None
        listed_slugs = {
            str(value).strip()
            for value in listed_documents.get(corpus_slug, [])
            if str(value).strip()
        }
        if document_slug not in listed_slugs:
            return None
        returned_corpus = str(payload.get("corpus_slug") or "").strip()
        if returned_corpus and returned_corpus != corpus_slug:
            return None
        returned_slug = str(payload.get("document_slug") or "").strip()
        if returned_slug != document_slug:
            return None
        try:
            requested_offset = int(tool_args.get("char_offset", 0) or 0)
            returned_offset = int(payload.get("char_offset", 0) or 0)
            total_chars = int(payload.get("total_chars", 0) or 0)
        except (TypeError, ValueError):
            return None
        text = str(payload.get("text") or "")
        if (
            requested_offset != 0
            or returned_offset != requested_offset
            or total_chars <= 0
            or not text.strip()
        ):
            return None
        return corpus_slug, document_slug

    def verify_reference_result(
        self,
        event: AstrMessageEvent,
        tool: Any,
        tool_args: dict[str, Any] | None,
        tool_result: Any,
    ) -> None:
        if not self.formal_generation(event):
            return
        tool_name = str(getattr(tool, "name", ""))
        if tool_name not in {"list_documents", "get_document_text"}:
            return

        expected_corpus = str(
            event.get_extra("contract_generation_reference_corpus_slug", "") or ""
        ).strip()
        actual_corpus = (
            str(tool_args.get("corpus_slug") or "").strip()
            if isinstance(tool_args, dict)
            else ""
        )
        if expected_corpus and actual_corpus != expected_corpus:
            logger.warning(
                "Generation integrity ignored reference result from unexpected corpus: "
                "expected=%s actual=%s tool=%s",
                expected_corpus,
                actual_corpus or "<empty>",
                tool_name,
            )
            return

        payload = self.tool_result_payload(tool_result)
        if payload is None:
            logger.warning(
                "Generation integrity verification failed: tool=%s result_unparseable=true",
                tool_name,
            )
            return

        if tool_name == "list_documents":
            verified = self.verified_document_listing(payload, tool_args)
            if verified is None:
                logger.warning(
                    "Generation integrity verification failed: "
                    "list_documents returned no corpus-bound usable documents."
                )
                return
            corpus_slug, slugs = verified
            existing = event.get_extra("contract_gateway_reference_documents", {})
            listings = dict(existing) if isinstance(existing, dict) else {}
            current = {
                str(value).strip()
                for value in listings.get(corpus_slug, [])
                if str(value).strip()
            }
            current.update(slugs)
            listings[corpus_slug] = sorted(current)
            event.set_extra("contract_gateway_reference_documents", listings)
            event.set_extra("contract_gateway_reference_list_verified", True)
            logger.info(
                "Generation integrity reference list verified: corpus=%s documents=%d",
                corpus_slug,
                len(slugs),
            )
            return

        existing = event.get_extra("contract_gateway_reference_documents", {})
        listings = dict(existing) if isinstance(existing, dict) else {}
        pair = self.verified_document_text(payload, tool_args, listings)
        if pair is None:
            logger.warning(
                "Generation integrity verification failed: get_document_text did not "
                "match a previously verified corpus/document pair with non-empty first-chunk text."
            )
            return
        corpus_slug, document_slug = pair
        pairs = event.get_extra("contract_gateway_reference_text_pairs", [])
        verified_pairs = (
            [dict(item) for item in pairs if isinstance(item, dict)]
            if isinstance(pairs, list)
            else []
        )
        if not any(
            item.get("corpus_slug") == corpus_slug
            and item.get("document_slug") == document_slug
            for item in verified_pairs
        ):
            verified_pairs.append({"corpus_slug": corpus_slug, "document_slug": document_slug})
        event.set_extra("contract_gateway_reference_text_pairs", verified_pairs)
        event.set_extra("contract_gateway_reference_text_verified", True)
        logger.info(
            "Generation integrity reference text verified: corpus=%s document=%s",
            corpus_slug,
            document_slug,
        )

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
