---
name: contract-docassemble
description: >
  合同文书生成前置核验、合同库实时来源读取、Docassemble interview 选择、变量收集、DOCX 生成验证和临时 HTTPS 下载交付规则。
---

# 合同文书生成

## 执行原则

Docassemble 是合同文书生成的唯一执行引擎。不得使用 Shell、Python、通用 HTTP、本地脚本、`python-docx`、临时文件编辑或其他方式替代 Docassemble 生成 DOCX。

Builder 正式生成必须同时具备以下 7 个工具：

```text
list_documents
get_document_text
search_corpus
docassemble_gateway_status
docassemble_generate_document
contract_download_delivery_status
publish_contract_download
```

如果运行期提示 `builder_tool_binding_incomplete` 或任一上述工具缺失，立即返回 `[CONTRACT_DOCASSEMBLE:BLOCKED]` 和 `missing_tools`，不得开始生成。

## 生成确认门

如果输入包含：

```text
must_not_execute=true
error=generation_confirmation_required
```

说明当前只是主人格的生成前确认阶段。不得调用任何工具；立即返回：

```text
[CONTRACT_DOCASSEMBLE:BLOCKED]
reason=generation_confirmation_required
confirmation_prompt_sent=true
```

只有 Contract Generation Flow 已确认用户明确同意生成后，才进入下面的正式流程。

## 前置来源核验

正式生成合同或合同条款前，必须在**本轮**实时读取合同库中的相关合同或经批准模板，不能使用主人格转述、历史会话正文或模型记忆替代。

执行顺序：

1. `list_documents` 在目标 Corpus 中发现候选参考合同；
2. 对选中的真实 `document_slug` 从 `char_offset=0` 调用 `get_document_text`；
3. 返回 `next_offset` 时继续读取，直到 `next_offset=null`；
4. `search_corpus` 可用于补充定位相似条款，但不能替代正文读取；
5. 只有本轮取得的正文才能作为生成来源。

没有相关合同/模板、正文尚未产出、正文读取失败或 Builder 没有 OpenContracts 只读工具时停止生成，返回 `[CONTRACT_DOCASSEMBLE:BLOCKED]`，不得用主人格提供的摘要冒充已核验来源。

## Interview 与交付配置核验

1. 调用 `docassemble_gateway_status(refresh_interviews=true)` 获取 Gateway 配置和允许的 interview。
2. 调用 `contract_download_delivery_status`，确认 `configured=true`。
3. 只能选择 `allowed_interviews` 中且实际可用的 interview；不得自行猜测 interview filename。
4. **正式客户合同不得使用文件名包含 `smoke` 的 interview。** `contractbot_api_smoke.yml` 只用于 API 链路测试；如果 allowlist 中只有 smoke interview，返回 `[CONTRACT_DOCASSEMBLE:BLOCKED]`，要求管理员配置正式生成 interview。
5. 没有匹配的正式 allowlist interview 或临时下载配置不可用时停止生成，不得降级到 Python/Shell。
6. API Key 由 Gateway 持有，不得要求、读取、输出或记录 API Key。

## 信息核验

以用户已经确认的生成方案、本轮读取的参考合同和正式 interview 所需变量为准。

用户已经明确确认“未补项按占位符保留”时，可以按确认方案保留占位符；不得把模型自行推测的内容当作用户确认值。若发现会改变双方角色、金额、付款责任、工期、验收、违约或争议解决等核心结构的新缺口，而确认方案中未覆盖，应返回 `[CONTRACT_DOCASSEMBLE:BLOCKED]`，由主人格再次向用户确认。

调用 `docassemble_generate_document` 时一次性提供完整变量对象。Gateway 使用一次性 session，不由 LLM 模拟 Docassemble 网页逐题回答。

如果 Gateway 返回：

```text
status=blocked
failure_stage=missing_variable
```

将 `missing_variables` 原样返回主助手，不要通过多轮猜字段的方式不断试错。

## Interview 最终返回契约

ContractBot 使用的 Docassemble interview 必须在完成时通过 `json_response()` 返回：

```json
{
  "contractbot_document": {
    "status": "complete",
    "file_number": 123,
    "filename": "contract.docx",
    "extension": "docx"
  }
}
```

`file_number` 必须来自 Docassemble 生成的 `DAFile.number`。Gateway 随后通过官方 `/api/file/<file_number>?extension=docx` 取回 DOCX。

## 临时下载发布

只有 `docassemble_generate_document` 返回 `status=ready` 后才能调用 `publish_contract_download`。

参数必须来自同一次 Gateway 成功结果：

```text
source_path = output_path
filename = output_filename
```

不得改用模型猜测的本地路径、历史轮次路径、上传暂存路径或任意系统文件。Delivery Plugin 会再次验证来源目录白名单、DOCX 结构、文件大小和复制 SHA-256。

发布成功必须返回：

```text
status=ready
download_url=https://download.ri0n72y.top/contracts/<token>/<filename>
expires_at=<ISO-8601>
```

链接 token 由插件生成，不由模型生成、改写或复用。

## 结果状态

只有 Docassemble Gateway 已取得真实 DOCX 且 Delivery Plugin 已返回有效 HTTPS `download_url` 时，首行返回：

```text
[CONTRACT_DOCASSEMBLE:READY]
```

向主助手返回：

- `download_url`
- `filename`
- `size_bytes`
- `expires_at`
- `interview`

不要向主助手或客户返回本地 `output_path`。

需要补充变量、Builder 工具绑定不完整、未配置正式 allowlist、只有 smoke interview、interview 不存在、合同库来源不可读或生成/交付配置不满足时，首行返回：

```text
[CONTRACT_DOCASSEMBLE:BLOCKED]
```

Docassemble API 正式调用失败、DOCX 下载/校验失败或临时下载发布失败时，首行返回：

```text
[CONTRACT_DOCASSEMBLE:FAILED]
```

禁止在 `BLOCKED` 或 `FAILED` 后调用 Shell、Python、本地文件工具或通用 HTTP 进行补救。

## 文件交付

默认输出 DOCX。企业微信不直接发送生成文件；成功交付形式是 Delivery Plugin 返回的临时 HTTPS 下载链接。

PDF、纯文本或聊天中的 Markdown 不能替代默认 DOCX 文件。客户明确要求其他格式时，可在后续独立流程中处理；本 Skill 当前只认定真实 DOCX + 有效临时下载链接为成功结果。
