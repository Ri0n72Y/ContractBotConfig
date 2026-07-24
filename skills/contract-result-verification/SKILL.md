---
name: contract-result-verification
description: 核验 OpenContracts 上传结果并输出企业微信状态标记。
---

# 结果核验

内部可以保留文档标识、远端路径查询和处理状态；客户回复不得展示任务编号、哈希、内部路径、数据库约束或子代理原始报告。

## 状态优先级

1. 文档路径已存在、`confirmation_required` 或路径唯一约束冲突：`[CONTRACT_UPLOAD:DUPLICATE_CONFIRMATION_REQUIRED]`
2. REST 路径查询失败、端点不存在、认证失败或结果不完整，且没有执行上传：`[CONTRACT_UPLOAD:BLOCKED]`
3. 文件已接收，正文、标注或检索尚未核验完成：`[CONTRACT_UPLOAD:PROCESSING]`
4. 文档正文可读并通过检索验证：`[CONTRACT_UPLOAD:COMPLETE]`
5. 已调用正式能力但失败：`[CONTRACT_UPLOAD:FAILED]`

暂存成功、HTTP 接收、文档记录创建和 `processing` 都不能单独证明文档处理完成。首次上传应核验服务端返回 `created`；确认重新上传成功时应核验服务端返回 `updated` 或等价的新版本结果。
