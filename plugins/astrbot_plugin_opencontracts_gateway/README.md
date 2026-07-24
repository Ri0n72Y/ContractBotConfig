# OpenContracts REST Gateway 0.5.1

- 认证：查重和上传均复用现有 `WorkerKey auth_token`

## 重复判断

重复身份改为 OpenContracts 的原生文档路径，而不是确定性 slug：

1. 使用原始文件名计算 OpenContracts 路径。
2. 路径存在时要求客户确认“重新上传”。
3. 确认后使用同一原始文件名上传，由 OpenContracts 返回 `updated` 并创建新版本。
4. 路径不存在时返回 `new`，再执行上传。

插件不再向导入接口提交 `slug`，避免不同版本之间的 slug 唯一约束冲突。

本地 receipts 只用于审计及恢复历史导入文件名，不用于证明远端不存在。


## Architecture UML

```mermaid
flowchart LR
    Event[Plugin Event] --> Handler[Plugin Handler]
    Handler --> Agent[Contract Agent]
    Agent --> Tool[MCP/Skill Tool Boundary]
```

## Design Constraint

本组件不得绕过 MCP 边界直接调用 OpenContracts REST 接口。
