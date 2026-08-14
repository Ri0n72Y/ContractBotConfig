# Persona 手动配置与 Markdown 发布

## 发布约定

本地构建后，`dist/personas/` 为每个人格生成：

```text
contract_master_orchestrator-1.22.md
contract_opencontracts_operator-1.17.md
contract_docassemble_builder-1.19.md
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

不绑定 `contract-orchestrator`；生成路由规则已固化在 Master Persona。生成 handoff 不再指定 `corpus_slug`，合同库数据源由 Builder 当前绑定的 MCP 连接决定。

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

## contract_docassemble_builder 1.19

Tools：

```text
list_documents
get_document_text
docassemble_generate_document
publish_contract_download
```

Skills：无。

Builder 的数据库优先、占位符、Docassemble 与 Delivery 规则已固化在 Persona。两个 status 工具只用于管理员排障，不绑定给 Builder。Builder 不要求或猜测 `corpus_slug`。

## Persona / Subagent 更新后的重载

AstrBot 的 subagent orchestrator 在 reload 时会把 Persona 的 system prompt 和 tools 物化到 handoff Agent。仅在 Persona 页面修改后，如果相关 subagent/handoff 没有刷新，handoff 对象本身可能暂时保留旧 Prompt/旧 ToolSet。

因此更新 Master/Builder Persona 后仍建议：

1. 在 Persona 页面保存新的 Prompt / Tools / Skills；
2. 到 Agent/Subagent 配置确认对应 persona_id 仍指向正确 Persona；
3. 保存并重载 Agent/Subagent 配置；
4. 若其他子人格行为仍显示旧配置，再重启 AstrBot。

对于 Builder 生成链，Generation Flow 0.2.1 不再依赖 handoff 缓存：每次 `transfer_to_docassemble_builder` 执行前，它会从当前 PersonaManager 重新读取 `contract_docassemble_builder` Prompt，并从当前全局 Tool Manager 重建四个核心工具。因此只要 Persona 页面已经保存成功、四个工具当前处于注册/启用状态，旧 handoff 中残留的 status-only Prompt/ToolSet 不会继续进入 Builder 运行。

## 运行语义

- 生成/起草/按当前方案生成：Master 直接委派 Builder，不要求固定确认口令；
- 生成任务中的数据库补字段由 Builder 自己读取，不先委派 Operator；
- 独立合同库查询/分析才委派 Operator；
- 未从用户或合同库取得的普通草稿字段保留 `【待填写】`；
- 只有真实 DOCX 和 HTTPS 发布成功才返回 READY。

## 发布文件职责

```text
plugins/*.zip   → 安装/升级插件
skills/*.zip    → 导入 Skill（生成相关 Skill 当前不绑定运行人格）
personas/*.md   → 手动更新 Persona Prompt、Tools、Skills
```

构建器支持 `skills: []`，会在 Persona Markdown frontmatter 中明确输出空列表。
