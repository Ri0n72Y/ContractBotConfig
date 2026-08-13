from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

from .config.settings import DeliverySettings
from .services.publication_service import PublicationService


class ContractDownloadDelivery(Star):
    """Publish allowlisted generated DOCX files through expiring HTTPS links."""

    def __init__(
        self,
        context: Context,
        config: AstrBotConfig | None = None,
    ) -> None:
        super().__init__(context, config)
        self.settings = DeliverySettings.from_config(config or {})
        self.publications = PublicationService(self.settings)
        self._cleanup_task: asyncio.Task | None = None

    async def initialize(self) -> None:
        result = await asyncio.to_thread(self.publications.cleanup_expired)
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info(
            "Contract download delivery 0.1.0 initialized: configured=%s "
            "ttl_seconds=%d cleanup_removed=%d",
            self.settings.validation_error() is None,
            self.settings.ttl_seconds,
            result.get("removed", 0),
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
            await asyncio.sleep(self.settings.cleanup_interval_seconds)
            result = await asyncio.to_thread(self.publications.cleanup_expired)
            if result.get("skipped_unsafe"):
                logger.warning(
                    "Contract download cleanup skipped unsafe token directories: %d",
                    result["skipped_unsafe"],
                )

    @staticmethod
    def _json(**payload: Any) -> str:
        return json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            default=str,
        )

    @filter.llm_tool(name="contract_download_delivery_status")
    async def contract_download_delivery_status(
        self,
        event: AstrMessageEvent,
    ) -> str:
        """检查临时合同下载发布配置和清理状态。"""
        del event
        cleanup = await asyncio.to_thread(self.publications.cleanup_expired)
        error = self.settings.validation_error()
        return self._json(
            configured=error is None,
            configuration_error=error,
            public_base_url=self.settings.public_base_url,
            ttl_seconds=self.settings.ttl_seconds,
            max_file_bytes=self.settings.max_file_bytes,
            allowed_source_dirs=[
                str(path) for path in self.settings.allowed_source_dirs
            ],
            cleanup=cleanup,
        )

    @filter.llm_tool(name="publish_contract_download")
    async def publish_contract_download(
        self,
        event: AstrMessageEvent,
        source_path: str,
        filename: str = "",
    ) -> str:
        """将已生成且位于白名单目录中的 DOCX 发布为临时 HTTPS 下载链接。

        Args:
            source_path(string): Docassemble Gateway 返回的 output_path。
            filename(string): 可选客户下载文件名；为空时使用源文件名。
        """
        del event
        result = await asyncio.to_thread(
            self.publications.publish,
            source_path=source_path,
            filename=filename,
        )
        return self._json(**result)
