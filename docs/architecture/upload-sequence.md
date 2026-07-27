# 合同上传时序

## 新合同

```mermaid
sequenceDiagram
    participant U as 用户
    participant R as Router
    participant M as Master
    participant H as Handoff Policy
    participant O as OpenContracts Operator
    participant MCP as OpenContracts Public MCP
    participant G as Upload Gateway
    participant OC as OpenContracts
    participant RG as Result Guard

    U->>R: 上传合同并选择 1
    R->>R: 暂存文件 + 计算 SHA-256
    R->>R: 从原文件名提取唯一日期提示
    R->>M: contract_task_context + identity_hints + targets.opencontracts
    M->>M: 正文身份优先；正文日期为空时使用 filename hint
    M->>H: transfer input(JSON contract_identity)
    H->>O: 同步结构化任务 + public MCP contract
    O->>G: opencontracts_gateway_status
    G-->>O: normalized identity
    O->>MCP: list_documents(corpus_slug, search=document_title)
    MCP-->>O: 无标题完全一致文档
    O->>G: date + title + staged_path + sha256
    G->>OC: WorkerKey + YYYY-MM-DD_合同标题.扩展名
    OC-->>G: created
    G-->>O: processing
    O->>MCP: list_documents + get_document_text + search_corpus
    MCP-->>O: processing 或 verified
    O-->>M: 标准状态标记
    M->>RG: 最终结果
    RG-->>U: 客户回复
```

公开 MCP 地址由 AstrBot 配置为 `/mcp/`。所有读取工具使用 `targets.opencontracts` 作为 `corpus_slug`；流程不调用 `get_corpus_info`、`opencontracts_check_duplicate` 或不存在的 corpus-scoped URL。

## 原文件名日期

```mermaid
sequenceDiagram
    participant R as Router
    participant M as Master
    participant U as 用户

    R->>R: 解析 original_name
    alt 唯一有效日期
        R->>M: identity_hints.contract_date=YYYY-MM-DD
        M->>M: 正文日期为空，直接采用提示
        Note over M,U: 不向用户追问日期
    else 无日期或多个不同日期
        R->>M: identity_hints 为空
        M-->>U: BLOCKED，询问缺失日期
    end
```

支持 `YYYY-M-D`、`YYYY.M.D`、`YYYY_M_D`、中文年月日和 `YYYYMMDD`。

## 远端合同已存在

```mermaid
sequenceDiagram
    participant U as 用户
    participant R as Router
    participant M as Master
    participant O as OpenContracts Operator
    participant MCP as OpenContracts Public MCP
    participant RG as Result Guard

    U->>R: 选择上传
    R->>M: contract_task_context
    M->>O: 规范化合同身份
    O->>MCP: list_documents(corpus_slug, search=document_title)
    MCP-->>O: 标题完全一致
    O-->>M: DUPLICATE_CONFIRMATION_REQUIRED
    M->>RG: 最终状态
    RG->>R: preserve=duplicate_confirmation_required
    RG-->>U: 询问重新上传或取消
```

## BLOCKED 后恢复

```mermaid
sequenceDiagram
    participant U as 用户
    participant R as Router
    participant M as Master
    participant O as OpenContracts Operator
    participant RG as Result Guard

    M-->>RG: CONTRACT_UPLOAD:BLOCKED + 原因
    RG->>RG: 分类 missing_date / missing_title / system
    RG->>R: preserve=blocked + blocked_reason
    R->>R: state=awaiting_blocked_resolution
    R->>R: 保留 staged_path、SHA-256 和 pending
    RG-->>U: 文件已保留；补充信息或修复后回复继续
    U->>R: 日期 / 标题 / 继续
    R->>M: 原文件 + resume.user_input
    M->>O: 继续上传流程
```

`BLOCKED` 尚未写入，因此允许复用原暂存文件。客户回复“结束”或“取消”时 Router 清理；客户发送新文件时 Router 要求先结束当前保留任务。

即使模型漏写显式 BLOCKED 标记，只要最终文本明确说明日期或标题缺失，Result Guard 仍将其识别为可恢复阻断。

## 客户确认重新上传

```mermaid
sequenceDiagram
    participant U as 用户
    participant R as Router
    participant M as Master
    participant O as OpenContracts Operator
    participant G as Upload Gateway
    participant OC as OpenContracts

    U->>R: 重新上传
    R->>R: 记录 confirmation_id 和时间
    R->>M: reupload task context
    M->>O: 同步重新上传任务
    O->>G: date + title + confirmation_id
    G->>G: 校验会话、哈希、确认编号和有效期
    G->>OC: WorkerKey 文档导入
    OC-->>G: updated
    G-->>O: processing
```

## 提交状态未知

```mermaid
sequenceDiagram
    participant O as OpenContracts Operator
    participant G as Upload Gateway
    participant OC as OpenContracts
    participant RG as Result Guard
    participant U as 用户

    O->>G: opencontracts_upload_document
    G->>OC: POST /api/imports/documents/
    alt timeout / connection error
        OC--xG: 响应未知
        G-->>O: transport_commit_unknown
    else 5xx
        OC-->>G: server error
        G-->>O: upstream_commit_unknown
    else unexpected 2xx body
        OC-->>G: success status + invalid contract
        G-->>O: unexpected_success_response
    else updated without confirmation
        OC-->>G: updated
        G-->>O: unexpected_unconfirmed_update
    end
    O-->>RG: MANUAL_REVIEW
    RG-->>U: 已记录审计，请勿重复上传
```

这些路径可能已经写入，不属于可恢复 BLOCKED。Gateway 追加 receipt，Operator 禁止再次调用上传工具。

## 写入前路径冲突

只有能够确认尚未提交的路径冲突才转换为 `DUPLICATE_CONFIRMATION_REQUIRED`，并保留当前文件等待客户确认。
