# 合同子代理委派策略 0.5.1

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

生成任务执行 `transfer_to_docassemble_builder` 前，Handoff Policy 把解析后的 slug 写入当前事件：

```text
contract_opencontracts_corpus_slug
```

Generation Flow 只消费这个值，不再保存第二份 Corpus 配置。Builder 可见的 `list_documents/get_document_text` schema 不暴露 `corpus_slug`；Flow 在实际 MCP 调用时确定性注入该值，因此 Agent 不需要猜测、询问或调用 `list_public_corpuses`。

## Operator 规范化

`transfer_to_opencontracts_operator` 仍会把目标 Corpus 固化到规范化任务中的：

```text
targets.opencontracts
read_contract.corpus_slug
branch_task.corpus_slug
```

上传链仍使用 Gateway identity 和 WorkerKey 写入模型；本次 Builder 生成修复不改变 OpenContracts 上传协议。

## 时序

```text
Master
→ transfer_to_docassemble_builder
→ Handoff Policy(priority=1100) 解析并绑定 Corpus
→ Generation Flow(priority=1050) 重建 Builder 四工具并包装 list/get
→ Builder 调 list_documents/search 参数（不含 corpus_slug）
→ Flow 自动补入配置的 corpus_slug
→ 原 MCP Tool
```

如果 `default_opencontracts_corpus_slug` 为空且任务上下文也没有可解析目标，生成链会在 Builder 执行前一次性 BLOCKED；不会让 Agent 猜库或增加额外 MCP 调用。
