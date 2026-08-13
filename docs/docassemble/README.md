# ContractBot Docassemble 生成与部署

版本以根目录 `VERSIONS.md` 为准，Persona 工具绑定以 `personas/bindings.json` 为准。

## 正常链路

```text
用户请求 → Master 确认一次 → Builder 读取 OpenContracts
→ Gateway 核验 corpus_slug + document_slug
→ Docassemble 生成 DOCX
→ Delivery 发布临时 HTTPS 链接
→ Master 回复用户
```

职责边界：Generation Flow 负责确认和阶段提示；Docassemble Gateway 是唯一参考来源核验者；Download Delivery 负责文件发布，并在最终回复前保证 READY 与真实 HTTPS 发布结果一致。

## Builder

正常绑定 5 个工具：

```text
list_documents
get_document_text
search_corpus
docassemble_generate_document
publish_contract_download
```

`search_corpus` 是可选检索辅助。`docassemble_gateway_status` 与 `contract_download_delivery_status` 仅用于管理员排障，不绑定给 Builder，也不作为每次生成的 preflight，因此正常链路比旧方案少两个 tool call/LLM 循环。

## 来源核验

Builder 先 `list_documents(corpus_slug=...)`，再从 `char_offset=0` 读取候选 `document_slug`。Gateway 只接受同一 Corpus、本轮列表中的真实文档且正文非空；空列表、空正文、跨 Corpus 同名 slug、错误响应不能解锁生成。

## Gateway

推荐配置：

```text
base_url = http://docassemble
api_key = <Docassemble API Key>
allowed_interviews = [<正式 interview>]
default_interview = <正式 interview>
output_retention_seconds = 86400
output_cleanup_interval_seconds = 300
```

正常生成把 `interview` 留空使用 `default_interview`。`contractbot_api_smoke.yml` 只用于 API smoke。Gateway 只有真实得到 `status=ready + output_path + output_filename` 时才记录本轮可交付输出。

## Delivery

推荐配置：

```text
public_root = data/public_downloads
public_base_url = https://download.ri0n72y.top/contracts
allowed_source_dirs = [data/plugins_data/astrbot_plugin_docassemble_gateway/output]
ttl_seconds = 1800
```

每次发布先清空旧 publication success 状态，只有真实 HTTPS 发布成功才写回成功。正式生成只能发布同一次 Gateway 输出。Builder 如果声称 `[CONTRACT_DOCASSEMBLE:READY]` 但本轮没有真实发布成功，最终客户回复不会报告成功；这不增加确认、LLM 回合或工具调用。

## 阶段提示

```text
用户确认 → 开始读取合同库
Gateway 已核验来源 + 即将生成 → “正在通过 Docassemble 生成 DOCX”
Gateway 已得到本轮 DOCX + 即将发布 → “正在准备临时 HTTPS 下载链接”
```

## 生命周期

```text
Gateway output_dir   24 小时
public_downloads     30 分钟
Generation pending   30 分钟
```

## 构建与 E2E

```powershell
python -m compileall -q plugins scripts
python scripts/build_release.py --clean
```

E2E 检查：即时回执、一次确认、Builder 5 工具、无 status preflight、真实参考正文、真实 DOCX、HTTPS 下载成功、无真实发布时不会报告 READY。
