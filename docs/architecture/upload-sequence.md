# 合同上传时序

## 新合同

```mermaid
sequenceDiagram
    participant U as 用户
    participant R as Router
    participant M as Master
    participant H as Handoff Policy
    participant O as OpenContracts Operator
    participant MCP as OpenContracts MCP
    participant G as Upload Gateway
    participant OC as OpenContracts
    participant RG as Result Guard

    U->>R: 上传合同
    R->>R: 暂存、SHA-256、pending
    R-->>U: 操作菜单
    U->>R: 1
    R->>M: contract_task_context
    M->>H: transfer_to_opencontracts_operator
    H->>O: 同步结构化任务
    O->>MCP: 查询目标 Corpus 与文档身份
    MCP->>OC: list/read/search
    OC-->>MCP: 无匹配文档
    MCP-->>O: new
    O->>G: upload_document
    G->>G: 文件路径、大小、SHA-256 校验
    G->>OC: WorkerKey 文档导入
    OC-->>G: created / processing
    G-->>O: 上传回执
    O->>MCP: 核验处理状态
    MCP-->>O: processing 或 verified
    O-->>M: 统一状态标记
    M->>RG: 最终结果
    RG-->>U: 客户回复
```

## 远端合同已存在

```mermaid
sequenceDiagram
    participant U as 用户
    participant R as Router
    participant M as Master
    participant O as OpenContracts Operator
    participant MCP as OpenContracts MCP
    participant RG as Result Guard

    U->>R: 选择上传
    R->>M: contract_task_context
    M->>O: 上传任务
    O->>MCP: 查询文档身份
    MCP-->>O: existing document
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
    participant MCP as OpenContracts MCP
    participant G as Upload Gateway
    participant OC as OpenContracts

    U->>R: 重新上传
    R->>R: 记录 confirmation_id 和时间
    R->>M: reupload task context
    M->>O: 同步重新上传任务
    O->>MCP: 重新读取远端文档身份
    MCP-->>O: existing document
    O->>G: upload_document + confirmation_id
    G->>G: 校验 Router 确认状态
    G->>OC: WorkerKey 文档导入
    OC-->>G: updated / processing
    G-->>O: 新版本上传回执
    O->>MCP: 核验新版本处理状态
    MCP-->>O: processing 或 verified
    O-->>M: 统一状态
    M-->>U: 客户回复
```

## 状态原则

- `created` 或 `updated` 表示导入接口已接收并建立文档记录或版本。
- `processing` 表示 OpenContracts 仍在解析、标注或建立检索数据。
- `complete` 由 MCP 正文读取和搜索核验共同确认。
- `duplicate_confirmation_required` 保留 Router pending，等待确定性指令。
- `blocked` 表示远端状态不足以安全决定是否写入。
