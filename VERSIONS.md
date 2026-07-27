# Contract Bot 当前版本基线

## 插件

- astrbot_plugin_contract_doc_preconverter: 0.1.3
- astrbot_plugin_contract_file_router: 0.5.4
- astrbot_plugin_contract_handoff_policy: 0.4.6
- astrbot_plugin_opencontracts_gateway: 0.6.1
- astrbot_plugin_wecom_final_result_guard: 0.3.5

## Skills

- contract-direct-analysis: 1.14
- contract-opencontracts: 1.16.3
- contract-docassemble: 1.14
- contract-result-verification: 1.16.4
- contract-orchestrator: 1.15.4
- contract-conversation-control: 1.15

## 人格

- contract_docassemble_builder: 1.14
- contract_master_orchestrator: 1.18
- contract_opencontracts_operator: 1.17

## 当前状态

Phase 2-A 使用 OpenContracts 公开 MCP 与 WorkerKey 文件导入两个能力面：

- `.doc` 文件由 DOC Preconverter 通过 Gotenberg/LibreOffice 转换为 PDF；
- Router 0.5.4 维护上传、阻断恢复和暂存文件生命周期；
- Handoff 0.4.6 将合同库读取任务与上传任务分离：数据库读取时只向 Master 暴露 OpenContracts Operator 委派工具，并在实际委派前发送处理中提示；
- 合同库读取建立 `READY / PARTIAL / PENDING / FAILED` 状态契约；`total_chars=0`、`page_count=0` 或空正文视为 PENDING，不再使用本地工具或历史上下文补齐；
- Result Guard 0.3.5 将长合同分析按 UTF-8 字节和自然段拆分为多条企业微信消息，不再显示没有实际附件的虚假提示；
- 上传流程继续使用公开 MCP 的 `list_documents`、`get_document_text`、`search_corpus` 和 WorkerKey 导入网关；
- Gateway 不要求或报告配置 Corpus ID，receipt 继续作为追加式上传审计；
- Master 与 Operator 在合同库读取、分析和上传任务中均禁止 Shell、Grep、Python、通用 HTTP、配置读取、直接 MCP JSON-RPC 和本地文件回退。

临时 HTML/Markdown 报告链接及 Nginx 发布不属于本轮 P0-P1 范围。
