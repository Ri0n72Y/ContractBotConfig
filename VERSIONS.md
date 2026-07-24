# Contract Bot 当前版本基线

## 插件

- astrbot_plugin_contract_file_router: 0.5.0
- astrbot_plugin_contract_handoff_policy: 0.4.2
- astrbot_plugin_opencontracts_gateway: 0.5.1
- astrbot_plugin_wecom_final_result_guard: 0.2.3

## Skills

- contract-direct-analysis: 1.14
- contract-opencontracts: 1.15.1
- contract-docassemble: 1.14
- contract-result-verification: 1.15.1
- contract-orchestrator: 1.14
- contract-conversation-control: 1.14

## 人格

- contract_docassemble_builder: 1.14
- contract_master_orchestrator: 1.14
- contract_opencontracts_operator: 1.14

## 已知状态

此目录保存当前实际落盘、可恢复的完整版本基线。OpenContracts Gateway 0.5.1
仍使用 `/api/imports/documents/lookup/`，而最近日志已确认当前 OpenContracts 服务没有该路由。
该问题尚未在此初始基线中修复；后续应优先基于 OpenContracts MCP 的实际工具发现结果更新
Gateway、相关 Skill 和 OpenContracts Operator 人格，并递增版本号。
