# Contract Generation Flow

合同生成子人格的运行时编排插件。它不保存业务模板、不理解合同法律内容；它负责把 Generation Asset Corpus、Historical Contract Corpus、Draft Store、DOCX Generator 和 HTTPS Delivery 组合成少量 Builder 领域工具，并记录本轮生成证据。

## MVP 正式流程

正常新生成优先按 AI 回合组织，而不是按单个工具串行组织：

```text
Master handoff Builder

AI #1
├─ find_generation_assets(limit=3)
└─ find_similar_contracts(limit=3, best-effort)

AI #2
└─ read_generation_asset(max_chars=80000)
   └─ 只有模板返回 next_offset 才继续读取
   └─ 历史检索可用且片段明显不足时才 read_reference_contract

AI #3
└─ generate_and_publish_contract
   ├─ generate_contract_docx
   ├─ publish_contract_download
   └─ finalize_contract_draft（仅发布成功后）

AI #4
└─ [CONTRACT_GENERATION:READY]
```

AstrBot 支持一次模型响应返回多个 tool calls，因此模板检索和历史相似合同检索优先在同一次 AI 响应中发出。两者都只依赖用户需求，不互相依赖。Provider 不支持多 tool call 时才退化为顺序执行。

两个搜索默认各取 3 个最相关结果，首批候选明显不足时才扩大检索。`read_generation_asset` 首次默认 `max_chars=80000`，只有 `next_offset` 非空时才继续读取下一段。`find_similar_contracts` 成功且检索摘要够用时不再读取历史全文；确需全文时 `read_reference_contract` 首次默认 60000 字符。历史搜索 blocked 时 Builder 不重复重试，并在完整模板可用时继续生成。

DOCX 生成、HTTPS 发布和成功交付后的草稿持久化都是确定性动作，由 `generate_and_publish_contract` 内部顺序完成；模型不再处理中间 `output_path` 或 draft finalize。

## 修改当前会话上一版

```text
read_latest_contract_draft(max_chars=60000)
→ 只有 next_offset 非空时 read_contract_draft
→ generate_and_publish_contract(source_draft_id=...)
→ [CONTRACT_GENERATION:READY]
```

`read_latest_contract_draft` 一次返回最近成功交付草稿的 `draft_id`、元数据和首段正文。有效 `source_draft_id` 会跳过本轮模板/历史检索，因此修改上一版不要求 OpenContracts MCP、Generation Asset Corpus 或 Historical Contract Corpus 当前可用。

## Builder ToolSet

Builder Persona 的静态 Tools 保持为空。Generation Flow 0.6.2 在 handoff 前注入固定的、请求无关的 wrapper ToolSet：

```text
find_generation_assets
read_generation_asset
find_similar_contracts
read_reference_contract
read_latest_contract_draft
read_contract_draft
generate_and_publish_contract
```

不注入 list/status/preflight、显式 select template、分块草稿写入、裸 `generate_contract_docx`、裸 `publish_contract_download` 或内部 `finalize_contract_draft`。

Wrapper 底层按调用时动态解析 AstrBot 当前已激活工具：

```text
search_corpus
get_document_text
read_latest_contract_draft
read_contract_draft
generate_contract_docx
finalize_contract_draft
publish_contract_download
```

Wrapper 会先按公开 JSON schema 丢弃模型多带的无关参数，再注入内部 `corpus_slug` 和性能默认值。因此额外字段不会透传到底层 MCP/plugin handler，MCP 或 Generator/Delivery hot reload 后也不会继续持有旧 handler 对象。

Flow 0.6.2 不再直接调用动态解析到的 `FunctionTool.call()`，而是统一交给 AstrBot 原生 `FunctionToolExecutor`。因此 AstrBot 4.23.2 中把实现保存在 `handler` 的普通插件工具、MCPTool 和自定义 override-call Tool 都按框架原生语义执行；这个兼容层不增加模型调用或额外工具回合。

生成资产 Corpus 使用插件配置 `generation_asset_corpus_slug`。历史合同 Corpus 由 Handoff Policy 写入当前 event 的 `contract_opencontracts_corpus_slug`。

