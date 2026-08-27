# OpenContracts `local.yml` + Caddy 固定 IP 部署

这是当前 MVP 的标准部署流程。OpenContracts 使用现有 `local.yml`，服务器保留固定内网 IPv4，Caddy 直接给该 IP 提供 HTTPS。整个流程不需要 DNS，也不修改 Agent 的 hosts 文件。

```text
WorkBuddy / Harness
  -> https://<固定内网IP>/mcp/
  -> Caddy :443 (tls internal)
  -> OpenContracts django:8000
```

OpenContracts 只配置两个运行时检索 Corpus：`contracts-history` 和 `contract-templates`，两者在 MVP 中保持 public。会话经验不进入 OpenContracts；正式合同入库使用绑定 `contracts-history` 的 WorkerKey。

## 0. 需要先确定的值

部署前只需要确认：

```text
OPENCONTRACTS_SERVER_IP=<OpenContracts服务器固定内网IPv4>
OPENCONTRACTS_PATH=<服务器上的OpenContracts目录>
HISTORY_CORPUS=<历史合同Corpus slug>
TEMPLATE_CORPUS=<模板Corpus slug>
```

示例：

```text
OPENCONTRACTS_SERVER_IP=10.10.20.15
OPENCONTRACTS_PATH=D:\OpenContracts
HISTORY_CORPUS=contracts-history
TEMPLATE_CORPUS=contract-templates
```

服务器需要已经能够通过 `docker compose -f local.yml up -d` 正常启动 OpenContracts。

## 1. Agent MCP 配置

仓库根目录 `.mcp.json` 可以直接随项目使用：

```json
{
  "mcpServers": {
    "opencontracts": {
      "type": "http",
      "url": "${OPENCONTRACTS_MCP_URL}"
    }
  }
}
```

以 `10.10.20.15` 为例，Agent 最终环境变量应为：

```text
OPENCONTRACTS_BASE_URL=https://10.10.20.15
OPENCONTRACTS_MCP_URL=https://10.10.20.15/mcp/
OPENCONTRACTS_HISTORY_CORPUS=contracts-history
OPENCONTRACTS_TEMPLATE_CORPUS=contract-templates
OPENCONTRACTS_CA_BUNDLE=<本机caddy-root.crt路径>
NODE_EXTRA_CA_CERTS=<同一个caddy-root.crt路径>
OPENCONTRACTS_UPLOAD_WORKER_KEY=<正式入库WorkerKey>
```

`config/opencontracts.env.example` 中这些环境相关值保持空白，不提交真实 IP/Token。

## 2. 配置 OpenContracts 服务器

`Setup-OpenContractsLocalCaddy.ps1` 会完成以下动作：

1. 校验固定 IPv4、Docker、`local.yml` 和 Django env 文件；
2. 把 `local.yml` 中 Django 的 `8000:8000` 改为 `127.0.0.1:8000:8000`，并创建带时间戳的备份；
3. 把固定 IP 加入 `DJANGO_ALLOWED_HOSTS`；
4. 启动 OpenContracts `local.yml`；
5. 检查历史合同和模板两个 Corpus slug 是否存在，并设为 `is_public=True`；
6. 创建 Caddy 容器并加入 OpenContracts Docker network；
7. 只把 Caddy 的 `443/tcp` 暴露到宿主机；
8. Caddy 使用 `https://<固定IP>` + `tls internal`，反代 `django:8000`；
9. 导出内部 CA 根证书到 `.contractbot-caddy/caddy-root.crt`。

在服务器本机运行：

```powershell
.\Setup-OpenContractsLocalCaddy.ps1 `
  -OpenContractsPath 'D:\OpenContracts' `
  -ServerIp '10.10.20.15' `
  -HistoryCorpus 'contracts-history' `
  -TemplateCorpus 'contract-templates'
```

如当前部署需要 `fullstack` profile，再增加 `-StartFullStack`。

## 3. 通过远程 PowerShell 配置服务器

从管理员工作站建立 PowerShell Remoting session：

```powershell
$session = New-PSSession -ComputerName 'OC-SERVER'
```

直接把仓库里的脚本发送到远端执行，服务器上无需预先复制脚本：

```powershell
Invoke-Command `
  -Session $session `
  -FilePath '.\deploy\opencontracts\Setup-OpenContractsLocalCaddy.ps1' `
  -ArgumentList `
    'D:\OpenContracts', `
    '10.10.20.15', `
    'contracts-history', `
    'contract-templates'
```

执行完成后把 Caddy 根证书拉回管理员工作站：

```powershell
Copy-Item `
  -FromSession $session `
  'D:\OpenContracts\.contractbot-caddy\caddy-root.crt' `
  '.\caddy-root.crt'
```

## 4. 创建正式入库 WorkerKey

先查询历史合同 Corpus 的数据库 ID：

