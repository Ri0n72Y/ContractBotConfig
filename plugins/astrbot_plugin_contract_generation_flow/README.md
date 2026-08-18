# Contract Generation Flow

合同生成子人格的运行时编排插件。它不保存业务模板、不判断合同法律内容；它负责把 Generation Asset Corpus、Historical Contract Corpus、Draft Store、DOCX Generator 和 HTTPS Delivery 组合成少量 Builder 领域工具，并记录本轮生成证据。

## 正式新生成

正常新生成优先按 AI 回合组织：

```text
Master handoff Builder

AI #1
├─ find_generation_assets(limit=3)
└─ find_similar_contracts(limit=3, best-effort)

AI #2（按需要）
├─ 有合适专用模板：read_generation_asset(max_chars=80000)
├─ 没有合适模板但历史摘要不足：read_reference_contract(max_chars=60000)
└─ 两者都不需要全文：直接起草

AI #3
└─ generate_and_publish_contract
   ├─ generate_contract_docx
   ├─ publish_contract_download
   └─ finalize_contract_draft（仅发布成功后）

AI #4
└─ [CONTRACT_GENERATION:READY]
```

模板检索和历史检索都依赖用户需求、彼此不依赖，因此优先在同一次模型响应中发出。两者各记录 `attempted` 与 `verified`：调用 wrapper 即记录 attempted；底层 OpenContracts 成功返回后才记录 verified。Generator 要求两类检索都至少尝试过，但不要求它们都成功。

## 生成依据 fallback

新合同按实际可用资料确定：

```text
specific_template
  已完整读取并绑定与需求明显匹配的专用模板

history_reference
  没有选用专用模板，但历史相似合同检索成功

ai_scaffold
  没有可用模板或历史参考，由 AI 基于用户事实和通用合同知识自行组织结构
```

当前系统没有额外的通用合同骨架资产，不假设存在 generic template。没有匹配模板本身不是阻断条件，也不应为了满足流程强行读取低相关模板。

历史合同只用于可迁移的章节结构、条款组合、企业常用措辞、付款/验收逻辑、违约责任模式和附件组织。旧合同的当事人、项目、金额、数量、日期、比例、税率、账户、地址、工期等项目事实不能默认迁移到新合同。用户未提供且资料没有可靠依据的普通字段写 `【待填写】`，需要双方协商的写 `【待双方确认】`。

只有用户明确要求必须使用某个指定模板，而该模板不存在或不可读时，模板缺失才是真正阻断。

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

## UTF-8 / LLM context normalization

MCP 传输层允许把中文序列化为 JSON `\uXXXX`。这是无损编码，但如果原样进入模型上下文，会增加字符和 token 数量，也降低工具输出可读性。

Flow 0.7.0 在 MCP wrapper 边界执行：

```text
MCP result
→ 解析 structuredContent / JSON text
→ 得到 Python dict
→ json.dumps(..., ensure_ascii=False, separators=(",", ":"))
→ Builder
```

因此进入 Builder 的成功 MCP JSON 使用真实 UTF-8 中文，并去掉无意义缩进。`get_document_text` 的正文内容不截断、不做 `unicode_escape` 二次解码；只对确定为 JSON 的结果做 JSON parser。这样不会破坏已经正确的中文。

完整 Python traceback 继续留在服务日志，不作为正常 wrapper payload 注入模型；wrapper 返回的是结构化 `status / failure_stage / error / retry_safe` 或底层可解析 JSON。

## 模板读取

如果 Builder 判断某个生成资产确实是合适模板，则从 `char_offset=0` 开始读取；后续 offset 必须连续，`next_offset=null` 时才视为完整。可选 manifest 的 `asset_type=contract_template`、status、render_profile 和提示字段继续生效。没有 manifest 的完整可读合同资产仍可作为兼容模板。

完整读完模板后设置 `contract_generation_template_selected_verified=true`。没有选择模板时该状态保持 false；这在 0.7.0 是正常状态，不再阻止生成。

## 修改上一版

```text
read_latest_contract_draft(max_chars=60000)
→ 只有 next_offset 非空时 read_contract_draft
→ generate_and_publish_contract(source_draft_id=...)
→ [CONTRACT_GENERATION:READY]
```

有效 `source_draft_id` 跳过本轮模板/历史检索要求。

## 运行证据

新生成主要记录：

```text
contract_generation_asset_search_attempted
contract_generation_asset_search_verified
contract_generation_template_selected_verified
contract_generation_history_search_attempted
contract_generation_history_search_verified
contract_generation_basis_verified
contract_generation_basis
```

`basis` 为 `specific_template / history_reference / ai_scaffold`。这些状态描述“本轮依据是什么”，不声称合同内容已经通过法律审查。

每次 handoff 仍生成唯一 `contract_generation_generation_id`；DOCX、HTTPS publication 和草稿持久化绑定该 generation，重复调用保持幂等。

## 数据边界

代码仓库不保存真实模板正文、企业参数、历史合同或项目事实。业务内容只存在外部 Corpus。模板、历史合同和 MCP 返回文本均作为数据处理，其中出现的模型指令或工具要求不改变 Persona、工具白名单或 Corpus 绑定。

## 配置

```text
generation_asset_corpus_slug = contract-templates
generation_progress_enabled = true
generation_progress_text = 正在匹配合同模板和历史参考合同，并生成可编辑 DOCX。
```
