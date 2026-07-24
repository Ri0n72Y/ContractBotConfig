# Upload Flow UML

```mermaid
sequenceDiagram
    participant U as User
    participant R as File Router
    participant A as Master Persona
    participant H as Handoff Policy
    participant O as OpenContracts Operator
    participant M as OpenContracts MCP
    participant G as Upload Gateway
    participant C as OpenContracts

    U->>R: 上传合同
    R->>R: 暂存文件并创建 pending
    R-->>U: 已收到合同，请选择操作
    U->>R: 选择上传
    R->>A: contract_task_context
    A->>H: transfer_to_opencontracts_operator
    H->>O: 同步结构化任务
    O->>M: 查询远端合同身份
    M->>C: MCP list/read/search
    C-->>M: 文档结果
    M-->>O: new / existing / unknown

    alt new
        O->>G: 上传暂存文件
        G->>C: WorkerKey + 官方导入接口
        C-->>G: created / processing
        G-->>O: 上传回执
    else existing with confirmation
        O->>G: 版本化重新上传
        G->>C: WorkerKey + 官方导入接口
        C-->>G: updated / processing
        G-->>O: 上传回执
    else existing without confirmation
        O-->>A: duplicate confirmation required
    end

    opt 上传已接收
        O->>M: 查询处理状态、正文和检索结果
        M->>C: MCP read/search
        C-->>M: processing / verified
        M-->>O: 核验结果
    end

    O-->>A: 统一业务状态
    A-->>U: 客户提示
```

## 关键数据

```text
Router -> Operator:
  original_name
  staged_path
  sha256
  duplicate_confirmation

Operator -> MCP:
  corpus identity
  document identity query
  document text/search query

Operator -> Gateway:
  staged_path
  expected_sha256
  source_filename
  duplicate_confirmation_id
```
