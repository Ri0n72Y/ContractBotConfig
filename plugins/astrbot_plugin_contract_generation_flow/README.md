# Contract Generation Flow

合同文书生成的会话控制插件。它不生成 DOCX，也不访问 Docassemble API；它只负责生成流程的用户体验和运行期护栏。

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

首次 `transfer_to_docassemble_builder` 会被拦截为 `must_not_execute=true`，不会实际生成。插件短时保存主人格提交的生成方案，并直接向企业微信发送 `confirmation_message`。

待确认状态默认保留 30 分钟。用户回复 `确认生成`、`确认`、`开始生成` 等确认语后，下一次委派才会真正执行。用户在确认前补充或修改信息时，主人格应提交更新后的方案，插件会重新发送确认。

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

## Docassemble smoke interview

运行期指令明确禁止普通客户合同使用文件名包含 `smoke` 的 interview。Smoke interview 仅用于基础 API 链路验证，不能作为生产合同模板。

## 配置

所有字段都有默认值。常用配置：

```text
generation_ack_enabled = true
confirmation_ttl_seconds = 1800
```

阶段提示文字可在 AstrBot WebUI 中调整。

## 数据

待确认方案保存在：

```text
data/plugins_data/astrbot_plugin_contract_generation_flow/pending_generation.json
```

仅用于跨消息确认恢复，超过 TTL 后在后续消息进入时清理。日志不会记录方案正文。
