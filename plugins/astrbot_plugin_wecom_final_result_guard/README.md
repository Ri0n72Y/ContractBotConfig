# 企业微信最终结果保护 0.2.3

本次只修正 OpenContracts REST 阻断信息：

- 不再提示检查 `read_bearer_token` 或“读取凭证”。
- 将 `lookup_path`、`rest_endpoint_missing`、路径查询失败识别为阻断状态。
- 将 OpenContracts 路径唯一约束冲突识别为重复确认状态。
- 客户端默认提示改为检查 REST 路径查询端点和容器服务。


## Architecture UML

```mermaid
flowchart LR
    Event[Plugin Event] --> Handler[Plugin Handler]
    Handler --> Agent[Contract Agent]
    Agent --> Tool[MCP/Skill Tool Boundary]
```

## Design Constraint

本组件不得绕过 MCP 边界直接调用 OpenContracts REST 接口。
