# ContractBot Docassemble 生成与部署

版本以根目录 `VERSIONS.md` 为准，Persona 工具绑定以 `personas/bindings.json` 为准。

## 正常链路

```text
用户明确要求生成/起草/制作
→ Master 直接委派 Builder
→ Generation Flow 从 AstrBot 当前 Tool Manager 重建 Builder 四工具 ToolSet
→ Builder 调 list_documents 获取当前绑定 MCP 数据源的真实文档列表
→ Builder 选择最相关 document_slug，并从 offset 0 读取非空正文
→ 合同库可复用信息优先，仍缺失的普通字段保留【待填写】
→ Gateway 核验本轮 Builder 的真实 list→get 读取
→ Docassemble 生成 DOCX
→ Delivery 发布临时 HTTPS 链接
→ Master 回复用户
```

生成草稿不设置额外固定确认口令。用户说“按这个生成”“开始生成”等自然语言执行表达直接进入生成，不要求再回复“确认生成”。生成任务中需要从合同库补字段时由 Builder 自己读取，不先经过 Operator。

Generation Flow 只负责一条生成处理中提示和 Builder 运行时四工具重建，不保存 pending confirmation，也不维护确认 TTL/别名状态机。Gateway 不再裁剪 Builder ToolSet，也不管理合同库 slug。

## Persona 与工具

Master：

```text
Tools:
transfer_to_opencontracts_operator
transfer_to_docassemble_builder

Skills:
contract-direct-analysis
contract-conversation-control
contract-result-verification
```

Builder：

```text
Tools:
list_documents
get_document_text
docassemble_generate_document
publish_contract_download

Skills: 无
```

生成主路径核心规则固化在 Master/Builder Persona，不绑定 `contract-orchestrator` 或 `contract-docassemble`。两个 status 工具只用于管理员排障，不绑定给 Builder；语义检索保留在 Operator 独立分析路径，不进入常态生成工具集。

AstrBot handoff 会基于 subagent 配置/Persona 在 reload 时物化子 Agent 的 system prompt 与 tools。部署更新 Persona 或 subagent 绑定后，需要在 WebUI 保存并重载相关 Agent/配置（必要时重启 AstrBot），确保 handoff 对象刷新。即使旧 handoff 仍残留旧工具列表，Generation Flow 0.2.1 会在 Builder 请求开始时从当前全局 Tool Manager 重新解析四个核心工具，并用准确 ToolSet 替换运行时列表。

## 合同库读取策略

生成链不要求 Master、Builder、Gateway 或 handoff 指定 `corpus_slug`。合同库数据源由 Builder 当前绑定的 MCP 连接决定。

Builder 默认：

1. `list_documents` 一次取得当前 MCP 数据源中的真实列表；
2. 选择一份最相关的主参考，不默认扫描全部文档；
3. 对列表中的真实 `document_slug` 调用 `get_document_text(char_offset=0, max_chars=30000)`；有 `next_offset` 再继续；
4. 只有主参考确实不足时才读取第二份相关合同；
5. 某个候选正文为空可换下一份；所有相关参考都不可读才 BLOCKED。

Gateway 只负责本轮真实来源核验：必须先看到 Builder 本轮 `list_documents` 的真实结果，再看到其中某个 `document_slug` 从 offset 0 返回非空正文。Operator 或历史会话中的读取结果不能替代本轮 Builder 读取。

## 缺失字段策略

默认：

```text
draft_policy = database_first_then_placeholder
```

用户明确值优先；其余先从合同库参考正文取得。仍未找到的金额、付款节点、工商字段、具体日期、质保比例、争议机构等普通草稿字段写成 `【待填写】` / `【待双方确认】` 并继续生成。只有用户明确要求字段完整才能生成时，才以缺失字段阻断。

因此用户说“这些内容先从数据库拿，没有的留空，我自己写”后，不应再次要求其补同一批字段。

## Gateway

必须配置真实生产 interview：

```text
base_url = http://docassemble
api_key = <Docassemble API Key>
allowed_interviews = [<正式 interview>]
default_interview = <正式 interview>
output_retention_seconds = 86400
output_cleanup_interval_seconds = 300
```

`docs/docassemble/contractbot_document_generation.yml` 是当前最小生产生成样例，接收 `document_title` 和 `document_body`。

`contractbot_api_smoke.yml` 仅用于 API smoke，不能作为正式 `default_interview`。如果运行环境仍只 allowlist smoke interview，正式生成必然 BLOCKED；不要通过每次请求调用 status 工具绕过这项部署配置。

## Delivery

```text
public_root = data/public_downloads
public_base_url = https://download.ri0n72y.top/contracts
allowed_source_dirs = [data/plugins_data/astrbot_plugin_docassemble_gateway/output]
ttl_seconds = 1800
```

只有同一次 Gateway 的 `output_path/output_filename` 可以发布。只有真实 HTTPS 发布成功后才能向客户报告 READY。

## 客户消息数量

正常生成只需要：

```text
1 条处理中提示
1 条最终成功/失败结果
```

不再发送“收到 → 待确认 → 最终确认 → 读取完成 → DOCX 已生成 → 正在发布”等多层阶段消息。

## 构建与 E2E

```powershell
python -m compileall -q plugins scripts
python scripts/build_release.py --clean
```

建议 E2E 使用：

```text
根据合同库生成一份合同；相关条款先从数据库找，找不到的留空，按这个生成。
```

验收重点：不要求固定确认口令、不先委派 Operator、不调用 Skill shell、不调用两个 status preflight、不要求/猜测 `corpus_slug`、Builder 实际 ToolSet 为四个核心工具、不默认扫描全部文档、未找到字段保留占位符、真实 DOCX + HTTPS 下载成功。
