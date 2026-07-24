# Phase 1 代码审计

审计基线：`main` 分支初始提交。Phase 1 不修改插件运行时代码，也不调整组件版本。

## 摘要

| 组件 | 主文件规模 | 当前职责密度 | Phase 2 优先级 |
|---|---:|---|---|
| Contract File Router | 1038 行 | 很高 | P0 |
| OpenContracts Gateway | 982 行 | 很高 | P0 |
| WeCom Final Result Guard | 331 行 | 中高 | P1 |
| Contract Handoff Policy | 258 行 | 中 | P2 |

两个 P0 文件同时承担领域规则、存储、网络或平台适配、状态机和 AstrBot 生命周期，已经超过适合单文件维护的范围。

## 1. Contract File Router

文件：`plugins/astrbot_plugin_contract_file_router/main.py`

### 当前职责

- 用户菜单、提示文本和别名分类；
- 文件组件解析和本地暂存；
- 文件名清理、大小限制和 SHA-256；
- 平台重复回调抑制；
- pending JSON 读写；
- cancelled task JSON 读写；
- 暂存文件和过期状态清理；
- 合同会话状态机；
- Conversation 创建；
- `contract_task_context` 构建；
- 显式 LLM 请求；
- `on_llm_request` 上下文注入；
- `after_message_sent` pending 清理。

### 主要问题

1. `intake()` 同时处理文件事件、文本指令、偏离流程、运行锁恢复、状态转换和 LLM 调度。
2. 文件系统存储格式直接暴露给事件处理器。
3. 会话状态以自由字典表达，字段约束依赖调用顺序。
4. 提示文本、业务动作和状态机规则位于同一模块。
5. `_build_task_context()` 包含 OpenContracts 工具与实现细节，使 Router 与下游能力演进耦合。
6. `attach_context()` 和显式请求路径存在两套上下文注入方式，需要在拆分后统一。

### Phase 2 拆分建议

- `domain/task_state.py`：状态枚举、状态转换和任务记录模型；
- `domain/actions.py`：上传、分析和问答动作；
- `services/staging_service.py`：文件暂存和清理；
- `services/session_service.py`：会话状态和超时恢复；
- `services/task_context_factory.py`：下游无关的任务上下文；
- `storage/json_state_store.py`：原子 JSON 持久化；
- `handlers/file_event_handler.py` 与 `text_event_handler.py`：事件入口；
- `main.py`：AstrBot 过滤器和服务协调。

## 2. OpenContracts Gateway

文件：`plugins/astrbot_plugin_opencontracts_gateway/main.py`

### 当前职责

- 插件配置读取和校验；
- WorkerKey/Bearer Authorization 生成；
- REST 路径查询客户端；
- 官方导入接口客户端；
- 暂存文件安全校验；
- SHA-256 计算；
- 文件名和 metadata 标准化；
- receipt JSON 读写、合并和查询；
- Router 重复确认状态校验；
- 远端重复判断；
- 路径冲突识别；
- 上传与版本化重新上传；
- 三个 LLM Tool 的返回结构组装。

### 主要问题

1. 读取和写入路径位于同一类，当前读取依赖不存在的 `/api/imports/documents/lookup/`。
2. `auth_mode` 同时支持 WorkerKey 和 Bearer，而目标 Gateway 写入模型只需要 WorkerKey。
3. receipt 同时承担审计线索、文件名恢复和远端重复判断辅助，职责边界模糊。
4. `opencontracts_upload_document()` 包含配置、校验、重复读取、确认、HTTP、冲突分类、receipt 和响应构建完整流程。
5. Tool 返回结构由大量字典直接拼装，缺少领域结果类型。
6. HTTP 错误文本和数据库约束名称进入上层状态分类。

### Phase 2 首要迁移

1. OpenContracts Operator 使用 MCP 完成远端文档识别。
2. Gateway 保留 WorkerKey 导入写入、文件校验、确认绑定和 receipt。
3. `opencontracts_check_duplicate` 在 MCP 读取稳定后移除或改为纯规则工具。
4. `opencontracts_gateway_status` 返回写入配置和 MCP 工具可用性契约，不再返回读取 Bearer 或 lookup path 状态。

