# 合同文件接收与路由 0.5.0

## 主要变化

- 路由器不再读取 OpenContracts receipt 判断合同是否存在；所有上传均交给网关实时查询 OpenContracts。
- “结束”成为当前合同流程中的最高优先级指令，可清理等待状态并允许立即开始新任务。
- 等待操作或等待重新上传确认时收到另一份文件，不覆盖旧任务；新文件作为误发送处理并给出明确提示。
- 等待重新上传确认时支持“重新上传”“取消”“结束”三条确定性指令。
- 运行中收到新消息会返回处理中提示；迟到的已取消任务结果通过共享登记文件交给最终结果保护插件抑制。
- 暂存文件在取消、完成或失败后主动清理，保留 TTL 作为异常兜底。

## 配套版本

- astrbot_plugin_opencontracts_gateway >= 0.3.0
- astrbot_plugin_wecom_final_result_guard >= 0.2.0
- astrbot_plugin_contract_handoff_policy >= 0.4.1


## Architecture UML

```mermaid
flowchart LR
    Event[Plugin Event] --> Handler[Plugin Handler]
    Handler --> Agent[Contract Agent]
    Agent --> Tool[MCP/Skill Tool Boundary]
```

## Design Constraint

本组件不得绕过 MCP 边界直接调用 OpenContracts REST 接口。
