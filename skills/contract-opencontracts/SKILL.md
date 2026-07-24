---
name: contract-opencontracts
description: OpenContracts REST 路径查重、确认绑定、上传和处理状态核验。
---

# OpenContracts 操作

## 固定顺序

1. 调用 `opencontracts_gateway_status`。
2. 对每个文件调用 `opencontracts_check_duplicate`，同时传入：
   - `staged_path`
   - `expected_sha256`
   - `source_filename=source_files[].original_name`
3. 查重工具必须调用 OpenContracts 的 `GET /api/imports/documents/lookup/`，使用现有 WorkerKey，并按原始文件名对应的 OpenContracts 文档路径判断是否存在。
4. 返回 `status=unknown`、`blocked`、REST 端点不可用、认证失败或响应结构不完整时立即停止，首行输出 `[CONTRACT_UPLOAD:BLOCKED]`。
5. 路径已存在且任务上下文没有有效客户确认时立即停止，首行输出 `[CONTRACT_UPLOAD:DUPLICATE_CONFIRMATION_REQUIRED]`。
6. 路径不存在或已有有效确认时调用 `opencontracts_upload_document`。
7. 上传参数中的 `source_filename` 必须使用 `source_files[].original_name`；不得使用带时间戳的暂存文件名。
8. `duplicate_confirmation_id` 从任务上下文原样传入，不自行生成或修改。

## 路径和版本规则

- 不生成或传递确定性 slug。
- OpenContracts 使用稳定原始文件名生成文档路径。
- 同一路径首次上传应返回 `created`。
- 客户确认重新上传后，同一路径上传应返回 `updated`，表示创建新版本。
- 路径唯一约束竞争冲突按重复确认处理，不得更换文件名或另建路径重试。
- 本地 receipt 只用于审计和恢复历史导入文件名，不得用于证明远端不存在。

## 结果

- 文件被接口接收，正文、标注或检索尚未核验完成：首行输出 `[CONTRACT_UPLOAD:PROCESSING]`。
- 正文可读并完成检索核验：首行输出 `[CONTRACT_UPLOAD:COMPLETE]`。
- 正式调用失败：首行输出 `[CONTRACT_UPLOAD:FAILED]`。

只使用获配的 OpenContracts 专用工具。禁止调用 Shell、Python、通用 HTTP 和主动消息工具。
