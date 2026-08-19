# ContractBotConfig

企业合同 AstrBot 配置与扩展工程。Master 是唯一面向企业微信客户的角色；OpenContracts 保存外部生成资产与历史合同；Builder 负责模板匹配、历史参考和合同编制；Contract DOCX Generator 生成可编辑 DOCX；Download Delivery 发布临时 HTTPS 链接；成功发布且 Draft finalize 成功的 Markdown 才成为下一轮可修改的“上一版”。

## 当前正式组件

### Plugins

```text
astrbot_plugin_contract_doc_preconverter   .doc → PDF 预转换
astrbot_plugin_contract_file_router        文件暂存、正文快照、会话状态
astrbot_plugin_contract_handoff_policy     OpenContracts Corpus 绑定与 Operator handoff 规范化
astrbot_plugin_opencontracts_gateway       WorkerKey 合同写入
astrbot_plugin_contract_generation_flow    Builder 运行时工具、生成状态与证据
astrbot_plugin_contract_docx_generator      DOCX 渲染与 Draft Store
astrbot_plugin_contract_download_delivery  HTTPS 临时交付
astrbot_plugin_wecom_final_result_guard     企业微信结果归一与长文本分段
```

正式发行不包含旧 Docassemble Gateway。

### Skills

只保留两个真正复用的 Skill：

```text
contract-direct-analysis
contract-conversation-control
```

OpenContracts 操作和状态核验已收敛到 Operator Persona + Handoff/Gateway/Result Guard；生成工作流已收敛到 Builder Persona + Generation Flow，不再用重复 Skill 叠加 prompt。

### Personas

```text
contract_master_orchestrator       1.26
contract_opencontracts_operator    1.18
contract_docassemble_builder       1.27 / generation protocol v7
```

`contract_docassemble_builder` 是当前 AstrBot Subagent 的既有 Persona ID；正式运行链不使用 Docassemble Gateway。

绑定以 `personas/bindings.json` 为准：

- Master：Tools=`transfer_to_opencontracts_operator`,`transfer_to_docassemble_builder`；Skills=`contract-direct-analysis`,`contract-conversation-control`。
- Operator：5 个 OpenContracts/Gateway Tools；Skills 为空。
- Builder：静态 Tools/Skills 都为空，由 Generation Flow 注入受限运行时工具。

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
→ find_generation_assets + find_similar_contracts
→ specific_template / history_reference / ai_scaffold
→ generate_and_publish_contract
   → generate_contract_docx
   → publish_contract_download
   → finalize_contract_draft
→ READY / PARTIAL / BLOCKED / FAILED
```

没有匹配专用模板不是默认阻断。用户明确要求“只能使用指定模板”时，Flow 用 `list_documents` 按精确 document slug 或唯一标准化标题确定身份；找不到或标题歧义时 fail-closed，不转历史合同或 AI fallback。

普通模式中，模板也只能从本轮 `find_generation_assets` 返回候选中绑定。历史合同只迁移适用的结构、条款组合和措辞；项目特定金额、日期、比例、税率、账户、地址、工期等默认不得继承，除非用户通过 `reference_value_fields` 明确授权具体字段。

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

`release_lib.py` 直接遍历当前 `plugins/` 和 `skills/` 目录，因此已删除的旧组件不会再进入 release。

完整版本见 `VERSIONS.md`；部署绑定见 `docs/deployment/persona-manual-config.md`。
