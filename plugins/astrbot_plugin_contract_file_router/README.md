# 合同文件接收与路由 0.5.0

本插件是合同流程的入口适配器，负责把企业微信文件事件转换为可恢复的合同任务，并在当前消息事件中启动主人格请求。

## 职责

- 接收 AstrBot 文件组件并复制到插件暂存目录。
- 计算文件 SHA-256、大小和会话文件指纹。
- 维护等待操作、运行中、重复确认和结束后的会话状态。
- 生成 `contract_task_context`，将用户选择转换为明确的业务操作。
- 在企业微信当前事件中创建 LLM 请求。
- 在任务完成、取消或过期后清理暂存文件。
- 与最终结果保护插件共享取消任务和重复确认状态。

OpenContracts 的合同发现、正文读取和检索由 OpenContracts Operator 使用 MCP 完成；Router 提供文件、用户意图、确认状态和任务契约。

## 组件 UML

```mermaid
classDiagram
    class ContractFileRouter {
        +initialize()
        +intake(event)
        +attach_context(event, request)
        +clear_pending_after_result(event)
    }

    class MessageClassifier {
        +classify(text)
    }

    class StagingService {
        +stage_files(event)
        +calculate_sha256(path)
        +cleanup_files(record)
    }

    class SessionStateStore {
        +load()
        +save()
        +clear_session(session)
        +recover_stale_dispatch(session)
    }

    class TaskContextFactory {
        +build(action, record)
    }

    ContractFileRouter --> MessageClassifier
    ContractFileRouter --> StagingService
    ContractFileRouter --> SessionStateStore
    ContractFileRouter --> TaskContextFactory
```

当前 `main.py` 仍将这些职责放在同一个类中。Phase 2-A 由 Handoff Policy 将上传分支规范化为 MCP 读取与 WorkerKey 写入能力；Router 的模块拆分和任务上下文清理安排在 Phase 2-B。

## 会话状态 UML

```mermaid
stateDiagram-v2
    [*] --> Idle
    Idle --> AwaitingAction: 收到并暂存文件
    AwaitingAction --> TaskRunning: 选择快速分析或提问
    AwaitingAction --> UploadRunning: 选择上传
    UploadRunning --> AwaitingDuplicateConfirmation: MCP或导入竞争发现已有合同
    AwaitingDuplicateConfirmation --> ReuploadRunning: 回复重新上传
    AwaitingDuplicateConfirmation --> Idle: 回复取消或结束
    ReuploadRunning --> AwaitingDuplicateConfirmation: 再次需要确认
    UploadRunning --> Idle: 完成、处理中回复或失败
    ReuploadRunning --> Idle: 完成、处理中回复或失败
    TaskRunning --> Idle: 结果发送完成
    AwaitingAction --> Idle: 取消、结束或超时
```

## 上传协作时序

```mermaid
sequenceDiagram
    participant U as 用户
    participant R as ContractFileRouter
    participant M as Master Persona
    participant H as Handoff Policy
    participant O as OpenContracts Operator
    participant MCP as OpenContracts MCP
    participant G as Upload Gateway

    U->>R: 上传文件
    R->>R: 暂存、校验、创建 pending
    R-->>U: 显示操作菜单
    U->>R: 选择上传
    R->>R: 创建 contract_task_context
    R->>M: 显式 LLM 请求
    M->>H: transfer_to_opencontracts_operator
    H->>O: 规范化后的同步任务
    O->>MCP: 获取 corpus 和远端文档摘要
    alt 新合同或已有重新上传确认
        O->>G: WorkerKey 导入写入
        G-->>O: 导入状态
        O->>MCP: 正文和检索核验
    end
    O-->>M: 业务状态
    M-->>U: 最终回复
```

## 任务上下文契约

Router 生成的 `contract_task_context` 包含：

```text
task_id
operation
source_files[]
source_files[].original_name
source_files[].staged_path
source_files[].sha256
duplicate_confirmation
recommended_subagents
branch_tasks
expected_outputs
```

上传分支声明的能力包括：

```text
get_corpus_info
list_documents
opencontracts_gateway_status
opencontracts_upload_document
get_document_text
search_corpus
```

`original_name` 是 MCP 文档搜索和导入文件名的输入；`staged_path` 由上传网关读取本地暂存文件。

## 后续拆分目标

```text
astrbot_plugin_contract_file_router/
├── main.py
├── domain/
│   ├── actions.py
│   └── task_state.py
├── handlers/
│   ├── file_event_handler.py
│   └── text_event_handler.py
├── services/
│   ├── staging_service.py
│   ├── task_context_factory.py
│   └── session_service.py
└── storage/
    ├── pending_store.py
    └── cancelled_task_store.py
```

`main.py` 最终只保留 AstrBot 生命周期、事件过滤器和服务协调。
