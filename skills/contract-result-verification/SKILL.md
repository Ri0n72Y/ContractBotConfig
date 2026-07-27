---
name: contract-result-verification
description: 核验 OpenContracts 公开 MCP 读取结果和 WorkerKey 导入结果，并输出确定性状态。
---

# 结果核验

## 合同库读取状态

状态优先级：

1. 文档发现或 MCP 调用失败、目标缺失、结果结构不可核验、分片 offset 不前进：`[CONTRACT_READ:FAILED]`。
2. 目标文档存在，但 `page_count=0`、`total_chars=0`、正文为空或没有首段正文：`[CONTRACT_READ:PENDING]`。
3. 多份目标文档中仅部分正文按分片完整读取：`[CONTRACT_READ:PARTIAL]`。
4. 所有目标文档正文均从 `char_offset=0` 读取至 `next_offset=null`：`[CONTRACT_READ:READY]`。

核验规则：

- `search_corpus` 空结果不能替代正文读取，也不能证明分片失败；
- `total_chars=0` 表示没有可分片正文，不应继续尝试后续 offset；
- `PARTIAL` 的分析范围只能覆盖已读取文档；
- 不得使用 Shell、Grep、本地文件、历史会话正文或模型记忆补齐 MCP 空结果；
- 任一 `CONTRACT_READ` 状态均为当前轮次终态。

## 上传状态优先级

1. 可能已经提交或未确认 `updated`：`[CONTRACT_UPLOAD:MANUAL_REVIEW]`。
2. 远端存在标题完全一致的文档且无有效确认：`[CONTRACT_UPLOAD:DUPLICATE_CONFIRMATION_REQUIRED]`。
3. 目标、身份、配置、MCP、文件、确认或权限条件未满足且尚未写入：`[CONTRACT_UPLOAD:BLOCKED]`。
4. 文件已接收，正文或语义检索尚未就绪：`[CONTRACT_UPLOAD:PROCESSING]`。
5. 正文可读并通过同一目标 Corpus 的检索核验：`[CONTRACT_UPLOAD:COMPLETE]`。
6. 已确认没有发生提交且正式导入失败：`[CONTRACT_UPLOAD:FAILED]`。

`HTTP 201`、`created`、`updated` 和 `processing` 只证明写入或处理阶段，不代表正文及检索完成。没有调用标注工具时，不声明标注完成。
