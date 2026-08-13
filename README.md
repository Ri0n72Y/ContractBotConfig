# ContractBotConfig

企业合同 AstrBot 配置与扩展工程。Master 统一面向企业微信客户，OpenContracts 负责合同存储与读取，Docassemble 负责最终 DOCX，Generation Flow 负责一次生成确认与阶段提示，Download Delivery 负责临时 HTTPS 交付和最终交付一致性。

## 当前生成链路

```text
用户请求 → Master 整理并确认
→ Builder 读取 OpenContracts
→ Gateway 核验 corpus_slug + document_slug
→ Docassemble 生成 DOCX
→ Delivery 发布本轮 Gateway 输出
→ Master 返回 HTTPS 下载链接
```

Builder 正常绑定：

```text
list_documents
get_document_text
search_corpus
docassemble_generate_document
publish_contract_download
```

`search_corpus` 是可选检索辅助。两个 status 工具仅保留给管理员排障，不再作为每次生成的 preflight。

Generation Flow 不再维护第二套 OpenContracts 结果解析；Gateway 0.1.4 是唯一来源核验者。Delivery 0.1.3 每次发布先清空旧成功状态，并在最终回复前阻止没有真实 HTTPS 发布记录的 READY 被报告为成功。

当前关键版本：

```text
contract_generation_flow      0.1.3
docassemble_gateway            0.1.4
contract_download_delivery     0.1.3
contract-docassemble           1.18
contract_docassemble_builder   1.17
contract_master_orchestrator   1.20
```

版本以 `VERSIONS.md` 为准；生成部署与 E2E 见 `docs/docassemble/README.md`；Persona 手动绑定以 `personas/bindings.json` 为准。

## 构建

```powershell
python -m compileall -q plugins scripts
python scripts/build_release.py --clean
```

插件和 Skill 输出 ZIP；Persona 输出每人格一份 Markdown，文件头列出 Tools / Skills 供 WebUI 手动配置。
