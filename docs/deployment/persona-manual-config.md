# Persona 手动配置与 Markdown 发布

## 发布约定

本地构建后，`dist/personas/` 为每个人格生成一份 Markdown：

```text
contract_master_orchestrator-1.21.md
contract_opencontracts_operator-1.17.md
contract_docassemble_builder-1.18.md
```

文件头列出 `persona_id`、`version`、`tools`、`skills`；正文 `System Prompt` 复制到 AstrBot WebUI。绑定源数据统一维护在 `personas/bindings.json`。

## 当前人格绑定

### contract_master_orchestrator 1.21

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

不绑定 `contract-orchestrator`。生成主路径路由规则已经固化在 Master Persona，避免为加载生成编排 Skill 再产生 shell/文件读取工具轮次。

### contract_opencontracts_operator 1.17

Tools：

```text
list_documents
get_document_text
search_corpus
opencontracts_gateway_status
opencontracts_upload_document
```

Skills：`contract-opencontracts`、`contract-result-verification`。

### contract_docassemble_builder 1.18

Tools：

```text
list_documents
get_document_text
search_corpus
docassemble_generate_document
publish_contract_download
```

Skills：无。

Builder 的数据库优先、占位符、Docassemble 与 Delivery 规则已经固化在 Persona，不绑定 `contract-docassemble`。`search_corpus` 是可选辅助；Generation Flow 只要求另外四个核心工具必须存在。

`docassemble_gateway_status` 和 `contract_download_delivery_status` 仍由插件提供，但只用于管理员排障，不绑定给 Builder。

## 运行语义

- 用户要求生成/起草/按当前方案生成：Master 直接委派 Builder，不要求固定确认口令；
- 生成任务即使要求“从合同库找字段”，也由 Builder 自己读取，不先委派 Operator；
- 独立合同库查询/分析才委派 Operator；
- Builder 未从用户或合同库取得的普通草稿字段保留 `【待填写】`，不反复向用户追问；
- Builder 只有真实生成 DOCX 并发布 HTTPS 后才返回 READY。

## 发布文件职责

```text
plugins/*.zip   → AstrBot WebUI 安装/升级插件
skills/*.zip    → AstrBot WebUI 导入 Skill（生成相关 Skill 当前不绑定运行人格）
personas/*.md   → 手动更新 Persona Prompt、Tools、Skills
```

构建阶段会校验每个人格都有对应 binding；`skills: []` 是合法绑定，表示该 Persona 不加载 Skill。
