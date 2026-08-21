# Contract Bot 当前版本基线

## 插件

- astrbot_plugin_contract_doc_preconverter: 0.1.3
- astrbot_plugin_contract_docx_generator: 0.5.1
- astrbot_plugin_contract_download_delivery: 0.2.5
- astrbot_plugin_contract_file_router: 0.5.8
- astrbot_plugin_contract_generation_flow: 0.8.0
- astrbot_plugin_contract_handoff_policy: 0.5.3
- astrbot_plugin_opencontracts_gateway: 0.6.2
- astrbot_plugin_wecom_final_result_guard: 0.3.5

正式发行不再包含 Docassemble Gateway 或任何旧文书生成回滚组件。

## Skills

- contract-direct-analysis: 1.14
- contract-conversation-control: 1.15
- contract-document-specification: 1.0

OpenContracts 读取/上传/核验规则由 Operator Persona、Handoff Policy、OpenContracts Gateway 和 Result Guard 共同承担。生成流程由 Builder Persona 与 Generation Flow 承担；`contract-document-specification` 只负责正式合同的文档结构与格式规范，不提供固定合同条款或模板替换逻辑。

Generation Flow 0.8.0 修复 AstrBot handoff 子人格未自动注入 Persona Skills 的运行时缺口：它复用 AstrBot `PersonaManager/SkillManager` 读取 Builder 实际绑定且启用、并且当前受限读取入口可直接 grounding 的 Skill 元数据，构造不含 Shell/任意文件路径指令的受限 inventory，并只注入本次 handoff input；Skill 正文通过受限 `read_bound_skill` 读取。Flow 不修改共享 Handoff Agent 的 system prompt，也不开放 Shell、Python、通用 HTTP 或任意文件读写。正式生成在任何 DOCX 写入前强制确认 `contract-document-specification` 已完成 grounding。

## 人格

- contract_docassemble_builder: 1.30（generation protocol v7；绑定 contract-document-specification；system prompt 强制在组织最终 document_markdown 前先 grounding）
- contract_master_orchestrator: 1.26（generation policy protocol 2）
- contract_opencontracts_operator: 1.18（自包含，无 Skill）

正式合同生成按“专用模板 -> 历史参考 -> AI 自组织结构”回退；没有通用合同骨架资产。正式生成 handoff 必须显式携带 generation_policy_protocol=2 与 fallback_policy。strict 指定模板按精确 document slug 或唯一标准化标题确定身份；普通模式模板绑定也必须来自本轮生成资产搜索候选。写操作 timeout/cancel 按 commit-unknown、retry_safe=false 处理；HTTPS 已发布但 draft finalize 失败返回 PARTIAL，不返回 READY。

Builder 的内容组织仍依据用户事实、模板、历史合同和通用合同知识自由组合；文档规范 Skill 只统一封面、标题层级、编号、表格、留白、签署页、附件和分页表达。Builder 1.30 把“先 `read_bound_skill(contract-document-specification)`、再组织最终正文”的固定规则放在 Persona system prompt；request-local handoff input 只携带本轮 Skill inventory 和业务任务。

Persona 绑定以 `personas/bindings.json` 为准；正式架构见 `docs/architecture/system-context.md` 与 `docs/architecture/ai-docx-generation.md`。
