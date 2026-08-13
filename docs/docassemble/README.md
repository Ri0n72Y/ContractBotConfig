# ContractBot Docassemble 生成与部署

本目录用于维护 ContractBot 的 Docassemble 生成 interview、部署说明和 smoke 验收材料。

## 当前目标链路

正式合同生成闭环为：

```text
企业微信用户
→ contract_master_orchestrator
→ Contract Generation Flow
→ 用户确认生成方案
→ contract_docassemble_builder
→ OpenContracts list_documents
→ OpenContracts get_document_text
→ Docassemble Gateway
→ Docassemble API / interview
→ DOCX
→ Contract Download Delivery
→ HTTPS 临时下载链接
```

正式生成只有在用户确认、OpenContracts 参考正文、Docassemble 输出和 Delivery 发布四段都成功后才算完成。

## 当前组件版本

以仓库根目录 `VERSIONS.md` 为唯一版本基线。本链路当前关键版本：

```text
astrbot_plugin_contract_generation_flow 0.1.2
astrbot_plugin_docassemble_gateway       0.1.4
astrbot_plugin_contract_download_delivery 0.1.1
contract-docassemble                     1.17
contract_docassemble_builder             1.16
contract_master_orchestrator             1.20
```

## 1. Docassemble API Key

AstrBot 与 Docassemble 同一 Docker 网络时，Gateway 默认使用：

```text
base_url = http://docassemble
```

MVP 暂可使用管理员 API Key。不要把 Key 写入 Persona、Skill、Git、聊天内容、Tool 参数或日志。独立服务账户迁移继续由安全债务 Issue 跟踪。

## 2. Smoke interview

仓库保留：

```text
docs/docassemble/contractbot_api_smoke.yml
```

它只用于验证 Docassemble session / file API 链路，不是生产合同模板。

部署 smoke 时可在本地 PowerShell 使用：

```powershell
$secure = Read-Host "Docassemble API Key" -AsSecureString
$env:DOCASSEMBLE_API_KEY = [System.Net.NetworkCredential]::new('', $secure).Password
python scripts/deploy_docassemble_smoke.py
Remove-Item Env:DOCASSEMBLE_API_KEY
```

脚本会返回完整 interview filename，例如：

```text
docassemble.playground1:contractbot_api_smoke.yml
```

不要自行猜测 Playground 用户编号。

**正式客户合同生成不得使用文件名包含 `smoke` 的 interview。** Docassemble Gateway 会在正式生成路径中确定性阻止该用法。

## 3. 正式生成 interview

仓库提供最小非 smoke 示例：

```text
docs/docassemble/contractbot_document_generation.yml
```

它可用于验证正式链路，但生产环境仍应优先使用经过批准的真实 Docassemble package / interview / DOCX template，并定义稳定的结构化变量契约。

生产 interview 完成时必须返回：

```text
contractbot_document.status = complete
contractbot_document.file_number = <正整数>
contractbot_document.extension = docx
```

Gateway 再通过：

```text
GET /api/file/<file_number>?extension=docx
```

取回真实 DOCX。

## 4. 本地构建

继续使用本地构建 + AstrBot WebUI 发布流程：

```powershell
git checkout main
git pull --ff-only origin main
python -m compileall -q plugins scripts
python scripts/build_release.py --clean
```

插件和 Skill 仍输出 ZIP；Persona 不再输出 ZIP。

```text
dist/
├── plugins/
├── skills/
├── personas/
│   ├── contract_master_orchestrator-<version>.md
│   ├── contract_opencontracts_operator-<version>.md
│   └── contract_docassemble_builder-<version>.md
└── MANIFEST.json
```

Persona Markdown 文件头会列出需要在 AstrBot WebUI 手动绑定的 Tools / Skills。

## 5. Docassemble Gateway 配置

WebUI 安装当前版本的：

```text
astrbot_plugin_docassemble_gateway
```

推荐配置：

```text
base_url = http://docassemble
api_key = <Docassemble API Key>
allowed_interviews = [<完整正式 interview filename>]
default_interview = <完整正式 interview filename>
result_descriptor_key = contractbot_document
output_dir = data/plugins_data/astrbot_plugin_docassemble_gateway/output
timeout_seconds = 90
max_file_bytes = 31457280
verify_tls = true
cleanup_sessions = true
output_retention_seconds = 86400
output_cleanup_interval_seconds = 300
```

`output_dir` 是短期生成源目录，不是长期合同归档。Gateway 默认保留自身生成的 DOCX 24 小时，每 5 分钟扫描一次。

清理器只删除 `output_dir` 直属、文件名符合 Gateway 自身 `12位十六进制前缀_*.docx` 规则且已经超过 TTL 的普通文件；不递归删除目录，不处理未知文件和符号链接。

## 6. Generation Flow 配置

`astrbot_plugin_contract_generation_flow` 默认：

```text
confirmation_ttl_seconds = 1800
cleanup_interval_seconds = 60
```

待确认生成方案只短时写入：

```text
data/plugins_data/astrbot_plugin_contract_generation_flow/pending_generation.json
```

