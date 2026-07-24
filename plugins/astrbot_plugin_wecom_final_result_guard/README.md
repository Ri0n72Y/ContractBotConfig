# 企业微信最终结果保护 0.3.0

本插件位于 AstrBot 结果装饰阶段，将合同内部状态转换为一条适合企业微信客服发送的客户回复。

## 职责

- 读取最终 `MessageEventResult` 并收集 Plain 与非文本组件。
- 识别合同上传状态标记。
- 将内部状态转换为稳定的客户语言。
- 在重复确认场景设置 `contract_preserve_pending_reason`。
- 抑制客户已结束任务产生的迟到结果。
- 以 UTF-8 字节数控制企业微信文本长度。
- 保留有限数量的文件或图片组件。

## 组件 UML

```mermaid
classDiagram
    class WecomFinalResultGuard {
        +initialize()
        +normalize_result(event)
    }

    class UploadStatusClassifier {
        +classify(text) UploadStatus
    }

    class CustomerMessageMapper {
        +map(status) string
    }

    class CancelledTaskStore {
        +consume(task_id) bool
    }

    class Utf8Truncator {
        +truncate(text, max_bytes)
    }

    WecomFinalResultGuard --> UploadStatusClassifier
    WecomFinalResultGuard --> CustomerMessageMapper
    WecomFinalResultGuard --> CancelledTaskStore
    WecomFinalResultGuard --> Utf8Truncator
```

当前实现仍集中在 `main.py`。图中的辅助组件是后续 Phase 2 拆分目标。

## 结果处理时序

```mermaid
sequenceDiagram
    participant A as Master Persona
    participant E as AstrBot Result Event
    participant G as WeCom Final Result Guard
    participant R as Contract File Router
    participant W as WeCom Adapter

    A->>E: 最终文本 + 状态标记
    E->>G: on_decorating_result
    G->>G: 检查 cancelled task
    G->>G: 分类上传状态
    G->>G: 映射客户回复
    alt 重复确认
        G->>R: event extra 标记保留 pending
    end
    G->>G: UTF-8 截断并合并消息链
    G->>W: 单条客户结果
```

## 状态映射

```mermaid
flowchart TD
    Marker[内部状态标记]
    Complete[COMPLETE]
    Processing[PROCESSING]
    Duplicate[DUPLICATE_CONFIRMATION_REQUIRED]
    Blocked[BLOCKED]
    Failed[FAILED]
    Customer[客户回复]

    Marker --> Complete --> Customer
    Marker --> Processing --> Customer
    Marker --> Duplicate --> Customer
    Marker --> Blocked --> Customer
    Marker --> Failed --> Customer
```

上游稳定标记：

```text
[CONTRACT_UPLOAD:COMPLETE]
[CONTRACT_UPLOAD:PROCESSING]
[CONTRACT_UPLOAD:DUPLICATE_CONFIRMATION_REQUIRED]
[CONTRACT_UPLOAD:BLOCKED]
[CONTRACT_UPLOAD:FAILED]
```

0.3.0 的兼容分类已改为识别 MCP 读取不完整、WorkerKey 导入配置、导入端点和版本写入冲突。客户阻断提示指向 OpenContracts MCP 连接和文档导入服务。

## 与 Router 的共享状态

```mermaid
flowchart LR
    Router[Contract File Router]
    Registry[cancelled_contract_tasks.json]
    EventExtra[contract_preserve_pending_reason]
    Guard[Final Result Guard]

    Router --> Registry
    Registry --> Guard
    Guard --> EventExtra
    EventExtra --> Router
```

## 后续拆分目标

```text
astrbot_plugin_wecom_final_result_guard/
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
