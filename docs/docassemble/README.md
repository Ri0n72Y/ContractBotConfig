# ContractBot Docassemble 生成与部署

版本以根目录 `VERSIONS.md` 为准，Persona 工具绑定以 `personas/bindings.json` 为准。

## 正常链路

```text
用户明确要求生成/起草/制作
→ Master 直接委派 Builder
→ Builder 在 contracts 中选择最相关参考合同并读取正文
→ 合同库可复用信息优先，仍缺失的普通字段保留【待填写】
→ Gateway 核验本轮 corpus_slug + document_slug
→ Docassemble 生成 DOCX
→ Delivery 发布临时 HTTPS 链接
→ Master 回复用户
```

生成草稿不设置额外固定确认口令。用户说“按这个生成”“开始生成”等自然语言执行表达直接进入生成，不要求再回复“确认生成”。生成任务中需要从合同库补字段时由 Builder 自己读取，不先经过 Operator。

Generation Flow 只负责一条生成处理中提示和 Builder 核心工具绑定检查，不保存 pending confirmation，也不维护确认 TTL/别名状态机。

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
search_corpus
docassemble_generate_document
publish_contract_download

Skills: 无
```

生成主路径的核心规则已经固化在 Master/Builder Persona，不绑定 `contract-orchestrator` 或 `contract-docassemble`，避免为读取 Skill 再产生 shell/文件工具轮次。两个 status 工具只用于管理员排障，不绑定给 Builder。

## 合同库读取策略

当前生成库固定使用：

```text
corpus_slug = contracts
```

Builder 默认：

1. `list_documents` 一次取得真实列表；
2. 选择一份最相关的主参考，不默认扫描整个 Corpus；
3. `get_document_text(char_offset=0, max_chars=30000)`，有 `next_offset` 再继续；
4. 只有确有必要才读第二份参考或调用 `search_corpus`；
5. 某个候选正文为空可换下一份；所有相关参考都不可读才 BLOCKED。

Gateway 仍负责本轮真实来源核验：必须先有同一 Corpus 的 `list_documents` 成功结果，再有其中真实 `document_slug` 的非空正文结果。历史会话摘要不能替代本轮读取。

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

`docs/docassemble/contractbot_document_generation.yml` 是当前最小生产生成样例，接收：

```text
document_title
document_body
```

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

建议 E2E 使用包含以下语义的一条请求直接验证：

```text
根据合同库生成一份合同；相关条款先从数据库找，找不到的留空，按这个生成。
```

验收重点：不要求固定确认口令、不先委派 Operator、不调用 Skill shell、不调用两个 status preflight、不调用 `list_public_corpuses` 猜库、Builder 不扫描整个 Corpus、未找到字段保留占位符、真实 DOCX + HTTPS 下载成功。
