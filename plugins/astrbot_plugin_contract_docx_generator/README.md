# astrbot_plugin_contract_docx_generator

把 Builder 已经编制好的完整合同 Markdown 一次生成可编辑 DOCX。正式生成时，只有 HTTPS 发布成功后的 Markdown 才保存为当前会话“上一版”，供后续修改。

插件不读取合同库、不判断法律正确性、不补业务事实。Generation Flow 负责知识来源尝试和模板绑定；Generator 负责校验正式生成证据、校验 Builder 显式声明的生成依据并确定性渲染。

## Generator 原生工具

```text
get_latest_contract_draft        管理员/兼容用途，只返回最近成功交付草稿元数据
read_latest_contract_draft       最近成功交付草稿元数据 + 首段正文
read_contract_draft              仅在 next_offset 非空时继续读取
generate_contract_docx           生成 DOCX；正式 Builder 由 Flow 组合调用
finalize_contract_draft          内部工具；仅在 HTTPS 发布成功后持久化本轮草稿
```

正式 Builder 不直接暴露 `generate_contract_docx` 或 `finalize_contract_draft`。Generation Flow 将 Generator、Delivery 和交付后草稿持久化组合为 `generate_and_publish_contract`。

## 新生成与生成依据

正式新生成前，Generator 要求 Builder 已经至少尝试过：

```text
contract_generation_asset_search_attempted = true
contract_generation_history_search_attempted = true
```

这两个状态表示流程已经尝试利用企业知识，不要求对应知识源一定成功。

Builder 在最终生成调用中必须显式声明：

```text
generation_basis = specific_template
                 | history_reference
                 | ai_scaffold
```

Generator 不根据“某次搜索调用成功”自动推导 basis，而是验证声明与证据：

```text
specific_template
  contract_generation_template_selected_verified = true

history_reference
  没有绑定专用模板
  contract_generation_history_search_verified = true
  contract_generation_history_search_result_count > 0

ai_scaffold
  没有绑定专用模板
  历史结果可以为空、不可用，或虽有候选但 Builder 判断不适配
```

这使 `ai_scaffold` 能准确表达“实际主要由 AI 基于用户事实和通用合同知识组织”，不会因为历史搜索技术上成功但结果为空而误记为 `history_reference`。

Generator 验证成功后写入：

```text
contract_generation_basis_verified = true
contract_generation_basis = <实际 basis>
```

## 指定模板约束

如果当前 event 中：

```text
contract_generation_require_specific_template = true
```

Generator 只接受 `generation_basis=specific_template`，并要求已经完整绑定一个模板。`history_reference` 和 `ai_scaffold` 都会被代码级阻断。

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

## 修改上一版

```text
read_latest_contract_draft(max_chars=60000)
→ 只有 next_offset 非空时 read_contract_draft
→ generate_and_publish_contract(
     source_draft_id=<上一版 draft_id>,
     generation_basis=source_draft
   )
```

有效 `source_draft_id` 代表用户已经选定修改来源，不要求重新跑模板或历史检索。上一版排版 profile 继续优先沿用。

`generation_basis` 会保存进 finalized draft manifest；`get_latest_contract_draft`、`read_latest_contract_draft` 和 `read_contract_draft` 都会把该字段返回。旧草稿 manifest 没有该字段时保持向后兼容。

## 内容边界

知识来源优先级由 Builder 执行：用户本轮明确事实优先；专用模板用于结构和企业规则；历史合同用于可迁移结构、条款组合和措辞。历史合同里的当事人、项目、金额、数量、日期、比例、税率、账户、地址和工期等旧项目事实不能默认进入新合同。

Renderer 不执行唯一 H1、required headings、条款数量或商业逻辑等合同内容硬校验。普通未知字段由 Builder 使用 `【待填写】`，需要双方协商的字段使用 `【待双方确认】`。

## Render profile

当前支持 `standard_contract`。正式新生成有专用模板时优先使用模板 profile；没有模板时使用 `standard_contract`。未知 profile 在正式链路回退到 `standard_contract`。

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
