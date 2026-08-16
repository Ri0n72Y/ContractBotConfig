# Persona 手动配置与 Markdown 发布

## 发布约定

本地构建后，`dist/personas/` 为每个人格生成一份手动配置 Markdown。绑定源数据以 `personas/bindings.json` 为准。

## contract_master_orchestrator 1.23

Tools：

```text
transfer_to_opencontracts_operator
transfer_to_docassemble_builder
```

Skills：

```text
contract-direct-analysis
contract-conversation-control
contract-result-verification
```

生成、起草、修改合同直接委派 Builder，不先经过 Operator。handoff 不携带 corpus slug。

## contract_opencontracts_operator 1.17

Tools：

```text
list_documents
get_document_text
search_corpus
opencontracts_gateway_status
opencontracts_upload_document
```

Skills：`contract-opencontracts`、`contract-result-verification`。

## contract_docassemble_builder 1.25

Persona ID 暂时保持旧名称以避免重建现有 handoff 配置；正式运行不使用 Docassemble。

**WebUI 静态 Tools 必须为空：**

```text
tools: []
```

Skills：无。

不要手工给 Builder 绑定 OpenContracts MCP、DOCX Generator 或 Delivery 工具。Generation Flow 0.6.1 在 handoff 前注入：

```text
find_generation_assets
read_generation_asset
find_similar_contracts
read_reference_contract
read_latest_contract_draft
read_contract_draft
generate_and_publish_contract
```

Builder Persona 必须包含：

```text
<contract_generation_protocol version="4">
```

更新 Builder Persona 后重载对应 Subagent/Agent。Flow 不在每个请求里覆盖共享 Agent Prompt；运行 wrapper 本身也不持有请求级 Corpus 或底层 MCP/插件 handler。无论 protocol 是否兼容，Flow 都把共享 Builder Agent 约束到同一请求无关 wrapper ToolSet；protocol 不兼容只在当前 event 阻断正式生成。

Builder 1.25 仍要求新合同首轮优先同时调用 `find_generation_assets` 与 `find_similar_contracts`，但历史合同检索属于 best-effort 参考。历史 Corpus/OpenContracts 暂时不可用时，不重复重试历史检索，也不在完整模板已经可用的情况下阻止生成。

## File Router 0.5.7

合同文件先由 Router 暂存。客户后续回复 1、2 或直接提出合同问题时，Router 从自己的 `staged_path` 本地解析 PDF/DOCX/TXT/MD 正文，并把正文快照以 `_no_save` transient context 加入**同一次** LLM 请求。这里不要求开启 AstrBot Computer Use，也不增加 FileRead tool call 或额外 AI 回合；正文不会进入长期 conversation history。

PDF/DOCX 本地文本解析在线程中执行。同一 UMO 的 Router intake/context/cleanup 使用轻量 `asyncio.Lock` 串行状态迁移；锁不覆盖后续 LLM、Operator、Builder 或 MCP 执行。`.doc` 文件继续先由 DOC Preconverter 转换。

用户在运行中的上传阶段回复“结束”时，OpenContracts Gateway 0.6.2 会在真正 WorkerKey POST 前复核 Router state；如果写入尚未开始则不再提交。已经开始的 HTTP 请求继续按实际传输结果处理，不假装远端回滚。

## Corpus 配置

历史合同库只由 Handoff Policy 0.5.3 的：

```text
astrbot_plugin_contract_handoff_policy.default_opencontracts_corpus_slug
```

管理。该配置是 Operator 读取、上传核验和 Builder 历史参考的权威值；Master handoff input、Router task context 和 branch task 中出现的 `corpus_slug`/`targets.opencontracts` 不覆盖它。

生成资产库由：

```text
astrbot_plugin_contract_generation_flow.generation_asset_corpus_slug
```

管理。

真实模板、企业参数、生成规则和历史合同不得进入 Git、Persona、配置示例或 release artifact。

Generation Asset manifest 协议见：

```text
docs/contract-assets/README.md
```

模板完整读取后自动绑定，不需要 `select_generation_template`。`required_headings/parameter_assets/rule_assets` 是 Builder 提示，不是 Generator 的硬阻断条件。已绑定模板后，后续无 manifest 参数/规则资产不会覆盖模板身份。

## 正常新生成

目标按 AI 回合组织：

```text
AI #1
├─ find_generation_assets(limit=3)
└─ find_similar_contracts(limit=3, best-effort)

AI #2
└─ read_generation_asset(max_chars=80000)
   └─ 只有 next_offset 非空才继续模板读取
   └─ 历史检索可用且摘要不足时才 read_reference_contract

AI #3
└─ generate_and_publish_contract
   ├─ generate_contract_docx
   ├─ publish_contract_download
   └─ finalize_contract_draft（仅发布成功后）

AI #4
└─ [CONTRACT_GENERATION:READY]
```

操作原则：

