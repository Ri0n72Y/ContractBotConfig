# AI 合同编制与 DOCX 生成架构

## 目标

正式合同生成不依赖 Docassemble interview/Jinja。Builder 先尝试利用 Generation Asset Corpus 和 Historical Contract Corpus，再编制完整 Markdown；DOCX Generator 一次生成 Word，Delivery 确定性发布 HTTPS，只有成功交付的 Markdown 才进入 Draft Store 供后续修改。

当前优先级：

1. 跑完整个真实链路；
2. 尽量减少一次生成中的 LLM API 回合；
3. 有合适企业模板/历史资料时优先使用；
4. 没有合适模板或参考时仍允许 AI 基于用户事实生成；
5. 不把历史合同的旧项目事实默认迁移到新合同；
6. 只针对低并发下真正存在的共享状态问题做线程安全处理。

```text
用户
  ↓
Master
  ↓
Contract Builder
  ├─ Generation Asset Corpus（优先尝试）
  ├─ Historical Contract Corpus（优先尝试）
  ├─ AI 自组织结构 fallback
  ├─ Final Draft Store
  └─ generate_and_publish_contract
       ├─ DOCX Generator
       ├─ HTTPS Delivery
       └─ delivery-success draft finalize
```

代码仓库不保存真实合同模板、企业参数、历史合同、项目事实或其他业务数据。

## 新合同生成依据

Builder 在首个知识工具回合优先并行调用：

```text
find_generation_assets(limit=3)
find_similar_contracts(limit=3)
```

两类调用都记录 `attempted`；底层 OpenContracts 成功时才记录 `verified`。Generator 要求两类来源都至少尝试过，但不要求任何来源必须成功。

最终依据按以下顺序确定：

```text
specific_template
  有明显匹配并已完整读取的专用合同模板

history_reference
  没有绑定专用模板，但历史相似合同检索成功

ai_scaffold
  没有可用模板或历史参考，由 AI 基于用户事实和通用合同知识组织完整结构
```

当前没有额外的“通用合同骨架”资产，也不假设存在一个 generic template。没有合适模板本身不是阻断条件；Builder 不应为了满足流程强行选择低相关模板。

只有用户明确要求必须使用某个指定模板，而该模板不存在或不可读取时，模板缺失才是 BLOCKED 条件。

## 信息来源与事实边界

Builder 使用顺序：

```text
用户本轮明确事实
  > 合适专用模板中的结构/企业规则
  > 历史相似合同中的可迁移结构和措辞
  > AI 通用合同知识
```

历史合同可参考：章节结构、条款组合、企业常用措辞、付款与验收逻辑、违约责任模式、附件组织。

历史合同不得默认迁移：旧当事人、旧项目名称、金额、单价、数量、具体日期、付款/质保/违约比例、税率、账户、地址、工期等项目特定事实。普通未知字段写 `【待填写】`；需要双方协商的写 `【待双方确认】`。

## 新生成链路

```text
Master handoff Builder

AI #1
├─ find_generation_assets(limit=3)
└─ find_similar_contracts(limit=3)

AI #2（按需要）
├─ 有合适模板：read_generation_asset(max_chars=80000)
├─ 历史摘要不足：read_reference_contract(max_chars=60000)
└─ 无需全文：直接起草

AI #3
└─ generate_and_publish_contract
   ├─ generate_contract_docx
   ├─ publish_contract_download
   └─ finalize_contract_draft（仅发布成功后）

AI #4
└─ [CONTRACT_GENERATION:READY]
```

Provider 不支持同一响应多 tool call 时才顺序执行。不要为 list/status/preflight、普通缺失字段或重复确认增加回合。

## 修改上一版

```text
read_latest_contract_draft(max_chars=60000)
→ 只有 next_offset 非空时 read_contract_draft
→ generate_and_publish_contract(source_draft_id=<上一版>)
→ [CONTRACT_GENERATION:READY]
```

有效 `source_draft_id` 表示用户已选定修改来源，因此不要求重新跑模板/历史检索，也不要求 OpenContracts 当前可用。

## Builder ToolSet ownership

Builder Persona 静态 Tools 为空。Generation Flow 0.7.0 在 handoff 前注入固定 wrapper：

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

## 模板读取与绑定

当 Builder 判断候选确实适合作为模板时，从 `char_offset=0` 开始读取；每块 offset 必须连续，`next_offset=null` 时才视为完整。Manifest 是可选元数据；没有 manifest 的完整可读合同资产仍可作为兼容模板。

完整读完合适模板后设置：

```text
contract_generation_template_selected_verified = true
```

没有选择模板时该状态保持 false，这是正常 fallback 状态，不再阻止 Generator。

## 正式生成证据

Generation Flow / Generator 0.7.0 / 0.5.0 使用：

```text
contract_generation_asset_search_attempted
contract_generation_asset_search_verified
contract_generation_template_selected_verified
contract_generation_history_search_attempted
contract_generation_history_search_verified
contract_generation_basis_verified
contract_generation_basis
```

Generator 对新合同的硬流程证据只有两个 `*_attempted`。之后自动记录 `specific_template / history_reference / ai_scaffold`。这些状态描述本轮生成依据，不代表法律审查或内容绝对正确。

## UTF-8 与模型上下文

OpenContracts MCP 可能把 JSON 中文序列化成 `\uXXXX`。Generation Flow 在 wrapper 边界先解析 JSON，再以：

```python
json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
```

重新返回 Builder。这样模型收到真实 UTF-8 中文，避免 raw Unicode escape 增加 token 和理解噪声。正文不使用 `unicode_escape` 二次解码。

完整 traceback 留在服务日志；正常模型工具结果保持结构化。Windows PowerShell 5.1 的 native stdin 编码风险见 `docs/deployment/utf8-runtime-boundaries.md`。

## DOCX、交付与 Draft Store

Generator 一次接收完整 `document_title + document_markdown` 并生成 DOCX。生成成功后先把 Markdown 保存在当前 event 的 pending draft；只有 HTTPS 发布成功后才调用 `finalize_contract_draft` 写入 `_drafts/`。

同一 `generation_id` 的 verified DOCX 和成功 publication 均幂等复用，避免模型重复调用造成重复渲染或重复发布。DOCX 渲染发生不可重试失败后设置 terminal failure，同一 handoff 不重复烧生成回合。

当前 render profile 为 `standard_contract`。有模板时优先使用模板声明 profile；无模板时使用 `standard_contract`；未知 profile 回退到该值。

## 并发与运行依赖

- Generation Asset Corpus 为插件级配置；
- Historical Contract Corpus 为 event 级绑定；
- Builder Agent 只持有请求无关 wrapper ToolSet；
- wrappers 在调用时动态解析当前底层 Tool；
- Draft Store 使用 `RLock`；
- Publication audit 使用进程内锁；
- 每轮生成拥有唯一 generation_id。

Flow 在 handoff 层只把 Builder Persona protocol 不兼容视为正式运行阻断。知识库/Corspus/tool 的临时不可用由具体 wrapper 返回 blocked；完成两类知识来源尝试后，如果正式生成工具可用且用户没有指定模板硬要求，可进入 AI fallback。
