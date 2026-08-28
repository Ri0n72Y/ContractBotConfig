# OpenContracts + Caddy 部署流程

当前实际环境按以下方式部署：

- OpenContracts 继续使用现有 `local.yml`，本仓库不修改它。
- OpenContracts `django` service 已加入外部 Docker network：`legal-network`。
- `django` 在该网络上明确声明 alias：`opencontracts-api`。
- Caddy 使用独立 Docker Compose，并加入同一个 `legal-network`。
- Caddy 通过 `opencontracts-api:8000` 访问 Django，不依赖 Compose 生成的容器名，也不经过宿主机映射的 `8000:8000`。
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
opencontracts-api:8000
        |
        v
OpenContracts django
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

```powershell
cd deploy/opencontracts
Copy-Item .env.example .env
```

按实际机器修改：

```text
OPENCONTRACTS_LOCAL_YML=C:/path/to/OpenContracts/local.yml
OPENCONTRACTS_LAN_IP=10.10.20.15

CADDY_IMAGE=caddy:2-alpine
CADDY_CONTAINER_NAME=contractbot-opencontracts-caddy
CADDY_CA_OUTPUT=runtime/opencontracts-caddy-root.crt

HISTORY_CORPUS=contracts-history
TEMPLATE_CORPUS=contract-templates

WORKER_NAME=contractbot-formal-ingest
WORKER_RATE_LIMIT=30
WORKER_EXPIRES_DAYS=365
```

`OPENCONTRACTS_LAN_IP` 填 Windows 主机用于局域网访问的固定 IPv4。

`legal-network` 与 `opencontracts-api` 已经由现有 OpenContracts `local.yml` 定义，因此不作为部署变量重复填写。

## 2. OpenContracts 保持现状

继续使用现有方式启动 OpenContracts。

当前 `local.yml` 中 Django 的相关网络配置为：

```yaml
networks:
  default:
  legal-network:
    aliases:
      - opencontracts-api
```

宿主机仍可以保留：

```yaml
ports:
  - "8000:8000"
```

Caddy 不使用宿主机 8000，而是通过 Docker 网络访问 `opencontracts-api:8000`。

## 3. Caddy Compose

`caddy/compose.yml`：

```yaml
services:
  caddy:
    image: ${CADDY_IMAGE:-caddy:2-alpine}
    container_name: ${CADDY_CONTAINER_NAME:-contractbot-opencontracts-caddy}
    restart: unless-stopped
    environment:
      OPENCONTRACTS_LAN_IP: ${OPENCONTRACTS_LAN_IP}
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

volumes:
  caddy_data:
  caddy_config:
```

## 4. Caddy 路由

`Caddyfile`：

```caddy
{
    auto_https disable_redirects
    admin off
}

https://{$OPENCONTRACTS_LAN_IP} {
    tls internal

    @mcp path /mcp /mcp/*
    handle @mcp {
        reverse_proxy opencontracts-api:8000 {
            header_up Host localhost:8000
            flush_interval -1
        }
    }

    @imports path /api/imports/documents /api/imports/documents/*
    handle @imports {
        reverse_proxy opencontracts-api:8000 {
            header_up Host localhost:8000
        }
    }

    handle {
        respond 404
    }
}
```

`header_up Host localhost:8000` 保持 Django local profile 常用的 Host 值，因此无需为 Caddy 的固定 LAN IP 修改 OpenContracts 配置。

## 5. 启动 Caddy

```powershell
cd deploy/opencontracts/caddy
.\manage.ps1 up
```

等价命令：

```powershell
docker compose `
  --env-file ..\.env `
  -f .\compose.yml `
  up -d
```

Harness 使用：

```text
https://<OPENCONTRACTS_LAN_IP>/mcp/
```

正式入库使用：

```text
https://<OPENCONTRACTS_LAN_IP>/api/imports/documents/
```

## 6. 导出 Caddy Root CA

```powershell
.\manage.ps1 export-ca
```

默认输出：

```text
deploy/opencontracts/runtime/opencontracts-caddy-root.crt
```

将该 CA 分发到需要访问 OpenContracts 的 WorkBuddy / Harness 主机。

## 7. 日常操作

```powershell
.\manage.ps1 up
.\manage.ps1 logs
.\manage.ps1 export-ca
.\manage.ps1 down
```

`caddy_data` volume 保存内部 CA，普通 `down` / `up` 不会更换 CA。

## 8. Agent / Harness 配置

```text
OPENCONTRACTS_BASE_URL=https://<固定内网IP>
OPENCONTRACTS_MCP_URL=https://<固定内网IP>/mcp/
OPENCONTRACTS_HISTORY_CORPUS=contracts-history
OPENCONTRACTS_TEMPLATE_CORPUS=contract-templates
OPENCONTRACTS_CA_BUNDLE=<本机Root CA路径>
NODE_EXTRA_CA_CERTS=<同一Root CA路径>
OPENCONTRACTS_UPLOAD_WORKER_KEY=<WorkerKey>
```

Windows WorkBuddy / Harness：

```powershell
.\Configure-AgentOpenContracts.ps1 `
  -ServerIp '<固定内网IP>' `
  -CaddyRootCertificate '<opencontracts-caddy-root.crt路径>' `
  -HistoryCorpus 'contracts-history' `
  -TemplateCorpus 'contract-templates' `
  -UploadWorkerKey '<WorkerKey>' `
  -EnvironmentScope Machine
```

仓库根目录 `.mcp.json` 继续使用 `${OPENCONTRACTS_MCP_URL}`。
