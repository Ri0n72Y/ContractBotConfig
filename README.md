# ContractBotConfig

企业合同 AstrBot 配置与扩展工程。Master 是唯一面向企业微信客户的角色；OpenContracts 保存外部生成资产与历史合同；Builder 负责模板匹配、历史参考和合同编制；Contract DOCX Generator 生成可编辑 DOCX；Download Delivery 发布临时 HTTPS 链接；成功发布且 Draft finalize 成功的 Markdown 才成为下一轮可修改的“上一版”。

## 当前正式组件

### Plugins

```text
astrbot_plugin_contract_doc_preconverter   .doc → PDF 预转换
astrbot_plugin_contract_file_router        文件暂存、正文快照、会话状态
astrbot_plugin_contract_handoff_policy     OpenContracts Corpus 绑定与 Operator handoff 规范化
astrbot_plugin_opencontracts_gateway       WorkerKey 合同写入
astrbot_plugin_contract_generation_flow    Builder 运行时工具、Skill grounding、生成状态与证据
astrbot_plugin_contract_docx_generator      DOCX 渲染与 Draft Store
astrbot_plugin_contract_download_delivery  HTTPS 临时交付
astrbot_plugin_wecom_final_result_guard     企业微信结果归一与长文本分段
```

正式发行不包含旧 Docassemble Gateway。

### Skills

当前保留三个真正复用的 Skill：

```text
contract-direct-analysis
contract-conversation-control
contract-document-specification
```

OpenContracts 操作和状态核验已收敛到 Operator Persona + Handoff/Gateway/Result Guard；生成工作流仍由 Builder Persona + Generation Flow 保证。`contract-document-specification` 是独立的文档表达规范层，只约束封面、标题层级、编号、表格、留白、签署页、附件和分页，不提供固定合同条款，也不把生成流程变成模板变量替换。

### Personas

```text
contract_master_orchestrator       1.26
contract_opencontracts_operator    1.18
contract_docassemble_builder       1.28 / generation protocol v7
```

`contract_docassemble_builder` 是当前 AstrBot Subagent 的既有 Persona ID；正式运行链不使用 Docassemble Gateway。

绑定以 `personas/bindings.json` 为准：

- Master：Tools=`transfer_to_opencontracts_operator`,`transfer_to_docassemble_builder`；Skills=`contract-direct-analysis`,`contract-conversation-control`。
- Operator：5 个 OpenContracts/Gateway Tools；Skills 为空。
- Builder：静态 Tools 为空；Skills=`contract-document-specification`；Generation Flow 在 handoff 时注入受限运行时业务工具和 Skill grounding 入口。

## Builder Skill grounding

AstrBot 4.23.2 的主 Agent 会自动处理 Persona Skills，但 handoff 子人格不会再次经过主 Agent 的 Skill 注入流程。Generation Flow 0.7.3 因此在 Builder handoff 边界复用 AstrBot 原生：

```text
PersonaManager
SkillManager
build_skills_prompt
```

把 Builder 当前实际绑定、且启用的 Skill inventory 注入子人格。Skill 正文不复制进 Persona 或 Plugin 配置。

Builder 额外看到一个受限工具：

```text
read_bound_skill(skill_name)
```

它只能读取 Builder 已绑定的 Skill，模型不能提供文件路径。正式运行仍不开放 Shell、Python、通用 HTTP、任意文件读写或 raw MCP 绕过。

当前 `contract-document-specification` 是正式合同生成必需的文档规范 Skill。Builder 在调用 `generate_and_publish_contract` 前必须已经通过 `read_bound_skill` 成功读取它；否则组合工具在任何 DOCX/发布写操作开始前返回 retry-safe BLOCKED。

## 合同生成

Master 正式 handoff 必须发送：

```text
generation_policy_protocol=2
fallback_policy=allow_ai_fallback | require_specific_template
```

Builder prompt 必须包含：

```text
<contract_generation_protocol version="7">
```

新合同默认流程：

```text
用户要求生成
→ Master → Builder
→ read_bound_skill(contract-document-specification)
→ find_generation_assets + find_similar_contracts
→ specific_template / history_reference / ai_scaffold
→ Builder 按 contract-document-specification 组织最终 document_markdown
→ generate_and_publish_contract
   → generate_contract_docx
   → publish_contract_download
   → finalize_contract_draft
→ READY / PARTIAL / BLOCKED / FAILED
```

没有匹配专用模板不是默认阻断。用户明确要求“只能使用指定模板”时，Flow 用 `list_documents` 按精确 document slug 或唯一标准化标题确定身份；找不到或标题歧义时 fail-closed，不转历史合同或 AI fallback。

普通模式中，模板也只能从本轮 `find_generation_assets` 返回候选中绑定。历史合同只迁移适用的结构、条款组合和措辞；项目特定金额、日期、比例、税率、账户、地址、工期等默认不得继承，除非用户通过 `reference_value_fields` 明确授权具体字段。

文档规范 Skill 不决定生成依据，也不改变上述证据优先级。Builder 仍按当前交易自由增删和组合条款；Skill 只负责让最终合同具有稳定的正式文档结构。

完整 READY 必须同时证明：DOCX ready、HTTPS publication ready、Draft finalize ready 且 `draft_saved=true`。如果 HTTPS 已成功而 Draft Store 未可靠落盘，返回 PARTIAL 并保留下载链接，不自动重跑整条生成链。写操作 timeout/cancel/commit-unknown 一律按 `retry_safe=false` 处理。

## OpenContracts 读取与上传

历史合同 Corpus 由：

```text
astrbot_plugin_contract_handoff_policy.default_opencontracts_corpus_slug
```

唯一配置。生成资产 Corpus 由：

```text
astrbot_plugin_contract_generation_flow.generation_asset_corpus_slug
```

唯一配置。

Operator 读取：

```text
list_documents
→ get_document_text(offset=0 → next_offset=null)
→ search_corpus（补充检索/核验）
→ CONTRACT_READ:READY/PARTIAL/PENDING/FAILED
```

Operator 上传：

```text
opencontracts_gateway_status
→ list_documents 精确查重
→ opencontracts_upload_document
→ list_documents + get_document_text + search_corpus 核验
→ CONTRACT_UPLOAD:*
```

WorkerKey 决定写入 Corpus；公开 MCP 只用于读取、发现和核验。提交状态未知时进入 MANUAL_REVIEW，禁止自动重试。

## UTF-8 与模型上下文

Generation Flow 在工具边界先处理 `isError/is_error`，成功 JSON 解析后用 `ensure_ascii=False` 紧凑序列化。完整 traceback 留服务日志；模型侧只接收短结构化错误。不要用 `unicode_escape` 二次解码正常 Unicode 字符串。

## 构建

```powershell
python -m compileall -q plugins scripts
python scripts/build_release.py --clean
```

输出：

```text
dist/plugins/*.zip
dist/skills/*.zip
dist/personas/*.md
dist/MANIFEST.json
```

`release_lib.py` 直接遍历当前 `plugins/` 和 `skills/` 目录，因此 `contract-document-specification` 会自动进入 release。

完整版本见 `VERSIONS.md`；部署绑定见 `docs/deployment/persona-manual-config.md`。
