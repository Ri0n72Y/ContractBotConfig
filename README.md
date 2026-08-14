# ContractBotConfig

企业合同 AstrBot 配置与扩展工程。Master 统一面向企业微信客户，OpenContracts 负责合同存储与读取，Docassemble 负责最终 DOCX，Generation Flow 在 Builder handoff 执行前从当前 PersonaManager 刷新 Prompt、从当前 Tool Manager 重建四工具运行时工具集，Download Delivery 负责临时 HTTPS 交付和最终交付一致性。

## 当前生成链路

```text
用户要求生成/起草/按当前方案生成
→ Master 直接委派 Builder
→ Flow 从当前 PersonaManager 刷新 Builder Prompt
→ Flow 从当前 Tool Manager 重建 Builder 四个运行工具
→ Builder 用当前绑定的 MCP 数据源列出并读取最相关参考合同
→ 数据库可复用信息优先；仍缺失的普通字段保留【待填写】
→ Gateway 核验本轮 Builder 的真实 document_slug + 非空正文读取
→ Docassemble 生成 DOCX
→ Delivery 发布本轮 Gateway 输出
→ Master 返回 HTTPS 下载链接
```

合同草稿生成不要求额外固定确认口令。只读数据库任务才单独委派 OpenContracts Operator；生成任务即使包含“从数据库找字段”也由 Builder 自己读取，避免 Master → Operator → Builder 的重复链路。

生成链不要求 Persona 或 handoff 指定 `corpus_slug`；合同库数据源由 Builder 当前绑定的 MCP 连接决定。AstrBot 的 handoff Agent 会在 subagent reload 时物化 Persona Prompt/Tools，因此旧 handoff 可能暂时保留旧值。Flow 0.2.1 每次执行 Builder handoff 前直接从当前 PersonaManager 重新读取 `contract_docassemble_builder` Prompt，并从当前全局 Tool Manager 重新解析四个工具；不再依赖 handoff 中缓存的旧 Prompt/status-only ToolSet。

Builder 正常只使用：

```text
list_documents
get_document_text
docassemble_generate_document
publish_contract_download
```

两个 status 工具仅用于管理员排障。生成 Builder 不绑定额外语义搜索工具，也不绑定生成 Skill；核心规则直接固化在 Persona，避免无业务产出的工具轮次。

当前关键版本：

```text
contract_generation_flow      0.2.1
contract_handoff_policy        0.5.0
docassemble_gateway            0.2.1
contract_download_delivery     0.2.0
contract-docassemble           1.20
contract-orchestrator          1.18
contract_docassemble_builder   1.19
contract_master_orchestrator   1.22
```

版本以 `VERSIONS.md` 为准；生成部署与 E2E 见 `docs/docassemble/README.md`；Persona 手动绑定以 `personas/bindings.json` 为准。

## 构建

```powershell
python -m compileall -q plugins scripts
python scripts/build_release.py --clean
```

插件和 Skill 输出 ZIP；Persona 输出每人格一份 Markdown，文件头列出 Tools / Skills 供 WebUI 手动配置。
