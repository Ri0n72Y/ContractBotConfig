---
name: contract-orchestrator
description: 合同主人格的客户交互、同步委派和上传状态编排。
---

# 合同任务编排

用户选择上传或重新上传后，路由插件先发送简短确认，再保持当前企业微信事件同步委派 `opencontracts_operator`，设置 `background_task=false`。

## 上传流程

1. OpenContracts Operator 通过 corpus-scoped MCP 获取 corpus 信息并按原始文件名搜索合同。
2. MCP 返回已有合同且当前任务没有客户确认时，首行输出 `[CONTRACT_UPLOAD:DUPLICATE_CONFIRMATION_REQUIRED]`。
3. MCP 读取没有完成时，首行输出 `[CONTRACT_UPLOAD:BLOCKED]`，本次不启动写入。
4. 新合同或已有有效确认时，检查 WorkerKey 导入网关并执行写入。
5. 导入参数中的 `source_filename` 使用路由任务上下文的 `original_name`。
6. 文件已接收但正文或检索尚未核验完成时输出 `[CONTRACT_UPLOAD:PROCESSING]`。
7. 正文可读并通过 MCP 检索核验后输出 `[CONTRACT_UPLOAD:COMPLETE]`。
8. 正式执行失败时输出 `[CONTRACT_UPLOAD:FAILED]`。

## 会话控制

等待操作或重复确认期间，只接受当前流程定义的指令。用户发送另一份文件时，路由插件保留当前任务并提示先发送“结束”。`结束`、`取消`和`重新上传`由路由插件确定性处理。

上传任务委派给 `opencontracts_operator`，最终结果在当前企业微信事件中返回。