插件会在运行期间主动扫描并清除超过 TTL 的待确认方案，不再依赖“下一条用户消息”触发惰性清理。

## 7. Builder WebUI 绑定

`contract_docassemble_builder` 必须完整绑定以下 7 个 Tool：

```text
list_documents
get_document_text
search_corpus
docassemble_gateway_status
docassemble_generate_document
contract_download_delivery_status
publish_contract_download
```

Skill：

```text
contract-docassemble
```

不要绑定 Shell、Python、`python-docx`、通用 HTTP、通用文件写入/编辑工具作为生成或交付后备路径。

Generation Flow 会检查 Builder 是否具备完整 7 工具；缺少任一工具时清空 Builder ToolSet 并返回 BLOCKED。

## 8. 正式生成 fail-closed 与参考合同核验

用户确认后，Builder 必须先实时读取 OpenContracts。

Gateway 自己把当前事件识别为正式合同生成任务后，**确认状态缺失也视为失败**。即使 Generation Flow 未加载、加载失败或没有注入 `contract_generation_confirmation_approved=true`，`docassemble_generate_document` 也只会返回 BLOCKED，不会退回直接生成。

Generation Flow 会做第一层工具结果检查；Docassemble Gateway 0.1.4 再做独立的执行边界核验。Gateway 不信任“工具被调用过”，也不只按 `document_slug` 判断来源，而是绑定完整来源身份：

```text
(corpus_slug, document_slug)
```

### list_documents

必须满足：

```text
请求 corpus_slug 非空
无 error
如果返回 corpus_slug，则必须与请求一致
total_count > 0
documents 为非空列表
至少一条 document.slug 非空
```

通过后，Gateway 按 `corpus_slug` 记录本轮真实文档 slug 集合。

### get_document_text

至少一个调用必须满足：

```text
请求 corpus_slug 非空
请求 document_slug 非空
该 document_slug 必须来自同一 corpus_slug 的本轮 list_documents 结果
如果返回 corpus_slug，则必须与请求一致
返回 document_slug 与请求一致
char_offset = 0
total_chars > 0
text 非空
```

只有 Gateway 自己的 corpus/document 关联核验通过后，才允许 `docassemble_generate_document`。

因此以下情况都不能解锁生成：

```text
Generation Flow 确认状态缺失
list_documents 返回 error
合同库为空
list_documents 与 get_document_text 使用不同 corpus_slug
get_document_text 返回 total_chars=0
get_document_text 返回 text=""
读取未在同一 Corpus 的本轮 list_documents 中出现的 slug
从非零 offset 直接开始读取
```

## 9. 本轮 Gateway 输出与 Download Delivery 绑定

正式生成进入 `docassemble_generate_document` 时，Gateway 会先清空当前事件中旧的生成输出绑定。

只有本轮 Docassemble 真实结果同时满足：

```text
success = true
status = ready
output_path 非空
output_filename 非空
```

Gateway 才记录：

```text
contract_generation_gateway_output_verified = true
contract_generation_gateway_output.output_path
contract_generation_gateway_output.output_filename
```

Contract Download Delivery 0.1.1 对正式生成任务再次执行硬校验：

```text
source_path 必须解析为本轮 Gateway output_path
filename 必须完全等于同一次 Gateway output_filename
```

因此 `output_dir` 中历史生成的其他合法 DOCX，即使仍位于 allowlist 且未超过 24 小时保留期，也不能冒充本轮生成结果发布。

Builder 随后调用：

```text
publish_contract_download
```

成功后得到：

```text
https://download.ri0n72y.top/contracts/<token>/<filename>
```

公网副本默认 30 分钟过期。Gateway 原始生成文件与公网副本使用不同生命周期：

```text
Gateway output_dir        默认 24 小时
public_downloads          默认 30 分钟
```

Master 只向客户展示 HTTPS 下载地址、文件名和有效期，不展示本地 `output_path`。

## 10. 正式生成验收标准

企业微信端到端测试应至少确认：

- 新生成请求立即收到“已收到/先整理信息”的消息；
- 首次请求只形成确认方案，不实际读取或生成；
- 用户补充信息后仍保持确认门；
- 用户明确“确认生成”后才进入 Builder；
- Generation Flow 未提供确认状态时 Gateway fail-closed；
- Builder 的 7 个 Tool 全部可见；
- `list_documents` 返回真实文档；
- `get_document_text` 使用与 `list_documents` 相同的 `corpus_slug`，并至少对列表中的一个 slug 从 offset 0 返回非空正文；
- 空正文 / OpenContracts error / Corpus 不一致时 Docassemble 被 BLOCKED；
- 正式生成没有使用 smoke interview；
- `docassemble_generate_document` 返回真实 `source_file_number` 和有效 DOCX；
- `publish_contract_download` 只接受同一次 Gateway 返回的 `output_path + output_filename`；
- 尝试发布同目录历史 DOCX 时被 BLOCKED；
- 正常发布返回 HTTPS URL；
- 浏览器可下载并打开 DOCX；
- 日志中没有 Shell / Python / python-docx / 通用 HTTP 降级生成路径。

Smoke interview 的单独 API 验证仍可继续使用，但它不能替代上述正式链路验收。
