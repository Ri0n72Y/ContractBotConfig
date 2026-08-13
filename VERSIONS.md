# Contract Bot 当前版本基线

## 插件

- astrbot_plugin_contract_doc_preconverter: 0.1.3
- astrbot_plugin_contract_download_delivery: 0.1.0
- astrbot_plugin_contract_file_router: 0.5.4
- astrbot_plugin_contract_generation_flow: 0.1.0
- astrbot_plugin_contract_handoff_policy: 0.4.6
- astrbot_plugin_docassemble_gateway: 0.1.1
- astrbot_plugin_opencontracts_gateway: 0.6.1
- astrbot_plugin_wecom_final_result_guard: 0.3.5

## Skills

- contract-direct-analysis: 1.14
- contract-opencontracts: 1.16.3
- contract-docassemble: 1.17
- contract-result-verification: 1.16.4
- contract-orchestrator: 1.16
- contract-conversation-control: 1.15

## 人格

- contract_docassemble_builder: 1.16
- contract_master_orchestrator: 1.20
- contract_opencontracts_operator: 1.17

## 当前状态

Phase 2-A 使用 OpenContracts 公开 MCP 与 WorkerKey 文件导入两个能力面，并为合同文书生成增加 Docassemble API Gateway、生成确认流程和临时 HTTPS 下载交付：

- AstrBot 配置 OpenContracts 公开 `/mcp/`，Operator 使用任务上下文中的 `targets.opencontracts` 作为目标 `corpus_slug`；
- 公开 MCP 的 `list_documents`、`get_document_text` 和 `search_corpus` 提供合同发现、正文读取和语义检索；
- OpenContracts 上传网关使用 WorkerKey 向其绑定 Corpus 调用官方 `/api/imports/documents/` 写入端点；
- `.doc` 文件在进入 Contract File Router 前由 DOC Preconverter 0.1.3 通过 Gotenberg/LibreOffice 转换为 PDF；
- Router 0.5.4 维护上传、阻断恢复和暂存文件生命周期；
- Handoff 0.4.6 将合同库读取任务与上传任务分离：合同库读取时 Master ToolSet 只保留 `transfer_to_opencontracts_operator`，并在实际委派前发送处理中提示；
- Contract Generation Flow 0.1.0 为文书生成提供即时回执、生成前用户确认门、开始生成/Docassemble/下载发布阶段提示，以及 Builder 7 工具完整性护栏；
- 新的生成请求先由 Master 形成生成方案和缺失项确认清单，用户明确“确认生成”后才允许真正委派 Builder；确认前的首次委派被转换为 `must_not_execute=true`，不会调用生成工具；
- Builder 正式生成必须同时具备 `list_documents`、`get_document_text`、`search_corpus`、两个 Docassemble Gateway 工具和两个 Contract Download Delivery 工具；缺少任一工具时直接 BLOCKED；
- 正式客户生成必须在本轮实时读取 OpenContracts 参考正文，不得把主人格转述或历史上下文冒充已核验来源；
- 正式客户生成禁止使用文件名包含 `smoke` 的 Docassemble interview；仓库提供 `docs/docassemble/contractbot_document_generation.yml` 作为最小生产生成 interview 样例；
- 合同库读取建立 `READY / PARTIAL / PENDING / FAILED` 状态契约；`total_chars=0`、`page_count=0` 或正文为空视为 PENDING，不再使用本地工具或历史上下文补齐；
- Result Guard 0.3.5 将长合同分析按 UTF-8 字节和自然段拆分为多条企业微信消息，不再显示没有实际附件的虚假提示；
- 合同远端身份统一为 `YYYY-MM-DD 合同标题`，远端文件名统一为 `YYYY-MM-DD_合同标题.原扩展名`；
- OpenContracts Gateway 不要求或报告配置 Corpus ID，也不保存 MCP 读取凭证；
- Router 直接生成公开 MCP 上传任务契约，Handoff 继续执行兼容校验并阻止旧契约进入 Operator；
- Master 和 Operator 在合同库读取、分析和上传任务中禁止 Shell、Grep、Python、通用 HTTP、配置文件读取、直接 MCP JSON-RPC 和本地文件回退；
- 传输异常、服务端 5xx、成功响应结构异常和未确认版本写入进入人工核查，禁止自动重试；
- OpenContracts Gateway receipt 为追加式上传审计；
- Docassemble Gateway 0.1.1 使用 `http://docassemble`、API Key 和 allowlist interview 调用官方 session/file API，并允许 Builder 在生成完成后调用受控下载交付工具；
- Docassemble Builder 1.16 只允许通过 Gateway 完成最终 DOCX 生成，再通过 Contract Download Delivery 0.1.0 发布临时 HTTPS 下载链接；
- Contract Download Delivery 只接受 `allowed_source_dirs` 下的有效 DOCX，复制到 `data/public_downloads/<48-hex-token>/`，默认 30 分钟过期并以非递归安全清理器删除；
- 企业微信最终交付使用 `https://download.ri0n72y.top/contracts/<token>/<filename>`，Master 不向客户展示本地 `output_path`；
- ContractBot 使用的 API-first Docassemble interview 完成时必须返回 `contractbot_document.file_number`，Gateway 再通过 `/api/file/<file_number>` 取回并校验 DOCX。

Docassemble MVP 暂可使用管理员 API Key；独立服务账户作为安全债务在 Issue #7 跟踪。

Docassemble API 直连 smoke 已验证：`docassemble.playground1:contractbot_api_smoke.yml` 可创建 session、生成并下载有效 DOCX；该 interview 仅用于 smoke，不得用于普通客户合同。

临时下载基础设施已验证：AstrBot `/AstrBot/data` 为宿主机 bind mount；`download.ri0n72y.top` 通过 Cloudflare Tunnel 将 `^/contracts/.*` 转发到宿主机 `127.0.0.1:6198`，本地与公网下载 SHA-256 一致。正式 Master → Generation Flow → Builder → OpenContracts → Docassemble Gateway → Download Delivery 端到端验收仍需在 WebUI 更新组件与工具绑定后完成。
