# AI 合同编制与 DOCX 生成架构

## 目标

正式合同生成不依赖 Docassemble interview/Jinja。Builder 优先利用 Generation Asset Corpus 和 Historical Contract Corpus，再编制完整 Markdown；DOCX Generator 一次生成 Word，Delivery 确定性发布 HTTPS，只有成功交付的 Markdown 才进入 Draft Store 供后续修改。

当前优先级：

1. 跑完整个真实链路；
2. 尽量减少一次生成中的 LLM API 回合；
3. 有合适企业模板/历史资料时优先使用；
4. 没有合适模板或参考时仍允许 AI 基于用户事实生成；
5. 不把历史合同的旧项目事实默认迁移到新合同；
6. 用户明确禁止 fallback 时必须代码级 fail-closed；
7. 生成依据、版本来源和指定模板身份可审计；
8. MCP/插件异常详情不进入模型上下文；
9. 只针对低并发下真正存在的共享状态问题做线程安全处理。

```text
用户
  ↓
Master
  ↓
Contract Builder
  ├─ Generation Asset Corpus
  ├─ Historical Contract Corpus（allow fallback 时）
  ├─ AI 自组织结构 fallback
  ├─ Final Draft Store
  └─ generate_and_publish_contract(
       source_draft_id=?,
       generation_basis=...
     )
       ├─ DOCX Generator
       ├─ HTTPS Delivery
       └─ delivery-success draft finalize
```

代码仓库不保存真实合同模板、企业参数、历史合同、项目事实或其他业务数据。

## Generation policy protocol

正式 Master → Builder handoff 必须显式携带：

```text
generation_policy_protocol = 1
fallback_policy = allow_ai_fallback | require_specific_template
```

以下情况全部 fail-closed：

```text
handoff input 非法 JSON
generation_policy_protocol 缺失或不是 1
fallback_policy 缺失
fallback_policy 提供了未知值
require_specific_template 缺少 required_template_query
```

Flow 记录：

```text
contract_generation_policy_protocol
contract_generation_policy_verified
contract_generation_policy_error
contract_generation_fallback_policy
```

这个 handoff protocol 与 Builder prompt protocol 分别解决两个不同的版本错配问题：

- `generation_policy_protocol=1`：防止旧 Master 与新 Flow 半兼容；
- `<contract_generation_protocol version="6">`：防止旧 Builder 与新 Flow 半兼容。

Generator 在正式渲染前必须验证 policy verified，不能把错误或缺失 policy 静默解释成允许 AI fallback。

## allow_ai_fallback

正常新合同生成优先在同一个模型响应并行：

```text
find_generation_assets(limit=3)
find_similar_contracts(limit=3)
```

两类调用都记录 `attempted`；底层 OpenContracts 成功时记录 `verified`。历史检索的结果证据是累积的：

```text
contract_generation_history_search_had_results
contract_generation_history_search_result_count
contract_generation_history_candidates
```

后续一次 `results=[]` 不会抹掉前面已经获得的历史结果。

最终 `generation_basis` 由 Builder 显式声明：

```text
specific_template
  有明显匹配、已完整读取并明确绑定的专用合同模板

history_reference
  没有绑定专用模板；历史检索成功、本轮至少曾返回实际结果，且 Builder 确实采用这些结果作结构/条款参考

ai_scaffold
  没有合适模板；历史结果为空、不可用，或虽有候选但明显不适配，由 AI 基于用户事实和通用合同知识组织完整结构

source_draft
  本轮只以上一版成功交付草稿作为主要内容依据
```

当前没有额外的“通用合同骨架”资产，也不假设存在 generic template。

## require_specific_template

如果用户明确表达“必须使用某个指定模板”“找不到就不要生成”“只能按该模板生成”，Master handoff：

```text
generation_policy_protocol = 1
fallback_policy = require_specific_template
required_template_query = <用户原始指定名称或 document slug>
```

strict-template 证据链：

```text
required_template_query
        ↓ 必须原样作为 query
find_generation_assets
        ↓ strict 模式内部改走确定性身份解析
list_documents(contract-templates, 分页)
        ↓
精确 document slug
或标准化模板标题身份匹配
        ↓
contract_generation_required_template_candidates
        ↓ 仅候选 slug 可 use_as_template=true
read_generation_asset 全文连续读取
        ↓
contract_generation_selected_template_required_match_verified=true
        ↓
generation_basis=specific_template
        ↓
Generator strict gate
```

