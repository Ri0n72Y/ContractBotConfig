# 合同子代理委派策略 0.5.4

本插件只负责委派参数规范化、OpenContracts 目标 Corpus 的单一配置来源，以及 ContractBot 当前事件交付模型要求的同步 handoff 约束；不接管 AstrBot 的 Agent、Persona、ToolSet 或 Skill 生命周期。

运行基线：AstrBot 4.27.x+。

## Corpus 单一配置

AstrBot WebUI 中只配置一次：

```text
default_opencontracts_corpus_slug = contracts
```

该值同时用于：

- OpenContracts Operator 独立合同库读取；
- OpenContracts 上传前目标库发现/核验；
- Builder 生成任务的历史合同读取。

`default_opencontracts_corpus_slug` 是运行时权威值。Master/Builder handoff input、Router task context 和 branch task 中即使出现 `corpus_slug` 或 `targets.opencontracts`，也不会覆盖该配置。

生成任务执行 `transfer_to_docassemble_builder` 前，Handoff Policy 把配置值写入当前事件：

```text
contract_opencontracts_corpus_slug
```

Generation Flow 只消费这个事件状态，不保存第二份历史合同 Corpus 配置。Builder 的受限知识工具不暴露 `corpus_slug` 参数。

## 同步 handoff

ContractBot 的生成和合同库任务都以当前企业微信事件同步返回结果。Handoff Policy 因此在调用以下两个子代理前确定性写入：

```text
background_task = false
```

适用于：

```text
transfer_to_docassemble_builder
transfer_to_opencontracts_operator
```

这是 ContractBot 的业务交付约束，不是 Agent runtime 接管。AstrBot 仍负责 handoff、Persona、Tool 和子代理执行；本插件只阻止这些业务链进入 AstrBot 的后台 handoff / CronMessageEvent 二次唤醒路径。

Master Persona 仍应显式传 `background_task=false`，代码侧约束作为确定性兜底。

## Operator 规范化

`transfer_to_opencontracts_operator` 会把同一个配置值固化到规范化任务中的：

```text
targets.opencontracts
read_contract.corpus_slug
branch_task.corpus_slug
mcp_contract.corpus_slug
```

上传链继续使用 Gateway identity 和 WorkerKey 写入模型。Router 只提供上传任务意图、staged file 和身份提示，不拥有 Corpus 配置。

## Builder 生成时序

```text
Master
→ transfer_to_docassemble_builder(background_task=false)
→ Handoff Policy(priority=1100)
   ├─ 写入 contract_opencontracts_corpus_slug
   └─ 强制 background_task=false
→ Generation Flow(priority=1050)
   ├─ 校验 generation policy
   ├─ 校验 Builder 必需 Tool/Skill 可用
   └─ 不修改 Agent ToolSet / system prompt / handoff input
→ AstrBot 按 Builder Persona/WebUI 静态绑定提供业务工具
→ Builder grounding + 模板/历史取证
→ generate_and_publish_contract
   ├─ generate_contract_docx
   ├─ publish_contract_download
   └─ finalize_contract_draft
→ [CONTRACT_GENERATION:READY|PARTIAL|FAILED]
→ Master 在当前企业微信事件回复
```

Builder 当前正式绑定以 `personas/bindings.json` 为准。部署时确认配置正确即可；本插件不额外实现 Tool/Skill allowlist 审计状态机。

## 缺失 Corpus

如果 `default_opencontracts_corpus_slug` 为空：

- Operator canonical context 的 `targets.opencontracts` 为空，读取任务失败、上传任务 BLOCKED；
- Builder event 中历史 Corpus 为空，历史合同工具返回 blocked；
- Agent 不调用 `list_public_corpuses` 猜库，也不要求客户确认 Corpus。

这里不增加额外 status/preflight 调用；缺失配置只在现有领域工具真正需要该值时暴露。
