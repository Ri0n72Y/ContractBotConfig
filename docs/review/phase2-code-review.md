# Phase 2-A 代码审查与 Git 历史整理

## Git 历史

Phase 1 已通过 squash merge 进入 `main`：

```text
944253b  Phase 1 squash
```

原 Phase 2 分支建立在 squash 前的 Phase 1 分支历史上，因此相对 `main` 显示为：

```text
ahead 19
behind 1
merge-base = Phase 1 之前的提交
```

Phase 2 树已重新挂接到 `944253b`：

```text
944253b  Phase 1 squash
  └── aa0ef14  Phase 2-A
```

整理后：

```text
ahead 1
behind 0
merge-base = 944253b
```

旧 PR #2 保留为历史记录。面向 `main` 的审查入口为 PR #3。

## 审查范围

- OpenContracts MCP 读取流程；
- WorkerKey 文档导入网关；
- Gateway 模块拆分；
- Handoff 兼容层；
- Router 任务上下文；
- WeCom 最终结果分类；
- 单元测试和发布结构。

## 已确认的设计

### 读取与写入分离

```text
OpenContracts Operator
├── OpenContracts MCP：发现、正文、检索、处理核验
└── Upload Gateway：WorkerKey 文档导入
```

Gateway 配置中不再包含读取 Bearer Token，也不再实现 `/api/imports/documents/lookup/`。

### Gateway 拆分

`main.py` 已缩减为 AstrBot Tool 适配器。文件验证、确认验证、导入客户端、响应映射和 receipt 持久化已拆为独立模块。

### OpenContracts 版本语义

OpenContracts 对同一路径的再次导入返回 `updated`，表示已经创建新版本。HTTP 400/409 路径冲突只能作为兼容分支，不能代表完整的版本确认边界。

## 本轮修复

### 未确认的 `updated`

此前 Gateway 将所有 `201 + ok + document_id` 视为正常写入。若 MCP 身份判断漏掉已有文档，OpenContracts 可能直接返回 `updated`，导致没有有效客户确认的新版本写入被当作普通成功。

现在：

```text
status=updated + confirmed=false
→ 保存审计 receipt
→ failure_stage=unexpected_unconfirmed_update
→ write_committed=true
→ manual_review_required=true
```

该结果准确表明写入已经发生，同时阻止系统把它报告为普通上传成功。

### 响应策略拆分

HTTP 分类和路径冲突映射提取到：

```text
services/import_response_policy.py
```

`ImportResultService` 保持在 200 行以内，响应策略可以独立测试和演进。

## 合并前仍需处理

### Router 任务上下文

Router 0.5.0 仍在 `branch_tasks.required_tools` 和动态说明中包含旧工具名：

```text
opencontracts_check_duplicate
```

Handoff Policy 0.4.3 会在委派时将 OpenContracts 分支改写为 MCP 读取和 Gateway 写入工具，因此当前子助手不会收到旧 Tool 集。Router 自身的上下文仍应在 Phase 2-B 拆分时同步更新，消除兼容层依赖。

### MCP 文档身份

Corpus-scoped MCP 的 `list_documents` 摘要提供 `slug`、`title` 等字段，但不提供 DocumentPath 或文件哈希。当前流程以稳定原始文件名主体和精确标题匹配作为合同身份约定。

这项约定需要覆盖以下测试：

1. 当前系统首次上传后再次上传同名合同；
2. 同名、内容变化的版本写入；
3. 历史文档标题不符合当前命名约定；
4. MCP 分页或返回结构不完整；
5. MCP 判断为新合同、写入端返回 `updated` 的竞态。

### WeCom fallback 分类

正式状态标记具有最高优先级。当前自然语言兼容分类仍有两项待拆分：

- 泛化的 `opencontracts mcp` 文本可能把未带标记的成功说明识别为 blocked；
- `import_endpoint_missing` 位于 failed fallback 中，而 Gateway 将 404 定义为 blocked。

Phase 2-C 拆分 `UploadStatusClassifier` 时应增加独立测试并删除这些歧义。

## 当前合并状态

Git 历史已经适合对 `main` 审查。PR 保持 Draft，直到：

- Gateway 新增测试通过；
- Router 兼容项的处理范围得到确认；
- Result Guard fallback 分类完成修正或明确进入后续 PR。
