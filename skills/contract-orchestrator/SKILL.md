---
name: contract-orchestrator
description: 合同主人格的客户交互、合同身份提取、同步委派和上传状态编排。
---

# 合同任务编排

用户选择上传或重新上传后，路由插件先发送简短确认。主人格在当前企业微信事件中完成合同身份提取，再同步委派 `opencontracts_operator`，设置 `background_task=false`。

## 合同身份

上传前必须从当前合同正文提取：

- `contract_date`：统一为 `YYYY-MM-DD`；优先使用合同首页或标题附近明确标注的合同日期，其次使用签署日期，再其次使用明确生效日期；多方签署日期不一致时使用最晚签署日期。
- `contract_title`：使用正文中的正式合同名称，去除文件扩展名、路径和无意义编号前缀。

无法可靠取得任一字段时停止上传，首行输出 `[CONTRACT_UPLOAD:BLOCKED]`，说明需要用户补充合同日期或标题。不得猜测。

调用 `transfer_to_opencontracts_operator` 时，`input` 使用 JSON：

```json
{
  "contract_identity": {
    "contract_date": "2026-07-25",
    "contract_title": "软件开发服务合同"
  }
}
```

远端身份由 OpenContracts Gateway 确定性规范化。通常格式为：

```text
document_title = YYYY-MM-DD 合同标题
normalized_filename = YYYY-MM-DD_合同标题.原扩展名
```

标题含文件名不安全字符或超过 UTF-8 字节限制时，Gateway 会安全处理文件名并追加短哈希；MCP 查重仍使用 Gateway 返回的完整 `identity.document_title`。

## 上传流程

1. OpenContracts Operator 先调用 `opencontracts_gateway_status`，传入合同日期、合同标题和原始文件名，取得规范化 `identity.document_title`。
2. Operator 使用 corpus-scoped MCP 获取 Corpus 信息，并以该 `identity.document_title` 搜索合同。
3. MCP 返回标题完全一致的已有合同，且当前任务没有有效客户确认时，首行输出 `[CONTRACT_UPLOAD:DUPLICATE_CONFIRMATION_REQUIRED]`。
4. MCP 读取没有完成或 Gateway 身份规范化失败时，首行输出 `[CONTRACT_UPLOAD:BLOCKED]`，本次不启动写入。
5. 新合同或已有有效确认时，使用 WorkerKey 导入网关执行写入。写入目标由 WorkerKey 绑定，不传配置 Corpus ID。
6. 上传参数传递 Gateway 返回的规范化日期和标题，以及 `source_files[].original_name`。网关生成规范化远端文件名。
7. 文件已接收但正文或检索尚未核验完成时输出 `[CONTRACT_UPLOAD:PROCESSING]`。
8. 正文可读并通过 MCP 检索核验后输出 `[CONTRACT_UPLOAD:COMPLETE]`。
9. 传输异常、服务端 5xx、成功响应结构异常或未确认版本写入时输出 `[CONTRACT_UPLOAD:MANUAL_REVIEW]`，明确禁止重复上传。
10. 已确认没有提交且正式请求失败时输出 `[CONTRACT_UPLOAD:FAILED]`。

## 会话控制

等待操作或重复确认期间，只接受当前流程定义的指令。用户发送另一份文件时，路由插件保留当前任务并提示先发送“结束”。`结束`、`取消`和`重新上传`由路由插件确定性处理。

上传任务委派给 `opencontracts_operator`，最终结果在当前企业微信事件中返回。
