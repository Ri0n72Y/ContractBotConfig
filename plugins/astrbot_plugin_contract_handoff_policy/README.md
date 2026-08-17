# 合同子代理委派策略 0.5.3

本插件只负责委派参数规范化与 OpenContracts 目标 Corpus 的单一配置来源，不维护重复委派计数或额外确认状态机。

## Corpus 单一配置

AstrBot WebUI 中只配置一次：

```text
default_opencontracts_corpus_slug = contracts
```

该值同时用于：

- OpenContracts Operator 独立合同库读取；
- OpenContracts 上传前目标库发现/核验；
- Builder 生成任务的参考合同读取。

`default_opencontracts_corpus_slug` 是运行时权威值。Master/Builder handoff input、Router task context 和 branch task 中即使出现 `corpus_slug` 或 `targets.opencontracts`，也不会覆盖这个配置；规范化后的 canonical context 统一写入 Handoff Policy 的配置值。

生成任务执行 `transfer_to_docassemble_builder` 前，Handoff Policy 把配置值写入当前事件：

```text
contract_opencontracts_corpus_slug
```

Generation Flow 只消费这个值，不再保存第二份历史合同 Corpus 配置。Builder 的领域 wrappers 不暴露 `corpus_slug`；实际 OpenContracts MCP 调用时由 wrapper 从当前 event 读取并注入该值，因此 Agent 不需要猜测、询问或调用 `list_public_corpuses`。

## Operator 规范化

`transfer_to_opencontracts_operator` 会把同一个配置值固化到规范化任务中的：

```text
targets.opencontracts
read_contract.corpus_slug
branch_task.corpus_slug
mcp_contract.corpus_slug
```

上传链仍使用 Gateway identity 和 WorkerKey 写入模型。Router 只提供上传任务意图、staged file 和身份提示，不拥有 Corpus 配置。

## Builder 生成时序

```text
Master
→ transfer_to_docassemble_builder
→ Handoff Policy(priority=1100) 把 default_opencontracts_corpus_slug 写入当前 event
→ Generation Flow(priority=1050) 校验 Builder protocol v4，并绑定固定请求无关 wrapper ToolSet
→ Builder 首轮优先同时调用：
   ├─ find_generation_assets(limit=3)
   └─ find_similar_contracts(limit=3, best-effort)
→ read_generation_asset(max_chars=80000)
→ generate_and_publish_contract
   ├─ generate_contract_docx
   ├─ publish_contract_download
   └─ finalize_contract_draft（仅发布成功后）
→ [CONTRACT_GENERATION:READY]
```

当前 Builder wrappers 为：

```text
find_generation_assets
read_generation_asset
find_similar_contracts
read_reference_contract
read_latest_contract_draft
read_contract_draft
generate_and_publish_contract
```

新合同正式生成仍要求完成生成资产检索并完整读取一个可用模板。历史相似合同检索是优先执行的 best-effort 参考：历史 Corpus 或 OpenContracts 暂时不可用时，历史 wrapper 可以返回 blocked，但不会在模板已完整的情况下成为 Generator 的代码级生成门槛，也不会要求客户确认或增加 status/preflight 调用。

Flow 在 handoff 时不因为底层 MCP/Generator/Delivery 某个工具瞬时不可用而改写共享 Agent ToolSet；wrapper 在实际调用时动态解析对应底层工具并返回 blocked。这样插件或 MCP hot reload 不会让一个请求清空另一个请求的 Builder 工具。

## 缺失 Corpus

如果 `default_opencontracts_corpus_slug` 为空：

- Operator canonical context 的 `targets.opencontracts` 为空，读取任务返回失败、上传任务返回 BLOCKED；
- Builder event 中的历史 Corpus 为空，调用历史合同 wrapper 时返回 blocked；Builder 仍可在生成资产模板完整可用时继续生成；
- Agent 不调用 `list_public_corpuses` 猜库，也不要求客户确认 Corpus。

这里不增加额外 status/preflight 调用；缺失配置只在现有领域工具真正需要该值时暴露。
