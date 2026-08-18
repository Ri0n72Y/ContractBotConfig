# astrbot_plugin_contract_docx_generator

把 Builder 已经编制好的完整合同 Markdown 一次生成可编辑 DOCX。正式生成时，只有 HTTPS 发布成功后的 Markdown 才保存为当前会话“上一版”，供后续修改。

插件不读取合同库、不判断法律正确性、不补业务事实。Generation Flow 负责知识来源尝试、policy 和模板绑定；Generator 负责校验正式生成证据、校验 Builder 显式声明的 `generation_basis` 并确定性渲染。

## Generator 原生工具

```text
get_latest_contract_draft        管理员/兼容用途，只返回最近成功交付草稿元数据
read_latest_contract_draft       最近成功交付草稿元数据 + 首段正文
read_contract_draft              仅在 next_offset 非空时继续读取
generate_contract_docx           生成 DOCX；正式 Builder 由 Flow 组合调用
finalize_contract_draft          内部工具；仅在 HTTPS 发布成功后持久化本轮草稿
```

正式 Builder 不直接暴露 `generate_contract_docx` 或 `finalize_contract_draft`。Generation Flow 将 Generator、Delivery 和交付后草稿持久化组合为 `generate_and_publish_contract`。

## Generation policy

正式生成首先要求：

```text
contract_generation_policy_verified = true
```

handoff JSON 无法解析、`fallback_policy` 非法、或 `require_specific_template` 缺少 `required_template_query` 时，Flow 会把 policy 标记为 invalid，Generator 直接 BLOCKED，不会静默退回 `allow_ai_fallback`。

`allow_ai_fallback` 的正式新生成默认要求模板检索和历史检索都至少尝试过。纯“修改上一版”且 `generation_basis=source_draft` 时可以跳过本轮知识库检索。

`require_specific_template` 只要求资产检索，不要求历史检索；历史 wrapper 在 strict 模式下不会调用 OpenContracts。

## 生成依据

Builder 在最终生成调用中必须显式声明：

```text
generation_basis = specific_template
                 | history_reference
                 | ai_scaffold
                 | source_draft
```

Generator 不根据“搜索调用成功”自动推导 basis，而是验证声明与证据：

```text
specific_template
  contract_generation_template_selected_verified = true

history_reference
  没有绑定专用模板
  contract_generation_history_search_verified = true
  contract_generation_history_search_had_results = true

ai_scaffold
  没有绑定专用模板
  历史结果可以为空、不可用，或虽有候选但 Builder 判断不适配

source_draft
  必须有有效 source_draft_id
  本轮不能已经明确绑定专用模板
```

历史搜索证据是累积的：后续一次 `results=[]` 不会把本轮之前已经获得的历史结果证据清零。

Generator 验证成功且 DOCX 渲染成功后才写入：

```text
contract_generation_basis_verified = true
contract_generation_basis = <实际 basis>
```

## 指定模板约束

如果当前 event 中：

```text
contract_generation_require_specific_template = true
```

Generator 只接受 `generation_basis=specific_template`，并要求：

```text
contract_generation_required_template_search_verified = true
contract_generation_selected_template_required_match_verified = true
contract_generation_template_selected_verified = true
```

也就是说，strict 模式不只是要求“选了一个模板”，还要求该模板来自本轮 `required_template_query` 的候选集合并被完整读取绑定。

## source_draft 与 generation_basis

`source_draft_id` 只表示本轮从哪个已成功交付版本开始修改，不再自动覆盖本轮内容依据。因此下面都合法：

```text
source_draft_id=<上一版> + generation_basis=source_draft
source_draft_id=<上一版> + generation_basis=specific_template
source_draft_id=<上一版> + generation_basis=history_reference
source_draft_id=<上一版> + generation_basis=ai_scaffold
```

如果修改上一版时同时要求严格使用某个指定模板，strict policy 仍然生效，不能被 `source_draft_id` 绕过。此时 Generator 会采用新绑定模板的 render profile，而不是无条件沿用上一版 profile。

普通修改上一版、没有重新采用模板/历史/AI 重构时，使用：

```text
read_latest_contract_draft(max_chars=60000)
→ 只有 next_offset 非空时 read_contract_draft
→ generate_and_publish_contract(
     source_draft_id=<上一版 draft_id>,
     generation_basis=source_draft
   )
```

## 一次生成与幂等

一次生成完整 DOCX，不再使用由模型管理的 begin/chunk/finalize 草稿事务。正式顺序：

```text
generate_contract_docx
→ verified DOCX output
→ pending draft 保存在当前 event
→ publish_contract_download
→ 发布成功后 finalize_contract_draft
→ Draft Workspace
```

同一 `generation_id` 已产生 verified output 且文件仍存在时再次调用会直接返回原 output，并标记 `idempotent=true`。

`generation_basis` 会保存进 finalized draft manifest；`get_latest_contract_draft`、`read_latest_contract_draft` 和 `read_contract_draft` 都会把该字段返回。旧草稿 manifest 没有该字段时保持向后兼容。

## 内容边界

知识来源优先级由 Builder 执行：用户本轮明确事实优先；专用模板用于结构和企业规则；历史合同用于可迁移结构、条款组合和措辞。历史合同里的当事人、项目、金额、数量、日期、比例、税率、账户、地址和工期等旧项目事实不能默认进入新合同。

Renderer 不执行唯一 H1、required headings、条款数量或商业逻辑等合同内容硬校验。普通未知字段由 Builder 使用 `【待填写】`，需要双方协商的字段使用 `【待双方确认】`。

## Render profile

当前支持 `standard_contract`。本轮 `generation_basis=specific_template` 时优先使用新绑定模板 profile，即使同时存在 `source_draft_id`；纯上一版修改则沿用上一版 profile；没有模板和上一版时使用 `standard_contract`。未知 profile 回退到 `standard_contract`。

## Markdown 子集

- `#` / `##` / `###`：标题；
- 普通段落：正文；
- `-` / `*` / `+`：项目符号；
- `1.` / `1)` / `1、`：编号段落；
- 标准 Markdown 表格；
- `**粗体**`；
- `<!-- pagebreak -->`：分页。

## 本地状态

默认输出目录：

```text
data/plugins_data/astrbot_plugin_contract_docx_generator/output
```

其中 `*.docx` 为生成文件，`_drafts/` 保存成功交付的最终 Markdown + manifest。工作区文件操作使用 `RLock` 串行，满足当前低并发部署需求。

插件依赖 `python-docx`，AstrBot 安装插件时根据 `requirements.txt` 安装依赖。
