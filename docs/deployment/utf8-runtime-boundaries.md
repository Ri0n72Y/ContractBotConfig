# UTF-8 与模型上下文边界

## 目标

合同正文、MCP 工具结果、插件 JSON 和运维脚本统一保持 UTF-8，避免两类问题：

1. 无损但冗长的 JSON Unicode escape（例如 `\u6750\u6599`）原样进入 LLM，增加 token 和阅读噪声；
2. 编码转换把中文替换成 `?`，导致信息不可恢复。

只有被送入模型上下文的日志/工具文本才产生 token 成本；普通服务日志本身不会。

## Python / JSON

模型可见 JSON：

```python
json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
```

MCP 文本先 JSON parse，再重新序列化。不要对正常 Unicode 字符串调用 `.decode("unicode_escape")`，不要把 `repr(payload)` 当模型上下文。

## MCP / ToolResult

处理顺序：

```text
执行工具
→ 先检查 isError / is_error
→ error：完整详情/traceback 只写服务日志，模型得到短结构化错误
→ success：解析 structuredContent / content[].text
→ JSON parse
→ ensure_ascii=False 紧凑序列化
→ Builder
```

Generation Flow 0.7.2 对对象和 dict 形态的 ToolResult 都执行这一边界。读操作异常可以返回 retry-safe；DOCX/发布/finalize 等写操作异常由 Flow 按 `retry_safe=false` / `commit_unknown` 处理，不能为了隐藏 traceback 而错误声明可安全重试。

## 容器环境

自维护 Python 容器建议：

```text
PYTHONUTF8=1
PYTHONIOENCODING=utf-8
LANG=C.UTF-8
LC_ALL=C.UTF-8
```

业务数据解码应严格失败；stdout/stderr 的 `errors=replace` 只能作为日志防崩保护。

## Windows PowerShell 5.1

不要把包含中文源码的 here-string 直接管道给 native `docker exec -i ... python -`：

```powershell
$Script = @'
print("中文")
'@
$Script | docker exec -i container python -
```

推荐：

```text
UTF-8 文件 → docker cp → 容器内执行
```

或者：

```text
UTF-8 bytes → Base64 → ASCII stdin → 容器内 decode
```

如果运维脚本必须走 ASCII stdin，可以用 Python `\uXXXX` 表示固定 literal；这只是传输 workaround，不是业务数据格式。

## `\uXXXX` 与 `????`

```text
\u6750\u6599
```

是无损 JSON escape，解析后可恢复正常中文。

```text
????
```

表示字符已经在上游编码边界被替换，原始信息已丢失，不能依赖模型恢复。
