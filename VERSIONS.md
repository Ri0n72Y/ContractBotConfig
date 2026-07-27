# Contract Bot 当前版本基线

## 插件

- astrbot_plugin_contract_file_router: 0.5.1
- astrbot_plugin_contract_handoff_policy: 0.4.5
- astrbot_plugin_contract_upload_runtime_guard: 0.1.0
- astrbot_plugin_opencontracts_gateway: 0.6.1
- astrbot_plugin_wecom_final_result_guard: 0.3.2

## Skills

- contract-direct-analysis: 1.14
- contract-opencontracts: 1.16.3
- contract-docassemble: 1.14
- contract-result-verification: 1.16.2
- contract-orchestrator: 1.15.3
- contract-conversation-control: 1.14

## 人格

- contract_docassemble_builder: 1.14
- contract_master_orchestrator: 1.17
- contract_opencontracts_operator: 1.17

## 当前状态

Phase 2-A 使用 OpenContracts 公开 MCP 与 WorkerKey 文件导入两个能力面：

- 上传运行时保护插件在 LLM 请求前从暂存文件中本地提取结构化合同身份，不把合同正文作为 Tool Result 返回；
- 主人格上传请求只保留 `transfer_to_opencontracts_operator`，文件读取、Shell、Python、HTTP 等工具从本轮请求中移除；
- Operator 先调用 `list_public_corpuses`，对配置 slug 做精确匹配；配置为空或失效且公开列表只有一个 Corpus 时使用该唯一值；仍有歧义时阻止上传；
- 解析后的 slug 用于 `list_documents`、`get_document_text` 和 `search_corpus`；
- OpenContracts 上传网关使用 WorkerKey 向其绑定 Corpus 调用官方 `/api/imports/documents/` 写入端点；
- 合同远端身份统一为 `YYYY-MM-DD 合同标题`，远端文件名统一为 `YYYY-MM-DD_合同标题.原扩展名`；
- `BLOCKED` 或 `FAILED` 后任务结束并清理暂存文件，管理员修复后由客户重新上传；
- 传输异常、服务端 5xx、成功响应结构异常和未确认版本写入进入人工核查，禁止自动重试；
- Gateway receipt 为追加式上传审计。

合同原文不得出现在通用工具返回、模型回复或应用日志中。后续 Phase 2 将继续拆分 Contract File Router 和 WeCom Final Result Guard。
