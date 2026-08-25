# Migration Spec

## 1. Purpose

定义从当前 AstrBot 实现迁移到 WorkBuddy/Harness + OpenContracts 的执行顺序、代码去留和删除门槛。

## 2. Branch contract

```text
astrbot-solution     当前 AstrBot 完整历史方案，冻结备份
workbuddy-refactor   新架构重构分支
main                 在 WorkBuddy 方案验收前不直接承载破坏性重构
```

任何 AstrBot-only 删除都先发生在 `workbuddy-refactor`。

## 3. Phase M0 — Architecture / Spec

交付：

- `docs/architecture/*` 更新为新运行模型；
- `docs/spec/*` 成为实现规范；
- 旧 AstrBot 文档不再作为该分支的事实来源。

退出条件：架构与 spec 相互一致，无仍要求 Master/Operator/Builder 才能工作的正式流程。

## 4. Phase M1 — Capability PoC

必须验证：

1. WorkBuddy remote MCP URL + auth；
2. OpenContracts 私有 corpus 权限隔离；
3. 本地文件分析；
4. WorkBuddy Skill 导入；
5. 微信客服号/微信助理任务；
6. 产物回传能力；
7. OpenContracts 文件归档路径。

本阶段只写 PoC/测试，不大规模删除旧代码。

## 5. Phase M2 — Skill skeleton

新建：

```text
skills/opencontracts-contract/
```

迁移顺序：

```text
contract-direct-analysis
→ drafting/modification rules from Builder
→ contract-document-specification
→ archive/read rules from Operator/Gateway
→ conversation rules that remain useful outside AstrBot
```

删除所有 AstrBot runtime 指令后再进入新 Skill。

## 6. Phase M3 — Local helpers

从旧插件抽取：

### Renderer

来源：`astrbot_plugin_contract_docx_generator`

目标：

```text
skills/opencontracts-contract/scripts/render_docx.py
```

只迁移 renderer/domain 逻辑，不迁移 AstrBot decorators/config lifecycle。

### File helpers

来源：File Router / DOC Preconverter 中纯文件处理逻辑。

目标：Skill script common modules。

### Upload helpers

来源：OpenContracts Gateway 中身份、hash、commit-unknown、核验等确定性规则。

目标：

```text
upload_contract.py
verify_archive.py
```

HTTP 调用应改为当前 OpenContracts 官方接口，不复制旧插件 adapter。

## 7. Phase M4 — OpenContracts scripts/patches

新建：

```text
scripts/opencontracts/
patches/opencontracts/
```

必须先通过 `check_version` 再配置或 patch。

Patch 只针对 PoC 已证明缺失的能力；不提前设计大规模 fork。

## 8. Phase M5 — Office E2E

测试矩阵：

| Case | Local file | MCP | Write | Expected |
| --- | --- | --- | --- | --- |
| quick analysis | yes | no | no | analysis |
| enterprise analysis | yes | yes | no | grounded analysis |
| modify | yes | optional | local output | DOCX + summary |
| strict template draft | no/inputs | yes | local output | DOCX or fail-closed |
| archive new | yes | yes | remote | verified complete/processing |
| archive duplicate | yes | yes | remote after confirm | version/update |
| commit unknown | yes | yes | uncertain | manual review |

全部通过后才允许删除对应 AstrBot 组件。

## 9. Phase M6 — WeChat Host E2E

至少测试：

- 微信文本指令；
- 微信输入合同文件（若通道支持）；
- 合同分析；
- 合同修改；
- 产物查看/回传；
- MCP 失效；
- Host 重启；
- 写入 commit-unknown；
- 多用户/多会话实际行为。

测试结果写入部署文档，不根据产品宣传推断。

## 10. Phase M7 — Legacy cleanup

### Can remove

通过对应新 E2E 后，从 `workbuddy-refactor` 删除：

```text
personas/
plugins/astrbot_plugin_contract_handoff_policy
plugins/astrbot_plugin_wecom_final_result_guard
plugins/astrbot_plugin_contract_generation_flow
```

其余插件按能力迁移完成情况删除。

### Must not remove early

以下能力的新实现未验收前，不删除旧来源：

- DOCX renderer；
- `.doc` 兼容；
- upload commit-unknown policy；
- exact duplicate/version handling；
- document specification；
- generation basis logic。

## 11. Repository cleanup target

最终目标不再存在正式 AstrBot runtime 目录：

```text
personas/                    removed
plugins/astrbot_plugin_*     removed
```

保留历史的方式是 Git branch/tag，不是在新主线维护 disabled legacy code。

## 12. CI requirements

重构后 CI 至少包含：

```text
python compile/test for Skill scripts
renderer fixture tests
OpenContracts patch version tests
config secret scan
Skill package build
Markdown/spec link checks
```

有可用 OpenContracts 测试实例时增加 integration tests；真实客户凭证永不进入 CI repository secrets 以外的位置。

## 13. Migration completion gate

- [ ] Architecture/spec merged on refactor branch；
- [ ] Capability PoC complete；
- [ ] Skill Pack complete；
- [ ] local renderer complete；
- [ ] OpenContracts scripts complete；
- [ ] office E2E complete；
- [ ] WeChat Host E2E complete；
- [ ] legacy deletion justified by replacement tests；
- [ ] README/VERSIONS/deployment docs rewritten；
- [ ] PR from `workbuddy-refactor` to `main` reviewed after above gates。
