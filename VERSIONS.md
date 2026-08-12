# Contract Bot 当前版本基线

## 插件

- astrbot_plugin_contract_doc_preconverter: 0.1.3
- astrbot_plugin_contract_file_router: 0.5.4
- astrbot_plugin_contract_handoff_policy: 0.4.6
- astrbot_plugin_docassemble_gateway: 0.1.0
- astrbot_plugin_opencontracts_gateway: 0.6.1
- astrbot_plugin_wecom_final_result_guard: 0.3.5

## Skills

- contract-direct-analysis: 1.14
- contract-opencontracts: 1.16.3
- contract-docassemble: 1.15
- contract-result-verification: 1.16.4
- contract-orchestrator: 1.15.4
- contract-conversation-control: 1.15

## 人格

- contract_docassemble_builder: 1.15
- contract_master_orchestrator: 1.18
- contract_opencontracts_operator: 1.17

## 当前状态

Phase 2-A 使用 OpenContracts 公开 MCP 与 WorkerKey 文件导入两个能力面，并为合同文书生成增加 Docassemble API Gateway：

- AstrBot 配置 OpenContracts 公开 `/mcp/`，Operator 使用任务上下文中的 `targets.opencontracts` 作为目标 `corpus_slug`；
- 公开 MCP 的 `list_documents`、`get_document_text` 和 `search_corpus` 提供合同发现、正文读取和语义检索；
- OpenContracts 上传网关使用 WorkerKey 向其绑定 Corpus 调用官方 `/api/imports/documents/` 写入端点；
- `.doc` 文件在进入 Contract File Router 前由 DOC Preconverter 0.1.3 通过 Gotenberg/LibreOffice 转换为 PDF；
- Router 0.5.4 维护上传、阻断恢复和暂存文件生命周期；
- Handoff 0.4.6 将合同库读取任务与上传任务分离：合同库读取时 Master ToolSet 只保留 `transfer_to_opencontracts_operator`，并在实际委派前发送处理中提示；
- 合同库读取建立 `READY / PARTIAL / PENDING / FAILED` 状态契约；`total_chars=0`、`page_count=0` 或正文为空视为 PENDING，不再使用本地工具或历史上下文补齐；
- Result Guard 0.3.5 将长合同分析按 UTF-8 字节和自然段拆分为多条企业微信消息，不再显示没有实际附件的虚假提示；
- 合同远端身份统一为 `YYYY-MM-DD 合同标题`，远端文件名统一为 `YYYY-MM-DD_合同标题.原扩展名`；
- OpenContracts Gateway 不要求或报告配置 Corpus ID，也不保存 MCP 读取凭证；
- Router 直接生成公开 MCP 上传任务契约，Handoff 继续执行兼容校验并阻止旧契约进入 Operator；
- Master 和 Operator 在合同库读取、分析和上传任务中禁止 Shell、Grep、Python、通用 HTTP、配置文件读取、直接 MCP JSON-RPC 和本地文件回退；
- 传输异常、服务端 5xx、成功响应结构异常和未确认版本写入进入人工核查，禁止自动重试；
- OpenContracts Gateway receipt 为追加式上传审计；
- Docassemble Gateway 0.1.0 使用 `http://docassemble`、API Key 和 allowlist interview 调用官方 session/file API；
- Docassemble Builder 1.15 只允许通过 Gateway 完成最终 DOCX 生成，不得使用 Shell、Python、`python-docx`、通用 HTTP 或本地脚本替代；
- ContractBot 使用的 API-first Docassemble interview 完成时必须返回 `contractbot_document.file_number`，Gateway 再通过 `/api/file/<file_number>` 取回并校验 DOCX。

Docassemble MVP 暂可使用管理员 API Key；独立服务账户作为安全债务在 Issue #7 跟踪。

Docassemble API 直连 smoke 已验证：`docassemble.playground1:contractbot_api_smoke.yml` 可创建 session、生成并下载有效 DOCX；AstrBot Master → Builder → Gateway 的端到端 smoke 仍需在 WebUI 绑定后完成。
