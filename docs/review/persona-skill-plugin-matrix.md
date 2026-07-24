# Persona、Skill、Plugin 职责矩阵

本矩阵用于判断一条规则应放在哪一层，减少提示词、Skill 和插件之间的重复。

## 内容归属

| 内容类型 | Persona | Skill | Plugin | Tool Schema / MCP |
|---|---|---|---|---|
| 角色身份和业务范围 | 主责 | 参考 |  |  |
| 客户沟通风格 | 主责 |  | Result Guard 可做平台格式化 |  |
| 任务步骤和工具顺序 |  | 主责 | 提供确定性入口 | Tool 提供能力 |
| 文件暂存和清理 |  |  | 主责 |  |
| 会话状态和超时恢复 |  | 规则摘要 | 主责 |  |
| OpenContracts 读取 | 角色范围 | 调用编排 |  | MCP 主责 |
| OpenContracts 上传 | 角色范围 | 调用编排 | Gateway 主责 | Gateway Tool 契约 |
| 重复确认输入 | 客户说明 | 流程说明 | Router 主责 |  |
| 上传完成标准 | 核验原则 | 主责 | Guard 映射 | MCP 返回证据 |
| 客户最终状态文案 | 沟通原则 | 状态含义 | Result Guard 主责 |  |
| DOCX 生成依据 | 角色范围 | 主责 | 生成工具适配 | Docassemble Tool |

## Persona

### `contract_master_orchestrator`

保留：

- 唯一面向客户的合同法务助手身份；
- 合同接收、问答、分析、生成和专业助手协调范围；
- 简洁、自然、业务化的客户表达；
- 只陈述已核验结果；
- 文书生成需要已有合同、批准模板或用户输入。

流程步骤、具体 Tool 名称、REST/MCP 实现和 pending 字段由 Skill、Plugin 和 Tool 契约表达。

### `contract_opencontracts_operator`

保留：

- OpenContracts 合同库操作范围；
- 读取远端状态、上传、版本化重新上传和核验职责；
- 结构化返回给主人格；
- 远端信息不足时返回未知或阻断状态。

MCP Tool 顺序和 Gateway 参数位于 `contract-opencontracts` Skill。

### `contract_docassemble_builder`

保留：

- 使用现有合同、批准模板和用户信息生成文书；
- 缺少关键来源或变量时返回清单；
- 以实际 DOCX 文件作为完成证据。

## Skills

### `contract-orchestrator`

- 接收 Router 的结构化任务；
- 选择对应专业子助手；
- 保持当前事件同步交付；
- 根据子助手状态生成主人格最终状态标记。

### `contract-opencontracts`

目标顺序：

```text
1. 检查 Gateway 写入配置和 MCP Tools 可用性
2. 使用 MCP 解析目标 Corpus 与远端合同身份
3. existing + 无确认 -> duplicate confirmation required
4. new 或已有确认 -> Gateway 上传
5. 使用 MCP 核验处理状态、正文和检索结果
6. 返回稳定业务状态
```

### `contract-result-verification`

只定义：

- 五类上传状态；
- 每类状态需要的证据；
- `complete` 的正文和检索核验条件；
- `processing` 与 `complete` 的区别。

### `contract-conversation-control`

描述用户可见流程规则，Router 实现具体状态转换。

### `contract-direct-analysis`

描述当前暂存合同的字段提取、风险审查、引用位置和不确定性输出。

### `contract-docassemble`

描述来源选择、变量收集、生成、DOCX 验证和交付。

## Plugins

### Contract File Router

确定性地处理：

- 文件接收和暂存；
- 菜单和指令分类；
- pending 状态转换；
- 取消、结束和重复确认；
- 任务上下文和当前事件请求；
- 暂存文件生命周期。

### Contract Handoff Policy

确定性地处理：

- 目标子助手解析；
- 分支任务提取；
- 委派参数标准化；
- 当前事件同步模式；
- 单事件调用计数。

### OpenContracts Gateway

确定性地处理：

- WorkerKey 写入配置；
- 本地暂存文件安全校验；
- 官方导入接口；
- Router 重复确认绑定；
- 上传回执。

### WeCom Final Result Guard

确定性地处理：

- 状态标记到客户文案的映射；
- 单条 Plain 输出；
- UTF-8 字节限制；
- 重复确认 pending 保留；
- 迟到结果抑制。

## MCP 与外部工具

### OpenContracts MCP

提供：

- Corpus 发现；
- 文档列表和身份信息；
- 文档正文；
- 语义搜索；
- 处理状态和检索可用性证据。

### OpenContracts Import Gateway Tool

提供：

- 写入配置状态；
- 新合同上传；
- 确认后的版本化重新上传；
- 标准化写入结果。

### Docassemble Tool

提供：

- 文书生成；
- DOCX 文件输出；
- 生成错误和变量缺失结果。

## 变更判断

- 角色或沟通范围变化：更新 Persona 版本。
- 操作流程或核验规则变化：更新 Skill 版本。
- 确定性行为、Tool 参数或返回值变化：更新 Plugin 版本。
- 纯 README、UML、审计或发布文档变化：维持组件版本。
