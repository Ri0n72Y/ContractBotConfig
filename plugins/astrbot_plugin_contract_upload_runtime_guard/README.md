# 合同上传运行时保护

该插件只处理合同上传阶段的两个运行时边界：

1. 在插件内存中从暂存文件提取合同日期和正式标题，仅把结构化身份交给主人格；
2. 在主人格调用前移除文件读取、Shell、Python、HTTP 等通用工具，避免合同原文进入 AstrBot Tool Result 和 Core 日志；
3. 在 Handoff 完成后加入公开 MCP Corpus 的确定性解析规则。

## 隐私边界

主人格上传请求只保留：

```text
transfer_to_opencontracts_operator
```

合同正文不会作为工具返回值进入模型上下文或日志。当前安全提取支持：

- DOCX：直接读取 `word/document.xml`；
- PDF：使用运行环境中的 `pypdf`，只扫描前四页；
- TXT / Markdown：本地读取。

无法可靠提取日期或标题时，流程输出 `[CONTRACT_UPLOAD:BLOCKED]`，不会退回通用文件读取工具。

## Corpus 解析

Operator 先调用 `list_public_corpuses`：

- 配置 slug 存在精确匹配时使用该值；
- 配置为空或失效，且公开列表只有一个 Corpus 时使用该唯一值；
- 仍存在歧义时停止上传。

禁止尝试常见 slug、拼接其他 MCP 地址或直接发送 MCP JSON-RPC。

## 部署

该插件必须与以下组件同时启用：

- `astrbot_plugin_contract_file_router`
- `astrbot_plugin_contract_handoff_policy`
- `astrbot_plugin_opencontracts_gateway`
- `astrbot_plugin_wecom_final_result_guard`
