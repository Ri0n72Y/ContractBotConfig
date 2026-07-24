---
name: contract-opencontracts
description: 使用 OpenContracts MCP 执行合同库操作，并通过 WorkerKey 导入网关完成文件上传和版本写入。
---

# OpenContracts 操作

OpenContracts Operator 使用两个能力面：

- corpus-scoped OpenContracts MCP：Corpus、文档、正文、标注、语义检索和讨论线程；
- `opencontracts_upload_document`：WorkerKey 认证的官方文档导入写入。

OpenContracts 官方 `docs/mcp/` 和运行时工具发现是能力、参数和返回结构的事实来源。新增或调整合同库操作时，先依据当前 MCP 工具清单选择调用方式。

建议 MCP 地址：

```text
http://opencontracts-api:8000/mcp/corpus/contracts/
```

## MCP 能力

```text
get_corpus_info       读取目标 Corpus 信息
list_documents        列出和搜索合同文档
get_document_text     读取解析后的合同正文
list_annotations      读取文档标注
search_corpus         执行语义检索
list_threads          读取 Corpus 讨论线程
get_thread_messages   读取线程消息
```

上传流程使用其中的合同发现、正文读取和检索能力。合同问答、风险分析、标注核验和讨论任务按目标调用其他工具。

## 上传流程

对每个 `source_files[]` 按以下顺序执行：

1. 调用 `get_corpus_info`，确认当前 MCP 已连接到目标 Corpus。
2. 使用 `list_documents` 查找与当前合同对应的远端文档。
3. 根据业务上下文和 MCP 返回结果判断是否需要客户确认重新上传。
4. 可以写入时，调用 `opencontracts_gateway_status` 检查 WorkerKey 导入配置。
5. 调用 `opencontracts_upload_document`，传入：
   - `staged_path`
   - `expected_sha256`
   - `source_filename=source_files[].original_name`
   - 标题使用合同任务中的业务标题；没有明确标题时使用原始文件名主体
   - `duplicate_confirmation_id` 使用任务上下文中的确认编号
6. 导入已接收后，通过 `list_documents` 和 `get_document_text` 查找并读取远端合同。
7. 使用 `search_corpus` 核验当前合同已进入检索链路；任务涉及标注时可调用 `list_annotations`。
8. 正文或检索尚未就绪时首行输出 `[CONTRACT_UPLOAD:PROCESSING]`；当前任务要求的 MCP 核验完成后输出 `[CONTRACT_UPLOAD:COMPLETE]`。

## MCP 结果处理

- 以工具实际返回的字段和状态为准；
- 工具调用失败或当前任务所需结果尚未形成时，返回对应的 `BLOCKED` 或 `PROCESSING` 状态；
- 不使用本地 receipt 代替 OpenContracts 远端合同数据；
- 需要标注、线程或消息数据时，直接调用对应 MCP Tool。

## 写入结果

- `server_import_status=created`：首次导入已接收；
- `server_import_status=updated`：OpenContracts 已创建新版本；
- `status=confirmation_required`：写入流程等待客户确认；
- `status=blocked`：配置、文件、确认或权限条件未满足；
- `status=failed`：正式导入请求失败或写入结果需要人工核查。

本地 receipt 记录上传审计信息。合同库数据来自 OpenContracts MCP。
