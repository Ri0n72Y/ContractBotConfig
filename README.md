# ContractBotConfig

企业合同 AstrBot 配置与扩展工程。Master 面向企业微信客户；OpenContracts 保存外部生成资产和历史合同；Builder 负责模板匹配、历史参考和合同编制；Contract DOCX Generator 生成可编辑 DOCX，并在成功交付后保存最近版本草稿；Download Delivery 负责临时 HTTPS 交付。

## 当前正式生成链路

新合同优先按 AI 回合优化：

```text
用户要求生成/起草合同
→ Master 直接委派 Builder
→ Handoff Policy 绑定历史合同 Corpus
→ Generation Flow 校验 Builder protocol v4

AI #1
├─ find_generation_assets(limit=3)
└─ find_similar_contracts(limit=3, best-effort)

AI #2
└─ read_generation_asset(max_chars=80000)
   └─ 模板返回 next_offset 才继续读取
   └─ 历史检索可用且摘要明显不足时才 read_reference_contract

AI #3
└─ generate_and_publish_contract
   ├─ 生成 DOCX
   ├─ 发布 HTTPS
   └─ 发布成功后保存可修改草稿

AI #4
└─ Builder 返回 [CONTRACT_GENERATION:READY]

→ Master 返回文件名、下载链接和有效期
```

模板检索和历史检索彼此独立，优先在同一次模型响应中返回两个 tool calls。两个搜索默认各取 3 个最相关结果；只有首批结果明显不足时才扩大检索。历史相似合同是优先使用的 best-effort 参考：历史 Corpus/OpenContracts 暂时不可用时，不重复检索，也不在模板已经完整可用的情况下阻止生成。DOCX 生成、HTTPS 发布和交付后草稿持久化由 `generate_and_publish_contract` 内部确定性串联，模型不再处理中间 `output_path`。

修改当前会话上一版：

```text
read_latest_contract_draft(max_chars=60000)
→ 只有 next_offset 非空时 read_contract_draft
→ generate_and_publish_contract(source_draft_id=<上一版>)
→ [CONTRACT_GENERATION:READY]
```

“上一版”指当前会话最近一次**成功交付**的合同草稿。DOCX 已生成但 HTTPS 发布失败的版本不会替换上一版。有效 `source_draft_id` 不要求重新做模板和历史检索，也不要求 OpenContracts 当前可用。

普通未知字段由 Builder 根据用户要求、模板和 OpenContracts 内容处理；无法可靠确定时可写 `【待填写】` 或 `【待双方确认】`，不额外向用户确认。

## 文件上传与直接分析

企业微信合同文件由 File Router 先暂存。用户随后选择上传、快速分析或直接提问时，Router 从自己的 `staged_path` 确定性解析 PDF/DOCX/TXT/MD 正文，并把正文快照作为 `_no_save` transient context 加入**同一次** LLM 请求；不依赖 Computer Use，也不增加额外文件读取 tool call 或 AI 回合。该正文只参与当前请求，不写入 AstrBot conversation history，因此后续对话不会重复携带整份上一合同。PDF/DOCX 本地正文转换在线程中执行，不阻塞 asyncio event loop。

同一 UMO 的 Router 状态迁移使用轻量 `asyncio.Lock` 串行，锁不覆盖后续 LLM、Subagent 或 MCP 执行。运行中的上传在用户回复“结束”后，OpenContracts Gateway 会在 WorkerKey POST 前复核 Router 当前 task；如果写入尚未开始，则不再提交远端上传。已经开始的 HTTP 请求不假装可回滚，继续按实际传输结果处理。

## 数据面

历史合同 Corpus：

```text
astrbot_plugin_contract_handoff_policy.default_opencontracts_corpus_slug
```

该值是 Operator 读取、上传核验和 Builder 历史参考的唯一权威 Corpus 配置；handoff input 和 Router task context 不覆盖它。

生成资产 Corpus：

```text
astrbot_plugin_contract_generation_flow.generation_asset_corpus_slug
```

Builder 运行时看到：

```text
find_generation_assets
read_generation_asset
find_similar_contracts
read_reference_contract
read_latest_contract_draft
read_contract_draft
generate_and_publish_contract
```

