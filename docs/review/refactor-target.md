# Phase 2 重构目标与进度

## 顺序

```mermaid
flowchart LR
    A[Phase 2-A MCP读取与Gateway拆分]
    B[Phase 2-B Router状态机拆分]
    C[Phase 2-C Result Guard拆分]
    D[Phase 2-D Handoff纯函数提取]
    E[集成测试与发布]

    A --> B --> C --> D --> E
```

## Phase 2-A：已完成

### OpenContracts 读取

OpenContracts Operator 使用 corpus-scoped MCP：

```text
get_corpus_info
list_documents
get_document_text
search_corpus
```

### OpenContracts 写入

Upload Gateway 使用 WorkerKey 和官方 `/api/imports/documents/` 端点。

### Gateway 目录

```text
plugins/astrbot_plugin_opencontracts_gateway/
├── main.py
├── config/
│   ├── __init__.py
│   └── settings.py
├── domain/
│   ├── __init__.py
│   ├── models.py
│   └── results.py
├── clients/
│   ├── __init__.py
│   └── import_client.py
├── services/
│   ├── __init__.py
│   ├── confirmation_service.py
│   ├── file_service.py
│   ├── import_result_service.py
│   └── upload_service.py
├── storage/
│   ├── __init__.py
│   └── receipt_store.py
├── tests/
│   ├── __init__.py
│   └── test_services.py
├── _conf_schema.json
├── metadata.yaml
└── README.md
```

### 依赖方向

```mermaid
flowchart TD
    Main[main.py Tool Adapter]
    UploadService[UploadService]
    Validator[FileService]
    Confirmation[ConfirmationService]
    ImportClient[ImportClient]
    ResultService[ImportResultService]
    ReceiptStore[ReceiptStore]

    Main --> UploadService
    UploadService --> Validator
    UploadService --> Confirmation
    UploadService --> ImportClient
    UploadService --> ResultService
    ResultService --> ReceiptStore
```

## Phase 2-B：Contract File Router

### 目标目录

```text
plugins/astrbot_plugin_contract_file_router/
├── main.py
├── domain/
│   ├── actions.py
│   ├── pending_contract.py
│   └── task_state.py
├── handlers/
│   ├── file_event_handler.py
│   └── text_event_handler.py
├── services/
│   ├── conversation_service.py
│   ├── session_service.py
│   ├── staging_service.py
│   └── task_context_factory.py
├── storage/
│   ├── cancelled_task_store.py
│   └── pending_store.py
└── ui/
    └── prompts.py
```

### 状态模型

```mermaid
classDiagram
    class PendingContract {
        +session_id: str
        +state: TaskState
        +files: list~SourceFile~
        +created_at: float
        +updated_at: float
        +dispatch: DispatchInfo?
        +confirmation: DuplicateConfirmation?
    }

    class SourceFile {
        +original_name: str
        +staged_path: str
        +sha256: str
        +size_bytes: int
    }

    class DispatchInfo {
        +task_id: str
        +operation: str
        +started_at: float
    }

    class DuplicateConfirmation {
        +confirmation_id: str
        +confirmed_at: float?
    }

    PendingContract --> SourceFile
    PendingContract --> DispatchInfo
    PendingContract --> DuplicateConfirmation
```

JSON Store 负责 DTO 与持久化字典之间的转换；事件处理器通过服务修改状态。

## Phase 2-C：WeCom Final Result Guard

```text
plugins/astrbot_plugin_wecom_final_result_guard/
├── main.py
├── classification/
│   └── upload_status_classifier.py
├── mapping/
│   └── customer_message_mapper.py
├── storage/
│   └── cancelled_task_store.py
└── text/
    └── utf8_truncator.py
```

正式状态标记是分类器的主要输入。兼容旧文本的规则单独维护，并为每条规则记录移除条件。

## Phase 2-D：Handoff Policy

该插件保持小型，计划提取：

```text
routing.py
canonical_task.py
```

规范化上下文使用：

```text
document_read_channel = opencontracts_mcp
document_write_channel = worker_key_document_import
receipt_role = upload_audit
```

## 完成标准

- OpenContracts 读取日志来自 MCP Tool 调用；
- Gateway 状态只报告 WorkerKey 写入配置；
- Gateway 运行模块均低于 200 行；
- Router 与 Result Guard 的事件适配层和业务服务分离；
- 状态转换具备单元测试；
- 插件 README UML 与代码模块一致；
- 发布脚本输出可安装 ZIP 和 SHA-256 清单。
