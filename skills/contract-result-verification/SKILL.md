---
name: contract-result-verification
description: 核验 OpenContracts MCP 读取结果和 WorkerKey 导入结果，并输出企业微信状态标记。
---

# 结果核验

内部可以保留文档标识、MCP 工具结果、规范化合同身份和导入处理状态；客户回复使用自然业务语言。

## 状态优先级

1. Gateway 返回 `manual_review_required=true`、`status=manual_review_required`，或写入提交状态未知：`[CONTRACT_UPLOAD:MANUAL_REVIEW]`。
2. Gateway 返回未确认的 `updated`，即 `failure_stage=unexpected_unconfirmed_update`：`[CONTRACT_UPLOAD:MANUAL_REVIEW]`。
3. MCP 已找到规范化标题完全一致的文档，且没有有效重新上传确认：`[CONTRACT_UPLOAD:DUPLICATE_CONFIRMATION_REQUIRED]`。
4. 导入端点在写入前返回可确认的文档路径冲突：`[CONTRACT_UPLOAD:DUPLICATE_CONFIRMATION_REQUIRED]`。
5. MCP Corpus 或文档发现没有完成，且没有执行写入：`[CONTRACT_UPLOAD:BLOCKED]`。
6. 合同日期、合同标题、WorkerKey、文件校验、确认校验或权限条件未满足：`[CONTRACT_UPLOAD:BLOCKED]`。
7. 文件已接收，正文或语义检索尚未就绪：`[CONTRACT_UPLOAD:PROCESSING]`。
8. 文档正文可读，并通过 `search_corpus` 检索到该文档内容：`[CONTRACT_UPLOAD:COMPLETE]`。
9. 已确认没有发生提交且正式导入失败：`[CONTRACT_UPLOAD:FAILED]`。

## 安全规则

- `transport_commit_unknown`、`upstream_commit_unknown` 和 `unexpected_success_response` 均视为可能已经提交，禁止自动重试。
- `HTTP 201`、`created`、`updated` 和 `processing` 只证明写入或处理阶段，不代表正文及检索完成。
- 完成状态只声明“正文可读并已进入检索”；没有调用 `list_annotations` 时，不声明标注已经完成。
- WorkerKey 决定写入 Corpus。Gateway 不要求或显示配置 Corpus ID；写入后仍必须通过当前 corpus-scoped MCP 核验远端结果。
