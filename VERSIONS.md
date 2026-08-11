# Contract Bot 当前版本基线

## 插件

- astrbot_plugin_contract_doc_preconverter: 0.1.3
- astrbot_plugin_contract_file_router: 0.5.4
- astrbot_plugin_contract_handoff_policy: 0.4.5
- astrbot_plugin_docassemble_gateway: 0.1.0
- astrbot_plugin_opencontracts_gateway: 0.6.1
- astrbot_plugin_wecom_final_result_guard: 0.3.4

## Skills

- contract-direct-analysis: 1.14
- contract-opencontracts: 1.16.2
- contract-docassemble: 1.15
- contract-result-verification: 1.16.3
- contract-orchestrator: 1.15.3
- contract-conversation-control: 1.15

## 人格

- contract_docassemble_builder: 1.15
- contract_master_orchestrator: 1.17
- contract_opencontracts_operator: 1.16

## 当前状态

Phase 2-A 使用 OpenContracts 公开 MCP 与 WorkerKey 文件导入两个能力面，并为合同文书生成增加 Docassemble API Gateway：

- AstrBot 配置 OpenContracts 公开 `/mcp/`，Operator 使用任务上下文中的 `targets.opencontracts` 作为目标 `corpus_slug`；
- 公开 MCP 的 `list_documents`、`get_document_text` 和 `search_corpus` 提供合同发现、正文读取和语义检索；
- OpenContracts 上传网关使用 WorkerKey 向其绑定 Corpus 调用官方 `/api/imports/documents/` 写入端点；
- `.doc` 文件在进入 Contract File Router 前由 DOC Preconverter 0.1.3 通过 Gotenberg/LibreOffice 转换为 PDF；
- Router 0.5.4 在 `main.py` 定义实际 `Main` Star 入口类，并把三个事件处理器重新注册到 `main` 模块；导入 `runtime.py` 时产生的临时 Star 与 Handler 注册会在入口加载时移除；
- Router 0.5.4 使用 AstrBot `File.get_file()` 暂存文件，并从原始文件名确定性提取唯一有效日期作为 `identity_hints.contract_date`；正文日期字段为空时 Master 直接采用该日期，不再向客户提问；
- Router 0.5.4 增加 `awaiting_blocked_resolution`：`BLOCKED` 后保留 pending 和暂存文件，客户补充信息或回复“继续”时复用原文件；只有“结束/取消”或后续流程结束才清理；
- Result Guard 0.3.4 区分日期、标题、身份与系统阻断，即使缺少显式 BLOCKED 标记也可识别明确的身份缺失，并向 Router 设置保留信号；
- Conversation Control 1.15 定义阻断恢复输入、偏离文件和结束清理规则；
- 合同远端身份统一为 `YYYY-MM-DD 合同标题`，远端文件名统一为 `YYYY-MM-DD_合同标题.原扩展名`；
- OpenContracts Gateway 不要求或报告配置 Corpus ID，也不保存 MCP 读取凭证；
- Router 直接生成公开 MCP 上传任务契约，Handoff 继续执行兼容校验并阻止旧契约进入 Operator；
- Master 和 Operator Persona/Skill 禁止在上传流程中调用 Shell、Python、通用 HTTP、配置文件读取或直接 MCP JSON-RPC 绕过标准工具链；
- 传输异常、服务端 5xx、成功响应结构异常和未确认版本写入进入人工核查，禁止自动重试；
- OpenContracts Gateway receipt 为追加式上传审计；
- Docassemble Gateway 0.1.0 使用 `http://docassemble`、API Key 和 allowlist interview 调用官方 session/file API；
- Docassemble Builder 1.15 只允许通过 Gateway 完成最终 DOCX 生成，不得使用 Shell、Python、`python-docx`、通用 HTTP 或本地脚本替代；
- ContractBot 使用的 API-first Docassemble interview 完成时必须返回 `contractbot_document.file_number`，Gateway 再通过 `/api/file/<file_number>` 取回并校验 DOCX。

Docassemble MVP 暂可使用管理员 API Key；独立服务账户作为安全债务在 Issue #7 跟踪。

后续仍需在实际 Docassemble 中确认/部署目标合同 interview，并完成 AstrBot WebUI 绑定与真实生成验证。
