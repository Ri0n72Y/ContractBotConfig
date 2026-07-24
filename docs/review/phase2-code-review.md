# Phase 2-A 代码审查与 Git 历史整理

## Git 历史

Phase 1 已通过 squash merge 进入 `main`：

```text
944253b  Phase 1 squash
```

Phase 2 分支已经重新挂接到该提交。当前 PR 的 merge base 是 `944253b`，分支不再携带 squash 前的 Phase 1 提交历史。

```text
main / 944253b
  └── phase2-opencontracts-mcp-write-split
```

旧 PR #2 保留为历史记录。面向 `main` 的审查入口为 PR #3。PR 合并时使用 squash merge，将 Phase 2-A 的整理提交合并为一个 `main` 提交。

## 审查范围

- OpenContracts MCP 能力使用；
- WorkerKey 文档导入网关；
- Gateway 模块拆分；
- Handoff 兼容层；
- Router 任务上下文；
- WeCom 最终结果分类；
- AstrBot 发布和加载路径。

## OpenContracts MCP 事实来源

OpenContracts 官方 `docs/mcp/`、MCP 服务实现与运行时 `tools/list` 是 MCP 能力、参数和返回结构的事实来源。本项目不依据局部字段推断 MCP 能力不足，也不在 Gateway 中复制远端读取实现。

Corpus-scoped MCP 当前公开：

```text
get_corpus_info
list_documents
get_document_text
list_annotations
list_relationships
search_corpus
list_threads
get_thread_messages
create_thread_message
```

对应 Resources：

```text
corpus://{corpus_slug}
document://{corpus_slug}/{document_slug}
annotation://{corpus_slug}/{document_slug}/{annotation_id}
thread://{corpus_slug}/threads/{thread_id}
```

`create_thread_message` 由 MCP Tool 本身校验认证和资源权限。MCP 认证由 AstrBot MCP 连接管理。

上传、问答、风险分析、关系、标注和讨论线程流程按任务选择这些能力。后续新增 OpenContracts 操作时，先查看官方 `docs/mcp/`、MCP 服务实现和 AstrBot 中的工具发现结果。

## 已确认的设计

### MCP 与文件导入分工

```text
OpenContracts Operator
├── OpenContracts MCP：Corpus、文档、正文、标注、关系、检索和讨论线程
└── Upload Gateway：WorkerKey 文档导入
```

Gateway 配置中不包含读取 Bearer Token，也不实现 `/api/imports/documents/lookup/`。

### Gateway 拆分

`main.py` 已缩减为 AstrBot Tool 适配器。文件验证、确认验证、导入客户端、响应策略、结果映射和 receipt 持久化位于独立模块。

### OpenContracts 版本语义

OpenContracts 对同路径再次导入可返回 `updated`，表示新版本已经写入。Gateway 记录实际服务端结果，并区分带确认和未带确认的版本写入。

## 本轮修复

### 未确认的 `updated`

```text
status=updated + confirmed=false
→ 保存审计 receipt
→ failure_stage=unexpected_unconfirmed_update
→ write_committed=true
→ manual_review_required=true
```

该结果说明写入已经发生，同时避免将其包装为普通首次上传成功。

### 响应策略拆分

HTTP 分类和导入结果策略位于：

```text
services/import_response_policy.py
```

`ImportResultService` 负责持久化和业务结果映射。

## Phase 2-B 衔接项

Router 0.5.0 的旧任务上下文中仍出现 `opencontracts_check_duplicate`。Handoff Policy 0.4.3 会在委派时把 OpenContracts 分支规范为 MCP 与 Gateway 的当前工具集。Phase 2-B 拆分 Router 时，将直接更新 Router 的任务上下文和动态提示，移除该兼容层输入。

该事项不影响 Gateway 的工具注册，但应在 Router 重构时一并完成。

## WeCom 结果分类

正式状态标记仍是主要输入：

```text
[CONTRACT_UPLOAD:COMPLETE]
[CONTRACT_UPLOAD:PROCESSING]
[CONTRACT_UPLOAD:DUPLICATE_CONFIRMATION_REQUIRED]
[CONTRACT_UPLOAD:BLOCKED]
[CONTRACT_UPLOAD:FAILED]
```

自然语言 fallback 用于兼容现有运行结果。Phase 2-C 将其拆分为独立分类模块，保持正式状态标记优先。

## MVP 验证策略

项目架构和能力仍在高频变化。当前不维护单元测试矩阵，合并前验证限定为：

1. Python 语法和导入静态检查；
2. 发布 ZIP 能够在 AstrBot WebUI 中加载；
3. Plugin、Skill、Persona 和 MCP 工具分配能够初始化；
4. 在真实 AstrBot、企业微信和 OpenContracts 环境中执行一次最小上传流程。

静态检查命令：

```bash
python3 -m compileall -q plugins scripts
```

## 当前合并状态

Git 历史已经适合对 `main` 审查。PR 保持 Draft，直到当前分支的发布包完成 AstrBot 加载验证。加载通过后即可标记 Ready，并通过 squash merge 合并到 `main`。
