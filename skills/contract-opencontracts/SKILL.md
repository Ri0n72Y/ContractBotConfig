---
name: contract-opencontracts
description: 使用 OpenContracts 公开 MCP 执行目标 Corpus 的合同读取、分析和上传，并通过 WorkerKey 导入网关完成规范化文件写入。
---

# OpenContracts 操作

OpenContracts Operator 使用两个能力面：

- OpenContracts 公开 MCP `/mcp/`：按明确的 `corpus_slug` 执行文档发现、正文读取和语义检索；
- OpenContracts Gateway：确定性合同身份规范化，以及使用 WorkerKey 向其绑定 Corpus 执行官方文档导入。

只使用 AstrBot 已配置并注入的 MCP Tools。不得自行拼接 MCP 地址，不得调用 Shell、Grep、Python、通用 HTTP、读取配置文件、本地文件搜索或历史会话正文绕过标准工具链。

## 合同库读取、对比和总体分析

只读任务使用：

```text
list_documents
get_document_text
search_corpus
```

执行顺序：

1. 调用 `list_documents` 确认目标文档和真实 `document_slug`；不得把日期、标题片段或猜测直接当作远端 slug。
2. 对每份目标文档从 `char_offset=0` 调用 `get_document_text`，`max_chars=10000`。
3. 返回 `next_offset` 时使用该值继续读取，直到 `next_offset=null`。offset 不前进或重复时返回失败。
4. `page_count=0`、`total_chars=0`、`text=""` 或首段正文为空时，返回 `PENDING`，不得继续尝试不存在的后续分片。
5. `search_corpus` 只用于正文读取后的补充检索或交叉核验；空检索、空标注不能替代正文读取。
6. 多文档仅部分可读时，只分析已读取文档并明确未覆盖范围。

首行状态：

```text
[CONTRACT_READ:READY]
[CONTRACT_READ:PARTIAL]
[CONTRACT_READ:PENDING]
[CONTRACT_READ:FAILED]
```

- `READY`：所有目标正文完整读取；
- `PARTIAL`：仅部分目标正文完整读取；
- `PENDING`：文档存在，但 OpenContracts 尚未产出可读取正文；
- `FAILED`：目标缺失、MCP 失败、结果不可核验或分片异常。

任一 `CONTRACT_READ` 状态均为当前轮次终态。不得使用 Shell、Grep、本地文件、历史上下文或模型记忆补齐正文。收到 `must_not_execute=true` 时直接返回 `CONTRACT_READ:FAILED`，不得执行工具。

## 目标 Corpus

任务上下文必须提供：

```text
targets.opencontracts = 目标 Corpus slug
```

Handoff 会同时写入：

```text
mcp_contract.corpus_slug
branch_task.corpus_slug
```

三者应一致。上传流程直接把该值作为 `list_documents`、`get_document_text` 和 `search_corpus` 的 `corpus_slug`。

只读规范化上下文使用 `targets.opencontracts` 和 `read_contract.corpus_slug`。目标缺失时返回 `CONTRACT_READ:FAILED`；上传任务则返回 `[CONTRACT_UPLOAD:BLOCKED]`。不得调用 `list_public_corpuses` 猜测目标，也不得改用不存在的 corpus-scoped MCP 地址。

## 合同身份契约

上传任务必须包含：

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

文件名包含不安全字符或超过 UTF-8 字节限制时，Gateway 会安全替换或截断，并追加确定性短哈希。MCP 查重始终使用返回的完整 `identity.document_title`，不得根据文件名自行反推标题。

合同身份缺失、日期无效或 `identity_error` 非空时，不得调用上传工具，返回 `[CONTRACT_UPLOAD:BLOCKED]`。

## 公开 MCP 能力

上传链路使用：

```text
list_documents
get_document_text
search_corpus
```

其他非上传场景可以按需使用：

```text
list_public_corpuses
list_annotations
list_relationships
list_threads
get_thread_messages
create_thread_message
```

`list_public_corpuses` 不参与上传目标选择。`create_thread_message` 需要经过认证的 MCP 用户上下文。正文读取为空时不得调用其他能力猜测正文内容。

## 上传流程

对每个 `source_files[]` 按以下顺序执行：

1. 读取 `targets.opencontracts`，取得目标 `corpus_slug`；缺失则输出 `[CONTRACT_UPLOAD:BLOCKED]`。
2. 调用 `opencontracts_gateway_status`，传入合同日期、合同标题和原始文件名；确认 WorkerKey 配置可用，并取得 Gateway 返回的规范化身份。
3. 调用 `list_documents(corpus_slug=目标值, search=identity.document_title)` 查询远端文档，只把返回结果中 `title` 与该值完全一致的文档视为同一合同。
4. 找到完全一致文档且没有有效重新上传确认时，首行输出 `[CONTRACT_UPLOAD:DUPLICATE_CONFIRMATION_REQUIRED]` 并停止。
5. MCP 查询失败、结果不完整或规范化身份缺失时输出 `[CONTRACT_UPLOAD:BLOCKED]`，不得把未知状态当作新合同。
6. 可以写入时调用 `opencontracts_upload_document`，传入：
   - `staged_path`
   - `expected_sha256`
   - Gateway 返回的 `identity.contract_date`
   - Gateway 返回的 `identity.contract_title`
   - `source_filename=source_files[].original_name`
   - `duplicate_confirmation_id` 使用任务上下文中的确认编号
7. 网关返回 `manual_review_required=true`、`status=manual_review_required` 或 `write_committed=unknown`，或 failure stage 为 `unexpected_unconfirmed_update`、`transport_commit_unknown`、`upstream_commit_unknown`、`unexpected_success_response` 时，首行输出 `[CONTRACT_UPLOAD:MANUAL_REVIEW]`。禁止再次调用上传工具。
8. 导入已接收后，继续使用同一 `corpus_slug` 和步骤 2 返回的 `identity.document_title` 调用 `list_documents`，取得文档 slug。
9. 调用 `get_document_text(corpus_slug=目标值, document_slug=...)` 核验正文可读；调用 `search_corpus(corpus_slug=目标值, query=...)` 核验文档已进入检索链路。
10. 正文或检索尚未就绪时输出 `[CONTRACT_UPLOAD:PROCESSING]`；两项均核验完成后输出 `[CONTRACT_UPLOAD:COMPLETE]`。

## 禁止绕过

以下工具或行为不得用于合同读取、分析或上传：

```text
opencontracts_check_duplicate
get_corpus_info
Shell
Grep
Python
通用 HTTP
读取 Gateway 配置文件
直接调用 MCP JSON-RPC
探测其他 MCP URL
本地文件搜索
历史会话正文回填
```

标准工具缺失或返回失败时，上传任务输出 `[CONTRACT_UPLOAD:BLOCKED]`；只读任务输出 `[CONTRACT_READ:FAILED]`。不要尝试修复运行环境。

## 写入结果

- `server_import_status=created`：首次导入已接收；
- `server_import_status=updated` 且确认有效：新版本已写入；
- `status=confirmation_required`：等待客户确认；
- `status=blocked`：身份、配置、文件、确认或权限条件未满足，尚未写入；
- `status=manual_review_required`：可能已写入或已经发生未确认版本写入，禁止自动重试；
- `status=failed`：已确认没有提交的正式请求失败。

本地 receipt 为追加式上传审计。它不能作为远端合同不存在或正文内容的依据。
