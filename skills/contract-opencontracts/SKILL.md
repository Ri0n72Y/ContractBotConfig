---
name: contract-opencontracts
description: 使用 OpenContracts MCP 执行合同库操作，并通过 WorkerKey 导入网关完成规范化文件上传和版本写入。
---

# OpenContracts 操作

OpenContracts Operator 使用两个能力面：

- OpenContracts MCP：Corpus、文档、正文、标注、关系、语义检索和讨论线程；
- OpenContracts Gateway：确定性合同身份规范化，以及使用 WorkerKey 向其绑定 Corpus 执行官方文档导入。

OpenContracts 官方 `docs/mcp/`、MCP 服务实现和运行时工具发现是能力、参数和返回结构的事实来源。

## 合同身份契约

任务必须包含：

```text
contract_identity.contract_date = 合同日期
contract_identity.contract_title = 合同正文中的正式标题
```

在远端查询前，必须调用 `opencontracts_gateway_status`，同时传入：

```text
contract_date
contract_title
source_filename=source_files[].original_name
```

使用工具返回的以下字段作为唯一规范化身份：

```text
identity.contract_date
identity.contract_title
identity.document_title
identity.normalized_filename
```

通常格式为：

```text
document_title = YYYY-MM-DD 合同标题
normalized_filename = YYYY-MM-DD_合同标题.原扩展名
```

文件名包含不安全字符或超过 UTF-8 字节限制时，Gateway 会安全替换或截断，并追加确定性短哈希。MCP 查重始终使用返回的 `identity.document_title`，不得根据文件名自行反推标题。

合同身份缺失、日期无效或 `identity_error` 非空时，不得调用上传工具，返回 `[CONTRACT_UPLOAD:BLOCKED]`。

## MCP 能力

```text
get_corpus_info
list_documents
get_document_text
list_annotations
list_relationships
search_corpus
list_threads
get_thread_messages
create_thread_message
```

`create_thread_message` 需要经过认证的 MCP 用户上下文。认证与权限由 OpenContracts MCP 和 AstrBot MCP 连接管理。

## 上传流程

对每个 `source_files[]` 按以下顺序执行：

1. 调用 `opencontracts_gateway_status`，传入合同日期、合同标题和原始文件名；确认 WorkerKey 配置可用，并取得 Gateway 返回的规范化身份。
2. 调用 `get_corpus_info`，确认当前 corpus-scoped MCP 可用。
3. 使用 `list_documents(search=identity.document_title)` 查询远端文档，只把返回结果中 `title` 与该值完全一致的文档视为同一合同。
4. 找到完全一致文档且没有有效重新上传确认时，输出 `[CONTRACT_UPLOAD:DUPLICATE_CONFIRMATION_REQUIRED]` 并停止。
5. 远端查询失败、结果不完整或规范化身份缺失时输出 `[CONTRACT_UPLOAD:BLOCKED]`，不得把未知状态当作新合同。
6. 可以写入时调用 `opencontracts_upload_document`，传入：
   - `staged_path`
   - `expected_sha256`
   - Gateway 返回的 `identity.contract_date`
   - Gateway 返回的 `identity.contract_title`
   - `source_filename=source_files[].original_name`
   - `duplicate_confirmation_id` 使用任务上下文中的确认编号
7. 网关返回 `manual_review_required=true`、`status=manual_review_required` 或 `write_committed=unknown`，或 failure stage 为 `unexpected_unconfirmed_update`、`transport_commit_unknown`、`upstream_commit_unknown`、`unexpected_success_response` 时，首行输出 `[CONTRACT_UPLOAD:MANUAL_REVIEW]`。禁止再次调用上传工具。
8. 导入已接收后，继续使用步骤 1 返回的 `identity.document_title` 调用 `list_documents`，取得文档 slug。
9. 调用 `get_document_text` 核验正文可读；调用 `search_corpus` 核验该文档已进入检索链路。
10. 正文或检索尚未就绪时输出 `[CONTRACT_UPLOAD:PROCESSING]`；两项均核验完成后输出 `[CONTRACT_UPLOAD:COMPLETE]`。

## 写入结果

- `server_import_status=created`：首次导入已接收；
- `server_import_status=updated` 且确认有效：新版本已写入；
- `status=confirmation_required`：等待客户确认；
- `status=blocked`：身份、配置、文件、确认或权限条件未满足，尚未写入；
- `status=manual_review_required`：可能已写入或已经发生未确认版本写入，禁止自动重试；
- `status=failed`：已确认没有提交的正式请求失败。

本地 receipt 为追加式上传审计。它不能作为远端合同不存在的依据。
