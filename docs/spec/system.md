# System Spec

## 1. Scope

本 spec 定义 ContractBot 从 AstrBot 双层 Agent 方案迁移到 WorkBuddy/Harness + OpenContracts 的系统级要求。

## 2. Required scenarios

### S-01 办公室合同分析

用户可在 WorkBuddy 或兼容 harness 中选择本地 PDF/DOCX/文本合同进行分析。系统不得要求先上传 OpenContracts。

验收：

- 可读取本地文件；
- 可在不调用 OpenContracts 时完成纯本地分析；
- 当需要企业背景时可调用 MCP；
- 默认输出聚焦高优先级风险，不逐条复述全文。

### S-02 办公室合同修改

用户可基于本地合同提出修改要求，得到新文件和修改摘要。

验收：

- 原文件默认不覆盖；
- 能输出 DOCX；
- 修改只检索必要的企业知识；
- 产物可追溯到 source hash。

### S-03 新合同生成

用户可基于事实、模板和历史合同生成正式合同。

验收：

- 支持 `specific_template -> history_reference -> ai_scaffold`；
- strict 指定模板找不到时 fail-closed；
- 历史项目特定事实默认不继承；
- 文档规范在 renderer 前生效；
- 产物至少包含 DOCX。

### S-04 OpenContracts 查询

用户可通过 MCP 查询历史合同、模板、正文、语义搜索和关系信息。

验收：

- 私有 corpus 需要认证；
- 无权限用户不能得到文档正文或搜索命中；
- Skill 不绕过 MCP/权限层直读数据库。

### S-05 合同归档

用户可把本地合同明确归档到 OpenContracts。

验收：

- 归档前计算 source SHA-256；
- 归档前执行远端查重/身份解析；
- 已存在文档的覆盖/版本写入需要用户确认；
- 上传后通过 MCP 核验；
- commit-unknown 不自动重试。

### S-06 微信远程分析/修改

一线用户可通过 WorkBuddy 微信客服号/助理远程触发合同任务。

验收：

- Host 离线时不会伪装成功；
- Host 上已安装固定版本 Skill；
- Host 能访问认证 MCP；
- 至少完成一次合同分析和一次修改产物；
- 产物回传方式必须在 PoC 中记录真实行为。

## 3. System boundaries

### Runtime

系统不得自建新的 Persona/Handoff runtime。模型调度由 WorkBuddy/Harness 负责。

### Server

OpenContracts 是唯一长期合同数据服务。不得为了迁移方便永久保留第二套合同数据库或 Gateway 状态库。

### Client

合同修改/生成的模型推理由客户 harness 执行；默认不在 OpenContracts 服务端再次调用 LLM 完成同一任务。

## 4. Security requirements

### SEC-01 Authentication

企业私有 MCP 必须使用 OpenContracts 认证入口或等价受认证的 corpus-scoped 入口。

### SEC-02 Authorization

所有文档、corpus、标注、关系和写操作必须通过 OpenContracts service-layer permission check。

### SEC-03 Secrets

真实 token/WorkerKey/JWT 不得提交 Git，不得写入 Skill 包示例，不得记录在普通日志。

### SEC-04 File safety

本地 helper 必须限制工作目录、拒绝路径逃逸、拒绝模型拼接任意 shell。

### SEC-05 Write safety

任何无法确认是否已提交的写入都必须返回 `MANUAL_REVIEW` / `retry_safe=false`。

## 5. Data requirements

- `source_sha256`：本地源文件完整性；
- `contract_title`：合同正式标题或用户确认标题；
- `contract_date`：只有有依据时填写；
- `generation_basis`：生成/修改主要依据；
- `reference_documents`：本轮使用的企业资料；
- `remote_document_id/version`：归档后远端事实；
- `skill_version`：产生结果时使用的 Skill 版本。

## 6. Non-functional requirements

### NFR-01 Portability

核心合同规则不能绑定 WorkBuddy 私有 API；WorkBuddy 差异应位于 adapter。

### NFR-02 Upgradability

OpenContracts patch 必须绑定明确上游版本并可验证是否适用。

### NFR-03 Observability

远端写入需要 request id、principal、target、result；客户端产物需要 source hash 与 skill version。

### NFR-04 Minimal server complexity

能在 Skill/本地脚本完成的，不新增长期服务；能由 OpenContracts 原生完成的，不复制实现。

### NFR-05 Token ownership

默认分析/起草 token 消耗发生在客户选择的模型账户中。

## 7. Out of scope for first refactor

- 自建多租户聊天 SaaS；
- 重建 AstrBot Persona；
- 服务端统一托管所有客户模型 token；
- 强制所有合同都自动上传 OpenContracts；
- 在未验证 WorkBuddy 渠道前重建临时下载服务。

## 8. Global acceptance gate

只有以下条件全部通过，`workbuddy-refactor` 才能视为替代旧架构：

1. Office analysis E2E；
2. Office modification + DOCX E2E；
3. Authenticated MCP isolation test；
4. Archive + MCP verification E2E；
5. strict template generation test；
6. commit-unknown test；
7. WorkBuddy WeChat Host PoC；
8. `astrbot-solution` 可独立 checkout，旧方案没有因新分支重构被破坏。
