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

完整 traceback 只写服务日志。模型侧错误应收敛为 `status / failure_stage / error / retry_safe` 等结构化字段。

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

Generation Flow 0.7.0 会把可解析 MCP JSON 重新序列化为真实 UTF-8 紧凑 JSON 后再返回 Builder。因此 OpenContracts MCP 即使在传输文本中使用 Unicode escape，Builder 也不应再看到 raw `\uXXXX` JSON。

正文读取结果不进行额外“转译”；Unicode escape 的恢复属于 JSON parse 的正常行为，不增加额外 LLM 回合。
