# astrbot_plugin_contract_docx_generator

把 Builder 已经编制好的完整合同 Markdown 一次生成可编辑 DOCX。正式生成时，只有 HTTPS 发布成功后的 Markdown 才保存为当前会话“上一版”，供后续修改。

插件不读取合同库、不判断法律正确性、不补业务事实、不要求模板章节与代码规则逐项匹配。

## Generator 原生工具

```text
get_latest_contract_draft        管理员/兼容用途，只返回最近成功交付草稿元数据
read_latest_contract_draft       最近成功交付草稿元数据 + 首段正文
read_contract_draft              仅在 next_offset 非空时继续读取
generate_contract_docx           生成 DOCX；正式 Builder 由 Flow 组合调用
finalize_contract_draft          内部工具；仅在 HTTPS 发布成功后持久化本轮草稿
```

正式 Builder 不直接暴露 `generate_contract_docx` 或 `finalize_contract_draft`。Generation Flow 将 Generator、Delivery 和交付后草稿持久化组合为：

```text
generate_and_publish_contract
```

因此模型完成合同正文后只需要一个工具回合即可得到 HTTPS 下载链接。

## 新生成

Generator 接收：

```text
document_title
document_markdown
output_filename (optional)
render_profile (optional)
```

一次生成完整 DOCX，不再使用由模型管理的 begin/chunk/finalize 草稿事务。`max_markdown_chars` 只限制一次生成允许接收的最大文本量。

正式生成顺序是：

```text
generate_contract_docx
→ verified DOCX output
→ pending draft 保存在当前 event
→ publish_contract_download
→ 发布成功后 finalize_contract_draft
→ Draft Workspace
```

因此 DOCX 已生成但 HTTPS 发布失败时，不会替换用户可修改的“上一版”。如果同一 generation 再次尝试组合工具，Generator 会复用已经生成的 DOCX，Delivery 也会复用已经成功的 publication；不需要重新生成合同正文。

同一 `generation_id` 已经产生 verified output 且文件仍存在时，再次调用 Generator 直接返回原 output，并标记：

```text
idempotent = true
```

不会重新渲染 Word，也不会覆盖本轮成功状态。

## 修改上一版

Builder 正式路径：

```text
read_latest_contract_draft(max_chars=60000)
→ 只有 next_offset 非空时 read_contract_draft
→ generate_and_publish_contract(source_draft_id=<上一版 draft_id>)
```

`read_latest_contract_draft` 在一次本地操作中找到当前会话最近成功交付的 finalized 草稿并读取首段正文，不需要先调用 lookup 工具。

提供有效 `source_draft_id` 后，Generator 会把它作为本轮修改来源，沿用上一版的模板/排版元数据；不要求为了简单修改重新跑模板和历史检索，也不要求 OpenContracts 当前可用。

最近草稿不维护单独的 latest index。工作区直接扫描当前会话 finalized manifests 找最近版本。低于约 20 个使用者时，这比维护跨文件事务更简单，也避免 index/manifest 崩溃顺序问题。

## 正式生成流程证据

新合同正式生成前只把以下两项作为 Generator 的代码级必要证据：

```text
contract_generation_asset_search_verified = true
contract_generation_template_selected_verified = true
```

Builder 仍在首轮优先调用 `find_similar_contracts`，历史合同用于相似场景措辞、结构和条款参考；但 `contract_generation_history_search_verified` 只保留为运行诊断，不再是 Generator 的硬门槛。历史 Corpus 或 OpenContracts 暂时不可用时，只要生成资产检索和完整模板读取已经成功，就不因为历史参考暂时缺失而阻止生成，也不增加 status/preflight 或客户确认。

这些状态不用于判断合同内容“严格正确”。修改已有成功交付 draft 时同样不要求模板或历史检索状态。

同一轮 DOCX 渲染发生明确不可重试失败后，会设置 terminal failure，后续重复生成直接 blocked，避免模型反复烧生成回合。

## Render profile

当前支持：

```text
standard_contract
```

正式新生成优先使用已读取模板声明的 profile；修改上一版优先沿用 source draft profile。未知 profile 在正式链路回退到 `standard_contract`，避免因为排版配置导致整轮合同重新生成。

## Markdown 子集

- `#` / `##` / `###`：标题；
- 普通段落：正文；
- `-` / `*` / `+`：项目符号；
- `1.` / `1)` / `1、`：编号段落；
- 标准 Markdown 表格；
- `**粗体**`；
- `<!-- pagebreak -->`：分页。

Generator 只要求 `document_title` 和 `document_markdown` 非空且不超过配置长度。Renderer 不执行唯一 H1、required headings、条款数量或商业逻辑等合同内容硬校验。

## 本地状态

默认输出目录：

```text
data/plugins_data/astrbot_plugin_contract_docx_generator/output
```

其中：

```text
*.docx       最终生成文件
_drafts/     已成功交付的最终 Markdown + manifest
```

草稿 manifest 包含会话 owner hash、generation_id、模板资产标识和输出元数据。工作区文件操作使用 `RLock` 串行，满足当前低并发部署需求。

插件依赖 `python-docx`，AstrBot 安装插件时根据 `requirements.txt` 安装依赖。
