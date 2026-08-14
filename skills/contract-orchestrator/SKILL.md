---
name: contract-orchestrator
description: 合同主人格的任务路由、数据库读取、草稿生成和上传编排规则。
---

# 合同任务编排

本 Skill 保留为编排规则文档；当前 Master Persona 已内置核心路由规则，正常运行不要求加载本 Skill。

## 路由原则

按用户最终目标路由，不按句子中是否出现“合同库/数据库”路由：

- 只读、比较、总结、价格分析、总体分析 → `transfer_to_opencontracts_operator`；
- 最终目标是生成、起草、制作或修改合同文书 → `transfer_to_docassemble_builder`；
- 上传/重新上传 → 按 Router 的 `contract_task_context` 委派 `transfer_to_opencontracts_operator`。

生成任务即使包含“从合同库找”“按库里条款”“找不到留空”，仍直接交 Builder。不要先 Operator 检索、再把大段结果复制给 Builder；Builder 自己读取同一合同库。

## 草稿生成

用户明确要求生成、起草、制作、开始生成、按当前方案生成时，直接执行，不要求额外回复固定口令。

Master 不需要先收齐金额、付款、工期、质保、主体工商信息或争议机构。默认策略：

```text
corpus_slug = contracts
draft_policy = database_first_then_placeholder
```

用户明确提供的值优先；其余由 Builder 从合同库查找；仍没有的字段在草稿中保留 `【待填写】`/`【待双方确认】`。只有用户明确要求“字段不完整就不要生成”时才启用严格缺失阻断。

Builder handoff 保持简短，不复制历史正文或整份数据库分析结果。推荐结构：

```json
{
  "operation": "contract_generation",
  "user_request": "用户当前生成目标和已明确约束",
  "corpus_slug": "contracts",
  "draft_policy": "database_first_then_placeholder"
}
```

Builder 返回 READY 后只展示 filename、HTTPS download_url、expires_at；BLOCKED 只说明真正阻止执行的系统或来源条件，不把允许留空的字段重新要求客户填写；FAILED 不用本地工具补救。

## 独立合同库读取

独立读取任务只调用 Operator。目标 Corpus 由 Handoff Policy 从任务上下文取得；没有 Router 上下文时使用管理员配置的默认 Corpus，当前为 `contracts`。不得调用 `list_public_corpuses` 猜测目标。

Operator 应先 `list_documents`，再只读取完成任务真正需要的文档，不默认扫描整个 Corpus。正文为空时返回 PENDING；部分可读返回 PARTIAL；全部目标可读返回 READY；工具或目标失败返回 FAILED。

## 上传

上传流程继续使用 Router 的 `contract_task_context`。上传前必须取得 `contract_date` 和 `contract_title`；正文日期为空但 `identity_hints.contract_date` 存在时直接采用，不重复询问。Operator 使用 Gateway 规范化身份、公开 MCP 查重、WorkerKey 写入，并在同一目标 Corpus 核验正文与检索状态。

出现任一 `[CONTRACT_UPLOAD:*]` 终态后停止当前轮次工具调用。传输异常或提交状态不确定时进入 MANUAL_REVIEW，不自动重试。

## 禁止绕过

结构化合同任务不使用 Shell、Grep、Python、通用 HTTP、直接 MCP JSON-RPC、本地文件搜索或历史正文绕过专用插件/MCP。这里的目标是减少旁路和重复轮次，而不是增加额外确认步骤。
