# OpenContracts + Caddy 部署流程

当前部署约定：

- OpenContracts 已存在，继续使用其自带 `local.yml` / 现有 local 启动方式；本仓库不修改 OpenContracts compose 或源码。
- OpenContracts 的 `django` service 已连接既有外部 Docker network：`legal`。
- Caddy 使用单独的 Docker Compose，并加入同一个 `legal` network，通过 `django:8000` 访问 OpenContracts。
- 对 Harness 只提供固定内网 IP 的 HTTPS：`/mcp/` 与 `/api/imports/documents/`。
- OpenContracts 只使用两个业务 Corpus：`contracts-history`、`contract-templates`。

目录：

```text
deploy/opencontracts/
├── .env.example
├── opencontracts-admin.sh
├── Configure-AgentOpenContracts.ps1
└── caddy/
    ├── compose.yml
    ├── Caddyfile
    └── manage.sh
```

## 1. 填写部署环境变量

在 OpenContracts 主机上：

```bash
cd deploy/opencontracts
cp .env.example .env
```

编辑 `.env`：

```text
OPENCONTRACTS_LOCAL_YML=/opt/OpenContracts/local.yml
OPENCONTRACTS_LAN_IP=10.10.20.15

CADDY_IMAGE=caddy:2-alpine
CADDY_CONTAINER_NAME=contractbot-opencontracts-caddy
CADDY_CA_OUTPUT=/opt/contractbot/opencontracts-caddy-root.crt

HISTORY_CORPUS=contracts-history
TEMPLATE_CORPUS=contract-templates

WORKER_NAME=contractbot-formal-ingest
WORKER_RATE_LIMIT=30
WORKER_EXPIRES_DAYS=365
```

真实 `.env` 不提交 Git。

## 2. 启动 OpenContracts

继续使用 OpenContracts 现有启动方式。本仓库不包装、不覆盖它的 `local.yml`。

例如：

```bash
docker compose -f "$OPENCONTRACTS_LOCAL_YML" up -d
```

如果现有环境使用自己的 local profile 命令，继续使用原命令即可。

## 3. 将两个 Corpus 设为 public

```bash
cd deploy/opencontracts
sh opencontracts-admin.sh publish-corpuses
```

该命令只执行：

```text
contracts-history   -> is_public=True
contract-templates  -> is_public=True
```

不创建额外 Corpus。

## 4. 启动 Caddy

Caddy Compose 直接加入既有 `legal` network：

```bash
cd deploy/opencontracts/caddy
sh manage.sh up
```

对应拓扑：

```text
WorkBuddy / Harness
        |
        | HTTPS https://<OPENCONTRACTS_LAN_IP>/mcp/
        v
Caddy :443
        |
        | Docker network: legal
        v
OpenContracts django:8000
```

Caddy 只转发：

```text
/mcp/*
/api/imports/documents/*
```

其他路径返回 404。

## 5. 导出 Caddy Root CA

```bash
cd deploy/opencontracts/caddy
sh manage.sh export-ca
```

证书写到：

```text
$CADDY_CA_OUTPUT
```

把该文件分发给需要访问 OpenContracts 的 WorkBuddy / Harness 主机。

## 6. 创建正式入库 WorkerKey

```bash
cd deploy/opencontracts
sh opencontracts-admin.sh mint-worker-key
```

该 WorkerKey 绑定 `contracts-history`。命令输出的明文 token 只保存到 Agent / Harness 的 secret 环境，不写入 `.env`、Git、`.mcp.json` 或 Skill。

Agent 最终需要：

```text
OPENCONTRACTS_BASE_URL=https://<固定内网IP>
OPENCONTRACTS_MCP_URL=https://<固定内网IP>/mcp/
OPENCONTRACTS_HISTORY_CORPUS=contracts-history
OPENCONTRACTS_TEMPLATE_CORPUS=contract-templates
OPENCONTRACTS_CA_BUNDLE=<Agent上的Caddy Root CA路径>
NODE_EXTRA_CA_CERTS=<同一CA路径>
OPENCONTRACTS_UPLOAD_WORKER_KEY=<WorkerKey>
```

## 7. 配置 Windows WorkBuddy / Harness

将导出的 Root CA 复制到 Agent 后执行：

```powershell
.\Configure-AgentOpenContracts.ps1 `
  -ServerIp '10.10.20.15' `
  -CaddyRootCertificate 'C:\Temp\opencontracts-caddy-root.crt' `
  -HistoryCorpus 'contracts-history' `
  -TemplateCorpus 'contract-templates' `
  -UploadWorkerKey '<WorkerKey>' `
  -EnvironmentScope Machine
```

脚本会导入 CA 并写入 WorkBuddy / Harness 运行所需环境变量。之后重启 WorkBuddy / CodeBuddy 进程。

仓库根目录 `.mcp.json` 使用：

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

## 日常 Caddy 操作

```bash
sh caddy/manage.sh up
sh caddy/manage.sh logs
sh caddy/manage.sh export-ca
sh caddy/manage.sh down
```

OpenContracts 本身继续由它自己的 `local.yml` 生命周期管理。
