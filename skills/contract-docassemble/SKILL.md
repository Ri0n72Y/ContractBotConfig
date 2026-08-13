---
name: contract-docassemble
description: >
  合同库实时来源读取、Docassemble DOCX 生成和临时 HTTPS 下载交付规则。
---

# 合同文书生成

## 执行原则

Docassemble 是最终 DOCX 的唯一生成引擎。不得使用 Shell、Python、通用 HTTP、本地脚本、`python-docx`、临时文件编辑或其他方式替代 Gateway/Delivery。

Builder 正常绑定 5 个工具：

```text
list_documents
get_document_text
search_corpus
docassemble_generate_document
publish_contract_download
```

其中 `search_corpus` 是可选检索辅助；正式生成真正必需的是 `list_documents`、`get_document_text`、`docassemble_generate_document` 和 `publish_contract_download`。`docassemble_gateway_status` 与 `contract_download_delivery_status` 仅用于管理员排障，不是每次生成的前置步骤。

## 生成确认门

如果输入包含：

```text
must_not_execute=true
error=generation_confirmation_required
```

当前只是生成前确认阶段。不得调用任何工具；立即返回：

```text
[CONTRACT_DOCASSEMBLE:BLOCKED]
reason=generation_confirmation_required
confirmation_prompt_sent=true
```

只有 Contract Generation Flow 已记录用户确认后才进入正式生成。

## 本轮参考来源

正式生成前必须在本轮实时读取 OpenContracts，不能使用主人格转述、历史会话正文或模型记忆替代。

1. `list_documents` 在目标 Corpus 中取得候选参考合同；
2. 对选中的真实 `document_slug` 从 `char_offset=0` 调用 `get_document_text`；
3. 返回 `next_offset` 时继续读取直到 `next_offset=null`；
4. `search_corpus` 可用于辅助定位相似条款，但不能替代正文读取；
5. 没有相关合同、正文为空/未产出或读取失败时返回 `[CONTRACT_DOCASSEMBLE:BLOCKED]`。

Docassemble Gateway 是唯一运行时来源核验者，会按本轮 `corpus_slug + document_slug` 判断参考正文是否满足生成条件；Builder 不需要再做第二套状态核验。

## Interview

正常生成不要做每次请求的 status preflight。

- 默认把 `interview` 留空，让 Gateway 使用管理员已经配置的 `default_interview`；
- 只有任务上下文明确提供经批准的完整 interview filename 时才显式传入；
- Gateway 自己负责配置、allowlist、正式 interview 和 smoke interview 边界校验；
- Gateway 返回配置/allowlist/`smoke_interview_forbidden` 等 BLOCKED 时原样停止，不猜测其他 interview，不降级到其他生成路径；
- API Key 只由 Gateway 持有，不得请求、读取、输出或记录。

## 信息与生成

以用户已确认的生成方案和本轮参考合同为准。用户明确允许未补项保留占位符时可以保留；不得自行推测会改变双方角色、金额、付款责任、工期、验收、违约或争议解决的核心事实。

调用 `docassemble_generate_document` 时一次性提供完整 `variables`。如果 Gateway 返回：

```text
status=blocked
failure_stage=missing_variable
```

将 `missing_variables` 原样返回主助手，不通过多轮试错猜字段。

成功结果必须包含：

```text
success=true
status=ready
output_path=<Gateway DOCX>
output_filename=<客户文件名>
```

## 临时下载交付

只有 Gateway `status=ready` 后才调用：

```text
publish_contract_download
source_path = output_path
filename = output_filename
```

参数必须来自同一次 Gateway 结果。不得改用历史路径、上传暂存路径或模型猜测路径。Delivery 会执行来源 allowlist、DOCX 结构、大小和复制 SHA-256 校验。

发布成功必须返回：

```text
status=ready
download_url=https://download.ri0n72y.top/contracts/<token>/<filename>
expires_at=<ISO-8601>
```

链接 token 只由插件生成。

## 结果状态

只有 Gateway 已取得真实 DOCX 且 Delivery 已返回有效 HTTPS `download_url` 时，首行返回：

```text
[CONTRACT_DOCASSEMBLE:READY]
```

向主助手返回 `download_url`、`filename`、`size_bytes`、`expires_at`、`interview`，不要返回本地 `output_path`。

需要补充变量、合同库来源不可读、Gateway/Delivery 配置或 allowlist 不满足时返回：

```text
[CONTRACT_DOCASSEMBLE:BLOCKED]
```

Docassemble API、DOCX 下载/校验或临时链接发布失败时返回：

```text
[CONTRACT_DOCASSEMBLE:FAILED]
```

禁止在 BLOCKED/FAILED 后使用其他本地生成路径补救。

企业微信默认交付形式是临时 HTTPS DOCX 下载链接。PDF、纯文本或聊天 Markdown 不能替代默认 DOCX。
