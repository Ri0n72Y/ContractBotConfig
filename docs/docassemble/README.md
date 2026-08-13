# ContractBot Docassemble 生成与部署

本文是合同生成链路的部署说明，版本以根目录 `VERSIONS.md` 为准。

## 正常链路

```text
用户请求
→ Master 整理需求
→ 用户确认一次
→ Builder 读取 OpenContracts
→ Gateway 核验 corpus_slug + document_slug
→ Docassemble 生成 DOCX
→ Gateway 记录本轮 output_path + output_filename
→ Delivery 发布临时 HTTPS 链接
→ Flow 校验 READY 与真实发布结果一致
→ Master 回复用户
```

Generation Flow 不再维护第二套 OpenContracts 来源解析。Docassemble Gateway 是唯一来源核验者。

## Builder WebUI 绑定

正常绑定：

```text
list_documents
get_document_text
search_corpus
docassemble_generate_document
publish_contract_download
```

Skill：`contract-docassemble`。

`search_corpus` 是可选检索辅助。真正必需的是 `list_documents`、`get_document_text`、`docassemble_generate_document`、`publish_contract_download`。

以下工具只用于管理员排障，不绑定给 Builder，也不作为每次生成的 preflight：

```text
docassemble_gateway_status
contract_download_delivery_status
```

因此正常生成比旧流程少两个 tool call/LLM 循环。

## 参考合同

Builder 本轮先调用 `list_documents`，再对候选 `document_slug` 从 `char_offset=0` 调用 `get_document_text`；存在 `next_offset` 时继续读取。

Gateway 只接受同一 `corpus_slug` 下、来自本轮文档列表且正文非空的 `document_slug`。空列表、空正文、跨 Corpus 同名 slug、错误响应或从非零 offset 开始读取都不能形成 verified 状态。

## Docassemble Gateway

推荐配置：

```text
base_url = http://docassemble
api_key = <Docassemble API Key>
allowed_interviews = [<正式 interview>]
default_interview = <正式 interview>
result_descriptor_key = contractbot_document
output_dir = data/plugins_data/astrbot_plugin_docassemble_gateway/output
output_retention_seconds = 86400
output_cleanup_interval_seconds = 300
```

正常 Builder 调用 `docassemble_generate_document` 时把 `interview` 留空，使用管理员配置的 `default_interview`。只有任务明确给出经批准的完整 interview filename 时才显式传入。Gateway 自己负责配置、allowlist 和 smoke interview 校验。

`contractbot_api_smoke.yml` 只用于 API smoke，不用于客户合同。生产环境使用经批准的真实 interview/template。

Gateway 只有在真实返回 `success=true`、`status=ready` 且具有 `output_path/output_filename` 时才记录本轮可交付输出。

## Download Delivery

推荐配置：

```text
public_root = data/public_downloads
public_base_url = https://download.ri0n72y.top/contracts
allowed_source_dirs = [data/plugins_data/astrbot_plugin_docassemble_gateway/output]
ttl_seconds = 1800
cleanup_interval_seconds = 60
max_file_bytes = 31457280
```

正常 Builder 直接调用 `publish_contract_download`。发布工具自身完成配置、来源目录、DOCX 结构、大小和复制校验。

每次发布开始先把本事件的 publication success 状态清为 false；只有真实 HTTPS 发布成功才写回 true，避免旧成功状态污染后续尝试。

正式生成只允许发布同一次 Gateway 记录的 `output_path + output_filename`。

## READY 与阶段提示

Flow 不增加第二套确认。它只做一个终态一致性检查：Builder 若声称 `[CONTRACT_DOCASSEMBLE:READY]`，但本轮没有真实成功发布记录，则 handoff 结果改为 FAILED。

阶段提示也不增加新检查：

```text
用户确认后
→ 开始读取合同库

Gateway 已核验参考正文，且 Builder 即将调用 Docassemble
→ 参考合同正文已核验，正在生成 DOCX

Gateway 已记录本轮 ready 输出，且 Builder 即将调用 Delivery
→ DOCX 已生成，正在准备下载链接
```

## 生命周期

```text
Gateway output_dir   默认 24 小时
public_downloads     默认 30 分钟
Generation pending   默认 30 分钟
```

Gateway 清理器只删除自身命名规则匹配的直属过期 DOCX，不递归处理未知内容。Generation Flow 主动清理过期待确认状态。

## 构建与验收

```powershell
git checkout main
git pull --ff-only origin main
python -m compileall -q plugins scripts
python scripts/build_release.py --clean
```

Persona 构建为每人格一份 Markdown，Tools/Skills 以文件头为准。

E2E 至少确认：即时回执、一次确认、Builder 只有 5 个正常运行工具、没有 status preflight、Gateway 读取真实参考正文、Docassemble 返回真实 DOCX、Delivery 返回 HTTPS 链接、无真实发布时 READY 会被阻止。