strict 模式不使用 `search_corpus` 的普通语义相似结果证明模板身份。`search_corpus` 搜索 annotation/block 正文，而文档身份应基于 `list_documents` 返回的 slug/title。标题身份标准化忽略空白与标点，并允许常见展示尾缀 `生成模板` / `模板` / `template`，例如 `材料采购合同模板` 与 `材料采购合同_生成模板` 可以建立确定性标题身份。

如果只有语义相似但 slug/标准化标题不匹配，系统 BLOCKED；不能把另一个相似合同模板冒充用户点名模板。

strict 模式不调用历史合同检索。Flow 会阻止 `find_similar_contracts` / `read_reference_contract` 进入 OpenContracts，Generator 也不要求 `history_search_attempted`。

## source_draft 与本轮依据分离

`source_draft_id` 表示“从哪个已成功交付版本开始修改”；`generation_basis` 表示“本轮最终主要采用什么内容依据”。两者是正交维度：

```text
source_draft_id=<上一版> + generation_basis=source_draft
source_draft_id=<上一版> + generation_basis=specific_template
source_draft_id=<上一版> + generation_basis=history_reference
source_draft_id=<上一版> + generation_basis=ai_scaffold
```

普通修改上一版、不重新采用知识来源时：

```text
read_latest_contract_draft
→ read_contract_draft（如需分页）
→ generate_and_publish_contract(
     source_draft_id=<上一版>,
     generation_basis=source_draft
   )
```

有 source draft 时，正式生成的知识检索 gate 按本轮 basis 最小化：

```text
source_draft       → 不重新要求 OpenContracts 检索
specific_template  → 只要求生成资产检索；模板选择由 basis 校验继续验证
history_reference  → 只要求历史检索；实际结果由 basis 校验继续验证
ai_scaffold        → 不机械要求两个 Corpus 都重新检索
```

全新合同仍按企业资料优先原则要求生成资产与历史合同两类检索都至少尝试一次。

如果用户说“修改上一版，但这次必须按 XX 指定模板调整”，上一版仍作为编辑起点，但必须执行 strict-template 身份证据链：

```text
source_draft_id=<上一版>
generation_basis=specific_template
```

所以 `source_draft_id` 不能绕过 `require_specific_template`。

如果本轮以新模板为 basis，Generator 优先采用新绑定模板的 render profile；有 source draft 且本轮不是新模板时沿用上一版 profile。

## Draft lineage

finalized draft manifest 保存：

```text
generation_id
generation_basis
source_draft_id
template_asset_id
template_document_slug
```

语义规则：

- `source_draft_id` 是版本父节点；
- `specific_template` 时模板字段记录本轮新绑定模板；
- `source_draft` 时允许继承上一版模板 provenance；
- `history_reference` / `ai_scaffold` 时不把上一版模板 slug 错记成“本轮模板”，需要追溯时沿 `source_draft_id` 查看上一版 manifest。

旧 manifest 没有 `source_draft_id` / `generation_basis` 时向后兼容为空。

## 信息来源与事实边界

Builder 使用顺序：

```text
用户本轮明确事实
  > 合适专用模板中的结构/企业规则
  > 实际采用的历史相似合同中的可迁移结构和措辞
  > AI 通用合同知识
```

历史合同可参考：章节结构、条款组合、企业常用措辞、付款与验收逻辑、违约责任模式、附件组织。

历史合同不得默认迁移：旧当事人、旧项目名称、金额、单价、数量、具体日期、付款/质保/违约比例、税率、账户、地址、工期等项目特定事实。普通未知字段写 `【待填写】`；需要双方协商的写 `【待双方确认】`。

## Builder ToolSet ownership

Builder Persona 静态 Tools 为空。Generation Flow 0.7.1 在 handoff 前注入固定 wrapper：

```text
find_generation_assets
read_generation_asset
find_similar_contracts
read_reference_contract
read_latest_contract_draft
read_contract_draft
generate_and_publish_contract
```

