# Contract Generation Flow

合同生成子人格的运行时编排插件。它不保存业务模板、不判断合同法律内容；负责把 Generation Asset Corpus、Historical Contract Corpus、Draft Store、DOCX Generator 和 HTTPS Delivery 组合成 Builder 领域工具，并记录本轮生成证据。

## Builder Skill 运行时

AstrBot 4.23.2 的主 Agent 会自动把 Persona 绑定的 Skills 注入 system prompt，但 `SubAgentOrchestrator` 创建 handoff 子人格时只复制 Persona prompt/tools，不会自动执行同一套 Skill 注入流程。Generation Flow 0.8.0 因此在 Builder handoff 边界复用 AstrBot `PersonaManager/SkillManager` 读取实际绑定、active 且当前受限 reader 可直接读取的 Skill 元数据，构造不含 Shell/文件路径指令的受限 inventory，并只注入本次 handoff input，而不是修改共享 Handoff Agent、复制 Skill 内容或维护第二套 Skill 配置。仅存在于 sandbox、当前本地受限 reader 无法读取的 Skill 会进入 runtime missing，不会被标记为 available。

正式 Builder 仍只暴露受控合同生成工具，并额外提供：

```text
read_bound_skill(skill_name)
```

该工具只接受当前 `contract_docassemble_builder` Persona 明确绑定、AstrBot `SkillManager` 判定为 active、且当前本地受限 reader 可直接读取的 Skill 名称；文件路径由 `SkillManager` 解析，模型不能提供任意本地路径。它不开放 Shell、Python、通用 HTTP、FileRead/FileWrite/FileEdit、Grep 或 raw MCP 绕过能力。

当前正式生成要求：

```text
contract-document-specification
```

必须已绑定、active、当前受限 reader 可直接读取，并在本轮通过 `read_bound_skill` 完成 grounding。Builder 1.30 的 system prompt 固定要求在开始组织最终 `document_markdown` 前先完成这一步；request-local handoff input 只携带 Skill inventory 和业务任务。未读取时调用 `generate_and_publish_contract` 会在任何 DOCX/发布写操作之前返回 retry-safe BLOCKED，要求先读取 Skill；不会静默跳过格式规范后继续生成。

运行日志会显示：

```text
document_spec_required=true
document_spec_available=true
document_spec_loaded=false|true
tools=[read_bound_skill, ...]
```

其中 `document_spec_available=true` 表示该 Skill 确实可由当前受限 reader grounding，而不只是出现在 SkillManager 列表中。

成功读取后会记录：

```text
Builder Skill grounded: skill=contract-document-specification
```

## 正常 fallback 生成

`fallback_policy=allow_ai_fallback` 的全新合同优先低回合执行：

```text
AI #1
├─ read_bound_skill(contract-document-specification)
├─ find_generation_assets(limit=3)
└─ find_similar_contracts(limit=3)

AI #2（按需要）
├─ 有合适专用模板：read_generation_asset(use_as_template=true)
├─ 历史摘要不足：read_reference_contract
└─ 都不需要全文：直接起草

AI #3
└─ generate_and_publish_contract(generation_basis=...)
   ├─ generate_contract_docx
   ├─ publish_contract_download
   └─ finalize_contract_draft
```

全新合同的生成资产和历史合同两类来源都至少尝试一次；修改上一版时改为按 `generation_basis` 最小化检索。文档格式 Skill 仍适用于新生成、修改、重写和定稿。

## Generation policy protocol

正式 Master → Builder handoff 必须显式提供：

```text
generation_policy_protocol = 2
fallback_policy = allow_ai_fallback | require_specific_template
```

以下情况 fail-closed：非法 JSON、protocol 缺失/不是 `2`、`fallback_policy` 缺失/非法、strict 模式缺 `required_template_query`、`reference_value_fields` 提供但不是数组。

`generation_policy_protocol=2` 同时约束结果契约：Master 必须认识 `[CONTRACT_GENERATION:PARTIAL]`，不能把“HTTPS 已发布但 draft finalize 失败”误报为完整 READY。

