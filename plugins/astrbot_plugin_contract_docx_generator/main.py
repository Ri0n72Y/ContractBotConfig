from __future__ import annotations

import asyncio
import contextlib
import json
from pathlib import Path
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

from .config.settings import GeneratorSettings, SUPPORTED_RENDER_PROFILES
from .services.draft_workspace import DraftWorkspaceError, DraftWorkspaceService
from .services.render_service import DocxRenderService, RenderError


PLUGIN_NAME = "astrbot_plugin_contract_docx_generator"
OUTPUT_VERIFIED_KEY = "contract_generation_renderer_output_verified"
OUTPUT_KEY = "contract_generation_renderer_output"
PENDING_DRAFT_KEY = "contract_generation_pending_draft"
PUBLICATION_VERIFIED_KEY = "contract_generation_download_publication_verified"
PUBLICATION_RECORD_KEY = "contract_generation_download_publication_record"


class ContractDocxGenerator(Star):
    """Render complete contract Markdown to DOCX and retain delivered drafts."""

    def __init__(
        self,
        context: Context,
        config: AstrBotConfig | None = None,
    ) -> None:
        super().__init__(context, config)
        self.settings = GeneratorSettings.from_config(config or {})
        self.workspace = DraftWorkspaceService(self.settings)
        self.renderer = DocxRenderService(self.settings)
        self._cleanup_task: asyncio.Task | None = None

    async def initialize(self) -> None:
        self.workspace.initialize()
        removed = await asyncio.to_thread(self.workspace.cleanup_expired)
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info(
            "Contract DOCX generator 0.4.2 initialized: output_dir=%s "
            "max_markdown_chars=%d cleanup_removed=%d",
            self.settings.output_dir,
            self.settings.max_markdown_chars,
            removed,
        )

    async def terminate(self) -> None:
        task = self._cleanup_task
        self._cleanup_task = None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(self.settings.output_cleanup_interval_seconds)
            removed = await asyncio.to_thread(self.workspace.cleanup_expired)
            if removed:
                logger.info("Contract DOCX generator cleanup removed=%d", removed)

    @staticmethod
    def _json(**payload: Any) -> str:
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    @staticmethod
    def _formal_generation(event: AstrMessageEvent) -> bool:
        return bool(event.get_extra("contract_generation_task", False))

    @staticmethod
    def _owner_key(event: AstrMessageEvent) -> str:
        return DraftWorkspaceService.owner_key(
            str(getattr(event, "unified_msg_origin", "") or "")
        )

    @staticmethod
    def _generation_id(event: AstrMessageEvent) -> str:
        return str(
            event.get_extra("contract_generation_generation_id", "") or ""
        ).strip()

    @staticmethod
    def _clear_output(event: AstrMessageEvent) -> None:
        event.set_extra(OUTPUT_VERIFIED_KEY, False)
        event.set_extra(OUTPUT_KEY, {})
        event.set_extra(PENDING_DRAFT_KEY, {})
        event.set_extra(PUBLICATION_VERIFIED_KEY, False)
        event.set_extra(PUBLICATION_RECORD_KEY, {})

    @classmethod
    def _current_output(cls, event: AstrMessageEvent) -> dict[str, Any] | None:
        if not event.get_extra(OUTPUT_VERIFIED_KEY, False):
            return None
        record = event.get_extra(OUTPUT_KEY, {})
        if not isinstance(record, dict):
            return None
        current_generation_id = cls._generation_id(event)
        if str(record.get("generation_id") or "") != current_generation_id:
            return None
        output_path = str(record.get("output_path") or "").strip()
        if not output_path:
            return None
        try:
            if not Path(output_path).expanduser().resolve(strict=True).is_file():
                return None
        except (OSError, RuntimeError, ValueError):
            return None
        return dict(record)

    @classmethod
    def _publication_matches_output(
        cls,
        event: AstrMessageEvent,
        output: dict[str, Any],
    ) -> bool:
        if not event.get_extra(PUBLICATION_VERIFIED_KEY, False):
            return False
        publication = event.get_extra(PUBLICATION_RECORD_KEY, {})
        if not isinstance(publication, dict):
            return False
        generation_id = cls._generation_id(event)
        return bool(
            str(publication.get("generation_id") or "") == generation_id
            and str(publication.get("source_path") or "").strip()
            == str(output.get("output_path") or "").strip()
            and str(publication.get("requested_filename") or "").strip()
            == str(output.get("output_filename") or "").strip()
        )

    def _formal_generation_error(
        self,
        event: AstrMessageEvent,
    ) -> tuple[str, str] | None:
        runtime_missing = event.get_extra(
            "contract_generation_builder_runtime_missing", []
        )
        if isinstance(runtime_missing, list) and runtime_missing:
            return "builder_runtime", "Builder 正式运行工具未完整加载。"
        required_flags = (
            (
                "contract_generation_asset_search_verified",
                "generation_asset_search",
                "正式生成前需要完成一次生成资产检索。",
            ),
            (
                "contract_generation_template_selected_verified",
                "generation_template",
                "正式生成前需要完整读取一个可用合同模板。",
            ),
        )
        for key, stage, message in required_flags:
            if not event.get_extra(key, False):
                return stage, message
        return None

    @staticmethod
    def _terminal_failure(event: AstrMessageEvent) -> str:
        if not event.get_extra("contract_generation_terminal_failure", False):
            return ""
        return str(
            event.get_extra("contract_generation_terminal_failure_reason", "")
            or "本轮生成已发生不可重试失败。"
        )

    @staticmethod
    def _mark_terminal_failure(event: AstrMessageEvent, reason: str) -> None:
        event.set_extra("contract_generation_terminal_failure", True)
        event.set_extra("contract_generation_terminal_failure_reason", str(reason))

    def _profile_for_generation(
        self,
        event: AstrMessageEvent,
        requested: str,
        source_draft: dict[str, Any] | None,
    ) -> str:
        if source_draft:
            selected = str(source_draft.get("render_profile") or "standard_contract").strip()
        elif self._formal_generation(event):
            selected = str(
                event.get_extra("contract_generation_selected_render_profile", "")
                or "standard_contract"
            ).strip()
        else:
            return self.renderer.validate_render_profile(requested)

        selected = selected or "standard_contract"
        if selected not in SUPPORTED_RENDER_PROFILES:
            logger.warning(
                "Unsupported render_profile=%s; falling back to standard_contract",
                selected,
            )
            return "standard_contract"
        return selected

    @staticmethod
    def _record_output(
        event: AstrMessageEvent,
        result: dict[str, Any],
        *,
        draft_id: str | None,
    ) -> None:
        record: dict[str, Any] = {
            "generation_id": str(
                event.get_extra("contract_generation_generation_id", "") or ""
            ),
            "output_path": result["output_path"],
            "output_filename": result["output_filename"],
            "size_bytes": result["size_bytes"],
            "renderer": PLUGIN_NAME,
            "render_profile": result["render_profile"],
        }
        if draft_id:
            record["draft_id"] = draft_id
        event.set_extra(OUTPUT_KEY, record)
        event.set_extra(OUTPUT_VERIFIED_KEY, True)

    def _idempotent_output_response(
        self,
        record: dict[str, Any],
    ) -> str:
        return self._json(
            success=True,
            status="ready",
            output_path=record.get("output_path"),
            output_filename=record.get("output_filename"),
            size_bytes=record.get("size_bytes"),
            render_profile=record.get("render_profile"),
            renderer=record.get("renderer") or PLUGIN_NAME,
            generation_id=record.get("generation_id"),
            draft_id=record.get("draft_id"),
            draft_saved=bool(record.get("draft_id")),
            idempotent=True,
        )

    async def _save_draft_payload(
        self,
        event: AstrMessageEvent,
        payload: dict[str, Any],
    ) -> str:
        manifest = await asyncio.to_thread(
            self.workspace.save_finalized,
            owner_key=self._owner_key(event),
            generation_id=str(payload.get("generation_id") or ""),
            template_asset_id=str(payload.get("template_asset_id") or ""),
            template_document_slug=str(payload.get("template_document_slug") or ""),
            document_title=str(payload.get("document_title") or ""),
            output_filename=str(payload.get("output_filename") or ""),
            render_profile=str(payload.get("render_profile") or "standard_contract"),
            markdown=str(payload.get("markdown") or ""),
            output=dict(payload.get("output") or {}),
        )
        return str(manifest.get("draft_id") or "")

    @filter.llm_tool(name="contract_docx_generator_status")
    async def contract_docx_generator_status(
        self,
        event: AstrMessageEvent,
    ) -> str:
        """管理员排障：检查 DOCX 生成器和最终草稿工作区配置。"""
        del event
        removed = await asyncio.to_thread(self.workspace.cleanup_expired)
        return self._json(
            configured=True,
            output_dir=str(self.settings.output_dir),
            supported_render_profiles=list(SUPPORTED_RENDER_PROFILES),
            max_markdown_chars=self.settings.max_markdown_chars,
            max_read_chars=self.settings.max_chunk_chars,
            max_file_bytes=self.settings.max_file_bytes,
            cleanup_removed=removed,
        )

    @filter.llm_tool(name="get_latest_contract_draft")
    async def get_latest_contract_draft(
        self,
        event: AstrMessageEvent,
    ) -> str:
        """管理员/兼容用途：取得当前会话最近一次成功交付草稿的元数据。"""
        try:
            manifest = await asyncio.to_thread(
                self.workspace.latest_finalized,
                owner_key=self._owner_key(event),
            )
        except DraftWorkspaceError as exc:
            return self._json(
                success=False,
                status="failed",
                failure_stage="draft_lookup",
                error=str(exc),
                retry_safe=True,
            )
        if manifest is None:
            return self._json(
                success=False,
                status="blocked",
                failure_stage="draft_lookup",
                error="当前会话没有可继续编辑的已交付合同草稿。",
                retry_safe=True,
            )
        return self._json(
            success=True,
            status="ready",
            draft_id=manifest.get("draft_id"),
            generation_id=manifest.get("generation_id"),
            template_asset_id=manifest.get("template_asset_id"),
            template_document_slug=manifest.get("template_document_slug"),
            document_title=manifest.get("document_title"),
            output_filename=manifest.get("output_filename"),
            render_profile=manifest.get("render_profile"),
            total_chars=manifest.get("markdown_chars"),
            finalized=True,
        )

    @filter.llm_tool(name="read_latest_contract_draft")
    async def read_latest_contract_draft(
        self,
        event: AstrMessageEvent,
        max_chars: int = 60000,
    ) -> str:
        """一次取得当前会话最近成功交付合同草稿的元数据和首段正文。"""
        try:
            result = await asyncio.to_thread(
                self.workspace.read_latest,
                owner_key=self._owner_key(event),
                max_chars=int(max_chars),
            )
        except (DraftWorkspaceError, OSError, TypeError, ValueError) as exc:
            return self._json(
                success=False,
                status="blocked",
                failure_stage="draft_read",
                error=str(exc),
                retry_safe=True,
            )
        if result is None:
            return self._json(
                success=False,
                status="blocked",
                failure_stage="draft_lookup",
                error="当前会话没有可继续编辑的已交付合同草稿。",
                retry_safe=True,
            )
        return self._json(success=True, status="ready", **result)

    @filter.llm_tool(name="read_contract_draft")
    async def read_contract_draft(
        self,
        event: AstrMessageEvent,
        draft_id: str,
        char_offset: int = 0,
        max_chars: int = 60000,
    ) -> str:
        """仅在上一版草稿有 next_offset 时继续读取后续 Markdown。"""
        try:
            result = await asyncio.to_thread(
                self.workspace.read,
                owner_key=self._owner_key(event),
                draft_id=draft_id,
                char_offset=int(char_offset),
                max_chars=int(max_chars),
            )
        except (DraftWorkspaceError, OSError, TypeError, ValueError) as exc:
            return self._json(
                success=False,
                status="blocked",
                failure_stage="draft_read",
                error=str(exc),
                retry_safe=True,
            )
        return self._json(success=True, status="ready", **result)

    @filter.llm_tool(name="finalize_contract_draft")
    async def finalize_contract_draft(
        self,
        event: AstrMessageEvent,
    ) -> str:
        """内部工具：成功发布后把本轮 Markdown 保存为下一轮可修改草稿。"""
        current = self._current_output(event)
        if current is None:
            return self._json(
                success=False,
                status="blocked",
                failure_stage="draft_finalize",
                error="本轮没有可持久化的已生成 DOCX。",
                retry_safe=True,
            )
        if current.get("draft_id"):
            return self._json(
                success=True,
                status="ready",
                generation_id=current.get("generation_id"),
                draft_id=current.get("draft_id"),
                draft_saved=True,
                idempotent=True,
            )
        if not self._publication_matches_output(event, current):
            return self._json(
                success=False,
                status="blocked",
                failure_stage="draft_finalize",
                error="本轮 DOCX 尚未完成与当前 generation 匹配的 HTTPS 发布。",
                retry_safe=True,
            )

        pending = event.get_extra(PENDING_DRAFT_KEY, {})
        if not isinstance(pending, dict) or not pending:
            return self._json(
                success=False,
                status="blocked",
                failure_stage="draft_finalize",
                error="本轮没有待持久化的合同草稿。",
                retry_safe=True,
            )
        if str(pending.get("generation_id") or "") != self._generation_id(event):
            return self._json(
                success=False,
                status="blocked",
                failure_stage="draft_finalize",
                error="待持久化草稿不属于当前 generation。",
                retry_safe=True,
            )
        try:
            draft_id = await self._save_draft_payload(event, pending)
        except (DraftWorkspaceError, OSError, TypeError, ValueError) as exc:
            logger.warning("Delivered contract draft persistence failed: %s", exc)
            return self._json(
                success=False,
                status="failed",
                failure_stage="draft_finalize",
                error=str(exc),
                retry_safe=True,
            )
        if not draft_id:
            return self._json(
                success=False,
                status="failed",
                failure_stage="draft_finalize",
                error="草稿持久化未返回 draft_id。",
                retry_safe=True,
            )

        current["draft_id"] = draft_id
        event.set_extra(OUTPUT_KEY, current)
        event.set_extra(OUTPUT_VERIFIED_KEY, True)
        event.set_extra(PENDING_DRAFT_KEY, {})
        return self._json(
            success=True,
            status="ready",
            generation_id=self._generation_id(event),
            draft_id=draft_id,
            draft_saved=True,
            idempotent=False,
        )

    @filter.llm_tool(name="generate_contract_docx")
    async def generate_contract_docx(
        self,
        event: AstrMessageEvent,
        document_title: str,
        document_markdown: str,
        output_filename: str = "",
        render_profile: str = "standard_contract",
        source_draft_id: str = "",
    ) -> str:
        """把完整合同 Markdown 一次生成可编辑 DOCX。"""
        current = self._current_output(event)
        if current is not None:
            return self._idempotent_output_response(current)

        self._clear_output(event)

        source_draft: dict[str, Any] | None = None
        source_id = str(source_draft_id or "").strip()
        if source_id:
            try:
                source_draft = await asyncio.to_thread(
                    self.workspace.read,
                    owner_key=self._owner_key(event),
                    draft_id=source_id,
                    char_offset=0,
                    max_chars=1000,
                )
            except (DraftWorkspaceError, OSError, TypeError, ValueError) as exc:
                return self._json(
                    success=False,
                    status="blocked",
                    failure_stage="source_draft",
                    error=str(exc),
                    retry_safe=True,
                )

        if self._formal_generation(event):
            terminal_reason = self._terminal_failure(event)
            if terminal_reason:
                return self._json(
                    success=False,
                    status="blocked",
                    failure_stage="terminal_failure",
                    error=terminal_reason,
                    retry_safe=False,
                )
            if source_draft is None:
                guard_error = self._formal_generation_error(event)
                if guard_error:
                    stage, message = guard_error
                    return self._json(
                        success=False,
                        status="blocked",
                        failure_stage=stage,
                        error=message,
                        retry_safe=True,
                    )

        title = str(document_title or "").strip()
        markdown = str(document_markdown or "").strip()
        if not title or not markdown:
            return self._json(
                success=False,
                status="blocked",
                failure_stage="document_input",
                error="document_title 和 document_markdown 不能为空。",
                retry_safe=True,
            )
        if len(markdown) > self.settings.max_markdown_chars:
            return self._json(
                success=False,
                status="blocked",
                failure_stage="document_markdown_size",
                error="document_markdown 超过允许长度。",
                max_markdown_chars=self.settings.max_markdown_chars,
                retry_safe=True,
            )

        try:
            profile = self._profile_for_generation(
                event,
                render_profile,
                source_draft,
            )
            filename = self.renderer.normalize_filename(
                output_filename,
                fallback=self.renderer.normalize_filename(title, "contract.docx"),
            )
            result = await asyncio.to_thread(
                self.renderer.render,
                document_title=title,
                document_markdown=markdown,
                output_filename=filename,
                render_profile=profile,
            )
        except (RenderError, OSError, TypeError, ValueError) as exc:
            reason = f"DOCX 生成失败：{exc}"
            if self._formal_generation(event):
                self._mark_terminal_failure(event, reason)
            logger.exception("Contract DOCX generation failed")
            return self._json(
                success=False,
                status="failed",
                failure_stage="docx_render",
                error=str(exc),
                retry_safe=False,
            )
        except Exception as exc:
            reason = f"DOCX 生成失败：{exc}"
            if self._formal_generation(event):
                self._mark_terminal_failure(event, reason)
            logger.exception("Contract DOCX generation failed")
            return self._json(
                success=False,
                status="failed",
                failure_stage="docx_render",
                error=str(exc),
                retry_safe=False,
            )

        template_asset_id = str(
            event.get_extra("contract_generation_selected_template_asset_id", "")
            or ""
        )
        template_document_slug = str(
            event.get_extra(
                "contract_generation_selected_template_document_slug", ""
            )
            or ""
        )
        if source_draft is not None:
            template_asset_id = (
                template_asset_id
                or str(source_draft.get("template_asset_id") or "")
            )
            template_document_slug = (
                template_document_slug
                or str(source_draft.get("template_document_slug") or "")
            )

        draft_payload = {
            "generation_id": self._generation_id(event),
            "template_asset_id": template_asset_id,
            "template_document_slug": template_document_slug,
            "document_title": title,
            "output_filename": result["output_filename"],
            "render_profile": result["render_profile"],
            "markdown": markdown,
            "output": {
                "output_filename": result["output_filename"],
                "size_bytes": result["size_bytes"],
                "render_profile": result["render_profile"],
            },
        }

        event.set_extra(PENDING_DRAFT_KEY, draft_payload)
        self._record_output(event, result, draft_id=None)
        logger.info(
            "Contract DOCX generated: generation_id=%s source_draft=%s draft_id=%s filename=%s size=%d",
            self._generation_id(event),
            source_id or "<new>",
            "<pending-delivery>",
            result["output_filename"],
            result["size_bytes"],
        )
        return self._json(
            **result,
            renderer=PLUGIN_NAME,
            generation_id=self._generation_id(event),
            source_draft_id=source_id or None,
            draft_id=None,
            draft_saved=False,
            idempotent=False,
        )
