from __future__ import annotations

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

from .clients.import_client import ImportClient
from .config.settings import GatewaySettings
from .services.confirmation_service import ConfirmationService
from .services.file_service import FileService
from .services.upload_service import UploadService
from .storage.receipt_store import ReceiptStore


class OpenContractsGateway(Star):
    """WorkerKey-authenticated OpenContracts document import tools."""

    def __init__(
        self,
        context: Context,
        config: AstrBotConfig | None = None,
    ) -> None:
        super().__init__(context, config)
        self.settings = GatewaySettings.from_config(config or {})
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)

        files = FileService(self.settings)
        confirmations = ConfirmationService(
            self.settings.router_state_path,
            self.settings.confirmation_ttl_seconds,
        )
        receipts = ReceiptStore(self.settings.data_dir)
        client = ImportClient(self.settings)
        self.uploads = UploadService(
            self.settings,
            files,
            confirmations,
            client,
            receipts,
        )

    async def initialize(self) -> None:
        logger.info(
            "OpenContracts upload gateway 0.6.2 initialized: "
            "base_url=%s corpus=worker-key-bound",
            self.settings.base_url,
        )

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

    @filter.llm_tool(name="opencontracts_gateway_status")
    async def opencontracts_gateway_status(
        self,
        event: AstrMessageEvent,
        check: str = "configuration",
        contract_date: str = "",
        contract_title: str = "",
        source_filename: str = "",
    ) -> str:
        """检查 WorkerKey 导入配置并返回可用于 MCP 查重的规范化合同身份。

        Args:
            check(string): 固定填写 configuration。
            contract_date(string): 可选合同日期；与合同标题一起提供时返回规范化身份。
            contract_title(string): 可选合同正式标题。
            source_filename(string): 可选原始文件名，用于生成规范化远端文件名。
        """
        del event, check
        return self.uploads.status(
            contract_date=contract_date,
            contract_title=contract_title,
            source_filename=source_filename,
        )

    @filter.llm_tool(name="opencontracts_upload_document")
    async def opencontracts_upload_document(
        self,
        event: AstrMessageEvent,
        staged_path: str,
        expected_sha256: str,
        contract_date: str,
        contract_title: str,
        source_filename: str = "",
        description: str = "",
        custom_meta: dict | None = None,
        duplicate_confirmation_id: str = "",
    ) -> str:
        """向 WorkerKey 绑定的 Corpus 导入合同或写入确认后的新版本。

        Args:
            staged_path(string): 合同路由器返回的绝对暂存路径。
            expected_sha256(string): 路由任务上下文中的 SHA-256。
            contract_date(string): 合同日期，使用 YYYY-MM-DD。
            contract_title(string): 合同正文中的合同标题。
            source_filename(string): source_files.original_name，仅用于保留原始文件名和扩展名。
            description(string): 可选文档说明。
            custom_meta(object): 可选业务元数据。
            duplicate_confirmation_id(string): 路由器签发的重新上传确认编号。
        """
        return await self.uploads.upload(
            session_key=str(event.unified_msg_origin),
            task_id=self._task_id(event),
            staged_path=staged_path,
            expected_sha256=expected_sha256,
            source_filename=source_filename,
            contract_date=contract_date,
            contract_title=contract_title,
            description=description,
            custom_meta=custom_meta,
            duplicate_confirmation_id=duplicate_confirmation_id,
        )
