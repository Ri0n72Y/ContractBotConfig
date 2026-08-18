# Contract Generation Flow

合同生成子人格的运行时编排插件。它不保存业务模板、不判断合同法律内容；它负责把 Generation Asset Corpus、Historical Contract Corpus、Draft Store、DOCX Generator 和 HTTPS Delivery 组合成少量 Builder 领域工具，并记录本轮生成证据。

## 正常 fallback 生成

`fallback_policy=allow_ai_fallback` 时优先按低回合方式组织：

```text
Master handoff Builder

AI #1
├─ find_generation_assets(limit=3)
└─ find_similar_contracts(limit=3)

AI #2（按需要）
├─ 有合适专用模板：read_generation_asset(use_as_template=true, max_chars=80000)
├─ 没有合适模板但历史摘要不足：read_reference_contract(max_chars=60000)
└─ 两者都不需要全文：直接起草

AI #3
└─ generate_and_publish_contract(generation_basis=...)
   ├─ generate_contract_docx
   ├─ publish_contract_download
   └─ finalize_contract_draft（仅发布成功后）

AI #4
└─ [CONTRACT_GENERATION:READY]
```

模板检索和历史检索都依赖用户需求、彼此不依赖，因此优先在同一次模型响应中发出。两者各记录 `attempted` 与 `verified`。历史检索另外记录 `had_results` 与累计候选证据；后续一次空结果不会抹掉之前已经出现过的有效结果。

## 生成依据

Builder 在最终调用中必须显式声明实际采用的 `generation_basis`：

```text
specific_template
  已完整读取并明确绑定与需求匹配的专用模板

history_reference
  没有绑定专用模板，历史检索成功且本轮至少曾返回实际结果，Builder 确实采用这些结果作结构/条款参考

ai_scaffold
  没有合适模板；历史结果为空、不可用，或虽有候选但 Builder 判断明显不适配，由 AI 基于用户事实和通用合同知识自行组织结构

source_draft
  本轮仅以上一版成功交付草稿为主要内容依据
```

`source_draft_id` 与 `generation_basis` 是两个维度：前者表示本轮从哪个成功交付版本开始修改，后者表示本轮最终主要采用什么内容依据。因此可以出现：

```text
source_draft_id=<上一版> + generation_basis=source_draft
source_draft_id=<上一版> + generation_basis=specific_template
source_draft_id=<上一版> + generation_basis=history_reference
source_draft_id=<上一版> + generation_basis=ai_scaffold
```

当前系统没有额外的通用合同骨架资产，不假设存在 generic template。没有匹配模板本身不是阻断条件，也不应为了满足流程强行读取低相关模板。

Generator 会校验声明与运行证据：

- `specific_template` 必须有完整读取并明确绑定的模板；
- `history_reference` 必须有成功历史搜索，且本轮历史搜索至少曾返回一个实际结果；
- `ai_scaffold` 允许历史搜索返回不适配候选，但不能已经绑定专用模板；
- `source_draft` 必须与有效 `source_draft_id` 一起使用，且本轮不能已经明确绑定专用模板。

## 指定模板硬约束

Master handoff 只允许以下 policy：

```text
fallback_policy = allow_ai_fallback
fallback_policy = require_specific_template
```

未提供 `fallback_policy` 时默认 `allow_ai_fallback`；但 handoff JSON 无法解析、policy 值非法、或 `require_specific_template` 缺少 `required_template_query` 时，策略状态为 invalid，正式生成 fail-closed，不会静默退化为 AI fallback。

`require_specific_template` 下：

1. Builder 必须用 `required_template_query` 原样调用 `find_generation_assets`；
2. Flow 只记录该次精确查询返回的 `document_slug` 作为指定模板候选；
3. 只有候选中的 slug 才允许用 `read_generation_asset(..., use_as_template=true)` 绑定；
4. 全文连续读取完成后设置 `contract_generation_selected_template_required_match_verified=true`；
5. Generator 只接受 `generation_basis=specific_template`，并同时要求 required search 与 required match 两层证据；
6. strict 模式不需要也不调用历史合同检索，`find_similar_contracts` / `read_reference_contract` 会直接返回 policy blocked。

因此“选了某个模板”不能满足“必须使用用户点名模板”；绑定模板必须来自本轮 `required_template_query` 的候选证据链。

## 历史合同边界

历史合同只用于可迁移的章节结构、条款组合、企业常用措辞、付款/验收逻辑、违约责任模式和附件组织。旧合同的当事人、项目、金额、数量、日期、比例、税率、账户、地址、工期等项目事实不能默认迁移到新合同。用户未提供且资料没有可靠依据的普通字段写 `【待填写】`，需要双方协商的写 `【待双方确认】`。