Builder 不看到 `corpus_slug`，也不直接看到 `generate_contract_docx` / `publish_contract_download` / `finalize_contract_draft`。历史 Corpus 从当前 `AstrMessageEvent` 读取，不写进共享 Handoff Agent。运行 wrappers 每次调用时动态解析当前底层 MCP/插件工具，并按公开 schema 过滤参数，因此模型多带无关参数不会透传到底层工具。底层调用统一交给 AstrBot 原生 `FunctionToolExecutor`，兼容 AstrBot 4.23.2 的 handler 型插件 Tool、MCPTool 和自定义 override-call Tool，不增加模型回合。

## Generation Assets

真实合同模板、企业参数、生成规则和历史合同都属于业务数据，**不得进入 Git 或 release artifact**。

仓库只保存抽象资产协议：

```text
docs/contract-assets/README.md
```

模板建议声明 `asset_id/asset_type/status/version/render_profile`。`required_headings/parameter_assets/rule_assets` 是 Builder 提示，不是代码级硬门槛。业务条款应主要存在模板正文和 OpenContracts 数据中，而不是复制成 Python 规则。

没有 manifest 的可读文档仍可作为兼容模板：仅当本轮尚未绑定模板时，首个完整读取的无 manifest 资产可以自动成为模板；一旦已经绑定模板，后续无 manifest 参数/规则文档不会覆盖模板身份。明确声明为其他 `asset_type` 的资产也不会覆盖模板。

## DOCX Generator

```text
astrbot_plugin_contract_docx_generator 0.4.2
```

正式 Builder 一次把完整 Markdown 交给组合工具。Generator 先生成 DOCX 并在当前 event 中保留待交付草稿；Delivery 发布成功后，组合工具再调用内部 `finalize_contract_draft` 持久化 Markdown 到 `_drafts/`，供下一轮修改。同一 `generation_id` 已有 verified DOCX 时重复生成直接幂等返回原 output；Delivery 对相同 generation/source/filename 也返回原 HTTPS publication。

新合同 Generator 的代码级生成证据只要求完成生成资产检索并完整读取一个可用模板。`contract_generation_history_search_verified` 仍可用于诊断，但不再作为 Generator 硬门槛。

Renderer 支持 A4、中文字体、标题、正文、Markdown 表格、列表、粗体、分页标记和页码。它只负责排版和文件生成，不执行唯一 H1、required headings、条款完整性或法律正确性等合同内容硬校验。

## MVP 风险边界

当前部署假设：

- 整个系统位于受信 Docker 局域网；
- 使用单一受控 OpenContracts 数据源；
- 使用人数不超过约 20 人。

因此代码不增加网络来源探测、MCP identity 筛查、分布式锁或高并发优化。主要保证：

- 请求特定 Corpus/生成状态不写入共享 Agent；
- Builder 共享 Agent 只持有请求无关 wrapper ToolSet；protocol 不兼容时仍绑定同一受限 ToolSet，并仅在当前 event 阻断正式生成；
- Router 同一 UMO 的短状态迁移串行，不把 LLM/MCP 执行纳入锁；
- staged 合同正文只进入当前模型请求，不进入长期 conversation history；
- 运行中上传在 WorkerKey 写入开始前尊重 Router 的“结束”状态；
- Draft Store 本地文件操作有线程锁；
- Publication audit 追加写入有进程内线程锁；
- 每轮生成使用唯一 `generation_id`；
- DOCX output 与 HTTPS publication 必须属于同一 generation_id；
- 成功生成/发布幂等；
- 不可重试渲染失败后同一轮禁止重复生成。

## Docassemble 迁移状态

`astrbot_plugin_docassemble_gateway`、`contract-docassemble` Skill 和 `docs/docassemble/` 暂时保留用于回滚和历史参考。正式 Builder ToolSet 已不包含 Docassemble 工具。

## 当前关键版本

```text
contract_file_router             0.5.7
contract_docx_generator          0.4.2
contract_generation_flow         0.6.2
contract_handoff_policy          0.5.3
contract_download_delivery       0.2.4
opencontracts_gateway            0.6.2
contract_docassemble_builder     1.25
contract_master_orchestrator     1.23
contract_opencontracts_operator  1.17
```

完整版本以 `VERSIONS.md` 为准；生成架构见 `docs/architecture/ai-docx-generation.md`；Persona 手动绑定和部署步骤见 `docs/deployment/persona-manual-config.md`。

## 构建

```powershell
python -m compileall -q plugins scripts
python scripts/build_release.py --clean
```

输出：

```text
dist/plugins/*.zip
dist/skills/*.zip
dist/personas/*.md
dist/MANIFEST.json
```