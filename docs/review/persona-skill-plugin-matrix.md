# Persona、Skill、Plugin 职责矩阵

当前原则：**规则只放在真正消费它的层，避免 Persona + Skill + Plugin 三份重复。** 不为回滚或旧实现保留正式发行组件。

## 分层

| 内容 | Persona | Skill | Plugin / Tool |
|---|---|---|---|
| 角色身份、任务边界、业务判断 | 主责 |  |  |
| 可复用的当前合同分析方法 |  | `contract-direct-analysis` | Router 提供正文快照 |
| 用户可见结束/取消/BLOCKED 恢复语义 | Master 边界 | `contract-conversation-control` | Router 实现确定性状态 |
| OpenContracts 读取/上传步骤 | Operator 主责 |  | Handoff/Gateway/MCP 提供确定性能力 |
| Corpus 绑定 |  |  | Handoff Policy 主责 |
| 文件暂存/会话 pending |  |  | File Router 主责 |
| WorkerKey 写入与上传审计 | Operator 只决定何时调用 |  | OpenContracts Gateway 主责 |
| 合同生成依据与模型起草 | Builder 主责 |  | Generation Flow 记录证据并包工具 |
| DOCX 渲染/Draft Store |  |  | DOCX Generator 主责 |
| HTTPS 发布 |  |  | Download Delivery 主责 |
| WeCom 最终文案/分段/迟到结果 | Master 只做业务表达 |  | Final Result Guard 主责 |

## Personas

### contract_master_orchestrator

负责：
- 唯一客户入口；
- 按最终目标在 Operator / Builder 间路由；
- generation policy protocol 2；
- strict template、PARTIAL、commit-unknown 的客户语义；
- 当前暂存合同的直接分析入口。

Master 不复制 Operator/Builder 的详细工具步骤。

### contract_opencontracts_operator

1.18 起为**自包含操作 Persona**，Skills 为空。负责：
- list_documents → get_document_text 分页读取；
- READ READY/PARTIAL/PENDING/FAILED；
- Gateway identity → 精确查重 → WorkerKey 上传 → MCP 核验；
- UPLOAD DUPLICATE/BLOCKED/PROCESSING/COMPLETE/MANUAL_REVIEW/FAILED；
- commit-unknown 禁止重试。

这些规则不再额外复制到 `contract-opencontracts` 或 `contract-result-verification` Skill。

### contract_docassemble_builder

正式运行不依赖 Docassemble Gateway。Builder 1.27 / protocol v7 负责：
- 专用模板 → 历史参考 → AI scaffold；
- strict template 身份约束；
- `reference_value_fields` 白名单；
- `source_draft_id` 与 `generation_basis`；
- READY/PARTIAL/FAILED 语义。

静态 Tools/Skills 均为空；Generation Flow 注入运行时工具。

## 保留 Skills

### contract-direct-analysis

用于 Master 针对 Router 注入的当前合同正文进行字段提取、风险审查、引用和不确定性表达。它与 OpenContracts 数据库任务无关，因此保留。

### contract-conversation-control

用于 Master 理解“结束/取消/继续/重新上传”等用户可见状态语义。Router 仍负责确定性状态机；Skill 只保留对话层规则，因此保留。

## 已删除 Skills

```text
contract-docassemble
contract-orchestrator
contract-opencontracts
contract-result-verification
```

原因：
- `contract-docassemble`：正式生成已由 Builder Persona + Generation Flow + DOCX Generator 替代；
- `contract-orchestrator`：核心路由已在 Master Persona，且该 Skill 未绑定；
- `contract-opencontracts`：必要操作规则已收敛到 Operator 1.18 和确定性插件；
- `contract-result-verification`：状态证据已由 Operator + Result Guard/插件契约承担。

## Plugins

正式保留：

```text
Contract DOC Preconverter
Contract File Router
Contract Handoff Policy
OpenContracts Upload Gateway
Contract Generation Flow
Contract DOCX Generator
Contract Download Delivery
WeCom Final Result Guard
```

删除：

```text
Docassemble Gateway
```

Delivery 不再接受旧 Gateway output，也不识别旧 `[CONTRACT_DOCASSEMBLE:READY]` 结果。

## 变更判断

- 角色/业务判断变化 → Persona 版本；
- 两个保留 Skill 的复用方法变化 → Skill 版本；
- 确定性状态、工具参数、文件/网络行为变化 → Plugin 版本；
- 纯历史审计文档变化 → 不升级组件。