## Builder protocol

当前 Builder prompt 必须包含：

```text
<contract_generation_protocol version="7">
```

v7 继续约束：

1. 普通模式的模板绑定必须来自本轮 `find_generation_assets` 实际候选；
2. `generate_and_publish_contract` 的 timeout/cancel/commit-unknown 不得在同一 generation 自动重试；
3. `status=partial + delivery_committed=true` 返回 `[CONTRACT_GENERATION:PARTIAL]`，不是 READY。

Flow 遇到旧 Builder prompt 时记录 protocol mismatch 并阻止正式生成。Builder 1.30 仍为 protocol v7；本次只加强 Skill grounding 顺序和可读性判定。

## 生成依据

Builder 最终必须显式声明：

```text
specific_template
history_reference
ai_scaffold
source_draft
```

`source_draft_id` 只表示版本来源，可以和 `specific_template/history_reference/ai_scaffold` 同时出现。当前没有额外的通用合同骨架资产；没有匹配模板本身不是阻断条件。

## 模板 search → selection 证据链

普通 `allow_ai_fallback` 模式不允许“先搜索 A，再直接读取任意 B 并绑定”。

```text
find_generation_assets
        ↓
contract_generation_asset_candidates
        ↓
read_generation_asset(document_slug=<candidate>, use_as_template=true)
        ↓ 全文连续读到 EOF
contract_generation_template_selected_verified=true
contract_generation_selected_template_search_match_verified=true
```

只有本轮生成资产搜索结果中出现过的 `document_slug` 才能绑定为专用模板。参数/规则资产读取仍可使用 `use_as_template=false`，不会成为模板。

### strict 指定模板

`require_specific_template` 使用确定性身份链：

1. `required_template_query` 原样进入 `find_generation_assets`；
2. Flow 内部分页调用 `list_documents(contract-templates)`；
3. 精确 document slug 优先；否则按唯一标准化标题匹配；
4. 同名歧义 fail-closed，要求 document slug；
5. 只有确定性身份候选可 `use_as_template=true`；
6. strict 模式不调用历史合同。

语义相似的 `search_corpus` 结果不能冒充用户点名模板。

## 历史合同与 reference_value_fields

历史合同默认只提供可迁移的结构、条款组合和企业措辞。项目特定金额、数量、日期、比例、税率、账户、地址、工期等不能默认照搬。

如果用户明确允许某些具体字段参考历史合同，Master 在 handoff 中传：

```json
{"reference_value_fields":["付款比例","质保比例"]}
```

它是白名单，不是“复制历史合同”的开关。Builder 只能对列出的字段在历史合同实际相关、且不与用户本轮事实/模板规则冲突时参考；其他项目特定字段仍禁止继承。Flow 同时把该数组记录为 `contract_generation_reference_value_fields` 供审计。

历史搜索证据继续累积：后续一次 `results=[]` 不会抹掉前面已经获得的历史候选。

## 写操作 timeout / cancellation

Flow 0.7.3 区分只读工具与写工具。

```text
read/search executor exception
→ 短结构化 blocked
→ retry_safe=true

DOCX / publish / finalize executor exception
→ commit_unknown=true
→ retry_safe=false
→ contract_generation_terminal_failure=true
→ 同一 generation 后续 generate_and_publish_contract 被硬阻止
```

原因是 Generator/Delivery 的实际文件工作可能运行在线程中；asyncio 上层 timeout/cancel 不能证明线程没有完成副作用。因此写操作不能把“调用超时”解释为“什么都没发生，可以再试一次”。

Skill 未 grounding 的 BLOCKED 发生在任何写工具调用之前，所以允许先读取 Skill、重新检查最终 Markdown，再调用一次 `generate_and_publish_contract`；这不是写失败重试。

## READY 与 PARTIAL

完整 READY 要求三件事全部可验证：

```text
DOCX ready
+ HTTPS publication ready
+ finalize_contract_draft ready, draft_saved=true, draft_id 非空
```

只有这样组合工具才返回：