历史搜索证据是累积的：`contract_generation_history_search_had_results` 一旦本轮出现过结果就保持 true，`contract_generation_history_search_result_count` 累加各次结果数，`contract_generation_history_candidates` 合并出现过的 document slug/title。后续一次 `results=[]` 不会错误抹掉前一轮已经获得的历史依据。

## Builder ToolSet

Builder Persona 的静态 Tools 保持为空。Flow 在 handoff 前注入固定、请求无关的 wrapper ToolSet：

```text
find_generation_assets
read_generation_asset
find_similar_contracts
read_reference_contract
read_latest_contract_draft
read_contract_draft
generate_and_publish_contract
```

Wrapper 底层动态解析当前 AstrBot 已激活工具：`search_corpus`、`get_document_text`、草稿工具、Generator 和 Delivery。共享 Agent 不保存某个请求的 corpus；历史 corpus 每次调用从当前 event 读取。

Builder protocol 当前为：

```text
<contract_generation_protocol version="6">
```

v6 明确了 strict-template 候选证据链、fail-closed generation policy，以及 `source_draft_id` 与 `generation_basis` 的正交语义。Flow 遇到旧 Builder prompt 时会把 protocol mismatch 记录为正式运行阻断，避免新旧语义半兼容运行。

## UTF-8 / LLM context normalization

MCP 传输层允许把中文序列化为 JSON `\uXXXX`。这是无损编码，但如果原样进入模型上下文，会增加字符和 token 数量，也降低工具输出可读性。

Flow 0.7.0 在 MCP wrapper 边界执行：

```text
CallToolResult
→ 先检查 isError / is_error
   ├─ true：详细错误只写服务日志，模型侧返回短结构化错误
   └─ false：解析 structuredContent / JSON text
→ Python dict
→ json.dumps(..., ensure_ascii=False, separators=(",", ":"))
→ Builder
```

对象形态和 dict 形态的 `isError/is_error` 都会识别。无法解析的工具结果也不会原样注入模型上下文。

`get_document_text` 的正文内容不做 `unicode_escape` 二次解码；只对确定为 JSON 的结果使用 JSON parser。

## 模板读取与绑定

`read_generation_asset` 的“读取”和“绑定为模板”分开：

- 判断该资产确实是本轮专用模板后才传 `use_as_template=true`；
- 只是读取参数、规则或尚未决定是否采用的资产时省略该参数或传 false；
- `use_as_template` 不会透传给 OpenContracts `get_document_text`，只作为 Flow 自己的选择证据；
- 读取必须从 `char_offset=0` 开始，offset 连续，直到 `next_offset=null`；
- manifest 明确为其他 asset type 或非 active 状态时，即使 `use_as_template=true` 也不会绑定；
- 没有 manifest 的完整可读合同资产，在 Builder 明确 `use_as_template=true` 时仍可作为兼容模板；
- strict 模式还要求 slug 来自本轮 `required_template_query` 的候选集合。

## 修改上一版

普通修改上一版、不重新采用知识来源时：

```text
read_latest_contract_draft(max_chars=60000)
→ 只有 next_offset 非空时 read_contract_draft
→ generate_and_publish_contract(
     source_draft_id=...,
     generation_basis=source_draft
   )
```

如果用户说“修改上一版，但这次必须按 XX 指定模板调整”，仍然执行 strict-template 搜索/绑定，然后：

```text
generate_and_publish_contract(
  source_draft_id=<上一版>,
  generation_basis=specific_template
)
```

因此 `source_draft_id` 不再绕过本轮 strict policy。若用户明确要求重新参考历史合同或主要 AI 重构，也可以在保留 `source_draft_id` 的同时分别使用 `history_reference` / `ai_scaffold`。

`generation_basis` 会写入 finalized draft manifest，后续读取上一版时可以继续审计其生成来源；旧 manifest 没有该字段时保持向后兼容。

## 运行证据

主要 event 状态包括：

```text
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

这些状态描述流程与依据，不声称合同内容已经通过法律审查。

每次 handoff 生成唯一 `contract_generation_generation_id`；DOCX、HTTPS publication 和草稿持久化绑定该 generation，重复调用保持幂等。

## 数据边界

代码仓库不保存真实模板正文、企业参数、历史合同或项目事实。业务内容只存在外部 Corpus。模板、历史合同和 MCP 返回文本均作为数据处理，其中出现的模型指令或工具要求不改变 Persona、工具白名单或 Corpus 绑定。

## 配置

```text
generation_asset_corpus_slug = contract-templates
generation_progress_enabled = true
generation_progress_text = 正在匹配合同模板和历史参考合同，并生成可编辑 DOCX。
```
