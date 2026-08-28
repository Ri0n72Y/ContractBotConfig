# OpenContracts + Caddy 部署流程

当前实际环境按以下方式部署：

- OpenContracts 已经运行，继续使用它现有的 `local.yml`；本仓库不修改 OpenContracts compose 或源码。
- Django 容器名：`opencontracts-django-1`。
- Django 已加入现有 Docker bridge network：`legal-network`。
- Caddy 使用独立 Docker Compose，并加入同一个 `legal-network`。
- Caddy 直接通过 Docker DNS 访问 `opencontracts-django-1:8000`，不经过宿主机映射的 `0.0.0.0:8000`。
- Harness 通过固定内网 IP 的 HTTPS 访问 `/mcp/` 与 `/api/imports/documents/`。

实际链路：

```text
WorkBuddy / Harness
        |
        | HTTPS https://<固定内网IP>/mcp/
        v
Caddy :443
        |
        | legal-network
        v
opencontracts-django-1:8000
```

## 文件

```text
deploy/opencontracts/
├── .env.example
├── opencontracts-admin.sh
├── Configure-AgentOpenContracts.ps1
└── caddy/
    ├── compose.yml
    ├── Caddyfile
    └── manage.ps1
```

## 1. 配置 `.env`

在仓库的 `deploy/opencontracts` 目录复制：

```powershell
Copy-Item .env.example .env
```

按实际机器修改 `.env`：

```text
OPENCONTRACTS_LOCAL_YML=C:/path/to/OpenContracts/local.yml
OPENCONTRACTS_LAN_IP=10.10.20.15
OPENCONTRACTS_UPSTREAM=opencontracts-django-1:8000

CADDY_IMAGE=caddy:2-alpine
CADDY_CONTAINER_NAME=contractbot-opencontracts-caddy
CADDY_CA_OUTPUT=runtime/opencontracts-caddy-root.crt

HISTORY_CORPUS=contracts-history
TEMPLATE_CORPUS=contract-templates

WORKER_NAME=contractbot-formal-ingest
WORKER_RATE_LIMIT=30
WORKER_EXPIRES_DAYS=365
```

其中 `OPENCONTRACTS_LAN_IP` 填 OpenContracts 所在 Windows 主机实际用于局域网访问的固定 IPv4。

`legal-network` 和 `opencontracts-django-1` 已经是当前环境的既定网络/容器名称，因此 Caddy Compose 直接使用它们。

## 2. OpenContracts 保持现状

继续使用现有方式启动 OpenContracts。Caddy 配置不会启动、停止或修改 OpenContracts。

当前 Caddy 只依赖：

```text
Docker network: legal-network
Django endpoint: opencontracts-django-1:8000
```

虽然 Django 同时映射了宿主机 `8000:8000`，Caddy 不使用这个宿主机端口。

## 3. Caddy Compose

`caddy/compose.yml` 的关键部分：

```yaml
services:
  caddy:
    image: ${CADDY_IMAGE:-caddy:2-alpine}
    container_name: ${CADDY_CONTAINER_NAME:-contractbot-opencontracts-caddy}
    restart: unless-stopped
    environment:
      OPENCONTRACTS_LAN_IP: ${OPENCONTRACTS_LAN_IP}
      OPENCONTRACTS_UPSTREAM: ${OPENCONTRACTS_UPSTREAM}
    ports:
      - "${OPENCONTRACTS_LAN_IP}:443:443/tcp"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    networks:
      - legal-network

networks:
  legal-network:
    external: true
    name: legal-network
```

这会让 Caddy 成为 `legal-network` 的另一个容器成员，与 `opencontracts-django-1` 直接通信。

## 4. Caddy 路由

`Caddyfile` 使用固定 IP 的内部 CA 证书，并只代理 Contract Skill Pack 需要的入口：

```caddy
{
    auto_https disable_redirects
    admin off
}

https://{$OPENCONTRACTS_LAN_IP} {
    tls internal

    @mcp path /mcp /mcp/*
    handle @mcp {
        reverse_proxy {$OPENCONTRACTS_UPSTREAM} {
            header_up Host localhost:8000
            flush_interval -1
        }
    }

    @imports path /api/imports/documents /api/imports/documents/*
    handle @imports {
        reverse_proxy {$OPENCONTRACTS_UPSTREAM} {
            header_up Host localhost:8000
        }
    }

    handle {
        respond 404
    }
}
```

`header_up Host localhost:8000` 让请求进入 Django 时保持 local profile 常见的 Host 值，不需要因为 Caddy 的固定 LAN IP 去改 OpenContracts 配置。

## 5. 启动 Caddy

在 PowerShell 中：

```powershell
cd deploy/opencontracts/caddy
.\manage.ps1 up
```

等价的 Docker Compose 命令是：

```powershell
docker compose `
  --env-file ..\.env `
  -f .\compose.yml `
  up -d
```

Caddy 对外地址：

```text
https://<OPENCONTRACTS_LAN_IP>/mcp/
```

正式入库地址：

```text
https://<OPENCONTRACTS_LAN_IP>/api/imports/documents/
```

## 6. 导出 Caddy Root CA

```powershell
.\manage.ps1 export-ca
```

默认写到：

```text
deploy/opencontracts/runtime/opencontracts-caddy-root.crt
```

该证书需要复制到使用 OpenContracts MCP 的 WorkBuddy / Harness 主机。

## 7. Caddy 日常操作

```powershell
.\manage.ps1 up
.\manage.ps1 logs
.\manage.ps1 export-ca
.\manage.ps1 down
```

Caddy 的 `caddy_data` volume 会保存内部 CA，因此普通 `down` / `up` 不会重新生成一套新的 CA。

## 8. Agent / Harness 配置

最终 Agent 侧使用：

```text
OPENCONTRACTS_BASE_URL=https://<固定内网IP>
OPENCONTRACTS_MCP_URL=https://<固定内网IP>/mcp/
OPENCONTRACTS_HISTORY_CORPUS=contracts-history
OPENCONTRACTS_TEMPLATE_CORPUS=contract-templates
OPENCONTRACTS_CA_BUNDLE=<本机Root CA路径>
NODE_EXTRA_CA_CERTS=<同一Root CA路径>
OPENCONTRACTS_UPLOAD_WORKER_KEY=<WorkerKey>
```

Windows WorkBuddy / Harness 可以继续使用：

```powershell
.\Configure-AgentOpenContracts.ps1 `
  -ServerIp '<固定内网IP>' `
  -CaddyRootCertificate '<opencontracts-caddy-root.crt路径>' `
  -HistoryCorpus 'contracts-history' `
  -TemplateCorpus 'contract-templates' `
  -UploadWorkerKey '<WorkerKey>' `
  -EnvironmentScope Machine
```

仓库根目录 `.mcp.json` 仍然使用 `${OPENCONTRACTS_MCP_URL}`。