Builder 不看到 corpus slug，也不直接看到裸 `generate_contract_docx`、`publish_contract_download` 或 `finalize_contract_draft`。历史 corpus 在每次 wrapper 调用时从当前 event 读取，避免共享 Agent 的并发污染。

底层动态依赖：

```text
search_corpus
list_documents
get_document_text
read_latest_contract_draft
read_contract_draft
generate_contract_docx
finalize_contract_draft
publish_contract_download
```

Builder protocol 当前为：

```text
<contract_generation_protocol version="6">
```

v6 明确 strict-template、policy fail-closed，以及 `source_draft_id` 与 `generation_basis` 的正交语义。Flow 检测到旧协议时阻断正式生成。

## 模板读取与绑定

Builder 只有已经决定采用某资产作为本轮专用模板时才传：

```text
read_generation_asset(..., use_as_template=true)
```

读取连续性要求：

1. 从 `char_offset=0` 开始；
2. 每块 offset 等于上一块实际末尾；
3. `next_offset=null` 才视为完整；
4. manifest 明确为非 `contract_template` 或非 active 时不绑定；
5. 没有 manifest 的完整可读合同资产只有在 Builder 明确 `use_as_template=true` 时才作为兼容模板；
6. strict 模式额外要求该 slug 来自本轮确定性身份解析候选集合。

普通参数、规则或探索性读取不自动成为模板。

## 正式生成证据

Generation Flow / Generator 使用的主要 event 状态：

```text
contract_generation_policy_protocol
contract_generation_policy_verified
contract_generation_policy_error
contract_generation_asset_search_attempted
contract_generation_asset_search_verified
contract_generation_asset_search_result_count
contract_generation_template_selected_verified
contract_generation_history_search_attempted
contract_generation_history_search_verified
contract_generation_history_search_result_count
contract_generation_history_search_had_results
contract_generation_history_candidates
contract_generation_fallback_policy
contract_generation_require_specific_template
contract_generation_required_template_query
contract_generation_required_template_search_verified
contract_generation_required_template_candidates
contract_generation_selected_template_required_match_verified
contract_generation_basis_verified
contract_generation_basis
```

这些状态描述本轮流程与依据，不代表法律审查或内容绝对正确。

## UTF-8 与工具异常边界

OpenContracts MCP 可能把 JSON 中文序列化成 `\uXXXX`。Generation Flow wrapper：

```text
FunctionToolExecutor.execute
→ 捕获底层直接抛出的 MCP / 插件 / timeout 异常
   ├─ logger.exception 保存完整 traceback
   └─ wrapper 内转换为 isError，不让异常逃到 AstrBot ToolLoop
→ 检查 isError / is_error（对象与 dict 形态）
   ├─ true：模型收到短结构化错误
   └─ false：解析 structuredContent / JSON text
→ Python dict
→ json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
→ Builder
```

这一步很重要：AstrBot 4.23.2 的外层 ToolLoop 在未捕获异常时会把异常文本作为 tool result 送回模型，因此异常必须在 Generation Flow wrapper 内先收敛。

dict-shaped `CallToolResult` 也先解包 `structuredContent` / `content`，不会把 wrapper 本身当业务结果。合法 JSON 中的 `\uXXXX` 在进入模型前恢复为真实 Unicode；正文不使用 `unicode_escape` 二次解码。

Windows PowerShell 5.1 的 native stdin 编码风险见 `docs/deployment/utf8-runtime-boundaries.md`。

## DOCX、交付与 Draft Store

Generator 一次接收完整 `document_title + document_markdown + generation_basis` 并生成 DOCX。生成成功后先把 Markdown 保存在当前 event 的 pending draft；只有 HTTPS 发布成功后才调用 `finalize_contract_draft` 写入 `_drafts/`。

同一 `generation_id` 的 verified DOCX 和成功 publication 均幂等复用。DOCX 渲染发生不可重试失败后设置 terminal failure，同一 handoff 不重复烧生成回合。

## 并发与运行依赖

- Generation Asset Corpus 为插件级配置；
- Historical Contract Corpus 为 event 级绑定；
- Builder Agent 只持有请求无关 wrapper ToolSet；
- wrappers 在调用时动态解析当前底层 Tool；
- Draft Store 使用 `RLock`；
- Publication audit 使用进程内锁；
- 每轮生成拥有唯一 generation_id。
