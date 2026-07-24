---
name: contract-orchestrator
description: 合同主人格的客户交互、同步委派和上传状态编排。
---

# 合同任务编排

用户选择上传或重新上传后，路由插件先发送简短确认，再保持当前企业微信事件同步委派 `opencontracts_operator`，设置 `background_task=false`。

## 上传流程

1. 每次上传都由 OpenContracts REST API 实时判断是否存在；不得依据 AstrBot receipt 跳过远端查询。
2. 远端状态无法确认时停止，最终首行输出 `[CONTRACT_UPLOAD:BLOCKED]`。
3. 返回 `confirmation_required` 时停止，最终首行输出 `[CONTRACT_UPLOAD:DUPLICATE_CONFIRMATION_REQUIRED]`。
4. 新文件或已有有效确认时执行上传，并传递原始文件名。
5. 文件已接收但处理尚未核验完成时输出 `[CONTRACT_UPLOAD:PROCESSING]`。
6. 正文可读并通过检索核验后输出 `[CONTRACT_UPLOAD:COMPLETE]`。
7. 正式执行失败时输出 `[CONTRACT_UPLOAD:FAILED]`。

## 会话控制

等待操作或重复确认期间，只接受当前流程定义的指令。用户发送另一份文件时，不覆盖旧任务；提示发送“结束”中断后再重新发送。`结束`、`取消`和`重新上传`由路由插件确定性处理，不交给模型猜测。

上传任务只允许委派给 `opencontracts_operator`。不得调用后台主动消息工具。
