# Contract Bot 当前版本基线

## 插件

- astrbot_plugin_contract_doc_preconverter: 0.1.3
- astrbot_plugin_contract_docx_generator: 0.4.2
- astrbot_plugin_contract_download_delivery: 0.2.4
- astrbot_plugin_contract_file_router: 0.5.7
- astrbot_plugin_contract_generation_flow: 0.6.2
- astrbot_plugin_contract_handoff_policy: 0.5.3
- astrbot_plugin_docassemble_gateway: 0.2.1
- astrbot_plugin_opencontracts_gateway: 0.6.2
- astrbot_plugin_wecom_final_result_guard: 0.3.5

Docassemble Gateway 0.2.1 暂时保留用于回滚，但已退出正式合同生成链。

## Skills

- contract-direct-analysis: 1.14
- contract-opencontracts: 1.16.3
- contract-docassemble: 1.20
- contract-result-verification: 1.16.4
- contract-orchestrator: 1.18
- contract-conversation-control: 1.15

`contract-docassemble` 1.20 暂时保留，但不绑定 Builder。

## 人格

- contract_docassemble_builder: 1.25
- contract_master_orchestrator: 1.23
- contract_opencontracts_operator: 1.17

正式合同生成链路见 `docs/architecture/ai-docx-generation.md`；Persona 绑定以 `personas/bindings.json` 为准。业务模板、企业参数和历史合同不进入代码仓库。