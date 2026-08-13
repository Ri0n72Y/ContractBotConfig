# ContractBotConfig

企业合同 AstrBot 配置与扩展工程。企业微信用户由 Master Persona 统一交互，OpenContracts 负责合同存储与读取，Docassemble 负责最终 DOCX 生成，Contract Generation Flow 负责一次生成确认、阶段提示和终态一致性，Contract Download Delivery 负责临时 HTTPS 交付。

## 当前生成链路

```text
用户请求
→ Master 整理需求
→ 用户确认
→ Builder 实时读取 OpenContracts
→ Gateway 核验 corpus_slug + document_slug
→ Docassemble 生成 DOCX
→ Gateway 记录本轮 output_path + output_filename
→ Delivery 发布本轮 Gateway 输出
→ Flow 校验 READY 与真实发布结果一致
→ Master 返回 HTTPS 下载链接
```

Builder 正常绑定 5 个工具：

```text
list_documents
get_document_text
search_corpus
docassemble_generate_document
publish_contract_download
```

`search_corpus` 是可选检索辅助。`docassemble_gateway_status` 与 `contract_download_delivery_status` 保留为管理员排障工具，不再绑定给 Builder，也不再作为每次生成的 preflight。

Generation Flow 不再维护第二套 OpenContracts 结果解析；Docassemble Gateway 0.1.4 是唯一来源核验者。阶段提示直接读取 Gateway 已产生的状态，Download Delivery 0.1.2 每次发布先清空旧成功位，再按真实 HTTPS 发布结果写回；Builder 的 READY 若没有对应成功发布记录会被降级为 FAILED。

Gateway 本地 DOCX 默认保留 24 小时；公网下载副本默认保留 30 分钟。详细配置和端到端验收统一见：

```text
docs/docassemble/README.md
```

当前版本以 `VERSIONS.md` 为唯一基线。当前生成链路关键版本：

```text
astrbot_plugin_contract_generation_flow    0.1.3
astrbot_plugin_docassemble_gateway          0.1.4
astrbot_plugin_contract_download_delivery   0.1.2
contract-docassemble                        1.18
contract_docassemble_builder                1.17
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
