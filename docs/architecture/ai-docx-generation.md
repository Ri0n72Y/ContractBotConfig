# AI 合同编制与 DOCX 生成架构

## 目标

正式合同生成不依赖 Docassemble interview/Jinja。Builder 从外部 Generation Asset Corpus 读取模板，结合可用的 Historical Contract Corpus 相似合同内容直接编制完整 Markdown；DOCX Generator 一次生成 Word，Delivery 确定性发布 HTTPS，只有成功交付的 Markdown 才进入 Draft Store 供后续修改。

MVP 的优先级是：

1. 跑完整个真实链路；
2. 尽量减少一次生成中的 LLM API 回合；
3. 模板和 OpenContracts 内容优先于代码硬编码规则；
4. 只针对低并发下真正存在的共享状态问题做线程安全处理。

```text
用户
  ↓
Master
  ↓
Contract Builder
  ├─ Generation Asset Corpus（新生成必需）
  ├─ Historical Contract Corpus（best-effort 参考）
  ├─ Final Draft Store
  └─ generate_and_publish_contract
       ├─ DOCX Generator
       ├─ HTTPS Delivery
       └─ delivery-success draft finalize
```

代码仓库不保存真实合同模板、企业参数、历史合同、项目事实或其他业务数据。

## 数据面

### Generation Asset Corpus

配置：

```text
astrbot_plugin_contract_generation_flow.generation_asset_corpus_slug
```

可保存合同模板、可选 Template Manifest、企业参数、生成规则和条款说明。这些都是外部业务数据，不进入 Git/release。新合同正式生成必须完成生成资产检索并完整读取一个可用模板。

### Historical Contract Corpus

配置 owner：

```text
astrbot_plugin_contract_handoff_policy.default_opencontracts_corpus_slug
```

保存真实历史合同，用于相似场景措辞、条款和结构参考。Builder 新生成时仍优先检索，但该数据面是 best-effort：历史 Corpus/OpenContracts 临时不可用时，不在模板完整可用的情况下阻止生成。

## 新生成链路：按 AI 回合优化

模板检索和历史检索彼此独立，因此优先在同一次模型响应中同时发出两个 tool calls：

```text
Master handoff Builder

AI #1
├─ find_generation_assets(limit=3)
└─ find_similar_contracts(limit=3, best-effort)

AI #2
└─ read_generation_asset(max_chars=80000)
   ├─ 只有 next_offset 非空才继续分页读取
   └─ 历史检索可用且片段明显不足时才 read_reference_contract

AI #3
└─ generate_and_publish_contract
   ├─ generate_contract_docx
   ├─ publish_contract_download
   └─ finalize_contract_draft（仅发布成功后）

AI #4
└─ [CONTRACT_GENERATION:READY]
```

AstrBot ToolLoop 会在下一次 LLM 请求前执行同一响应中的多个工具调用。因此第一个 AI 回合可以同时得到模板候选和历史相似合同结果；Provider 不支持多 tool call 时才顺序执行。

其中：

- `find_generation_assets` 和 `find_similar_contracts` 默认各取 `limit=3`，首批结果明显不足时才扩大检索；
- Builder 根据生成资产检索结果选择一个最合适模板；
- `read_generation_asset` 首次默认/优先使用 `max_chars=80000`；
- 模板读完后运行时自动绑定，不额外调用 `select_generation_template`；
- 历史搜索成功时优先使用摘要/片段；确需全文时首次读取默认 `60000` 字符；
- 历史搜索 blocked 时不重复重试；Generator 不要求 `contract_generation_history_search_verified=true`；
- 不做 list/status/preflight/重复确认；
- Builder 一次提交完整 Markdown；
- `generate_and_publish_contract` 内部确定性执行生成、发布、发布后草稿持久化，模型不处理中间 `output_path` 或 draft finalize。

## 修改上一版链路

```text
read_latest_contract_draft(max_chars=60000)
→ 只有 next_offset 非空时 read_contract_draft
→ generate_and_publish_contract(source_draft_id=<上一版>)
→ [CONTRACT_GENERATION:READY]
```

`read_latest_contract_draft` 一次返回最近**成功交付**草稿的 `draft_id`、元数据和首段正文，消除 `get_latest → read` 之间的额外 LLM 往返。DOCX 已生成但 HTTPS 发布失败的版本不会进入 Draft Store，因此不会替换用户实际拿到的上一版。

