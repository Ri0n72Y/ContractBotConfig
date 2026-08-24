# Persona 手动配置与组件升级

## 正式 Persona 绑定

绑定源数据以 `personas/bindings.json` 为准。正式环境不要额外绑定未列出的 Skill、Shell、Python、通用 HTTP 或通用文件写入工具。

### contract_master_orchestrator 1.27

Tools：

```text
transfer_to_opencontracts_operator
transfer_to_docassemble_builder
```

Skills：

```text
contract-direct-analysis
contract-conversation-control
```

Master 是唯一面向客户角色。企业微信中的合同分析默认简洁：先给总体判断，只列 3～6 个最高优先级风险，每点包含问题、位置和建议；自由问答只回答当前问题。本轮 Router 注入的合同正文优先使用 `contract_task_context` / `staged_contract_text`，不要通过 Shell、Grep、Python、通用 HTTP 或通用文件搜索发现本轮合同或 Skill。

完成本轮合同分析或问答后，可以简短询问是否还有其他需求；如已完成，用户可回复“结束”。Router 不维护持久化的 current-file 指针，后续用户指的是哪份合同由助手结合会话上下文判断。完整分析报告下载和独立网页版专业分析入口属于后续能力。

正式生成 handoff 必须显式发送：

```text
generation_policy_protocol=2
fallback_policy=allow_ai_fallback | require_specific_template
```

strict 模式另带 `required_template_query`。用户明确授权从历史合同参考项目特定值时，才传 `reference_value_fields` 数组。

### contract_opencontracts_operator 1.18

Tools：

```text
list_documents
get_document_text
search_corpus
opencontracts_gateway_status
opencontracts_upload_document
```

Skills：`[]`

Operator Persona 自包含合同库读取、上传、查重、分页、状态和不可重试规则。

### contract_docassemble_builder 1.30

Persona ID 保持为 `contract_docassemble_builder`。

WebUI 静态 Tools：

```text
read_bound_skill
find_generation_assets
read_generation_asset
find_similar_contracts
read_reference_contract
read_latest_contract_draft
read_contract_draft
generate_and_publish_contract
```

Skills：

```text
contract-document-specification
```

当前部署只考虑 AstrBot 4.27.x 及以上。Builder 的 Persona prompt、Tool 和 Skill 绑定由 AstrBot WebUI 管理；Generation Flow 不覆盖 Agent ToolSet、不修改 system prompt，也不改写 handoff input。

Builder 1.30 固定要求所有正式合同生成、重写、修改和定稿先调用：

```text
read_bound_skill(skill_name='contract-document-specification')
```

随后才能组织最终 `document_markdown` 并调用正式生成工具。

## 正式插件版本

```text
astrbot_plugin_contract_doc_preconverter    0.1.3
astrbot_plugin_contract_file_router         0.5.9
astrbot_plugin_contract_handoff_policy      0.5.4
astrbot_plugin_opencontracts_gateway        0.6.2
astrbot_plugin_contract_generation_flow     0.8.0
astrbot_plugin_contract_docx_generator      0.5.2
astrbot_plugin_contract_download_delivery  0.2.5
astrbot_plugin_wecom_final_result_guard     0.3.5
```

不安装 `astrbot_plugin_docassemble_gateway`。

## 正式 Skills

```text
contract-direct-analysis          1.15
contract-conversation-control     1.16
contract-document-specification  1.0
```

`contract-direct-analysis` 只要求企微默认输出重点摘要，不主动产生长篇完整分析。`contract-conversation-control` 1.16 与 File Router 0.5.9 的 retained staged-file 生命周期一致：结束/取消/TTL 只清理任务状态，不物理删除暂存文件；BLOCKED 只保留恢复该未完成任务所需的文件引用和业务状态。

## File Router 0.5.9 文件与任务生命周期

Router 不再显式维护“current file”。`pending` 只表示尚未结束的文件任务：等待选择、运行中、BLOCKED 或等待重复上传确认。

```text
收到文件
→ 暂存并记录 MD5 / SHA-256
→ 本轮分析 / 问答 / 上传
→ 任务完成后清除 pending/task 状态
→ 暂存文件继续留在磁盘
```

行为规则：

