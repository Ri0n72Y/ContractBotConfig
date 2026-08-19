# Persona 手动配置与组件升级

## 正式 Persona 绑定

绑定源数据以 `personas/bindings.json` 为准。正式环境不要额外绑定未列出的 Skill、Shell、Python、通用 HTTP 或通用文件写入工具。

### contract_master_orchestrator 1.26

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

Master 是唯一面向客户角色。合同库独立读取/分析交 Operator；最终目标是生成、起草、制作或修改合同则直接交 Builder。

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

Skills：

```text
[]
```

Operator Persona 已内置完整读取、上传、查重、分页、状态和不可重试规则，不再加载 `contract-opencontracts` 或 `contract-result-verification`。

### contract_docassemble_builder 1.27

当前 Persona ID 保持为 `contract_docassemble_builder`，但正式运行不使用 Docassemble Gateway。

WebUI 静态 Tools：

```text
[]
```

Skills：

```text
[]
```

Generation Flow 在 handoff 时注入：

```text
find_generation_assets
read_generation_asset
find_similar_contracts
read_reference_contract
read_latest_contract_draft
read_contract_draft
generate_and_publish_contract
```

Builder Prompt 必须包含：

```text
<contract_generation_protocol version="7">
```

## 正式插件版本

```text
astrbot_plugin_contract_doc_preconverter    0.1.3
astrbot_plugin_contract_file_router         0.5.7
astrbot_plugin_contract_handoff_policy      0.5.3
astrbot_plugin_opencontracts_gateway        0.6.2
astrbot_plugin_contract_generation_flow     0.7.2
astrbot_plugin_contract_docx_generator      0.5.1
astrbot_plugin_contract_download_delivery  0.2.5
astrbot_plugin_wecom_final_result_guard     0.3.5
```

不安装 `astrbot_plugin_docassemble_gateway`。

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
→ find_generation_assets + find_similar_contracts
→ specific_template / history_reference / ai_scaffold
→ generate_and_publish_contract
```

用户明确“必须使用指定模板，找不到就不要生成”：

```text
require_specific_template
→ required_template_query
→ list_documents 确定性身份解析
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

1. 升级 `astrbot_plugin_contract_download_delivery` 到 0.2.5，并把 `allowed_source_dirs` 改为只有 DOCX Generator output。
2. 卸载 `astrbot_plugin_docassemble_gateway`。
3. 删除四个废弃 Skill。
4. 导入/更新 Master 1.26、Operator 1.18、Builder 1.27。
5. 按本页重新绑定 Persona Tools/Skills。
6. 确认 Generation Flow 0.7.2、DOCX Generator 0.5.1、Handoff Policy 0.5.3、OpenContracts Gateway 0.6.2、Result Guard 0.3.5、Router 0.5.7、Preconverter 0.1.3 均已加载。
7. 再执行生成、读取、上传 E2E。

## 发布产物

```text
plugins/*.zip  → 安装/升级插件
skills/*.zip   → 只应出现 direct-analysis / conversation-control
personas/*.md  → 按文件头更新 Prompt、Tools、Skills
```

release 中不包含真实合同模板、历史合同或企业业务数据。
