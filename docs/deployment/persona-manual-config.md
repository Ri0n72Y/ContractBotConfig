# Persona 手动配置与 Markdown 发布

## 发布约定

本地构建后，`dist/personas/` 为每个人格生成：

```text
contract_master_orchestrator-1.22.md
contract_opencontracts_operator-1.17.md
contract_docassemble_builder-1.20.md
```

绑定源数据以 `personas/bindings.json` 为准。

## contract_master_orchestrator 1.22

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

不绑定 `contract-orchestrator`。生成 handoff 不向 Agent 传 `corpus_slug`；OpenContracts 目标 Corpus 由 Handoff Policy 的唯一配置解析。

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

## contract_docassemble_builder 1.20

Tools：

```text
list_documents
get_document_text
docassemble_generate_document
publish_contract_download
```

Skills：无。

Builder 1.20：

- 不要求、猜测或自行提供 `corpus_slug`；Flow 会把该参数从 list/get 可见 schema 中隐藏并自动注入 Handoff Policy 配置的目标 Corpus；
- `road_labor` 使用道路工程劳务固定 DOCX 模板；
- `material_purchase` 使用材料采购固定 DOCX 模板；
- 固定模板只提交结构化 `contract_data`，普通缺失字段由 interview 写 `【待填写】`；
- 尚无模板的合同使用 `generic` fallback；
- 两个 status 工具不绑定给 Builder。

## Persona / Subagent 更新后的重载

AstrBot 的 subagent orchestrator 在 reload 时会把 Persona 的 system prompt 和 tools 物化到 handoff Agent。因此 Persona 页面保存后仍建议保存/重载相关 Agent/Subagent 配置；若其他子人格仍表现为旧配置，再重启 AstrBot。

Generation Flow 0.2.2 每次 `transfer_to_docassemble_builder` 前还会从当前 PersonaManager 重新读取 Builder Prompt，并从当前 Tool Manager 重建四个核心工具，所以旧 handoff 的 status-only Prompt/ToolSet 不会继续进入 Builder。

## 运行语义

- 生成/起草/按当前方案生成：Master 直接委派 Builder，不要求固定确认口令；
- 生成任务中的数据库补字段由 Builder 自己读取，不先委派 Operator；
- Corpus slug 由 `astrbot_plugin_contract_handoff_policy.default_opencontracts_corpus_slug` 单点配置；
- 独立合同库查询/分析才委派 Operator；
- 未从用户或合同库取得的普通草稿字段保留 `【待填写】`；
- 只有真实 DOCX 和 HTTPS 发布成功才返回 READY。

## 发布文件职责

```text
plugins/*.zip   → 安装/升级插件
skills/*.zip    → 导入 Skill（生成相关 Skill 当前不绑定运行人格）
personas/*.md   → 手动更新 Persona Prompt、Tools、Skills
DOCX 模板       → 上传到 Docassemble Playground 的 Templates 文件夹
```

构建器支持 `skills: []`，会在 Persona Markdown frontmatter 中明确输出空列表。
