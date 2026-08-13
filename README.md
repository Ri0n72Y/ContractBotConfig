# ContractBotConfig

企业合同 AstrBot 配置与扩展工程。企业微信用户由 Master Persona 统一交互，OpenContracts 负责合同存储与读取，Docassemble 负责最终 DOCX 生成，Contract Generation Flow 负责生成前确认和进度提示，Contract Download Delivery 负责临时 HTTPS 交付。

## 当前生成链路

```text
用户请求
→ Master 整理需求
→ 用户确认
→ Builder 实时读取 OpenContracts
→ Gateway 核验 corpus_slug + document_slug
→ Docassemble 生成 DOCX
→ Gateway 记录本轮 output_path + output_filename
→ Delivery 只发布本轮 Gateway 输出
→ Master 返回 HTTPS 下载链接
```

Builder 必须绑定：

```text
list_documents
get_document_text
search_corpus
docassemble_gateway_status
docassemble_generate_document
contract_download_delivery_status
publish_contract_download
```

Generation Flow 提供确认和第一层结果检查；Docassemble Gateway 0.1.4 是最终执行边界：已识别的正式生成缺少用户确认时 fail-closed，参考正文必须来自同一 Corpus 的本轮真实文档。Contract Download Delivery 0.1.1 对正式生成只接受同一次 Gateway 记录的 `output_path + output_filename`，不能发布输出目录中的历史 DOCX 冒充本轮结果。

Gateway 本地 DOCX 默认保留 24 小时；公网下载副本默认保留 30 分钟。详细安全边界、配置项和端到端验收步骤统一见：

```text
docs/docassemble/README.md
```

当前版本以 `VERSIONS.md` 为唯一基线。当前生成链路关键版本：

```text
astrbot_plugin_contract_generation_flow    0.1.2
astrbot_plugin_docassemble_gateway          0.1.4
astrbot_plugin_contract_download_delivery   0.1.1
contract-docassemble                        1.17
contract_docassemble_builder                1.16
contract_master_orchestrator                1.20
```

## Persona 发布

Persona 源文件保留为 `personas/persona_*_v*.json`，构建后在 `dist/personas/` 输出每个人格一份 Markdown。文件头列出需要在 AstrBot WebUI 手动绑定的 Tools / Skills。绑定清单维护在 `personas/bindings.json`。

## 本地构建

```powershell
git checkout main
git pull --ff-only origin main
python -m compileall -q plugins scripts
python scripts/build_release.py --clean
```

插件和 Skill 输出 ZIP；Persona 输出 Markdown。部署继续通过 AstrBot WebUI 完成。
