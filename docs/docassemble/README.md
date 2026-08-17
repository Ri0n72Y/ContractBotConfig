# ContractBot Docassemble 遗留说明

Docassemble 已退出当前正式合同生成链。本目录只保留经过脱敏的旧 interview / smoke 文件和迁移说明，用于历史对照与有限回滚排障；不得在此目录保存真实模板正文、企业参数或其他业务数据。

当前正式架构见：

```text
docs/architecture/ai-docx-generation.md
```

当前正式新生成链：

```text
用户
→ Master
→ Contract Builder
→ 同一 AI 回合优先 find_generation_assets + find_similar_contracts
→ read_generation_asset
→ generate_and_publish_contract
→ HTTPS
```

`generate_and_publish_contract` 由 AstrBot Generation Flow 提供，内部确定性调用 `astrbot_plugin_contract_docx_generator` 的 `generate_contract_docx` 和 Download Delivery 的 `publish_contract_download`；不使用 Docassemble。

正式 Builder 不绑定：

```text
docassemble_generate_document
docassemble_gateway_status
contract-docassemble Skill
```

保留的旧组件：

```text
astrbot_plugin_docassemble_gateway
docs/docassemble/contractbot_document_generation.yml
docs/docassemble/contractbot_api_smoke.yml
contract-docassemble Skill
```

遗留 interview 只允许纯占位默认值。不要按照本目录配置新的生产生成流程。

当前 Persona、插件、外部 Generation Asset 协议和部署配置以以下文件为准：

```text
VERSIONS.md
personas/bindings.json
docs/deployment/persona-manual-config.md
docs/contract-assets/README.md
```