### Phase 2 拆分建议

- `config/settings.py`；
- `domain/upload_command.py`；
- `domain/upload_result.py`；
- `clients/import_client.py`；
- `services/file_validation_service.py`；
- `services/upload_service.py`；
- `services/confirmation_service.py`；
- `storage/receipt_store.py`；
- `main.py` 只负责 Tool 注册和 DTO 转换。

## 3. WeCom Final Result Guard

文件：`plugins/astrbot_plugin_wecom_final_result_guard/main.py`

### 当前职责

- 上传状态标记识别；
- REST 路径错误和数据库冲突文本兼容；
- 客户文案映射；
- cancelled task JSON 消费；
- UTF-8 字节截断；
- 消息链合并；
- 重复确认 pending 保留标记。

### 主要问题

1. `_classify_upload_result()` 同时识别正式标记、JSON 字段、REST 实现词和自然语言。
2. 客户文案、状态分类和持久化位于同一类。
3. 上游 Tool 契约变化会迫使 Guard 增加新的文本信号。

### Phase 2 拆分建议

- `classification/upload_status_classifier.py`；
- `mapping/customer_message_mapper.py`；
- `storage/cancelled_task_store.py`；
- `text/utf8_truncator.py`。

状态分类以正式标记为主，兼容文本作为迁移层并设置清理期限。

## 4. Contract Handoff Policy

文件：`plugins/astrbot_plugin_contract_handoff_policy/main.py`

### 当前职责

- 解析 Tool 和 Tool 参数；
- 解析推荐子助手；
- 规范化委派 JSON；
- 分支任务提取；
- 每事件调用计数；
- 企业微信同步模式设置。

### 主要问题

1. `duplicate_authority=opencontracts_remote_rest` 把具体读取实现写入委派协议。
2. 错误路径通过 `must_not_execute` JSON 交给子助手，契约可进一步类型化。
3. 调用计数存储和任务规范化可以分离，但当前规模仍可接受。

### Phase 2 建议

优先将协议字段调整为中性远端来源描述，例如 `remote_document_state` 和 `read_channel=mcp`；其余拆分排在 P0/P1 组件之后。

## 5. Skills 与 Personas

### 重复内容

- Router 动态 instruction、`contract-orchestrator`、OpenContracts Persona 和 `contract-opencontracts` 都描述上传工具顺序。
- OpenContracts Persona、`contract-opencontracts` 和 `contract-result-verification` 都包含 REST 路径和错误分类。
- 主 Persona 同时承载客户表达、状态机规则、重复判断实现和生成约束。

### Phase 2 内容归属

- Persona：角色、业务范围、信息质量和沟通方式；
- Skill：调用步骤、工具契约、结果标记和业务核验；
- Plugin：确定性状态、文件、事件和平台行为；
- Tool schema：参数和返回值。

Persona、Skill 或 Tool 行为修改时分别更新对应版本。

## 6. 配置与文档

- `config/opencontracts_gateway.example.json` 当前包含 `lookup_path` 和读取超时字段，需与 Phase 2 Gateway 配置同步调整。
- Gateway metadata 当前显示“REST 网关”，应在代码迁移时同步更新名称和版本。
- Handoff README 原标题版本与 metadata 不一致，本次文档分支已修正标题但未调整运行版本。
- 根 README 原内容只描述架构补丁，本次已扩展为完整项目说明。

## 7. 测试缺口

Phase 2 应建立：

```text
tests/
├── unit/
│   ├── router/
│   ├── gateway/
│   ├── handoff/
│   └── result_guard/
├── contract/
│   ├── test_task_context_contract.py
│   └── test_tool_result_contract.py
└── integration/
    ├── test_new_upload_flow.py
    ├── test_duplicate_confirmation_flow.py
    └── test_cancelled_late_result.py
```

重点覆盖状态转换、文件清理、确认绑定、MCP 远端身份解析、WorkerKey 导入和企业微信最终消息数量。

## 8. Phase 1 结论

当前包可作为运行基线和重构输入，但尚未符合冻结后的 MCP 读取架构。Phase 2 应先处理 OpenContracts 读取迁移，再拆 Gateway 和 Router。其余组件随后围绕稳定任务契约收敛。
