# Contract Bot 当前版本基线

## 插件

- astrbot_plugin_contract_file_router: 0.5.0
- astrbot_plugin_contract_handoff_policy: 0.4.3
- astrbot_plugin_opencontracts_gateway: 0.6.0
- astrbot_plugin_wecom_final_result_guard: 0.3.0

## Skills

- contract-direct-analysis: 1.14
- contract-opencontracts: 1.16.0
- contract-docassemble: 1.14
- contract-result-verification: 1.16.0
- contract-orchestrator: 1.15.0
- contract-conversation-control: 1.14

## 人格

- contract_docassemble_builder: 1.14
- contract_master_orchestrator: 1.15
- contract_opencontracts_operator: 1.15

## 当前状态

Phase 2 第一阶段完成 OpenContracts 读取与写入职责拆分：

- corpus-scoped OpenContracts MCP 提供合同发现、正文读取、语义检索和处理核验；
- OpenContracts 上传网关使用 WorkerKey 调用官方 `/api/imports/documents/` 写入端点；
- 上传网关不再实现 REST 路径查询，也不保存 MCP 读取凭证；
- Gateway `main.py` 已拆分为配置、文件校验、确认校验、导入客户端、上传服务和审计存储模块；
- 本地 receipt 仅用于上传审计。

后续 Phase 2 将继续拆分 Contract File Router 和 WeCom Final Result Guard。
