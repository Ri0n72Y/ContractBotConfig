# ContractBot Docassemble MVP 部署与验收

本目录用于验证 ContractBot 的真实 Docassemble 文书生成链路。

## 目标

先验证以下最小闭环：

```text
AstrBot Docassemble Builder
→ Docassemble Gateway
→ Docassemble API
→ API-first interview
→ Docassemble 生成 DOCX
→ /api/file/<file_number>
→ Gateway 保存真实 DOCX
```

本阶段只解决“最终文书必须由 Docassemble 生成”。企业微信文件下载/发送属于独立交付问题，不在本 smoke 的成功标准内。

## 已确认网络

当前部署中 AstrBot 与 Docassemble 同在 Docker `legal-network`，AstrBot 可访问：

```text
http://docassemble/
```

Gateway 在 AstrBot 容器内使用：

```text
base_url = http://docassemble
```

宿主机访问 Docassemble 使用：

```text
http://localhost:8080
```

## 1. 创建 MVP API Key

在 Docassemble 管理员账户中创建 API Key。

MVP 暂时允许使用管理员 Key。不要把 Key 写入 Persona、Skill、Git 仓库、聊天内容或日志。独立服务账户迁移由 Issue #7 跟踪。

## 2. 部署 smoke interview

仓库提供：

```text
docs/docassemble/contractbot_api_smoke.yml
```

它只验证 API 和 DOCX 链路，不是生产合同模板。

PowerShell 中执行：

```powershell
$secure = Read-Host "Docassemble API Key" -AsSecureString
$env:DOCASSEMBLE_API_KEY = [System.Net.NetworkCredential]::new('', $secure).Password
python scripts/deploy_docassemble_smoke.py
Remove-Item Env:DOCASSEMBLE_API_KEY
```

默认连接宿主机：

```text
http://localhost:8080
```

如果需要指定其他地址：

```powershell
$env:DOCASSEMBLE_BASE_URL = 'http://localhost:8080'
python scripts/deploy_docassemble_smoke.py
Remove-Item Env:DOCASSEMBLE_BASE_URL
```

成功时脚本会输出类似：

```text
Docassemble smoke interview deployed and validated.
interview=docassemble.playground1:contractbot_api_smoke.yml
gateway_base_url=http://docassemble
```

不要自行猜测 `playground1`。脚本会通过 `/api/user` 读取 API Key 所属用户 ID，并用 `/api/interview_data` 验证最终 interview filename。

## 3. 构建 ContractBot 发布包

```powershell
python -m compileall -q plugins scripts
python scripts/build_release.py --clean
```

应产生：

```text
dist/plugins/astrbot_plugin_docassemble_gateway-0.1.0.zip
dist/skills/contract-docassemble-1.15.zip
dist/personas/contract-personas.zip
```

## 4. 安装 Docassemble Gateway

在 AstrBot WebUI 安装：

```text
astrbot_plugin_docassemble_gateway-0.1.0.zip
```

配置：

```text
base_url = http://docassemble
api_key = <管理员 API Key>
allowed_interviews = [<脚本输出的完整 interview>]
default_interview = <脚本输出的完整 interview>
result_descriptor_key = contractbot_document
cleanup_sessions = true
```

## 5. 更新 Builder

导入最新 Persona：

```text
contract_docassemble_builder 1.15
```

绑定 Skill：

```text
contract-docassemble 1.15
```

Builder 只绑定以下工具：

```text
list_documents
get_document_text
search_corpus
docassemble_gateway_status
docassemble_generate_document
```

不要绑定：

```text
astrbot_execute_shell
astrbot_execute_python
通用 HTTP
通用文件写入/编辑工具
```

即使 WebUI 误绑定了这些工具，Docassemble Gateway 也会通过 Builder Persona 固定标记在 `on_llm_request` 阶段把 ToolSet 收敛到上述允许列表。

## 6. Gateway smoke 输入

smoke interview 接受三个顶层变量：

```json
{
  "document_title": "ContractBot Docassemble Smoke",
  "output_basename": "contractbot_smoke",
  "document_body": "这是由 Docassemble 实际生成的测试文档。"
}
```

Gateway 的 `variables` 顶层键只允许安全标识符：

```text
^[A-Za-z][A-Za-z0-9_]*$
```

复杂业务数据应作为这些顶层变量的 JSON 值传入，不允许把 `obj.attr`、`x[0]` 等表达式作为变量名交给 LLM 控制。

## 7. 成功标准

`docassemble_gateway_status(refresh_interviews=true)` 应满足：

```text
configured = true
validated_interviews 包含 smoke interview
invalid_interviews 为空
```

`docassemble_generate_document` 成功时应返回：

```text
success = true
status = ready
delivery_format = docx
source_file_number > 0
size_bytes > 0
output_path 位于 Docassemble Gateway output_dir
```

同时应满足：

- 输出文件是有效 DOCX/ZIP；
- Docassemble session 在调用结束后被删除；
- `generation_audit.jsonl` 不包含 API Key、合同正文或 variables 内容；
- Builder 日志中不出现 `astrbot_execute_python`、`astrbot_execute_shell`、`python-docx` 或 `gen_contract.py`；
- 只有真实 Gateway `status=ready` 才能返回 `[CONTRACT_DOCASSEMBLE:READY]`。

## 8. Smoke 通过后的生产模板阶段

不要把 smoke interview 当作生产模板。

下一阶段应盘点现有 Docassemble package/interview/template，并为正式合同模板建立 package，例如：

```text
docassemble.<package>:data/questions/<contract>.yml
```

生产 interview 优先使用：

```text
docx template file
```

将批准的 Word 模板作为 `data/templates/*.docx` 管理，并为每类合同定义稳定变量契约。生产 interview 同样必须返回 `contractbot_document.file_number`，才能被 Gateway 接受。
