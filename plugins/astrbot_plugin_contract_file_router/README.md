# 合同文件接收与路由 0.5.9

本插件把企业微信文件事件转换为可恢复的合同任务，在当前消息事件中启动主人格请求，并管理当前合同文件的会话状态。

## AstrBot 入口

`main.py:Main` 是唯一 AstrBot `Star` 入口；`runtime.py:ContractFileRouter` 是普通实现基类。事件处理器只注册在 `Main` 上。

## 核心职责

- 使用 AstrBot `File.get_file()` 取得文件并复制到插件暂存目录；
- 计算文件 SHA-256、大小和会话文件指纹；
- 管理等待操作、运行中、BLOCKED 恢复、重复确认、结束和文件切换状态；
- 从 `staged_path` 本地解析 PDF/DOCX/TXT/MD 正文，并以 `_no_save` transient context 注入当前 LLM 请求；
- 生成不携带固定 Corpus 的 `contract_task_context`，目标 Corpus 由 Handoff Policy 绑定；
- 对同一 UMO 的 intake/context/finalize 使用轻量 `asyncio.Lock` 串行状态迁移。

## 默认分析行为

快速分析和自由问答都由主人格直接处理，不新增文件读取工具调用。Router 0.5.9 会向当前任务追加简洁输出约束：

- 快速分析默认只给最重要的 4–6 个风险，最多 8 个；
- 每项直接包含风险、原文位置和修改建议；
- 不机械遍历全部条款，不重复多套总结结构；
- 自由问答只回答当前问题；
- 每次任务回复末尾询问用户是否还需要继续处理当前合同。

## 文件保留语义

0.5.9 不再把“本轮结果已发送”视为删除文件的条件。

```text
发送合同文件
→ Router 暂存并返回菜单
→ 用户分析 / 提问 / 上传
→ 本轮任务完成
→ 当前文件继续保留，可继续追问或修改
```

控制语义：

- `结束`：结束当前文件会话，允许普通新任务；暂存文件仍保留。
- `取消`：只取消当前操作；当前合同继续保留并可继续处理。
- `删除文件` / `删除当前文件`：物理删除当前暂存文件。
- 直接上传下一份文件：新文件成为当前文件；上一份文件退出当前上下文但不物理删除。
- 正常分析、问答、上传成功或失败：任务完成后回到可继续处理当前文件的状态，不自动删除。
- `BLOCKED` / 重复合同确认：继续沿用原有可恢复状态。

原 `pending_ttl_seconds` / `staging_ttl_seconds` 不再负责实时会话中的文件物理删除。长期未使用文件的定期清理由独立维护任务处理；当前版本不实现月度清理。

## 暂存合同正文

当前直接支持：

```text
.pdf
.docx
.txt
.md / .markdown
```

`.doc` 由 Contract DOC Preconverter 转换后进入 Router。单次直接注入最多保留前 `120000` 个字符；超过时会标记截断，不为了继续读取增加新的 AI tool call。

自由提问会把用户当前问题与暂存合同正文一起注入。正文使用 `_no_save`，不会写入长期 conversation history。

## 文件切换与迟到结果

用户上传下一份文件时，Router 会把旧的运行 task 登记为 cancelled，并切换到新文件；旧 task 的迟到结果继续由现有取消/Result Guard 机制抑制。旧暂存文件不会在切换时删除。

运行任务超时仍按原逻辑恢复业务状态；不得因超时删除用户保留的文件。

## 与 Result Guard 的事件契约

Result Guard 仍可设置：

```text
contract_preserve_pending_reason = duplicate_confirmation_required
contract_preserve_pending_reason = blocked
contract_blocked_reason = missing_date | missing_title | missing_identity | system
```

Router 在 `after_message_sent` 阶段消费这些标记。没有这些特殊保留原因时，普通任务只清理 dispatch 状态并返回 `awaiting_action`，不再 pop pending 或删除暂存文件。

## 任务上下文

```text
task_id
operation
source_files[]
source_files[].original_name
source_files[].staged_path
source_files[].sha256
identity_hints
resume.blocked_reason
resume.user_input
targets.opencontracts
duplicate_confirmation
branch_tasks
expected_outputs
```

Router 创建上下文时把 `targets.opencontracts` 和分支 `corpus_slug` 留空；`astrbot_plugin_contract_handoff_policy.default_opencontracts_corpus_slug` 是合同库 Corpus 的唯一配置 owner。

## 运行结构

```text
astrbot_plugin_contract_file_router/
├── main.py           # Main Star、会话锁、文件保留策略、request-only 正文快照注入
├── document_text.py  # staged PDF/DOCX/TXT/MD 本地解析
└── runtime.py        # 暂存、任务上下文与基础状态机实现
```
