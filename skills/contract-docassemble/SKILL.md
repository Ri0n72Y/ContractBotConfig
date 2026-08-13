---
name: contract-docassemble
description: 合同库参考读取、Docassemble DOCX 生成和临时 HTTPS 交付规则。
---

# 合同文书生成

本 Skill 保留为生成规则文档；当前 Builder Persona 已内置核心生成规则，正常运行不要求加载本 Skill。

## 最短执行路径

Builder 正常工具只有：

```text
list_documents
get_document_text
search_corpus
docassemble_generate_document
publish_contract_download
```

不做 `docassemble_gateway_status` 或 `contract_download_delivery_status` 的每请求 preflight。

生成请求本身就是草稿生成授权，不设置额外“确认生成”口令或二次确认门。

## 数据库优先，缺失留空

默认使用合同库 `corpus_slug=contracts`：

1. `list_documents` 一次取得文档列表；
2. 按合同类型、项目和主体选择一份最相关的主参考，不默认扫描整个 Corpus；
3. 对主参考从 `char_offset=0` 读取正文，`max_chars` 可用 30000；有 `next_offset` 时继续到完整；
4. 只有确有必要补充特定条款时才读取第二份参考或调用 `search_corpus`；
5. 某一候选正文为空可换下一份相关合同；所有相关合同均不可读才 BLOCKED。

用户明确给出的信息优先。用户未提供的信息先从参考合同中取得；数据库仍没有的字段默认写成 `【待填写】` 或 `【待双方确认】`，继续生成可编辑草稿。不要因为合同金额、付款节点、具体日期、主体工商信息、质保比例或争议机构为空而要求客户先补齐。

只有用户明确要求字段完整才能生成时，才把缺失字段作为阻断条件。

## Docassemble

根据用户需求和参考正文形成：

```text
document_title
完整 document_body
```

一次调用 `docassemble_generate_document`，`variables` 至少包含上述两个字段。正常情况下 `interview` 留空，使用管理员配置的正式 `default_interview`。Gateway 自己负责 allowlist、smoke 禁止和参考来源核验。

Gateway 成功必须包含：

```text
success=true
status=ready
output_path
output_filename
```

随后只调用一次：

```text
publish_contract_download
source_path = 同一次 Gateway 的 output_path
filename = 同一次 Gateway 的 output_filename
```

只有 Delivery 返回 `status=ready` 且有 HTTPS `download_url` 才返回 `[CONTRACT_DOCASSEMBLE:READY]`。没有可读参考、没有正式 interview 或配置不满足返回 BLOCKED；生成、DOCX 校验或发布失败返回 FAILED。任一终态后停止工具调用，不重复 handoff。
