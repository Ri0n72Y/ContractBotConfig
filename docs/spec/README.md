# WorkBuddy 重构 Specs

本目录是 `workbuddy-refactor` 的实现规范。`docs/architecture/` 解释系统为什么这样分层；这里定义实现必须满足什么条件。

## Specs

```text
system.md             总体功能、边界与验收
opencontracts.md      公网 MCP、认证、权限、文件导入与 patch
skill-pack.md         专有合同 Skill 包结构与行为
workbuddy-host.md     WorkBuddy 办公/微信宿主规范
migration.md          AstrBot 资产迁移与删除门槛
```

## 规范优先级

发生冲突时：

```text
用户当前明确要求
> 本目录 spec
> docs/architecture
> 旧 AstrBot README/Persona/Plugin 文档
```

旧 AstrBot 文档只代表 `astrbot-solution` 历史方案，不得作为新代码的运行时事实来源。

## 设计基线

- OpenContracts 是合同事实与权限来源；
- WorkBuddy/Harness 是 Agent runtime；
- Skill Pack 是合同领域行为与客户端脚本；
- 本地文件默认不自动归档；
- 企业私有 MCP 必须认证；
- 大文件上传走 OpenContracts HTTPS 文件入口；
- 客户模型承担分析/修改/起草 token；
- 不新增独立 ContractBot Agent Gateway。

## Definition of Done

本轮“架构/spec 重建”完成不代表代码迁移完成。代码重构必须逐项满足各 spec 的 acceptance criteria 后，才能删除对应 AstrBot 组件。
