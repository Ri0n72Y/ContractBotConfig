# 合同文件接收与路由 0.5.0

本插件是合同流程的入口适配器，负责把企业微信文件事件转换为可恢复的合同任务，并在当前消息事件中启动主人格请求。

本次仅完善架构文档，插件版本保持 `0.5.0`。

## 职责

- 接收 AstrBot 文件组件并复制到插件暂存目录。
- 计算文件 SHA-256、大小和会话文件指纹。
- 维护等待操作、运行中、重复确认和结束后的会话状态。
- 生成 `contract_task_context`，将用户选择转换为明确的业务操作。
- 在企业微信当前事件中创建 LLM 请求。
- 在任务完成、取消或过期后清理暂存文件。
- 与最终结果保护插件共享取消任务和重复确认状态。

OpenContracts 的远端读取由 OpenContracts Operator 调用 MCP Tools 完成；Router 只提供文件、用户意图和任务状态。

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

当前 `main.py` 仍将这些职责放在同一个类中。图中的辅助组件是 Phase 2 的拆分目标。

## 会话状态 UML

```mermaid
stateDiagram-v2
    [*] --> Idle
    Idle --> AwaitingAction: 收到并暂存文件
    AwaitingAction --> TaskRunning: 选择快速分析或提问
    AwaitingAction --> UploadRunning: 选择上传
    UploadRunning --> AwaitingDuplicateConfirmation: 远端返回合同已存在
    AwaitingDuplicateConfirmation --> ReuploadRunning: 回复重新上传
    AwaitingDuplicateConfirmation --> Idle: 回复取消或结束
    ReuploadRunning --> AwaitingDuplicateConfirmation: 重新上传未启动或需要再次确认
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

    U->>R: 上传文件
    R->>R: 暂存、校验、创建 pending
    R-->>U: 显示操作菜单
    U->>R: 选择上传
    R->>R: 创建 contract_task_context
    R->>M: 显式 LLM 请求
    M->>H: transfer_to_opencontracts_operator
    H->>O: 规范化后的同步任务
    O-->>M: 上传业务状态
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

OpenContracts Operator 使用这些字段调用 MCP 读取工具和上传 Gateway。`original_name` 是远端合同身份解析和上传文件名的输入，`staged_path` 只用于 Gateway 读取本地暂存文件。

## Phase 2 拆分目标

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
