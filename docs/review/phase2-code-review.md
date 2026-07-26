# Phase 2-A 代码审查与修复记录

## Git 历史

Phase 1 已通过 squash merge 进入 `main`：

```text
944253b  Phase 1 squash
```

PR #3 的 merge base 保持为 `944253b`。合并时使用 squash merge，将 Phase 2-A 整理为一个 `main` 提交。

## 审查范围

- OpenContracts MCP 能力使用；
- 合同远端身份与重复识别；
- WorkerKey 文档导入网关；
- 不确定提交和版本写入语义；
- Gateway 模块拆分；
- Handoff 上下文和安全约束；
- WeCom 最终结果分类；
- 上传审计；
- AstrBot 发布和加载路径。

## 已确认的设计

```text
OpenContracts Operator
├── OpenContracts MCP：Corpus、文档、正文、标注、关系、检索和讨论线程
└── Upload Gateway：合同身份规范化 + WorkerKey 文档导入
```

Gateway 不保存 MCP 读取凭证，不实现 `/api/imports/documents/lookup/`，也不要求配置 Corpus ID。写入目标由 WorkerKey 绑定。

## 审查发现与修复

### 1. 未确认版本写入被误判为处理中

修复后 `updated + confirmed=false` 返回：

```text
status=manual_review_required
failure_stage=unexpected_unconfirmed_update
write_committed=true
manual_review_required=true
retry_safe=false
```

Result Guard 在普通 processing 前识别人工核查状态，客户收到“请勿重复上传”的确定性回复。

### 2. 远端重复识别缺少稳定身份

统一使用：

```text
document_title = YYYY-MM-DD 合同标题
normalized_filename = YYYY-MM-DD_合同标题.原扩展名
```

主人格从合同正文提取 `contract_date` 和 `contract_title`，通过结构化 handoff input 传给 Operator。MCP 查询按规范化标题搜索，并对结果做标题完全一致比较。

### 3. 传输异常被当作普通失败

以下结果统一表示提交状态未知：

```text
transport_commit_unknown
upstream_commit_unknown
unexpected_success_response
```

Gateway 保存追加式审计 receipt，返回 `manual_review_required=true` 和 `retry_safe=false`。Operator 禁止自动重试。

### 4. Corpus 配置与 WorkerKey 绑定可能冲突

Gateway 删除 `default_corpus_id` 和 `default_corpus_slug` 配置。WorkerKey 直接决定写入目标，Gateway 不展示配置 ID。写入后由当前 corpus-scoped MCP 核验实际远端结果。

### 5. Handoff 覆盖 Router 安全约束

Handoff Policy 0.4.4 改为合并约束并去重，保留：

- 远端查询失败停止上传；
- 未知状态不得按新合同处理；
- receipt 不能作为远端不存在依据；
- 禁止绕过重复限制；
- 当前企业微信事件同步返回。

Handoff 还保留主人格原始结构化 input，并注入 identity/status contract。

### 6. 客户文案扩大完成范围

`COMPLETE` 只声明“正文可读并已进入检索”。没有调用 `list_annotations` 时，不声明标注完成。

### 7. Receipt 按文件名合并

Receipt schema v4 使用 append-only 记录。每次写入或提交状态未知形成独立 receipt，文件名仅作为审计字段。

## 正式状态标记

```text
[CONTRACT_UPLOAD:DUPLICATE_CONFIRMATION_REQUIRED]
[CONTRACT_UPLOAD:BLOCKED]
[CONTRACT_UPLOAD:PROCESSING]
[CONTRACT_UPLOAD:COMPLETE]
[CONTRACT_UPLOAD:MANUAL_REVIEW]
[CONTRACT_UPLOAD:FAILED]
```

状态优先级中，`MANUAL_REVIEW` 高于 `PROCESSING` 和 `FAILED`。

## Phase 2-B 衔接项

Router 0.5.0 的旧任务上下文仍出现 `opencontracts_check_duplicate`。Handoff Policy 0.4.4 会在委派时覆盖为当前 MCP 与 Gateway 工具集。Phase 2-B 拆分 Router 时应删除该遗留名称。

## MVP 验证策略

当前阶段不新增测试目录或测试代码。合并前执行：

```bash
python3 -m compileall -q plugins scripts
python scripts/build_release.py --clean
```

随后在 AstrBot WebUI 中加载发布 ZIP，并在真实 AstrBot、企业微信和 OpenContracts 环境验证：

1. 首次上传；
2. 重复合同确认后重新上传；
3. 合同日期或标题缺失时阻止上传；
4. 提交状态未知时进入人工核查；
5. 正文读取和检索完成状态。

## 当前合并状态

PR 保持 Draft，直到发布包完成 AstrBot WebUI 加载和真实最小流程验证。验证通过后标记 Ready，并通过 squash merge 合并到 `main`。