历史 Corpus 不存进共享 Handoff Agent。每个 wrapper 调用时从当前 `AstrMessageEvent` 读取绑定，所以并发会话不会互相覆盖 Corpus。共享 Agent 始终只收到同一个请求无关 ToolSet；某个请求恰逢 MCP/插件 hot reload 时，只会在真正调用对应 wrapper 时得到 blocked，不会把共享 Agent ToolSet 清空并影响其他请求。

## Persona protocol

Flow 接受：

```text
<contract_generation_protocol version="4">
```

Persona protocol 不兼容时当前 event 记录 runtime missing，Generator 会拒绝正式生成；Flow 不再因为单个请求的 protocol 状态去清空共享 Agent ToolSet。Persona 更新后按部署文档重载对应 Subagent。Flow 不在每个请求里原地刷新共享 Agent Prompt。

## 模板读取

Builder 通过 `find_generation_assets` 选择最合适候选，然后读取该候选。Manifest 是可选元数据，已有纯文本合同模板不需要为了 MVP 重新加工。

运行时只保留读取连续性和显式元数据排除规则：

1. `document_slug` 与请求一致；
2. 从 `char_offset=0` 开始；
3. 后续 offset 等于上一块实际文本末尾；
4. `next_offset=null` 时文本末尾等于 `total_chars`；
5. 本轮尚未绑定模板时，没有 manifest 的完整可读候选可以直接作为兼容模板；
6. manifest 明确声明 `contract_template` 且状态为空/active 时可以绑定模板；
7. 一旦已经绑定模板，后续无 manifest 参数/规则资产不会覆盖模板身份；
8. manifest 明确声明其他 asset type 或非 active 状态时不自动当作模板；
9. 完整读完后自动绑定，不要求额外 `select_generation_template` 调用。

Manifest 中的 `render_profile`、`required_headings`、`parameter_assets`、`rule_assets` 作为提示元数据记录。后面三项不作为正式生成代码级 gating；缺失或未知排版回退 `standard_contract`。模板正文和可用的 OpenContracts 资料才是 Builder 的主要依据。

## 运行证据

Flow 仍记录：

```text
contract_generation_asset_search_verified
contract_generation_template_selected_verified
contract_generation_history_search_verified
```

其中前两项是新合同 Generator 0.4.2 的代码级必要证据；`contract_generation_history_search_verified` 只表示本轮历史相似合同检索成功，用于诊断和观测，不再是 Generator 的硬门槛。修改已有成功交付 draft 时不要求上述知识库证据。

Flow 每次 handoff 生成唯一：

```text
contract_generation_generation_id
```

DOCX output 和 HTTPS publication 都绑定该 generation_id。Generator 和 Delivery 对同一 generation 的已成功结果幂等返回，避免模型误重复调用造成重新渲染或重复发布。

正式 Generator 生成 DOCX 后先把 Markdown 保存在当前 event 的 pending draft；只有 HTTPS publication 成功后，组合工具才调用内部 `finalize_contract_draft` 写入 Draft Store。发布失败不会改变用户可见的“上一版”。

## 运行依赖

Flow 在 handoff 时只把 Persona protocol 不兼容记录为 event 级正式生成阻断。底层工具和 Corpus 状态只用于诊断；实际是否可用由对应 wrapper 在调用时判断：

```text
search_corpus
get_document_text
read_latest_contract_draft
read_contract_draft
generate_contract_docx
finalize_contract_draft
publish_contract_download
```

因此 transient hot reload 不改变其他请求的 ToolSet。Generation Asset Corpus 和可用模板是新合同生成必要数据；Historical Contract Corpus 是优先使用的 best-effort 参考，不是修改已有 draft 的前置条件，也不在模板完整可用时单独阻止新生成。

## 数据边界

代码仓库不保存真实模板正文、企业参数、历史合同或项目事实。业务内容只存在外部 Corpus。

当前 MVP 假设 OpenContracts MCP 位于受信 Docker 局域网，部署用户少于 20 人。因此不增加 MCP server identity 探测、网络来源筛查、数据库锁、分布式锁或队列。主要并发边界是 Event 级状态隔离、请求无关共享 ToolSet、Draft Store 文件锁和 Delivery audit 写锁。

## 配置

```text
generation_asset_corpus_slug = contract-templates
generation_progress_enabled = true
generation_progress_text = 正在匹配合同模板和历史参考合同，并生成可编辑 DOCX。
```