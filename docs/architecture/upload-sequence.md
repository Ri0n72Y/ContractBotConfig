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
    R->>M: contract_task_context + targets.opencontracts
    M->>M: 提取 contract_date + contract_title
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
    O-->>M: 统一状态标记
    M->>RG: 最终结果
    RG-->>U: 客户回复
```

公开 MCP 地址由 AstrBot 配置为 `/mcp/`。所有读取工具使用 `targets.opencontracts` 作为 `corpus_slug`；流程不调用 `get_corpus_info`、`opencontracts_check_duplicate` 或不存在的 corpus-scoped URL。

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
    R->>M: contract_task_context + target corpus slug
    M->>M: 提取合同日期和标题
    M->>O: 规范化合同身份
    O->>MCP: list_documents(corpus_slug, search=document_title)
    MCP-->>O: 标题完全一致
    O-->>M: DUPLICATE_CONFIRMATION_REQUIRED
    M->>RG: 最终状态
    RG->>R: preserve pending reason
    RG-->>U: 询问重新上传或取消
```

## 客户确认重新上传

```mermaid
sequenceDiagram
    participant U as 用户
    participant R as Router
    participant M as Master
    participant O as OpenContracts Operator
    participant MCP as OpenContracts Public MCP
    participant G as Upload Gateway
    participant OC as OpenContracts

    U->>R: 重新上传
    R->>R: 记录 confirmation_id 和时间
    R->>M: reupload task context
    M->>M: 重新确认合同日期和标题
    M->>O: 同步重新上传任务
    O->>MCP: 按同一 corpus_slug 重新读取规范化标题对应文档
    MCP-->>O: existing document
    O->>G: date + title + confirmation_id
    G->>G: 校验会话、哈希、确认编号和有效期
    G->>OC: WorkerKey 文档导入
    OC-->>G: updated
    G-->>O: processing
    O->>MCP: 正文和检索核验
    MCP-->>O: processing 或 verified
    O-->>M: 统一状态
    M-->>U: 客户回复
```

## 公开 MCP 或工具失败

```mermaid
sequenceDiagram
    participant O as OpenContracts Operator
    participant MCP as OpenContracts Public MCP
    participant M as Master
    participant RG as Result Guard
    participant U as 用户

    O->>MCP: list_documents(corpus_slug, search)
    MCP--xO: 连接失败 / 工具缺失 / 响应不完整
    O-->>M: CONTRACT_UPLOAD:BLOCKED
    M->>RG: 立即结束，不再调用工具
    RG-->>U: 本次未上传；修复后重新上传合同
```

Master 和 Operator 不使用 Shell、Python、通用 HTTP、直接 MCP JSON-RPC、配置文件读取或 URL 探测补救失败。

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

上述路径都可能已经写入。Gateway 追加 receipt，Operator 禁止再次调用上传工具。

## 写入前路径冲突

```mermaid
sequenceDiagram
    participant O as OpenContracts Operator
    participant G as Upload Gateway
    participant OC as OpenContracts

    O->>G: 新合同上传
    G->>OC: POST /api/imports/documents/
    OC-->>G: document path conflict before commit
    G-->>O: confirmation_required
```

路径冲突只有在能够确认尚未提交时才转换为重复确认状态。
