# 合同子代理委派策略 0.4.1

允许的专业子代理：

- `opencontracts_operator`
- `docassemble_builder`

合同上传只委派给 `opencontracts_operator`。企业微信客服任务强制在当前事件同步执行。规范化后的委派上下文明确：OpenContracts 远端查询是重复判断权威，本地 receipt 不具备否定权威。


## Architecture UML

```mermaid
flowchart LR
    Event[Plugin Event] --> Handler[Plugin Handler]
    Handler --> Agent[Contract Agent]
    Agent --> Tool[MCP/Skill Tool Boundary]
```

## Design Constraint

本组件不得绕过 MCP 边界直接调用 OpenContracts REST 接口。
