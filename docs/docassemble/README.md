# ContractBot Docassemble 生成与部署

版本以根目录 `VERSIONS.md` 为准，Persona 工具绑定以 `personas/bindings.json` 为准。

## 正常生成链

```text
用户明确要求生成/起草/制作
→ Master 直接委派 Builder
→ Handoff Policy 从唯一配置解析 OpenContracts Corpus
→ Generation Flow 刷新 Builder Prompt 和四工具 ToolSet
→ Flow 将 corpus_slug 从 Builder 可见 schema 隐藏，并在实际 list/get MCP 调用时注入配置值
→ Builder list_documents → 选择主参考 → get_document_text(offset=0)
→ 合同库可复用信息优先，仍缺失的普通字段保留【待填写】
→ Builder 选择固定 DOCX template_key 或 generic fallback
→ Gateway 验证本轮真实参考读取并调用正式 Docassemble interview
→ Docassemble 基于固定 DOCX 模板生成排版稳定的 DOCX
→ Delivery 发布临时 HTTPS 链接
→ Master 回复用户
```

生成草稿不设置额外固定确认口令。用户说“按这个生成”“开始生成”等自然语言执行表达直接进入生成；生成任务中需要从合同库补字段时由 Builder 自己读取，不先经过 Operator。

## Corpus 配置

Corpus slug 只有一个配置 owner：`astrbot_plugin_contract_handoff_policy`。

```text
default_opencontracts_corpus_slug = contracts
```

该值同时用于独立读取、上传发现与 Builder 生成参考读取。Generation Flow 不保存第二份配置，只消费 Handoff Policy 在本轮 event 上绑定的目标 Corpus。

Builder 实际看到：

```text
list_documents(search=...)
get_document_text(document_slug=..., char_offset=0, max_chars=30000)
```

Builder 不看到也不提交 `corpus_slug`。Flow 在调用原 MCP Tool 前自动补入配置值。因此不要让 Persona 猜 `contracts/default`，也不要调用 `list_public_corpuses`。

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

Builder 1.20 支持：

```text
road_labor         道路工程劳务/施工固定 DOCX 模板
material_purchase  材料采购/供货固定 DOCX 模板
generic            尚无固定模板时的旧 document_body fallback
```

固定模板场景不再让 LLM 重写整份合同正文；Builder 只提交已知的 `contract_data` 和必要的列表数据，Interview 对未提供字段写入 `【待填写】` / `【待双方确认】`。

## 正式 interview

生产 interview：

```text
contractbot_document_generation.yml
```

支持变量：

```text
document_title
template_key
contract_data
material_items   # material_purchase 可选
boq_markdown     # road_labor 可选
document_body    # 仅 generic fallback
```

固定模板映射：

```text
road_labor
→ contractbot_road_labor_template.docx

material_purchase
→ contractbot_material_purchase_template.docx
```

`contractbot_api_smoke.yml` 仅用于 API smoke，不能作为正式 `default_interview`。

## Docassemble Playground 部署模板

在与 production interview 相同的 Playground / Project 中：

1. 打开 `Folders → Templates`；
2. 上传并保持以下**精确文件名**：

```text
contractbot_road_labor_template.docx
contractbot_material_purchase_template.docx
```

3. 回到 Questions/Interviews，使用仓库当前 `docs/docassemble/contractbot_document_generation.yml` 替换现有 production interview 内容并保存；
4. Gateway 的 `allowed_interviews/default_interview` 继续指向这个 production interview 的完整 filename，不需要改成 DOCX 模板名；
5. 重新开始一次新的 interview/session 做 E2E。

如果以后 package 化，则将两个 DOCX 放到 package 的 `data/templates/`，production YAML 保持同名引用即可。

## 模板字段策略

两个 Word 模板保留原合同的页面尺寸、段落、标题、分页、签署页和主要表格版式，只把业务可变位置替换为 Jinja/Docassemble 变量。

常用 `contract_data`：

```text
contract_number
project_name
work_name
project_location
signing_place
signing_date
party_a_name / party_b_name
party_a_address / party_b_address
party_a_legal_rep / party_b_legal_rep
party_a_agent / party_b_agent
party_a_bank / party_b_bank
party_a_account / party_b_account
party_a_tax_id / party_b_tax_id
party_a_postcode / party_b_postcode
party_a_phone / party_b_phone
party_a_email / party_b_email
```

道路劳务模板还使用工程工期、道路长度、设备材料、价格/税额、驻场代表等字段，并允许 `boq_markdown` 插入工程量清单。

材料采购模板使用 `pricing_clause` 承载固定单价或固定总价的完整计价表述，避免为两种价格模式维护两份 Word；材料清单由 `material_items` 动态生成表格行。

## 缺失字段策略

默认：

```text
draft_policy = reference_first_then_placeholder
```

用户明确值优先；其余先从本轮参考合同取得。不同项目的金额、单价、具体日期和比例不能默认照搬，除非用户明确授权这些字段也使用历史值。固定模板中未提供的普通字段由 interview 自动填 `【待填写】`；争议解决等需双方确定的字段可填 `【待双方确认】`。只有用户明确要求字段完整才能生成时才阻断。

## Gateway

```text
base_url = http://docassemble
api_key = <Docassemble API Key>
allowed_interviews = [<正式 interview>]
default_interview = <正式 interview>
output_retention_seconds = 86400
output_cleanup_interval_seconds = 300
```

Gateway 只验证本轮参考读取、正式 interview 和当前生成输出，不负责 Corpus 配置或 Builder ToolSet。

## Delivery

```text
public_root = data/public_downloads
public_base_url = https://download.ri0n72y.top/contracts
allowed_source_dirs = [data/plugins_data/astrbot_plugin_docassemble_gateway/output]
ttl_seconds = 1800
```

只有同一次 Gateway 的 `output_path/output_filename` 可以发布；只有真实 HTTPS 发布成功后才能向客户报告 READY。

## E2E

道路劳务：

```text
根据合同库生成一份道路工程劳务合同。项目名称是“XX项目”，地点是“广东省佛山市”，其他内容优先从合同库参考，找不到的留空，按这个生成。
```

材料采购：

```text
生成一份材料采购合同，项目名称“XX项目”，采用固定总价；材料范围和常用条款优先参考合同库，未提供的数据留空，直接生成。
```

日志验收：

```text
Contract handoff policy: bound generation corpus=contracts
Contract generation flow: refreshed Builder handoff ... corpus=contracts ...
```

Builder 的 `list_documents/get_document_text` 调用日志中不应再出现空 `corpus_slug`、`default` 或 Agent 猜测的 `contracts`；MCP 实际调用由 Flow 自动注入正确配置。

正常客户侧仍只需要一条处理中提示和一条最终成功/失败结果。
