# Contract Bot 当前版本基线

## 插件

- astrbot_plugin_contract_doc_preconverter: 0.1.3
- astrbot_plugin_contract_docx_generator: 0.5.1
- astrbot_plugin_contract_download_delivery: 0.2.4
- astrbot_plugin_contract_file_router: 0.5.7
- astrbot_plugin_contract_generation_flow: 0.7.2
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

- contract_docassemble_builder: 1.27（generation protocol v7）
- contract_master_orchestrator: 1.25（generation policy protocol 2）
- contract_opencontracts_operator: 1.17

正式合同生成链路见 `docs/architecture/ai-docx-generation.md`；Persona 绑定以 `personas/bindings.json` 为准。新合同生成按“专用模板 -> 历史参考 -> AI 自组织结构”回退，不要求仓库内存在通用合同骨架。正式生成 handoff 必须显式携带 generation_policy_protocol=2 与 fallback_policy；strict 指定模板身份按精确 document slug 或唯一标准化标题确定，语义相似不构成身份验证。普通模式的模板绑定也必须来自本轮生成资产搜索候选。写操作 timeout/cancel 按 commit-unknown、retry_safe=false 处理；HTTPS 已发布但 draft finalize 失败返回 PARTIAL 而不是 READY。业务模板、企业参数和历史合同不进入代码仓库。