- 普通任务完成后清除任务状态，不物理删除已接收文件；
- “结束/取消”只结束相关任务状态，不物理删除文件；
- 不提供用户侧“删除当前文件”入口，也不提示用户清理文件；
- 后续用户提到哪份合同，由助手根据会话上下文判断，不由 Router 维护 current-file 指针；
- pending TTL 只清理陈旧任务状态，不删除物理文件；
- staging TTL 不再由业务流程用于物理删除；
- 超过一个月未被引用文件的月度清理由后续维护任务实现。

临时文件区分使用 MD5。`source_files[].md5` 用作暂存身份和短时重复判定，`source_files[].sha256` 继续保留给下游完整性/上传链使用。暂存文件名包含 MD5 前缀。

## Skill runtime 验证

生成 E2E 时应看到：

```text
Contract generation flow 0.8.0 initialized
```

Builder handoff runtime ready 日志至少包含：

```text
document_spec_required=True
document_spec_available=True
document_spec_loaded=False
tools=['read_bound_skill', ...]
```

随后出现 Builder Skill grounded 日志，之后才允许 `generate_and_publish_contract` 开始写入。

## Download Delivery

`allowed_source_dirs` 只保留当前正式 Generator：

```text
data/plugins_data/astrbot_plugin_contract_docx_generator/output
```

不要再配置旧 Gateway output 目录。

## Generation policy

正常新合同：

```text
allow_ai_fallback
→ read_bound_skill(contract-document-specification)
→ find_generation_assets + find_similar_contracts
→ specific_template / history_reference / ai_scaffold
→ generate_and_publish_contract
```

用户明确“必须使用指定模板，找不到就不要生成”：

```text
require_specific_template
→ required_template_query
→ 确定性模板身份解析
→ read_generation_asset(use_as_template=true)
→ generation_basis=specific_template
```

修改上一版时，`source_draft_id` 表示版本来源，`generation_basis` 表示本轮主要依据；两者不是同一字段。

完整 READY 需要：

```text
DOCX ready
+ HTTPS publication ready
+ draft finalize ready / draft_saved=true / draft_id 非空
```

HTTPS 已发布但 Draft Store 未落盘时返回 PARTIAL。写操作 timeout/cancel/commit_unknown 不自动重试。

## OpenContracts Corpus

历史合同唯一权威配置：

```text
astrbot_plugin_contract_handoff_policy.default_opencontracts_corpus_slug
```

生成资产唯一权威配置：

```text
astrbot_plugin_contract_generation_flow.generation_asset_corpus_slug
```

Master/Operator/Builder 都不要猜测或覆盖 corpus slug。

## 需要从现有 AstrBot 环境删除

插件：

```text
astrbot_plugin_docassemble_gateway
```

Skills：

```text
contract-docassemble
contract-orchestrator
contract-opencontracts
contract-result-verification
```

同时从 Persona WebUI 解绑这些 Skill。旧插件确认不再需要其输出文件后，可清理对应配置和 `data/plugins_data/astrbot_plugin_docassemble_gateway/`。

## 建议部署顺序

1. 确认 AstrBot 为 4.27.x 或更高版本。
2. 升级 File Router 到 0.5.9。
3. 升级 `contract-direct-analysis` 到 1.15。
4. 升级 `contract-conversation-control` 到 1.16。
5. 导入/更新 Master 1.27，并确认正式 Tool / Skill 绑定与 `personas/bindings.json` 一致。
6. 保持 Builder 1.30、Operator 1.18 及其他正式插件版本与上方清单一致。
7. 重新测试：上传合同 → 快速分析/问答 → 结束；确认任务状态清理后暂存文件仍存在，且下一次文件上传不会依赖旧 current-file 状态。
8. 验证同一文件短时重复投递按 MD5 去重，同时 `source_files[].sha256` 仍存在。
9. 再执行一次正式合同生成 E2E，确认 Builder Skill grounding、DOCX、HTTPS 和 Draft finalize 正常。

## 发布产物

```text
plugins/*.zip  → 安装/升级插件
skills/*.zip   → direct-analysis / conversation-control / document-specification
personas/*.md  → 按文件头更新 Prompt、Tools、Skills
```

release 中不包含真实合同模板、历史合同或企业业务数据。
