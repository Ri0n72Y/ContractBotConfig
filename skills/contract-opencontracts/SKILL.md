---
name: contract-opencontracts
description: 使用 OpenContracts 公开 MCP 执行合同库读取、对比分析和上传核验，并通过 WorkerKey 导入网关完成规范化文件写入。
---

# OpenContracts 操作

OpenContracts Operator 使用两个能力面：

- OpenContracts 公开 MCP `/mcp/`：按明确的 `corpus_slug` 执行文档发现、正文读取和语义检索；
- OpenContracts Gateway：确定性合同身份规范化，以及使用 WorkerKey 向其绑定 Corpus 执行官方文档导入。

只使用 AstrBot 已配置并注入的工具。不得自行拼接 MCP 地址，不得调用 Shell、Grep、Python、通用 HTTP、读取配置文件、本地文件搜索或历史会话内容绕过标准工具链。

## 合同库读取和总体分析

只读任务使用：

```text
list_documents
get_document_text
search_corpus
```

任务上下文应提供目标 `corpus_slug`、查询目标或文档标识。读取流程：

1. 调用 `list_documents` 确认目标文档及其真实 `document_slug`；不得把日期、标题片段或猜测直接当作远端 slug。
2. 对每份目标文档调用：

```text
get_document_text(
  corpus_slug=目标值,
  document_slug=真实 slug,
  char_offset=0,
  max_chars=10000
)
```

3. 返回 `next_offset` 时，用该值继续读取；直到 `next_offset=null`。若 offset 不前进或重复，停止并返回失败。
4. `page_count=0`、`total_chars=0`、`text=""` 或首段没有正文时，视为 OpenContracts 尚未产出可读取正文。不得使用 `search_corpus`、`list_annotations`、本地文件或历史上下文代替正文。
5. `search_corpus` 只用于正文读取完成后的补充检索或交叉核验，不得据空检索结果推断正文内容。
6. 所有分析结论必须限定在本轮 MCP 实际返回的正文范围内，并列明未就绪文档。

只读状态必须位于首行：

```text
[CONTRACT_READ:READY]
[CONTRACT_READ:PARTIAL]
[CONTRACT_READ:PENDING]
[CONTRACT_READ:FAILED]
```

状态含义：

- `READY`：所有目标文档正文已按分片完整读取，可以基于本轮正文分析；
- `PARTIAL`：仅部分目标文档正文可读。只能分析已读取文档，并明确未覆盖范围；
- `PENDING`：目标文档存在，但正文尚未产出，例如 `page_count=0`、`total_chars=0` 或正文为空；
- `FAILED`：文档发现失败、目标缺失、MCP 工具失败、分片 offset 异常或结果结构不可核验。

任一 `CONTRACT_READ` 状态均为当前轮次终态。不得在状态后继续调用其他工具。收到 `must_not_execute=true` 时直接返回 `CONTRACT_READ:FAILED`，不得执行工具。

## 目标 Corpus

任务上下文必须提供目标 Corpus slug。上传任务使用 `targets.opencontracts`；只读任务可以使用规范化只读上下文中的 `targets.opencontracts` 或 `read_contract.corpus_slug`。目标缺失时返回对应失败或阻断状态，不调用 `list_public_corpuses` 猜测目标。

## 合同身份契约

上传任务必须包含：

```text
contract_identity.contract_date
contract_identity.contract_title
```

上传前调用 `opencontracts_gateway_status`，以返回的 `identity.document_title` 和 `identity.normalized_filename` 作为唯一规范化身份。文件名含不安全字符或超过 UTF-8 字节限制时，由 Gateway 安全处理；MCP 查重始终使用完整 `identity.document_title`。

## 上传流程

1. 读取 `targets.opencontracts`；缺失则输出 `[CONTRACT_UPLOAD:BLOCKED]`。
2. 调用 `opencontracts_gateway_status` 取得规范化身份。
3. 调用 `list_documents(corpus_slug=目标值, search=identity.document_title)`，只把标题完全一致的文档视为同一合同。
4. 已存在且没有有效重新上传确认时输出 `[CONTRACT_UPLOAD:DUPLICATE_CONFIRMATION_REQUIRED]`。
5. MCP 查询失败、身份缺失或结果不完整时输出 `[CONTRACT_UPLOAD:BLOCKED]`，不得把未知状态当作新合同。
6. 可以写入时调用 `opencontracts_upload_document`。写入目标由 WorkerKey 绑定，不传配置 Corpus ID。
7. 可能已经提交或出现未确认 `updated` 时输出 `[CONTRACT_UPLOAD:MANUAL_REVIEW]`，禁止重试。
8. 导入接收后，使用同一 `corpus_slug` 重新发现文档并调用 `get_document_text`、`search_corpus` 核验。
9. 正文或检索尚未就绪时输出 `[CONTRACT_UPLOAD:PROCESSING]`；两项均完成时输出 `[CONTRACT_UPLOAD:COMPLETE]`。
10. 已确认没有提交且正式导入失败时输出 `[CONTRACT_UPLOAD:FAILED]`。

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

本地 receipt 只承担追加式上传审计，不能作为远端合同内容或不存在的依据。
