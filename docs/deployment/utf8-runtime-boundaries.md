# UTF-8 与模型上下文边界

## 目标

合同正文、MCP 工具结果、插件 JSON 和运维脚本在各边界保持 UTF-8，避免两类问题：

1. 无损但冗长的 JSON Unicode escape（如 `\u6750\u6599`）原样进入 LLM，造成额外 token 和可读性下降；
2. 编码转换已经把中文替换为 `?`，导致信息不可恢复。

日志本身不会消耗 LLM token；只有日志或工具结果被注入模型上下文时才产生 token 成本。

## Python / JSON

模型可见 JSON 使用：

```python
json.dumps(payload, ensure_ascii=False)
```

需要紧凑工具输出时使用：

```python
json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
```

对 MCP 文本先用 JSON parser 得到结构化对象，再重新序列化。不要对正常 Unicode 字符串调用 `.decode("unicode_escape")`，也不要把 `repr(payload)` 当作模型上下文。

完整 traceback 只写服务日志。模型侧错误收敛为 `status / failure_stage / error / retry_safe` 等结构化字段。

## MCP / ToolResult 错误边界

处理 `CallToolResult` 的顺序：

```text
先检查 isError / is_error
→ error=true：详细内容写日志，模型只返回短结构化错误
→ error=false：解析 structuredContent / content[].text
→ JSON parse
→ ensure_ascii=False 紧凑序列化
```

对象形态和 dict 形态都按同一语义处理。无法解析的 ToolResult 不直接原样进入模型上下文。

## 只读异常与写异常必须分开

Generation Flow 0.7.2 不再把所有 executor exception 都视为 retry-safe。

只读工具（模板/历史搜索、文档读取、草稿读取）的执行异常没有外部写副作用，可以收敛为短结构化错误并保持 `retry_safe=true`。

DOCX 生成、HTTPS 发布、draft finalize 属于写操作。它们内部可能通过 `asyncio.to_thread()` 执行文件工作；上层 asyncio timeout/cancel 不能证明工作线程没有完成。因此：

```text
write executor exception
→ retry_safe=false
→ commit_unknown=true
→ 本 generation terminal
→ 禁止自动重试
```

如果 `generate_and_publish_contract` 本身被 timeout/cancel，Flow 先记录当前 write stage 与 commit-unknown，再保留取消语义交回 AstrBot。即使模型只看到框架的短 timeout/error，也会在下一次写工具调用被 terminal gate 阻止，避免重复生成或重复发布。

这类详细 traceback 仍只保留在服务日志；模型不需要看到 Python stack 才能知道“不要重试”。

## HTTPS 已发布但 draft finalize 失败

这是“交付已提交、版本持久化未完成”，不是普通失败，也不能返回完整 READY：

```text
status=partial
delivery_committed=true
draft_saved=false
retry_safe=false
manual_recovery_required=true
```

模型可以把已经确认的 HTTPS 下载链接交给用户，但必须说明该版本暂时不能可靠作为下一轮 Draft Store 的“上一版”，并且不能重新执行整条生成链补救。

## 容器环境

自维护 Python 容器建议设置：

```text
PYTHONUTF8=1
PYTHONIOENCODING=utf-8
LANG=C.UTF-8
LC_ALL=C.UTF-8
```

业务数据解码应严格失败而不是静默替换；stdout/stderr 的 `errors=replace` 只可作为日志防崩保护，不可作为业务数据修复方式。

## Windows PowerShell 5.1

不要通过以下形式向 `docker exec -i ... python -` 传包含中文源码的 here-string：

```powershell
$Script = @'
print("中文")
'@
$Script | docker exec -i container python -
```

Windows PowerShell 5.1 的 native stdin 编码转换可能把中文变为 `?`。运维脚本优先采用：

```text
UTF-8 文件 -> docker cp -> 容器内 python /tmp/script.py
```

或：

```text
UTF-8 bytes -> Base64 -> ASCII stdin -> 容器内 decode
```

如果脚本必须直接走 ASCII stdin，可把固定 Unicode literal 写成 Python `\uXXXX`，但这只适用于运维传输，不是业务数据存储格式。

## Generation Flow

Generation Flow 0.7.2 在模型边界执行：

- 成功 MCP JSON 先解析，再以真实 UTF-8 compact JSON 返回 Builder；
- `isError`、无法解析结果和 executor exception 不把原始 wrapper/traceback 塞入模型；
- 正文读取不做额外“转译”；Unicode escape 的恢复属于 JSON parse 的正常行为；
- 写异常额外携带 retry/commit 语义，避免为降低 token 而丢掉关键一致性信息。
