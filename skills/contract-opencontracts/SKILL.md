---
name: contract-opencontracts
description: 使用 OpenContracts MCP 读取合同，并通过 WorkerKey 导入网关完成上传和版本写入。
---

# OpenContracts 操作

OpenContracts Operator 使用两个已分配的能力面：

- corpus-scoped OpenContracts MCP：合同发现、正文读取、语义检索和处理核验；
- `opencontracts_upload_document`：WorkerKey 认证的官方文档导入写入。

建议在 AstrBot MCP 配置中将服务地址设为：

```text
http://opencontracts-api:8000/mcp/corpus/contracts/
```

## 上传流程

对每个 `source_files[]` 按以下顺序执行：

1. 调用 `get_corpus_info`，确认当前 MCP 已连接到目标 corpus。
2. 以 `source_files[].original_name` 的文件名主体作为搜索词调用 `list_documents`，并检查返回的 `total_count` 和 `documents`。
3. 将搜索结果中的文档标题与文件名主体进行精确比较；匹配项表示远端已有对应合同。
4. 已有合同且任务上下文没有 `duplicate_confirmation.confirmed=true` 时，首行输出 `[CONTRACT_UPLOAD:DUPLICATE_CONFIRMATION_REQUIRED]`，等待客户确认。
5. 新合同或已有有效确认时，调用 `opencontracts_gateway_status` 检查 WorkerKey 写入配置。
6. 调用 `opencontracts_upload_document`，传入：
   - `staged_path`
   - `expected_sha256`
   - `source_filename=source_files[].original_name`
   - 标题使用原始文件名主体
   - `duplicate_confirmation_id` 使用任务上下文中的确认编号
7. 导入返回 `accepted` 后，再次调用 `list_documents` 查找对应文档。
8. 文档出现后调用 `get_document_text` 读取首个文本窗口；取得正文后，从正文选择一段有区分度的短语调用 `search_corpus`。
9. 正文或检索尚未就绪时首行输出 `[CONTRACT_UPLOAD:PROCESSING]`；正文和检索均成功时输出 `[CONTRACT_UPLOAD:COMPLETE]`。

## MCP 结果判断

MCP 调用只有在返回结构完整时才支持后续判断：

- `get_corpus_info` 返回 corpus 信息；
- `list_documents` 返回 `total_count` 和 `documents`；
- 文档摘要至少包含 `slug` 和 `title`；
- `get_document_text` 返回 `document_slug`、`total_chars` 和 `text`。

MCP 连接失败、工具缺失或响应结构不完整时，首行输出 `[CONTRACT_UPLOAD:BLOCKED]`，并说明远端读取没有完成。

## 写入结果

- `server_import_status=created`：首次导入已接收；
- `server_import_status=updated`：确认后的版本写入已接收；
- `status=confirmation_required`：导入时发现已有文档，等待客户确认；
- `status=blocked`：配置、文件、确认或权限条件未满足；
- `status=failed`：正式导入请求失败。

本地 receipt 记录上传审计信息。合同发现与读取结果来自 OpenContracts MCP。
