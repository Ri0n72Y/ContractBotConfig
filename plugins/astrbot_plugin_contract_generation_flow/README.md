# Contract Generation Flow

合同文书生成的会话控制插件。它不生成 DOCX，也不访问 Docassemble API；它负责生成流程的用户体验、确认状态和运行期护栏。

## 目标流程

```text
用户提出生成请求
→ 立即回复“已收到”
→ Master 整理已知信息 / 缺失信息
→ 向用户发送确认清单
→ 等待“确认生成”或修改
→ 用户确认
→ 提示“开始读取合同库并生成”
→ Builder 实时读取 OpenContracts 参考合同
→ 提示“正在通过 Docassemble 生成 DOCX”
→ Docassemble Gateway 生成
→ 提示“正在准备下载链接”
→ Contract Download Delivery 发布 HTTPS 链接
→ Master 最终交付
```

## 确认门

首次 `transfer_to_docassemble_builder` 会被改写为 `must_not_execute=true`。对应 Builder 请求的 ToolSet 会被运行时直接清空，因此即使模型忽略提示，也不能在用户确认前调用 OpenContracts、Docassemble 或下载交付工具。

插件短时保存主人格提交的生成方案，并直接向企业微信发送 `confirmation_message`。待确认状态默认保留 30 分钟。用户回复 `确认生成`、`确认`、`开始生成` 等确认语后，下一次委派才会真正执行；用户补充或修改信息时会重新形成确认方案。用户回复取消类指令时，插件清除待确认状态并直接回复取消结果。

## Builder 工具护栏

正式生成时 Builder 必须同时具备：

```text
list_documents
get_document_text
search_corpus
docassemble_gateway_status
docassemble_generate_document
contract_download_delivery_status
publish_contract_download
```

缺少任一工具时插件会移除 Builder 的全部可调用工具，并要求返回：

```text
[CONTRACT_DOCASSEMBLE:BLOCKED]
reason=builder_tool_binding_incomplete
```

因此不会出现“只有 Docassemble 生成工具、没有合同库读取或下载发布工具，却仍然生成成功”的情况。

## 参考合同读取顺序

用户确认后，插件记录本轮是否实际调用过：

```text
list_documents
get_document_text
```

只有两者均已进入本轮工具调用链后，才发送 Docassemble 生成阶段提示。Docassemble Gateway 0.1.2 会再次检查这两个运行期标记；未经过该读取顺序的正式生成会返回 `status=blocked`，不会启动 Docassemble session。

该护栏保证“先读取参考合同、后生成”的调用顺序；参考正文是否足够支持具体条款，仍由 Builder Skill 根据工具返回结果判断。

## Docassemble smoke interview

正式客户合同不得使用文件名包含 `smoke` 的 interview。除运行期指令外，Docassemble Gateway 0.1.2 会在正式确认后的生成调用中确定性拒绝 smoke interview，包括 default interview 仍指向 smoke 的情况。

Smoke interview 仅用于基础 API 链路验证，不能作为生产合同模板。

## 配置

所有字段都有默认值。常用配置：

```text
generation_ack_enabled = true
confirmation_ttl_seconds = 1800
```

即时回执、确认兜底、取消回复和阶段提示文字均可在 AstrBot WebUI 中调整。

## 数据

待确认方案保存在：

```text
data/plugins_data/astrbot_plugin_contract_generation_flow/pending_generation.json
```

仅用于跨消息确认恢复，超过 TTL 后在后续消息进入或插件初始化时清理。日志不会记录方案正文。
