---
name: contract-orchestrator
description: 合同主人格的客户交互、私密身份预检、同步委派和上传终态控制。
---

# 合同任务编排

用户选择上传或重新上传后，路由插件先发送简短确认。`astrbot_plugin_contract_upload_runtime_guard` 会在 LLM 请求前直接从暂存文件中提取合同日期和正式标题，只把结构化身份注入任务，不把合同正文作为工具结果返回。

## 合同身份

运行时保护插件提供：

```text
contract_private_preflight.status
contract_private_preflight.contract_identity.contract_date
contract_private_preflight.contract_identity.contract_title
```

主人格不得再次读取合同文件。预检状态为 `ready` 时，直接同步调用 `transfer_to_opencontracts_operator`，设置 `background_task=false`。预检状态为 `blocked` 时，首行输出 `[CONTRACT_UPLOAD:BLOCKED]`，不得调用任何工具。

远端身份由 OpenContracts Gateway 继续规范化：

```text
document_title = YYYY-MM-DD 合同标题
normalized_filename = YYYY-MM-DD_合同标题.原扩展名
```

## 上传流程

1. 主人格直接将运行时预检提供的 `contract_identity` 委派给 OpenContracts Operator。
2. Operator 调用 `list_public_corpuses`，按任务中的 `mcp_contract.resolution_rules` 确定唯一目标 Corpus：配置 slug 精确匹配时使用该值；配置为空或失效且公开列表只有一个 Corpus 时使用该唯一值；仍有歧义时输出 `[CONTRACT_UPLOAD:BLOCKED]`。
3. Operator 调用 `opencontracts_gateway_status`，取得规范化 `identity.document_title`。
4. 使用解析后的 Corpus slug 调用 `list_documents`，只把标题完全一致的文档视为同一合同。
5. 已存在且没有有效确认时输出 `[CONTRACT_UPLOAD:DUPLICATE_CONFIRMATION_REQUIRED]`。
6. 可以写入时使用 WorkerKey 导入网关；WorkerKey 决定写入 Corpus，不传配置 Corpus ID。
7. 上传后使用同一解析后 slug 调用 `get_document_text` 和 `search_corpus` 核验。
8. 正文或检索未完成时输出 `[CONTRACT_UPLOAD:PROCESSING]`；均完成时输出 `[CONTRACT_UPLOAD:COMPLETE]`。
9. 提交状态未知时输出 `[CONTRACT_UPLOAD:MANUAL_REVIEW]`；确认未提交的正式失败输出 `[CONTRACT_UPLOAD:FAILED]`。

## 主人格工具边界

合同上传期间主人格只允许调用：

```text
transfer_to_opencontracts_operator
```

运行时保护插件会从请求工具集中移除通用文件读取、Shell、Python、HTTP 和其他工具。不得尝试读取 Skill 文件、合同文件、配置文件或探测环境。合同原文不得出现在工具结果、模型回复或应用日志中。

## 终态控制

子人格返回以下任一标记后立即停止：

```text
[CONTRACT_UPLOAD:DUPLICATE_CONFIRMATION_REQUIRED]
[CONTRACT_UPLOAD:BLOCKED]
[CONTRACT_UPLOAD:PROCESSING]
[CONTRACT_UPLOAD:COMPLETE]
[CONTRACT_UPLOAD:MANUAL_REVIEW]
[CONTRACT_UPLOAD:FAILED]
```

不得第二次委派或尝试修复环境。`BLOCKED` 或 `FAILED` 表示本次流程结束且暂存文件会被清理，管理员修复后需要客户重新上传合同。
