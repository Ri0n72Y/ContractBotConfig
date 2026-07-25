# Contract Bot 当前版本基线

## 插件

- astrbot_plugin_contract_file_router: 0.5.0
- astrbot_plugin_contract_handoff_policy: 0.4.4
- astrbot_plugin_opencontracts_gateway: 0.6.1
- astrbot_plugin_wecom_final_result_guard: 0.3.1

## Skills

- contract-direct-analysis: 1.14
- contract-opencontracts: 1.16.1
- contract-docassemble: 1.14
- contract-result-verification: 1.16.1
- contract-orchestrator: 1.15.1
- contract-conversation-control: 1.14

## 人格

- contract_docassemble_builder: 1.14
- contract_master_orchestrator: 1.16
- contract_opencontracts_operator: 1.16

## 当前状态

Phase 2 第一阶段完成 OpenContracts 读取与写入职责拆分，并收紧上传身份和不确定提交状态：

- corpus-scoped OpenContracts MCP 提供合同发现、正文读取、语义检索和处理核验；
- OpenContracts 上传网关使用 WorkerKey 向其绑定 Corpus 调用官方 `/api/imports/documents/` 写入端点；
- 合同远端身份统一为 `YYYY-MM-DD 合同标题`，远端文件名统一为 `YYYY-MM-DD_合同标题.原扩展名`；
- Gateway 不要求或报告配置 Corpus ID，也不保存 MCP 读取凭证；
- 传输异常、服务端 5xx、成功响应结构异常和未确认版本写入进入人工核查，禁止自动重试；
- Gateway receipt 改为追加式上传审计；
- Gateway `main.py` 保持 Tool 适配职责，文件校验、确认校验、导入客户端、结果映射和审计存储位于独立模块。

后续 Phase 2 将继续拆分 Contract File Router 和 WeCom Final Result Guard。