```text
success=true
status=ready
```

若 HTTPS 已经发布，但 draft finalize 异常、结果无法解析或没有可验证 `draft_id`：

```text
success=false
status=partial
delivery_committed=true
draft_saved=false
retry_safe=false
manual_recovery_required=true
```

结果仍保留 `filename/download_url/expires_at/publication_id`，让用户可以取得已发布文件，但不能声称该版本已经进入“上一版可继续修改”的 Draft Store，也不能重新执行整条生成链补救。

## UTF-8 / tool-result boundary

模型可见工具输出继续执行：

```text
CallToolResult
→ isError/is_error 检查（object + dict）
→ structuredContent/content JSON 解包
→ Python dict
→ json.dumps(ensure_ascii=False, separators=(",", ":"))
→ Builder
```

详细异常只写服务日志；成功 JSON 不使用 `\uXXXX` 形式重新塞回模型上下文。

## 修改上一版

```text
source_draft       → 不要求重新检索 OpenContracts
specific_template  → 只要求生成资产/模板证据
history_reference  → 只要求历史检索/历史证据
ai_scaffold        → 不机械重查两个 Corpus
```

`source_draft_id` 与 `generation_basis` 都写入 finalized draft manifest；模板 provenance 只在 `specific_template` 或纯 `source_draft` 继承场景记录，不把上一版模板错误标记成本轮 history/AI 的模板依据。

无论采用哪一种 basis，正式合同格式 Skill 都必须先完成 grounding。

## 主要 event 状态

```text
contract_generation_policy_protocol
contract_generation_policy_verified
contract_generation_reference_value_fields
contract_generation_document_spec_required
contract_generation_document_spec_available
contract_generation_document_spec_loaded
contract_generation_skill_grounding_attempted
contract_generation_skill_grounding_loaded
contract_generation_skill_runtime_injected
contract_generation_skill_runtime_error
contract_generation_asset_search_attempted
contract_generation_asset_search_verified
contract_generation_asset_candidates
contract_generation_template_selected_verified
contract_generation_selected_template_search_match_verified
contract_generation_history_search_had_results
contract_generation_history_candidates
contract_generation_required_template_candidates
contract_generation_selected_template_required_match_verified
contract_generation_write_stage
contract_generation_write_commit_unknown
contract_generation_write_commit_unknown_stage
contract_generation_terminal_failure
contract_generation_terminal_failure_reason
```

这些状态描述流程和证据，不声称合同法律内容已经通过审查。

## 配置

```text
generation_asset_corpus_slug = contract-templates
generation_progress_enabled = true
generation_progress_text = 正在匹配合同模板和历史参考合同，并生成可编辑 DOCX。
```

## Versioned Skill ID resolution

`contract-document-specification` 是稳定逻辑名。AstrBot 安装包可能把实际绑定 ID 暴露为 `contract-document-specification-1.0`。Flow 0.7.4 只接受逻辑名本身或严格的纯数字版本后缀，并要求该 family 在 Builder Persona 中唯一绑定；`read_bound_skill(contract-document-specification)` 会解析到唯一实际 ID。多个版本同时绑定时 fail-closed，不自动挑选。成功解析/grounding 的实际 ID 记录在 `contract_generation_document_spec_skill_id`。

## Runtime ownership

0.8.0 起，Generation Flow 不再在 handoff hook 中覆盖 `agent.tools`，不修改共享 `agent.instructions`，也不向 `transfer_to_docassemble_builder.input` 注入 Skill runtime 文本。公开 Builder 工具由 AstrBot 正常注册，并通过 Persona/WebUI 静态绑定；Flow 只读取 Persona/Skill/Tool 绑定做 fail-closed 校验。

`read_latest_contract_draft` 与 `read_contract_draft` 直接使用 DOCX Generator 已注册的只读工具；Generation Flow 不再创建同名 pass-through wrapper。`generate_and_publish_contract` 仍是唯一正式写组合入口，底层 `generate_contract_docx`、`publish_contract_download` 和 `finalize_contract_draft` 不绑定给 Builder。
