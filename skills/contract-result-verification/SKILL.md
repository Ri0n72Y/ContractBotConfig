---
name: contract-result-verification
description: 核验 OpenContracts MCP 读取结果和 WorkerKey 导入结果，并输出企业微信状态标记。
---

# 结果核验

内部可以保留文档标识、MCP 工具结果和导入处理状态；客户回复使用自然业务语言。

## 状态优先级

1. MCP 已找到对应文档，且没有有效重新上传确认：`[CONTRACT_UPLOAD:DUPLICATE_CONFIRMATION_REQUIRED]`
2. 导入端点在写入竞争中返回文档路径冲突：`[CONTRACT_UPLOAD:DUPLICATE_CONFIRMATION_REQUIRED]`
3. MCP corpus 或文档发现没有完成，且没有执行写入：`[CONTRACT_UPLOAD:BLOCKED]`
4. WorkerKey 配置、文件校验、确认校验或权限条件未满足：`[CONTRACT_UPLOAD:BLOCKED]`
5. 文件已接收，正文或语义检索尚未就绪：`[CONTRACT_UPLOAD:PROCESSING]`
6. 文档正文可读，并通过 `search_corpus` 检索到该文档内容：`[CONTRACT_UPLOAD:COMPLETE]`
7. 已调用正式导入能力但执行失败：`[CONTRACT_UPLOAD:FAILED]`

暂存成功、HTTP 201、文档记录创建和 `processing` 仅证明导入已被接收。首次上传应核验 `created` 或等价结果；确认后的版本写入应核验 `updated` 或等价结果。