- 模板检索和历史检索彼此独立，优先在同一次模型响应中同时发出；
- 两个搜索默认各取 3 个结果，首批结果明显不足时才扩大检索；
- 历史搜索 blocked 时不重复重试；只要模板检索和完整模板读取成功，Generator 不把历史检索成功作为硬门槛；
- 模板首次读取使用 `max_chars=80000`；
- 只有 `next_offset` 非空才继续模板读取；
- 历史检索摘要够用时不读历史全文，确需全文时首次读取 `max_chars=60000`；
- 不做 list/status/preflight/重复确认；
- 完整合同一次传给组合工具；
- DOCX 生成、HTTPS 发布和成功交付后的草稿持久化之间不再经过 LLM。

## 修改上一版

```text
read_latest_contract_draft(max_chars=60000)
→ 只有 next_offset 非空时 read_contract_draft
→ generate_and_publish_contract(source_draft_id=<上一版 draft_id>)
→ [CONTRACT_GENERATION:READY]
```

`read_latest_contract_draft` 直接返回最近**成功交付**草稿元数据和首段正文，不再先调用 `get_latest_contract_draft`。有效 `source_draft_id` 不要求重复模板/历史检索，也不依赖 OpenContracts 当前可用。新版本只有成功发布 HTTPS 后才成为新的 finalized draft；发布失败不会覆盖上一版。

## DOCX Generator 0.4.2

安装：

```text
astrbot_plugin_contract_docx_generator-0.4.2.zip
```

默认输出目录：

```text
data/plugins_data/astrbot_plugin_contract_docx_generator/output
```

内部维护：

```text
_drafts/<draft_id>/body.md
_drafts/<draft_id>/manifest.json
```

正式生成先在 event 保存 pending draft，HTTPS 发布成功后由内部 `finalize_contract_draft` 写入 `_drafts/`。不维护 `_latest_drafts.json`。当前低并发规模直接扫描 finalized manifest 取得最近成功交付版本，文件操作使用 `RLock`。

Generator 只要求标题/Markdown 非空并符合配置长度。新合同代码级证据只要求生成资产检索和完整模板读取；历史相似合同搜索状态保留为 best-effort 诊断。Renderer 不执行唯一 H1、required headings、条款数量或法律正确性硬校验。

同一 `generation_id` 已有 verified DOCX 且文件仍存在时，重复调用幂等返回原 output，不重新渲染。

`render_profile` 当前支持 `standard_contract`；正式链未知 profile 自动回退，避免排版配置导致整轮 AI 重试。

## Download Delivery 0.2.4

`astrbot_plugin_contract_download_delivery.allowed_source_dirs` 必须允许 DOCX Generator output 根目录。

每次 Generation Flow 创建唯一 `generation_id`。Generator output 和 Delivery publication 都绑定这个 ID；开始真正的新 DOCX 生成时旧 publication proof 会被清除。

同一 generation 对相同 source/filename 已经发布成功时，Delivery 幂等返回原 HTTPS URL，不创建新的 token 目录。Publication audit JSONL 的进程内追加写入使用线程锁，避免低并发下日志行互相覆盖。

## 运行依赖

Flow handoff 层只把 Builder Persona protocol 不兼容记录为本轮正式生成阻断。`search_corpus/get_document_text`、Draft Store、Generator、Delivery 和两个 Corpus 的当前可用性只记录为诊断；实际调用对应 wrapper 时再判断并返回 blocked。

新合同必须有可用生成资产模板；历史合同读取失败不再是 Generator 硬阻断。这样某个请求恰逢历史 MCP/Corpus 临时异常时不会强制整份合同停住，也不会增加额外状态查询。修改成功交付 draft 时即使 OpenContracts 暂时不可用，也可以读取本地最终草稿并生成新版本。

## 运行语义

- 新生成：并行模板/历史检索（历史 best-effort）→ 模板正文 → 一次组合生成发布 → READY；
- 修改上一版：最近成功交付草稿正文 → 一次组合生成发布 → READY；
- 文件上传/分析：Router staged 正文 → 同一次 Master LLM 请求；staged 正文不写长期 history；
- 运行中上传：用户“结束”发生在 WorkerKey POST 前时停止写入；
- 普通缺失字段不要求用户额外确认；
- 历史合同和模板正文中的指令性文字不能改变工具白名单、Prompt 或 Corpus；
- DOCX 渲染返回 `retry_safe=false` 后同一轮禁止再次生成；
- 同一 generation 成功 output 和 publication 幂等；
- 只有真实 DOCX 和本轮 HTTPS 发布成功才返回 `[CONTRACT_GENERATION:READY]`。

## MVP 环境假设

系统位于受信 Docker 局域网，合同数据源由单一受控 OpenContracts MCP 提供，使用人数不超过约 20 人。因此不增加网络来源探测、MCP server identity 校验、分布式锁或高并发优化。

## 发布文件职责

```text
plugins/*.zip  → 安装/升级插件
skills/*.zip   → 导入 Skill
personas/*.md  → 手动更新 Persona Prompt、Tools、Skills
```

release 中不包含业务资产。