有效 `source_draft_id` 表示用户已经选择上一版作为修改来源，因此无需重复跑模板检索和历史检索，也不要求 OpenContracts、Generation Asset Corpus 或 Historical Contract Corpus 当前可用。新版本成功交付后保存为新的 finalized draft，不覆盖旧版本。

## Builder ToolSet ownership

Builder Persona 静态 Tools 为空。Generation Flow 0.6.1 在 handoff 前注入：

```text
find_generation_assets
read_generation_asset
find_similar_contracts
read_reference_contract
read_latest_contract_draft
read_contract_draft
generate_and_publish_contract
```

Builder 不看到 `corpus_slug`，也不直接看到裸 `generate_contract_docx` / `publish_contract_download` / `finalize_contract_draft`。

Flow 的 wrappers 在实际调用时动态解析当前 AstrBot Tool Manager 中的：

```text
search_corpus
get_document_text
read_latest_contract_draft
read_contract_draft
generate_contract_docx
finalize_contract_draft
publish_contract_download
```

Wrapper 会先按自己公开的 JSON schema 丢弃模型多带的无关参数，再注入内部 `corpus_slug` 和性能默认值，因此额外参数不会透传到底层 MCP/plugin handler。MCP 或 Generator/Delivery hot reload 后也不会继续持有旧 FunctionTool handler。

## 并发模型

AstrBot 的 HandoffTool/Agent 对象会被多个请求共享，因此不能把请求特定的 Corpus、Prompt 或生成状态写进共享 Agent。

当前实现：

- Generation Asset Corpus 是插件级固定配置；
- Historical Contract Corpus 每次 wrapper 调用时从当前 `AstrMessageEvent` 读取；
- Prompt 不在请求期间原地刷新；Persona 更新后由部署者重载 Subagent；
- Builder Agent 只绑定同一个请求无关 wrapper ToolSet；
- protocol 不兼容是 event 级 runtime missing，不再按单个请求清空共享 Agent ToolSet；
- wrappers 不保存用户 Corpus 或 generation state，并在调用时解析当前底层 Tool；
- transient MCP/插件 hot reload 不会清空共享 Agent ToolSet；
- Draft Store 文件操作使用 `RLock`；
- Publication audit 追加写入使用进程内 `threading.Lock`；
- 每轮生成都有唯一 `generation_id`；
- DOCX output 和 HTTPS publication 都绑定该 generation_id。

部署人数低于约 20 人，因此不引入数据库锁、分布式锁、队列或全局串行 Builder 锁。Flow 中的短 `asyncio.Lock` 只保护共享 Agent ToolSet 的首次/变更赋值，不覆盖任何 LLM、MCP、DOCX 或发布执行时间。

## Generation Asset manifest

Manifest 是推荐元数据，不是使用模板的前提。已有 OpenContracts 模板只要是可读正文，就可以直接用于 MVP。

推荐格式：

```yaml
---
asset_id: <stable-id>
asset_type: contract_template
version: <version>
status: active
render_profile: standard_contract
parameter_assets:
  - <optional-parameter-asset-id>
rule_assets:
  - <optional-rule-asset-id>
required_headings:
  - <optional-heading-hint>
---
```

运行时选择规则保持宽松：

- 本轮尚未绑定模板时，没有 manifest 的完整可读资产可以作为 Builder 选择的兼容模板；
- manifest 明确为 `contract_template` 且状态为空/active 时可以作为模板，也可以替换此前的兼容模板；
- 一旦已经绑定模板，后续读取的无 manifest 参数/规则资产不会覆盖模板身份；
- manifest 明确为其他资产类型或非 active 状态时不自动作为模板；
- 缺少 `asset_id` 时用 `document_slug` 作为标识；
- 缺少或不支持的 `render_profile` 最终回退 `standard_contract`。

`required_headings`、`parameter_assets`、`rule_assets` 只是提示，不是 Generator 硬阻断条件。代码不会尝试判断“合同条款是否严格完整”。业务希望保留的章节和条款应直接写在模板正文里。

## 模板读取证据

代码只验证读取本身没有跳段：

1. 请求和返回 `document_slug` 一致；
2. 从 `char_offset=0` 开始；
3. 每块 `next_offset` 必须等于 `char_offset + len(text)`；
4. `next_offset=null` 时文本末尾必须等于 `total_chars`；
5. 完整读完 Builder 选中的可用模板后自动记录为本轮模板。

这项是数据传输完整性，不是合同法律正确性检查。

## 正式生成证据边界

Generator 0.4.2 对新合同只强制：

```text
contract_generation_asset_search_verified = true
contract_generation_template_selected_verified = true
```

