# 合同子代理委派策略 0.4.2

本插件把主人格发出的 `transfer_to_*` 调用规范化为专业子助手可执行的合同任务，并维持企业微信当前事件内的同步交付。

本次仅完善架构文档，插件版本保持 `0.4.2`。

## 职责

- 根据 `contract_task_context.recommended_subagents` 解析目标子助手。
- 将主人格的自然语言备注与结构化任务上下文合并。
- 为目标子助手提取对应的 `branch_task`、`operation`、`required_tools` 和 `expected_outputs`。
- 在企业微信平台和 `current_event_response` 模式下设置同步执行。
- 记录当前事件中每个子助手的调用次数，并在消息发送完成后清理计数。

本插件处理委派策略；OpenContracts 读取、上传和结果核验由 OpenContracts Operator 及其获配工具完成。

## 组件 UML

```mermaid
classDiagram
    class ContractHandoffPolicy {
        +initialize()
        +normalize_handoff(event, tool, tool_args)
        +clear_event_counts(event)
    }

    class HandoffResolver {
        +resolve_tool_args(args, kwargs)
        +expected_agents(context)
        +resolve_branch(context, agent)
    }

    class InvocationCounter {
        +increment(event_key, tool_name)
        +clear(event_key)
    }

    class CanonicalTaskBuilder {
        +build(task_context, agent, original_input)
    }

    ContractHandoffPolicy --> HandoffResolver
    ContractHandoffPolicy --> InvocationCounter
    ContractHandoffPolicy --> CanonicalTaskBuilder
```

当前实现位于单个 `main.py`。辅助类表示 Phase 2 可选拆分方向；该插件规模较小，拆分优先级低于 Router 和 OpenContracts Gateway。

## 委派时序

```mermaid
sequenceDiagram
    participant M as Master Persona
    participant T as transfer_to_* Tool
    participant P as Handoff Policy
    participant S as Specialist Persona

    M->>T: input + background_task
    T->>P: OnUsingLLMToolEvent
    P->>P: 读取 contract_task_context
    P->>P: 解析目标 agent 和 branch_task
    P->>P: 生成 canonical task JSON
    P->>T: 更新 input 与同步模式
    T->>S: 执行专业任务
    S-->>M: 返回结构化业务结果
```

## 路由映射

```mermaid
flowchart LR
    Context[contract_task_context]
    Resolver[Handoff Resolver]
    OC[opencontracts_operator]
    DA[docassemble_builder]

    Context --> Resolver
    Resolver -->|contract_system_upload / reupload| OC
    Resolver -->|document_generation| DA
```

当前映射：

```text
opencontracts_operator -> transfer_to_opencontracts_operator
docassemble_builder   -> transfer_to_docassemble_builder
```

## 规范化任务结构

专业子助手接收的 JSON 以 Router 的上下文为基础，并增加：

```text
delegated_agent
branch_task
operation
required_tools
expected_outputs
remaining_expected_subagents
main_agent_note
```

读取与上传工具的选择由目标 Persona 的 AstrBot GUI 工具分配和对应 Skill 决定。Handoff Policy 只传递任务契约，不实现 OpenContracts 或 Docassemble 业务能力。

## Phase 2 关注点

- 将 `duplicate_authority` 等实现相关字段替换为中性的远端数据来源描述。
- 让 `branch_task.required_tools` 与 OpenContracts MCP 读取工具、Gateway 上传工具的职责保持一致。
- 保持事件计数和同步交付逻辑独立于具体业务系统名称。
