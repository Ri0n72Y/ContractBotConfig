---
name: contract-result-verification
description: 核验 OpenContracts 公开 MCP 读取结果和 WorkerKey 导入结果，并输出企业微信状态标记。
---

# 结果核验

内部可以保留文档标识、MCP 工具结果、规范化合同身份和导入处理状态；客户回复使用自然业务语言。

## 状态优先级

1. Gateway 返回 `manual_review_required=true`、`status=manual_review_required`，或写入提交状态未知：`[CONTRACT_UPLOAD:MANUAL_REVIEW]`。
2. Gateway 返回未确认的 `updated`，即 `failure_stage=unexpected_unconfirmed_update`：`[CONTRACT_UPLOAD:MANUAL_REVIEW]`。
3. 公开 MCP 在目标 `corpus_slug` 中找到规范化标题完全一致的文档，且没有有效重新上传确认：`[CONTRACT_UPLOAD:DUPLICATE_CONFIRMATION_REQUIRED]`。
4. 导入端点在写入前返回可确认的文档路径冲突：`[CONTRACT_UPLOAD:DUPLICATE_CONFIRMATION_REQUIRED]`。
5. 目标 Corpus slug 缺失，或公开 MCP 文档发现没有完成，且没有执行写入：`[CONTRACT_UPLOAD:BLOCKED]`。
6. 合同日期、合同标题、WorkerKey、文件校验、确认校验或权限条件未满足且没有执行写入：`[CONTRACT_UPLOAD:BLOCKED]`。
7. 文件已接收，正文或语义检索尚未就绪：`[CONTRACT_UPLOAD:PROCESSING]`。
8. 文档正文可读，并通过同一目标 `corpus_slug` 的 `search_corpus` 检索到该文档内容：`[CONTRACT_UPLOAD:COMPLETE]`。
9. 已确认没有发生提交且正式导入失败：`[CONTRACT_UPLOAD:FAILED]`。

## 生命周期

- `BLOCKED`：尚未写入，是可恢复阻断。Result Guard 设置保留标记，Router 保存暂存文件和 pending 状态。客户补充缺失信息或管理员修复后回复“继续”时复用原文件；回复“结束”或“取消”时清理。
- `DUPLICATE_CONFIRMATION_REQUIRED`：保存暂存文件和确认状态，等待客户决定。
- `PROCESSING`、`COMPLETE`、`MANUAL_REVIEW`、`FAILED`：当前流程结束。普通暂存状态由 Router 清理。
- `MANUAL_REVIEW`：可能已经写入，禁止自动重试或再次上传。

## 安全规则

- `transport_commit_unknown`、`upstream_commit_unknown` 和 `unexpected_success_response` 均视为可能已经提交，禁止自动重试。
- `HTTP 201`、`created`、`updated` 和 `processing` 只证明写入或处理阶段，不代表正文及检索完成。
- 完成状态只声明“正文可读并已进入检索”；没有调用 `list_annotations` 时，不声明标注已经完成。
- WorkerKey 决定写入 Corpus。Gateway 不要求或显示配置 Corpus ID；写入后通过 AstrBot 已配置的公开 MCP `/mcp/`，使用 `targets.opencontracts` 作为 `corpus_slug` 核验远端结果。
- 不使用 `get_corpus_info`、`opencontracts_check_duplicate`、Shell、Python、通用 HTTP 或直接 MCP JSON-RPC 补救失败。