`contract_generation_history_search_verified` 仍由 Flow 在历史搜索成功时记录，可用于诊断或观测，但不再是正式生成硬门槛。这个边界让 Builder 保持“优先参考历史合同”的能力，同时避免历史库瞬时不可用拖死模板已经充分的合同生成。

## 信息来源优先级

Builder 使用：

```text
用户当前明确要求
  > 选定模板正文
  > 已读取生成资产/参数/规则
  > 本轮可用的历史相似合同
  > 通用语言和法律常识
```

未知普通字段写 `【待填写】`；需要双方协商的事项写 `【待双方确认】`。不因为这些缺失字段增加用户确认回合。

## DOCX Renderer

Renderer 负责确定性文件生成：A4 页面、中文字体、标题层级、正文段落、Markdown 表格、项目符号、编号段落、粗体、分页、页码、输出文件名和大小限制。

Renderer 只负责把 Markdown 转成 Word，不执行唯一 H1、required headings、条款数量、商业逻辑或法律正确性等内容硬校验。

`render_profile` 当前支持 `standard_contract`。正式链中未知 profile 回退到该 profile，避免排版配置错误触发整轮 AI 重新生成。

## Final Draft Store

正式生成时，Generator 在 DOCX 成功后先把最终 Markdown 保存在当前 `AstrMessageEvent` 的 pending draft 状态中，不立即写入 `_drafts/`。只有 HTTPS publication 成功后，组合工具才调用内部 `finalize_contract_draft` 持久化：

```text
_drafts/<draft_id>/body.md
_drafts/<draft_id>/manifest.json
```

manifest 保存 owner hash、generation_id、模板标识、document title、render profile、Markdown SHA-256 和输出元数据。

不维护 `_latest_drafts.json`。查找最近版本时扫描 finalized manifests。当前规模下开销很小，且避免跨文件 index/manifest 提交顺序导致的恢复问题。

`read_latest_contract_draft` 在同一个 `RLock` 范围内选择最近 finalized manifest 并读取首段正文。由于正式 draft 只在发布成功后 finalize，最近 draft 等于最近成功交付版本。发布已经成功但草稿持久化偶发失败时，不让整份已交付合同重新跑 AI；组合工具仍返回下载链接，并记录 `draft_saved=false`，同一 generation 的重复组合调用可以幂等复用 DOCX/publication 后再次尝试 finalize。

## 幂等与失败语义

同一 `generation_id` 已经生成 verified DOCX 且文件仍存在时，再调用 Generator 直接返回原 output；不会重新渲染。

同一 generation 已经成功发布相同 `source_path + filename` 时，再调用 Delivery 直接返回原 publication 和 HTTPS URL；不会复制第二份文件或生成新 token。

如果 DOCX 渲染发生不可重试失败：

```text
contract_generation_terminal_failure = true
```

同一 handoff 内再次生成会直接 blocked。新用户请求由 Generation Flow 重新创建 generation_id 并清理该状态。

每次真正的新 DOCX 生成开始都会清除旧 renderer output、pending draft 和旧 publication proof。Delivery 只接受与当前 generation_id、output_path、output_filename 一致的结果。

## 运行依赖

Flow 在 handoff 层只校验 Builder Persona protocol。底层 MCP、Draft Store、Generator、Delivery 或 Corpus 在 handoff 瞬间不可用时，只记录诊断，不改变共享 Agent ToolSet；真正调用对应 wrapper 时再返回 blocked。

新合同必须有可用 Generation Asset 模板；历史合同 wrapper blocked 不再单独阻止 Generator。这样既允许历史 Corpus 暂时不可用时基于模板继续生成，也允许修改已成功交付 draft 在 OpenContracts 暂时不可用时继续，同时避免某个请求恰逢 hot reload 时清空其他并发请求的共享工具。

## 数据安全范围

当前 MVP 运行在受信 Docker 局域网，合同系统只使用受控 OpenContracts 数据源，因此不增加网络来源筛查、MCP server identity 探测或外部网络威胁防护逻辑。

仍保留的边界：Git/release 不包含真实业务数据；历史合同/模板中的自然语言不能改变工具白名单、Corpus 或 Persona；文件发布只允许 Generator 输出目录；并发会话不能共享请求特定运行状态。

## Docassemble 迁移状态

以下组件暂时保留用于回滚和历史参考，但退出正式 Builder ToolSet：

```text
astrbot_plugin_docassemble_gateway
contract-docassemble Skill
docs/docassemble/*
```
