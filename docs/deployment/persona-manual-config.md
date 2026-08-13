# Persona 手动配置与 Markdown 发布

## 发布约定

Persona 不再作为 ZIP 或 AstrBot Persona JSON 发布包导入。

本地执行：

```bash
python3 scripts/build_release.py --clean
```

后，`dist/personas/` 为每个人格生成一份 Markdown：

```text
dist/personas/
├── contract_master_orchestrator-1.20.md
├── contract_opencontracts_operator-1.17.md
└── contract_docassemble_builder-1.16.md
```

每份文件头使用 YAML front matter 标注完整手动配置：

```yaml
---
persona_id: contract_docassemble_builder
version: "1.16"
tools:
  - list_documents
  - get_document_text
  - search_corpus
  - docassemble_gateway_status
  - docassemble_generate_document
  - contract_download_delivery_status
  - publish_contract_download
skills:
  - contract-docassemble
---
```

正文中的 `System Prompt` 代码块用于直接复制到 AstrBot WebUI。

Persona 的绑定源数据统一维护在：

```text
personas/bindings.json
```

构建阶段会校验：

- 每个 `persona_*_v*.json` 都必须有对应绑定；
- 绑定中不能存在没有 Persona 源文件的多余人格；
- Persona 文件名中的 ID 必须和 JSON 中的 `persona_id` 一致；
- Tools / Skills 必须是非空字符串列表。

这样 Persona Prompt 与手动 WebUI 绑定信息可以在同一次构建中交付，但仍由管理员在 AstrBot 中手动配置。

## 当前人格绑定

### contract_master_orchestrator

Tools：

```text
transfer_to_opencontracts_operator
transfer_to_docassemble_builder
```

Skills：

```text
contract-orchestrator
contract-direct-analysis
contract-conversation-control
contract-result-verification
```

Master 不绑定 OpenContracts MCP、Docassemble Gateway 或 Download Delivery 的执行工具。它只负责任务编排和客户回复。

### contract_opencontracts_operator

Tools：

```text
list_documents
get_document_text
search_corpus
opencontracts_gateway_status
opencontracts_upload_document
```

Skills：

```text
contract-opencontracts
contract-result-verification
```

### contract_docassemble_builder

Tools：

```text
list_documents
get_document_text
search_corpus
docassemble_gateway_status
docassemble_generate_document
contract_download_delivery_status
publish_contract_download
```

Skills：

```text
contract-docassemble
```

下载交付工具只绑定给 `contract_docassemble_builder`。Builder 在 `docassemble_generate_document` 返回真实 DOCX 后调用 `publish_contract_download`；Master 只消费 Builder 返回的 HTTPS `download_url`，不直接调用下载交付工具。

当前 Generation Flow 运行时还会检查 Builder 是否具备上述完整 7 个工具；缺少任一工具时正式生成会直接进入 BLOCKED，而不是尝试降级执行。

## 禁止的通用替代能力

除非后续架构明确修改，不向这些受控人格绑定用于绕过标准流程的通用能力：

```text
Shell
Python
python-docx
通用 HTTP
通用文件写入/编辑
直接 MCP JSON-RPC
```

## 源文件与发布文件

仓库中的 `personas/persona_*_v*.json` 继续作为 Persona Prompt 的版本化源文件，不再直接作为部署产物。

发布产物职责如下：

```text
plugins/*.zip   → AstrBot WebUI 安装/升级插件
skills/*.zip    → AstrBot WebUI 导入 Skill
personas/*.md   → 管理员手动创建/更新 Persona、复制 Prompt、绑定 Tools/Skills
```
