# Contract Skill Pack Spec

## 1. Purpose

定义面向 WorkBuddy 和其他 MCP-capable harness 的专有合同 Skill 包。Skill 是客户端领域能力，不是新的 Agent 平台。

## 2. Package layout

```text
skills/opencontracts-contract/
  SKILL.md
  VERSION
  references/
    analysis.md
    drafting.md
    modification.md
    document-specification.md
    archive.md
    safety.md
  scripts/
    render_docx.py
    upload_contract.py
    verify_archive.py
    common/
  adapters/
    workbuddy/
      install.md
      mcp.example.json
    generic/
      install.md
  tests/
    fixtures/
    test_renderer.py
    test_archive_contract.py
```

## 3. `SKILL.md` responsibilities

必须包含：

- 任务识别：分析 / 问答 / 修改 / 重写 / 生成 / 归档；
- 何时读本地文件、何时调用 OpenContracts；
- 何时加载对应 reference；
- 生成依据优先级；
- 高风险写入确认规则；
- 引用企业历史时的事实边界；
- 输出最小要求；
- 不得猜测 corpus 权限或远端事实。

不得包含：

- 固定客户 token；
- AstrBot Persona/Handoff 指令；
- 旧 ToolSet 名称作为运行时依赖；
- 客户私有合同内容；
- 强制所有任务调用 OpenContracts。

## 4. Analysis behavior

默认快速分析：

```text
总体判断
+ 3~6 个最高优先级风险
+ 每项：位置 / 问题 / 后果 / 建议
```

只有用户要求全面审查时才扩展到完整清单。

企业事实与模型判断应区分：

- 合同原文；
- 企业历史/模板；
- 一般法律/商业判断。

## 5. Modification behavior

- 优先最小修改，不无故重写整份合同；
- 保持原编号、表格、附件关系；
- 需要企业标准条款时再 MCP 查询；
- 输出新文件和 change summary；
- 默认保留原文件。

## 6. Drafting behavior

必须支持：

```text
specific_template
history_reference
ai_scaffold
```

strict 指定模板：

- 必须来自本轮 MCP 候选；
- 找不到/歧义则停止；
- 不允许偷偷回退 AI scaffold。

历史事实：

- 默认只参考结构/措辞/条款组合；
- 项目金额、日期、比例、账号、地址、税率、工期等不得自动继承。

## 7. Document specification

旧 `contract-document-specification` 的业务内容迁入 `references/document-specification.md`。

Skill 应在正式输出前应用该规范，但不需要 AstrBot `read_bound_skill` 或 grounding bridge。

## 8. Renderer contract

`render_docx.py` 必须是 harness-independent CLI/library。

建议接口：

```text
render_docx.py \
  --input contract.md \
  --metadata metadata.json \
  --output output.docx
```

要求：

- 确定性；
- 不访问网络；
- 不调用 LLM；
- 不执行任意 shell；
- 不覆盖输入；
- 输出 SHA-256；
- 错误写 stderr，成功结果可 JSON 输出。

## 9. Upload helper contract

`upload_contract.py`：

- 读取本地凭证环境/host secret；
- 不从 prompt 接受 raw token；
- 先本地 hash；
- 调用 OpenContracts 官方 HTTPS 文件入口；
- commit-unknown 返回 `manual_review`；
- 不自动循环重试写请求。

`verify_archive.py`：

- 只做读/核验；
- 通过 MCP 或官方只读 API 查询远端事实；
- 可安全重复执行。

## 10. Adapter requirements

### WorkBuddy adapter

必须提供：

- Skill 导入方式；
- MCP 用户级/项目级配置样例；
- secret 配置说明；
- Windows/macOS 路径说明；
- 微信助理工作目录注意事项。

### Generic adapter

只定义通用需求：

```text
can load Markdown skill instructions
can call remote MCP over HTTPS
can read/write local files
can execute approved local helper scripts
```

不声称所有 harness 配置格式相同。

## 11. Versioning

每个发行包必须有：

```text
skill_version
supported_opencontracts range
renderer_version
adapter versions
```

客户自定义规则应位于 override 文件，不直接修改 vendor Skill 核心文件。

## 12. Acceptance criteria

- [ ] WorkBuddy 能导入 Skill；
- [ ] 不调用 MCP 也能分析本地合同；
- [ ] 调 MCP 能检索企业合同；
- [ ] 修改任务能输出新 DOCX；
- [ ] strict template 无匹配时停止；
- [ ] history_reference 不迁移未授权项目值；
- [ ] upload helper 的 token 不进入模型输出/日志；
- [ ] 同一核心规则可被 WorkBuddy adapter 和至少一个 generic harness 使用。