```powershell
Invoke-Command -Session $session -ScriptBlock {
    Set-Location 'D:\OpenContracts'
    docker compose -f local.yml exec -T django python manage.py shell -c "from opencontractserver.corpuses.models import Corpus; print(list(Corpus.objects.filter(slug='contracts-history').values_list('id','slug','is_public')))"
}
```

假设结果中的 raw ID 为 `12`，创建 token：

```powershell
Invoke-Command -Session $session -ScriptBlock {
    Set-Location 'D:\OpenContracts'
    docker compose -f local.yml exec -T django python manage.py mint_worker_token `
      --corpus 12 `
      --worker-name contractbot-formal-ingest `
      --rate-limit 30 `
      --expires-days 365
}
```

命令输出的 `OC_WORKER_TOKEN=...` 明文只显示一次。把该值保存到 Agent/Harness 的 `OPENCONTRACTS_UPLOAD_WORKER_KEY`，不要写入 Git、`.mcp.json` 或 `SKILL.md`。

## 5. 配置 Windows Agent / WorkBuddy 主机

先把 `caddy-root.crt` 复制到目标 Agent：

```powershell
$agent = New-PSSession -ComputerName 'WORKBUDDY-01'

Copy-Item `
  '.\caddy-root.crt' `
  -ToSession $agent `
  -Destination 'C:\Temp\caddy-root.crt'
```

远程执行 Agent 配置脚本：

```powershell
Invoke-Command `
  -Session $agent `
  -FilePath '.\deploy\opencontracts\Configure-AgentOpenContracts.ps1' `
  -ArgumentList `
    '10.10.20.15', `
    'C:\Temp\caddy-root.crt', `
    'contracts-history', `
    'contract-templates', `
    '<WorkerKey>', `
    'Machine'
```

脚本会：

- 把 Caddy 根证书复制到固定本机目录；
- 导入 Windows Trusted Root；
- 设置 `OPENCONTRACTS_BASE_URL` 与 `OPENCONTRACTS_MCP_URL` 为固定 IP HTTPS URL；
- 设置历史合同和模板两个 Corpus slug；
- 设置 `OPENCONTRACTS_CA_BUNDLE` 和 `NODE_EXTRA_CA_CERTS`；
- 可选设置 `OPENCONTRACTS_UPLOAD_WORKER_KEY`。

长期运行的共享 WorkBuddy 主机建议 `Machine` scope；个人工作站可使用 `User` scope。修改持久环境变量后重启 WorkBuddy/CodeBuddy 进程。

## 6. 验证

OpenContracts 服务器：

```powershell
Invoke-Command -Session $session -ScriptBlock {
    Set-Location 'D:\OpenContracts'
    docker compose -f local.yml ps
    docker ps --filter name=opencontracts-caddy
    docker logs --tail 100 opencontracts-caddy
    Get-NetTCPConnection -LocalPort 443 -State Listen
    Get-NetTCPConnection -LocalPort 8000 -State Listen
}
```

预期：

```text
443 由 Caddy 对 LAN 提供 HTTPS
8000 只绑定 127.0.0.1
```

Agent 主机：

```powershell
Invoke-Command -Session $agent -ScriptBlock {
    Test-NetConnection 10.10.20.15 -Port 443
    Invoke-WebRequest https://10.10.20.15/admin/login/ -UseBasicParsing
}
```

然后重启 WorkBuddy，确认项目根目录 `.mcp.json` 中的 `opencontracts` 服务能够连接，并能使用预期 MCP 工具。

上传 helper 验证：

```powershell
python scripts/opencontracts/check_config.py
python scripts/opencontracts/upload_document.py --file .\test.docx --title 'MVP入库测试'
```

测试上传只应在明确准备好的测试文件和历史 Corpus 上执行。

## 7. 经验沉淀与 Skill 更新

会话经验不配置 OpenContracts Corpus，也不做向量化或运行时 retrieval。当前流程是：

```text
完成合同任务
-> 用户单独同意沉淀经验
-> contract-learning 生成本地 contract-experience-note.md
-> 维护人员定期收集和审核
-> 人工修改对应 Skill
-> 正常 Git review / release
```

这部分没有额外 OpenContracts 环境变量、WorkerKey 或服务端部署步骤。

## 8. 防火墙基线

当前拓扑要求：

```text
LAN/VPN -> 服务器固定IP:443 允许
LAN/VPN -> 服务器:8000 不允许
Internet -> 服务器:443 不允许
数据库/Redis/parser/embedder -> 仅 Docker 内部网络
```

Caddy 当前只映射 443；不需要开放 80。OpenContracts 不做公网 NAT/端口转发。

## 9. 固定 IP 变更

固定 IP 是当前 MVP 的部署配置。如果服务器 IP 发生变化，需要重新执行服务端 Caddy 配置脚本，并重新运行 Agent 配置脚本，使证书、URL 和 Django `ALLOWED_HOSTS` 同步到新 IP。

完整架构关系见 `docs/architecture/c4.md`。
