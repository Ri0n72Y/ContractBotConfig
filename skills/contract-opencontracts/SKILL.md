---
name: contract-opencontracts
description: 使用 OpenContracts 公开 MCP 确定目标 Corpus，并通过 WorkerKey 导入网关完成规范化合同上传和核验。
---

# OpenContracts 操作

OpenContracts Operator 使用：

- 公开 MCP `/mcp/`：列出公开 Corpus、发现文档、读取正文、执行语义检索；
- OpenContracts Gateway：规范化合同身份，并使用 WorkerKey 向其绑定 Corpus 导入合同。

只使用 AstrBot 已配置并注入的标准工具。不得调用 Shell、Python、通用 HTTP、直接 MCP JSON-RPC、配置文件读取或其他地址探测。

## 目标 Corpus 的确定性解析

任务包含：

```text
mcp_contract.configured_corpus_slug
mcp_contract.resolution_rules
```

上传开始后先调用 `list_public_corpuses`。解析规则固定为：

1. 公开列表中存在与配置 slug 完全一致的项时，使用该 slug；
2. 配置 slug 为空或不存在，且公开列表只有一个 Corpus 时，使用该唯一 Corpus；
3. 公开列表为空，或剩余多个 Corpus 无法唯一确定时，首行输出 `[CONTRACT_UPLOAD:BLOCKED]`；
4. 不得尝试 `contracts`、`default` 等常见名称，不得让模型猜测目标。

解析得到的 slug 是本次任务唯一目标，必须用于：

```text
list_documents
get_document_text
search_corpus
```

## 合同身份

任务必须包含运行时保护插件提供的：

```text
contract_identity.contract_date
contract_identity.contract_title
```

该身份由插件在本地内存中提取。Operator 不得调用任何文件读取工具，也不得要求主人格重新读取合同。

调用 `opencontracts_gateway_status`，传入合同日期、合同标题和 `source_files[].original_name`，取得：

```text
identity.contract_date
identity.contract_title
identity.document_title
identity.normalized_filename
```

MCP 查重只使用完整的 `identity.document_title`。

## 上传流程

1. 调用 `list_public_corpuses` 并按确定性规则得到唯一目标 slug。
2. 调用 `opencontracts_gateway_status` 获取规范化身份；身份缺失或错误时输出 `[CONTRACT_UPLOAD:BLOCKED]`。
3. 调用 `list_documents(corpus_slug=解析后值, search=identity.document_title)`；仅把返回标题完全一致的文档视为同一合同。
4. 已存在且没有有效重新上传确认时，输出 `[CONTRACT_UPLOAD:DUPLICATE_CONFIRMATION_REQUIRED]`。
5. MCP 查询失败或返回不完整时输出 `[CONTRACT_UPLOAD:BLOCKED]`，不得把未知状态当作新合同。
6. 可以写入时调用 `opencontracts_upload_document`，传入暂存路径、SHA-256、Gateway 返回的日期和标题、原始文件名及确认编号。
7. Gateway 返回 `manual_review_required`、`write_committed=unknown`，或 failure stage 为 `unexpected_unconfirmed_update`、`transport_commit_unknown`、`upstream_commit_unknown`、`unexpected_success_response` 时，输出 `[CONTRACT_UPLOAD:MANUAL_REVIEW]`，禁止再次上传。
8. 导入已接收后，使用同一解析后 slug 和 `identity.document_title` 再次调用 `list_documents` 获取文档 slug。
9. 调用 `get_document_text` 和 `search_corpus` 核验正文与检索状态。
10. 尚未就绪时输出 `[CONTRACT_UPLOAD:PROCESSING]`；均完成时输出 `[CONTRACT_UPLOAD:COMPLETE]`。

## 隐私边界

合同原文不得出现在：

```text
工具返回值
子人格回复
主人格回复
应用日志
```

禁止使用：

```text
astrbot_file_read_tool
opencontracts_check_duplicate
get_corpus_info
Shell
Python
通用 HTTP
配置文件读取
直接 MCP JSON-RPC
```

标准工具失败时直接返回对应终态，不尝试修复运行环境。本地 receipt 只用于追加式上传审计，不能证明远端合同不存在。
