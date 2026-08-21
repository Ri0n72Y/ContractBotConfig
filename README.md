# ContractBotConfig

企业合同 AstrBot 配置与扩展工程。Master 是唯一面向企业微信客户的角色；OpenContracts 保存外部生成资产与历史合同；Builder 负责模板匹配、历史参考和合同编制；Contract DOCX Generator 生成可编辑 DOCX；Download Delivery 发布临时 HTTPS 链接；成功发布且 Draft finalize 成功的 Markdown 才成为下一轮可修改的“上一版”。

## 当前正式组件

### Plugins

```text
astrbot_plugin_contract_doc_preconverter   .doc → PDF 预转换
astrbot_plugin_contract_file_router        文件暂存、正文快照、会话状态
astrbot_plugin_contract_handoff_policy     OpenContracts Corpus 绑定与 Operator handoff 规范化
astrbot_plugin_opencontracts_gateway       WorkerKey 合同写入
astrbot_plugin_contract_generation_flow    Builder 合同领域工具、Skill grounding、生成状态与证据
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
contract_docassemble_builder       1.30 / generation protocol v7
```

`contract_docassemble_builder` 是当前 AstrBot Subagent 的既有 Persona ID；正式运行链不使用 Docassemble Gateway。

绑定以 `personas/bindings.json` 为准：

- Master：Tools=`transfer_to_opencontracts_operator`,`transfer_to_docassemble_builder`；Skills=`contract-direct-analysis`,`contract-conversation-control`。
- Operator：5 个 OpenContracts/Gateway Tools；Skills 为空。
- Builder：Tools=`read_bound_skill`,`find_generation_assets`,`read_generation_asset`,`find_similar_contracts`,`read_reference_contract`,`read_latest_contract_draft`,`read_contract_draft`,`generate_and_publish_contract`；Skills=`contract-document-specification`。这些绑定由 AstrBot Persona/WebUI 管理。

## Builder Skill grounding

当前部署基线只考虑 AstrBot 4.27.x 及以上。Builder 的 Persona prompt、Tool 绑定和 Skill 绑定均由 AstrBot 管理；Generation Flow 0.8.0 不覆盖 `agent.tools`、不修改 `agent.instructions`，也不重写 handoff `input`。

AstrBot handoff 子人格当前不会自动把 Persona Skill 正文展开给 Builder，因此保留一个最小受限桥：

```text
read_bound_skill(skill_name)
```

它只接受 Builder 实际绑定、active 且当前本地 reader 可直接读取的 Skill 名称；模型不能传文件路径，也不会获得 Shell、Python、通用 HTTP、任意文件读写或 raw MCP 能力。同一 handoff 对已经成功 grounding 的文档规范 Skill 再次调用时返回 `already_grounded`，不重复返回整份 `SKILL.md`。

Builder 1.30 的 system prompt 固定要求：所有正式合同生成、重写、修改和定稿，必须先 `read_bound_skill(contract-document-specification)` 完成 grounding，再开始组织最终 `document_markdown`。Generation Flow 只读取 Persona/Skill/Tool 绑定做 fail-closed 校验；不向 handoff prompt 注入动态 Skill inventory。

当前 `contract-document-specification` 是正式合同生成必需的文档规范 Skill。Builder 在调用 `generate_and_publish_contract` 前必须已经成功读取它；否则组合工具在任何 DOCX/发布写操作开始前返回 retry-safe BLOCKED。

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

### Skill 版本化运行时 ID

仓库中的 Skill 逻辑名保持 `contract-document-specification`。AstrBot 实际安装/绑定时可能使用版本化运行时 ID，例如 `contract-document-specification-1.0`。Generation Flow 0.8.0 会把唯一绑定的 `contract-document-specification` 或 `contract-document-specification-<数字版本>` 解析为同一个逻辑 Skill；Builder 仍稳定调用 `read_bound_skill(contract-document-specification)`。若同时绑定多个该 Skill 版本则 fail-closed，不自动选择。

### AstrBot ownership boundary

Generation Flow 0.8.0 不再作为第二套 Agent runtime：不覆盖 Builder ToolSet、不改 system prompt、不包装 handoff input。Builder 的 8 个允许工具必须在 AstrBot Persona/WebUI 中静态绑定；Flow 只负责合同生成证据、状态机和写安全门槛。File Router 0.5.8 同时移除了对 AstrBot Star 全局注册表的直接修改。
