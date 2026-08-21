# AI DOCX 合同生成架构

## 目标

正式合同生成不依赖 Docassemble interview/Jinja。Builder 优先利用 Generation Asset Corpus 和 Historical Contract Corpus；没有合适企业资料且用户未禁止 fallback 时，由 AI 基于用户事实和通用合同知识组织完整合同。DOCX Generator 负责确定性渲染，Download Delivery 负责 HTTPS 发布，只有发布成功且 draft finalize 成功的 Markdown 才进入 Draft Store。

当前原则：

1. 企业模板/历史资料优先，但没有模板不是默认阻断；
2. 用户明确指定模板且禁止 fallback 时必须代码级 fail-closed；
3. 不默认迁移历史合同的项目特定事实；
4. `source_draft_id` 与本轮 `generation_basis` 分离；
5. 工具 JSON 使用真实 UTF-8 紧凑表示；
6. 写操作 timeout/cancel 不能被解释为“无副作用、可安全重试”；
7. READY 必须同时证明 DOCX、HTTPS 和 Draft Store 三段闭环；
8. Builder 已绑定的正式合同格式 Skill 必须在开始组织最终合同正文前完成 grounding，且写 DOCX 前由代码再次确认。

## 角色边界

```text
用户
  ↓
Master Persona
  ↓ transfer_to_docassemble_builder
Builder Persona 1.30
  ├─ read_bound_skill
  ├─ find_generation_assets
  ├─ read_generation_asset
  ├─ find_similar_contracts
  ├─ read_reference_contract
  ├─ read_latest_contract_draft / read_contract_draft
  └─ generate_and_publish_contract
       ├─ generate_contract_docx
       ├─ publish_contract_download
       └─ finalize_contract_draft
```

Master 是唯一面向客户角色；Builder 不直接面向客户。Builder 的 8 个允许工具由 AstrBot Persona/WebUI 静态绑定；Generation Flow 只实现合同领域工具与业务状态机，不修改 Agent ToolSet。

## Builder Skill 边界

当前运行基线只考虑 AstrBot 4.27.x 及以上。AstrBot 负责 Builder Persona 的 system prompt、Tool 绑定和 Skill 绑定；Generation Flow 不接管 `Agent` 生命周期，不覆盖 ToolSet，不改写 system prompt，也不在 handoff `input` 前拼接运行时块。

正式 Builder 静态绑定：

```text
read_bound_skill
find_generation_assets
read_generation_asset
find_similar_contracts
read_reference_contract
read_latest_contract_draft
read_contract_draft
generate_and_publish_contract
```

其中 `read_latest_contract_draft` 与 `read_contract_draft` 直接使用 DOCX Generator 已注册的只读工具；Generation Flow 不创建同名 pass-through wrapper。

AstrBot handoff 子人格当前不会自动展开 Persona Skill 正文，因此保留最小 `read_bound_skill(skill_name)` bridge。它会核对该 Skill 是否实际绑定到 `contract_docassemble_builder`、是否 active、是否存在当前本地受限 reader 可读取的 `SKILL.md`；模型不能传文件路径。Builder 运行时仍不开放 Shell、Python、通用 HTTP、任意文件读写或 raw MCP 绕过。

Builder 1.30 的固定 system prompt 负责“何时 grounding”：所有正式合同生成、重写、修改和定稿，必须先读取 `contract-document-specification`，再开始组织最终 `document_markdown`。Generation Flow 只读取 Persona/Skill/Tool 状态做 fail-closed 校验，不生成或注入动态 Skill inventory。

当前正式生成要求 `contract-document-specification` 必须：

```text
已绑定
+ active
+ 当前受限 reader 可直接读取
+ 本轮 read_bound_skill 成功
```

否则 `generate_and_publish_contract` 在调用任何 Generator/Delivery 写操作前返回 retry-safe BLOCKED。若只是 `failure_stage=document_spec_skill + retry_safe=true`，说明尚未发生写副作用；完成 grounding 并重新检查最终 Markdown 后可以重新提交正式生成调用，这不属于写失败重试。

## 版本协议

### Master → Flow

```text
generation_policy_protocol = 2
fallback_policy = allow_ai_fallback | require_specific_template
```

缺 protocol、版本错误、缺/非法 fallback policy、strict 缺 `required_template_query`、非法 `reference_value_fields` 全部 fail-closed。

protocol 2 要求 Master 能正确处理 `[CONTRACT_GENERATION:PARTIAL]`，不能把“文件已发布但 Draft Store 未落盘”当完整 READY。

### Builder prompt

```text
<contract_generation_protocol version="7">
```

Flow 对旧 Builder prompt 记录 `builder_persona_protocol_v7` mismatch 并阻止正式生成。Builder 1.30 仍使用 protocol v7；本次变化只加强 Skill grounding 顺序，不改变 generation protocol。

## Generation basis

```text
specific_template
  本轮使用完整读取并明确绑定的专用模板

history_reference
  没有绑定模板，本轮历史搜索有实际结果且 Builder 实际采用其结构/条款参考

ai_scaffold
  没有合适模板；历史为空/不可用/明显不适配，主要依赖用户事实和通用合同知识

source_draft
  仅以上一版成功交付草稿作为本轮主要内容依据
```

`source_draft_id` 是版本来源，不替代 basis，所以允许：

