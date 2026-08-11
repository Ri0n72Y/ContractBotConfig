---
name: contract-docassemble
description: >
  合同文书生成前置核验、Docassemble interview 选择、变量收集、DOCX 生成验证和交付规则。
---

# 合同文书生成

## 执行原则

Docassemble 是合同文书生成的唯一执行引擎。不得使用 Shell、Python、通用 HTTP、本地脚本、`python-docx`、临时文件编辑或其他方式替代 Docassemble 生成 DOCX。

允许的生成工具：

```text
docassemble_gateway_status
docassemble_generate_document
```

如需读取合同库中的参考合同，可使用已绑定的 OpenContracts 只读工具，但最终 DOCX 必须由 `docassemble_generate_document` 生成。

## 前置来源核验

生成合同或合同条款前，必须先确认合同库中存在与目标合同类型相关的现有合同或经批准模板。

没有相关合同或模板时停止生成，向主助手返回：

> 目前合同库中没有可参考的合同，请先上传合同后再生成。

不得根据一般常识、模型记忆或临时搜索自行编造合同条款。

## Interview 核验

1. 调用 `docassemble_gateway_status(refresh_interviews=true)` 获取 Gateway 配置和允许的 interview。
2. 只能选择 `allowed_interviews` 中且实际可用的 interview；不得自行猜测 interview filename。
3. 没有与目标合同类型匹配的 allowlist interview 时停止生成，不得降级到 Python/Shell。
4. API Key 由 Gateway 持有，不得要求、读取、输出或记录 API Key。

## 信息核验

根据现有合同、批准模板和目标 interview 确定所需变量。主体、金额、日期、履行内容、付款条件、违约责任等关键变量缺失时返回缺失清单，不自行补全。

调用 `docassemble_generate_document` 时一次性提供完整变量对象。Gateway 使用一次性 session，不由 LLM 模拟 Docassemble 网页逐题回答。

如果 Gateway 返回：

```text
status=blocked
failure_stage=missing_variable
```

将 `missing_variables` 原样返回主助手，等待用户补充后重新发起一次完整生成。

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

## 结果状态

生成成功并且 Gateway 已取得真实 DOCX 文件时，首行返回：

```text
[CONTRACT_DOCASSEMBLE:READY]
```

并返回 Gateway 提供的：

- `output_path`
- `output_filename`
- `size_bytes`
- `interview`

需要补充变量、未配置 allowlist、interview 不存在或 interview 未遵守文件返回契约时，首行返回：

```text
[CONTRACT_DOCASSEMBLE:BLOCKED]
```

Docassemble API 正式调用失败或 DOCX 下载/校验失败时，首行返回：

```text
[CONTRACT_DOCASSEMBLE:FAILED]
```

禁止在 `BLOCKED` 或 `FAILED` 后调用 Shell、Python 或本地文件工具进行补救。

## 文件交付

默认输出 DOCX。只有 `docassemble_generate_document` 返回 `status=ready` 且取得真实 `.docx` 文件后，才能报告生成成功。

PDF、纯文本或聊天中的 Markdown 不能替代默认 DOCX 文件。客户明确要求其他格式时，可在后续独立流程中处理；本 Skill 当前只认定 DOCX 为成功结果。
