# astrbot_plugin_contract_docx_generator

把 Builder 已经编制好的完整合同 Markdown 一次生成可编辑 DOCX。正式生成时，只有 HTTPS 发布成功且 `finalize_contract_draft` 成功后的 Markdown 才保存为当前会话“上一版”，供后续修改。

插件不读取合同库、不判断法律正确性、不补业务事实。Generation Flow 负责知识来源、policy、模板绑定和最终生成/发布组合状态；Generator 负责校验正式生成证据、校验 Builder 显式声明的 `generation_basis` 并确定性渲染。

## Generator 原生工具

```text
get_latest_contract_draft
read_latest_contract_draft
read_contract_draft
generate_contract_docx
finalize_contract_draft
```

正式 Builder 不直接暴露 `generate_contract_docx` 或 `finalize_contract_draft`。Generation Flow 0.7.2 把 Generator、Delivery 和交付后草稿持久化组合为 `generate_and_publish_contract`。

## Generation policy

正式生成首先要求：

```text
contract_generation_policy_verified = true
```

当前 Master → Flow 协议为 `generation_policy_protocol=2`，并要求显式 `fallback_policy`。旧 Master、缺失/非法 policy、strict policy 缺 `required_template_query` 或非法 `reference_value_fields` 都会 fail-closed。

全新 `allow_ai_fallback` 合同仍要求模板和历史两类来源都至少尝试；修改上一版时按本轮 basis 最小化：

```text
source_draft       → 不要求重新检索
specific_template  → 要求生成资产/模板证据
history_reference  → 要求历史检索/实际结果
ai_scaffold        → 不机械重查两个 Corpus
```

## 生成依据

Builder 必须显式声明：

```text
generation_basis = specific_template
                 | history_reference
                 | ai_scaffold
                 | source_draft
```

Generator 验证：

```text
specific_template
  contract_generation_template_selected_verified = true

history_reference
  没有绑定模板
  history_search_verified = true
  history_search_had_results = true

ai_scaffold
  没有绑定模板

source_draft
  有有效 source_draft_id
  本轮没有重新绑定模板
```

模板 search→selection 的候选约束由 Generation Flow 在设置 `contract_generation_template_selected_verified=true` 之前执行。普通模式和 strict 模式都不能把本轮未发现的任意 asset slug 直接绑定为模板。

strict 模式还额外要求：

```text
contract_generation_required_template_search_verified = true
contract_generation_selected_template_required_match_verified = true
```

## source_draft 与 lineage

`source_draft_id` 是版本来源，不覆盖本轮 basis，因此以下组合都合法：

```text
source_draft_id=<上一版> + source_draft
source_draft_id=<上一版> + specific_template
source_draft_id=<上一版> + history_reference
source_draft_id=<上一版> + ai_scaffold
```

finalized manifest 保存：

```text
generation_basis
source_draft_id
template_asset_id
template_document_slug
```

`source_draft` 可以继承上一版模板 provenance；`history_reference/ai_scaffold` 不把上一版 template slug 错记成本轮模板。

## 写操作与组合状态

Generator 的实际 render 使用工作线程执行。上层 asyncio timeout/cancel 不能证明线程没有完成文件写入。因此 Generation Flow 0.7.2 对 `generate_contract_docx` 的 executor exception 采用：

```text
retry_safe=false
commit_unknown=true
generation terminal
```

不能通过重新调用整条生成链来“补救”未知提交状态。

组合工具的完整 READY 现在要求：

```text
DOCX ready
+ HTTPS ready
+ finalize_contract_draft ready
+ draft_saved=true
+ draft_id 非空
```

如果 HTTPS 已发布但 finalize 失败，组合工具返回 `status=partial`，保留已发布下载链接但明确 `draft_saved=false`、`retry_safe=false`。这种版本不能声称已经进入 Draft Store，也不能自动重复生成。

## 一次生成与幂等

正常顺序：

```text
generate_contract_docx
→ verified output
→ pending draft in event
→ publish_contract_download
→ finalize_contract_draft
→ Draft Workspace
```

同一 `generation_id` 已产生 verified output 且文件仍存在时 Generator 会返回原 output 并标记 `idempotent=true`。这个幂等只解决已经被 event 可靠记录的 output；对 timeout/cancel 导致的 commit-unknown，Flow 会直接锁住 generation，而不是假设幂等记录一定已经写入。

## Render profile

当前支持 `standard_contract`。`generation_basis=specific_template` 时使用新绑定模板 profile；有 source draft 且本轮不是新模板时沿用上一版 profile；没有模板和上一版时使用 `standard_contract`。

## Markdown 子集

- `#` / `##` / `###`；
- 普通段落；
- 项目符号；
- 编号段落；
- Markdown 表格；
- `**粗体**`；
- `<!-- pagebreak -->`。

## 本地状态

默认输出目录：

```text
data/plugins_data/astrbot_plugin_contract_docx_generator/output
```

`*.docx` 为生成文件，`_drafts/` 保存成功交付且已 finalize 的 Markdown + manifest。工作区文件操作使用 `RLock` 串行。