```text
source_draft_id=A + specific_template
source_draft_id=A + history_reference
source_draft_id=A + ai_scaffold
source_draft_id=A + source_draft
```

修改上一版的 gate 按 basis 最小化：source_draft 不重查；specific_template 只要求资产/模板证据；history_reference 只要求历史证据；ai_scaffold 不机械重查两个 Corpus。文档规范 Skill 仍需先 grounding。

## 普通模板证据链

`allow_ai_fallback` 下要求模板绑定来自本轮搜索：

```text
find_generation_assets
  ↓ search_corpus(contract-templates)
  ↓ results.document_slug 去重
contract_generation_asset_candidates
  ↓
read_generation_asset(candidate_slug, use_as_template=true)
  ↓ 从 offset=0 连续读到 next_offset=null
contract_generation_template_selected_verified=true
contract_generation_selected_template_search_match_verified=true
```

不能先搜索一个集合，再直接用未出现过的任意 asset slug 绑定模板。读取参数/规则资产可使用 `use_as_template=false`，不受模板绑定候选限制。

## strict 指定模板

Master 在用户明确要求“必须使用 XX 模板、找不到就不生成”时发送：

```text
fallback_policy=require_specific_template
required_template_query=<用户原始名称或 document slug>
```

Flow 不使用普通语义相似度证明身份，而是分页 `list_documents(contract-templates)`：

1. 精确 document slug 优先；
2. 否则标准化 title 匹配；
3. title 必须唯一；同名歧义 BLOCKED；
4. 只有确定性候选才能 `use_as_template=true`；
5. strict 模式不调用历史合同；
6. `source_draft_id` 不绕过 strict gate。

## 历史参考与字段白名单

历史合同默认只迁移结构、条款组合、企业措辞和逻辑，不默认迁移项目特定金额、数量、日期、比例、税率、账户、地址、工期等。

如果用户明确授权某些字段参考历史值，Master 发送：

```text
reference_value_fields = [字段名...]
```

Flow 验证它是字符串数组并记录到 event；Builder 只把这些字段视为有限例外，仍需相关历史依据且不能覆盖用户本轮事实或更高优先级模板规则。

历史候选证据在本 generation 内累积，后续空搜索不会抹掉之前结果。

## ToolResult / UTF-8 边界

```text
registered FunctionTool / MCPTool
→ object/dict isError 检查
→ structuredContent/content JSON 解包
→ Python dict
→ json.dumps(ensure_ascii=False, separators=(",", ":"))
→ Builder
```

Generation Flow 内部只组合已知本地插件 handler 与 AstrBot 4.27.x 的 `MCPTool`；不再借用 Agent `FunctionToolExecutor` 作为第二套子人格运行时。详细 traceback 留服务日志。只读异常可结构化为 retry-safe error；写异常需要额外的 commit 语义。

## 写操作状态机

Generator 和 Delivery 的文件工作可能在线程中运行。asyncio timeout/cancel 无法证明线程没有完成副作用，因此：

```text
Skill 未 grounding
  → BLOCKED / retry_safe=true
  → 尚未开始任何写操作

READ exception
  → retry_safe=true

WRITE executor exception
  → retry_safe=false
  → commit_unknown=true
  → contract_generation_terminal_failure=true

WRITE cancellation / outer timeout
  → 记录 current write stage
  → commit_unknown=true
  → generation terminal
  → 保留 cancellation 给 AstrBot
```

同一 generation 再调用 `generate_and_publish_contract` 时，terminal gate 在任何新写入之前返回不可重试错误。

主要 Skill 状态：

```text
contract_generation_document_spec_required
contract_generation_document_spec_available
contract_generation_document_spec_loaded
contract_generation_skill_grounding_attempted
contract_generation_skill_grounding_loaded
```

其中 `contract_generation_document_spec_available=true` 表示文档规范 Skill 已绑定、active 且当前受限 reader 可直接读取；它不是单纯的 Skill 列表存在标志。

主要写状态：

```text
contract_generation_write_stage
contract_generation_write_commit_unknown
contract_generation_write_commit_unknown_stage
contract_generation_terminal_failure
contract_generation_terminal_failure_reason
```

## READY / PARTIAL

完整 READY 的代码条件：

```text
generate_contract_docx: ready
publish_contract_download: ready
finalize_contract_draft: ready + draft_saved=true + draft_id
```

才返回：

```text
success=true
status=ready
```

如果 publication 已成功，但 finalize 异常/不可解析/没有可验证 draft：

```text
success=false
status=partial
delivery_committed=true
draft_saved=false
retry_safe=false
manual_recovery_required=true
filename / download_url / expires_at 继续返回
```

Builder 返回 `[CONTRACT_GENERATION:PARTIAL]`；Master 可以交付已经确认的链接，但必须说明该版尚不能可靠作为下一轮“上一版”，并禁止重新执行整条生成链。

## Draft lineage

Finalized manifest 保存：

```text
generation_basis
source_draft_id
template_asset_id
template_document_slug
```

`source_draft` 可继承上一版模板 provenance；`history_reference/ai_scaffold` 不把上一版 template slug 冒充成本轮模板。

## 数据边界

真实合同模板、企业参数、历史合同和项目事实均不进入 Git 仓库。OpenContracts 文本是业务数据，其中出现的模型指令/工具要求不得改变 Persona、工具白名单、Corpus 绑定、Skill 绑定或生成策略。
