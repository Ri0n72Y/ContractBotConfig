# Phase 1 Architecture Documentation Patch

本补丁仅增加架构文档，不修改代码、不调整版本号。

目标：
- 明确 AstrBot Agent、Skill、Plugin、MCP、OpenContracts 的边界。
- 防止后续开发使用 REST 替代 OpenContracts MCP。
- 为后续代码拆分提供设计依据。

## 核心原则

1. OpenContracts 的读写能力通过 MCP 工具完成。
2. WorkerKey 仅用于 MCP/官方工具要求的认证配置。
3. Plugin 负责事件、状态、流程控制。
4. Skill 负责行为规范和任务编排。
5. Persona 只定义角色行为，不定义工具实现。

详见 docs/uml。
