# Persona 手动配置与 Markdown 发布

## 发布约定

Persona 不再作为 ZIP 或 Persona JSON 发布包导入。本地构建后，`dist/personas/` 为每个人格生成一份 Markdown：

```text
contract_master_orchestrator-1.20.md
contract_opencontracts_operator-1.17.md
contract_docassemble_builder-1.17.md
```

文件头列出 `persona_id`、`version`、`tools`、`skills`；正文 `System Prompt` 用于直接复制到 AstrBot WebUI。绑定源数据统一维护在 `personas/bindings.json`。

Builder 示例：

```yaml
---
persona_id: contract_docassemble_builder
version: "1.17"
tools:
  - list_documents
  - get_document_text
  - search_corpus
  - docassemble_generate_document
  - publish_contract_download
skills:
  - contract-docassemble
---
```

## 当前人格绑定

### contract_master_orchestrator

Tools：

```text
transfer_to_opencontracts_operator
transfer_to_docassemble_builder
```

Skills：`contract-orchestrator`、`contract-direct-analysis`、`contract-conversation-control`、`contract-result-verification`。

### contract_opencontracts_operator

Tools：

```text
list_documents
get_document_text
search_corpus
opencontracts_gateway_status
opencontracts_upload_document
```

Skills：`contract-opencontracts`、`contract-result-verification`。

### contract_docassemble_builder

Tools：

```text
list_documents
get_document_text
search_corpus
docassemble_generate_document
publish_contract_download
```

Skill：`contract-docassemble`。

`search_corpus` 是可选检索辅助。Generation Flow 只要求 `list_documents`、`get_document_text`、`docassemble_generate_document`、`publish_contract_download` 四个核心工具必须存在。

`docassemble_gateway_status` 和 `contract_download_delivery_status` 仍由插件提供，但作为管理员排障工具，不绑定给 Builder，不参与每次生成。

下载发布仍只由 Builder 调用；Master 只消费 Builder 返回的 HTTPS 下载结果。

## 发布文件职责

```text
plugins/*.zip   → AstrBot WebUI 安装/升级插件
skills/*.zip    → AstrBot WebUI 导入 Skill
personas/*.md   → 手动更新 Persona Prompt、Tools、Skills
```

构建阶段会校验每个人格都有对应 binding，且 Tools/Skills 均为有效字符串列表。
