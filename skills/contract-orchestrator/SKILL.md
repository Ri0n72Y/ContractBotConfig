---
name: contract-orchestrator
description: 合同主人格的客户交互、合同身份提取、同步委派和可恢复上传控制。
---

# 合同任务编排

用户选择上传或重新上传后，路由插件先发送简短确认。主人格在当前企业微信事件中完成合同身份提取，再同步委派 `opencontracts_operator`，设置 `background_task=false`。

## 合同身份

上传前必须取得：

- `contract_date`：统一为 `YYYY-MM-DD`；
- `contract_title`：使用正文中的正式合同名称，去除文件扩展名、路径和无意义编号前缀。

日期来源按以下顺序处理：

1. 合同首页或标题附近明确标注的合同日期；
2. 明确签署日期；多方日期不一致时使用最晚签署日期；
3. 明确生效日期；
4. 正文日期字段为空时，读取任务上下文 `identity_hints.contract_date`。该字段由 Router 从原始文件名中确定性提取，仅在文件名存在唯一有效日期时提供。

文件名日期支持：

```text
YYYY-M-D
YYYY.M.D
YYYY_M_D
YYYY年M月D日
YYYYMMDD
```

若正文没有可靠日期且 `identity_hints.contract_date` 存在，直接采用该日期，不再向客户提问。文件名存在多个不同日期时 Router 不提供提示，此时才请求客户补充。

客户在上次 `BLOCKED` 后补充的信息位于 `resume.user_input`。应结合当前保留的合同文件继续提取身份，不要求客户重新发送文件。

无法可靠取得任一身份字段时，首行输出 `[CONTRACT_UPLOAD:BLOCKED]`，明确说明缺少日期或标题。不得猜测。

调用 `transfer_to_opencontracts_operator` 时，`input` 使用 JSON：

```json
{
  "contract_identity": {
    "contract_date": "2026-07-25",
    "contract_title": "软件开发服务合同"
  }
}
```

远端身份由 OpenContracts Gateway 确定性规范化：

```text
document_title = YYYY-MM-DD 合同标题
normalized_filename = YYYY-MM-DD_合同标题.原扩展名
```

标题含文件名不安全字符或超过 UTF-8 字节限制时，Gateway 会安全处理文件名并追加短哈希；MCP 查重仍使用 Gateway 返回的完整 `identity.document_title`。

## 上传流程

1. OpenContracts Operator 从任务上下文读取 `targets.opencontracts` 作为公开 MCP 的目标 `corpus_slug`。
2. Operator 调用 `opencontracts_gateway_status`，传入合同日期、合同标题和原始文件名，取得规范化 `identity.document_title`。
3. Operator 使用 AstrBot 已配置的 OpenContracts 公开 MCP `/mcp/`，调用 `list_documents(corpus_slug=targets.opencontracts, search=identity.document_title)` 查询合同。
4. MCP 返回标题完全一致的已有合同，且当前任务没有有效客户确认时，首行输出 `[CONTRACT_UPLOAD:DUPLICATE_CONFIRMATION_REQUIRED]`。
5. 身份、目标 Corpus slug、MCP、配置、文件、确认或权限条件未满足且尚未写入时，首行输出 `[CONTRACT_UPLOAD:BLOCKED]`。
6. 新合同或已有有效确认时，使用 WorkerKey 导入网关执行写入。写入目标由 WorkerKey 绑定，不传配置 Corpus ID。
7. 上传参数传递 Gateway 返回的规范化日期和标题，以及 `source_files[].original_name`。网关生成规范化远端文件名。
8. 文件已接收但正文或检索尚未核验完成时输出 `[CONTRACT_UPLOAD:PROCESSING]`。
9. 正文可读并通过同一目标 Corpus 的 MCP 检索核验后输出 `[CONTRACT_UPLOAD:COMPLETE]`。
10. 传输异常、服务端 5xx、成功响应结构异常或未确认版本写入时输出 `[CONTRACT_UPLOAD:MANUAL_REVIEW]`，明确禁止重复上传。
11. 已确认没有提交且正式请求失败时输出 `[CONTRACT_UPLOAD:FAILED]`。

## 主人格工具边界

合同上传期间，主人格只执行：

```text
读取当前合同文件
transfer_to_opencontracts_operator
```

不得调用 Shell、Python、通用 HTTP、直接 MCP JSON-RPC、配置文件读取或环境探测来补救子人格失败。不得自行执行 OpenContracts 查重或上传。

## 当前轮次终态

以下任一标记出现后，主人格必须立即停止当前轮次的工具调用，并把结果交给最终结果保护插件：

```text
[CONTRACT_UPLOAD:DUPLICATE_CONFIRMATION_REQUIRED]
[CONTRACT_UPLOAD:BLOCKED]
[CONTRACT_UPLOAD:PROCESSING]
[CONTRACT_UPLOAD:COMPLETE]
[CONTRACT_UPLOAD:MANUAL_REVIEW]
[CONTRACT_UPLOAD:FAILED]
```

状态生命周期：

- `BLOCKED`：当前轮次停止，但 Router 保留暂存文件和会话。客户补充信息，或管理员修复后客户回复“继续”，使用同一暂存文件再次执行；客户回复“结束”或“取消”才清理。
- `DUPLICATE_CONFIRMATION_REQUIRED`：保留当前文件，等待“重新上传”或“取消”。
- `PROCESSING`、`COMPLETE`、`MANUAL_REVIEW`、`FAILED`：当前流程结束，Router 清理普通暂存任务；`MANUAL_REVIEW` 明确禁止重复上传。

## 会话控制

等待操作、阻断恢复或重复确认期间，只接受当前流程定义的输入。用户发送另一份文件时，Router 保留当前任务并提示先发送“结束”。`结束`、`取消`和`重新上传`由 Router 确定性处理。

上传任务委派给 `opencontracts_operator`，最终结果在当前企业微信事件中返回。
