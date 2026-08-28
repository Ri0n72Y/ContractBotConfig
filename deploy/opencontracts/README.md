# OpenContracts + Caddy 部署流程

默认部署保持 OpenContracts 原生 `local.yml` 不变，只额外启动 Caddy。

旧版 `.doc` 的默认策略已经改为 **Harness 本地优先**：优先复用用户机器现有的 Word/Office/文档能力读取或转换。仓库中的服务器转换容器仅作为 optional fallback 保留，默认不启动，也不通过 Caddy 暴露。

## 默认拓扑

现有 OpenContracts 环境提供：

- 外部 Docker network：`legal-network`；
- Django network alias：`opencontracts-api`；
- OpenContracts 自己的其他服务。

默认 ContractBot 部署：

```text
WorkBuddy / Harness
        |
        | HTTPS
        v
Caddy :443
   |
   +---- /mcp/* ---------------------> opencontracts-api:8000
   +---- /api/imports/documents/* ---> opencontracts-api:8000
```

Caddy 通过 `legal-network` 访问 `opencontracts-api:8000`，不依赖 Compose 自动生成的 Django 容器名，也不经过宿主机映射的 8000。

## 文件

```text
deploy/opencontracts/
├── .env.example
├── opencontracts-admin.sh
├── Configure-AgentOpenContracts.ps1
├── caddy/
│   ├── compose.yml
│   ├── Caddyfile
│   └── manage.ps1
└── converter/                 # optional，不属于默认部署
    ├── Dockerfile
    ├── app.py
    ├── compose.yml
    ├── manage.ps1
    └── README.md
```

## 1. 配置默认部署

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

HISTORY_CORPUS=contracts
TEMPLATE_CORPUS=contract-templates

WORKER_NAME=contractbot-formal-ingest
WORKER_RATE_LIMIT=30
WORKER_EXPIRES_DAYS=365
```

`legal-network` 与 `opencontracts-api` 已由 OpenContracts `local.yml` 定义，不重复作为部署变量。

## 2. OpenContracts 保持原样

继续按现有方式启动 OpenContracts。

Django 保持加入：

```yaml
networks:
  default:
  legal-network:
    aliases:
      - opencontracts-api
```

本仓库不修改 OpenContracts `local.yml`。

## 3. 启动默认 Caddy

```powershell
cd deploy/opencontracts/caddy
.\manage.ps1 up
```

等价于：

```powershell
docker compose `
  --env-file ..\.env `
  -f .\compose.yml `
  up -d
```

默认 Caddyfile 只开放：

```text
/mcp/*
/api/imports/documents/*
```

其他路径返回 `404`。默认**没有** `/contract-files/convert-to-pdf` 路由。

## 4. 导出 Caddy Root CA

```powershell
.\manage.ps1 export-ca
```

默认输出：

```text
deploy/opencontracts/runtime/opencontracts-caddy-root.crt
```

将该 CA 分发给需要访问 OpenContracts 的 Harness 主机。

## 5. Agent / Harness 配置

```text
OPENCONTRACTS_BASE_URL=https://<固定内网IP>
OPENCONTRACTS_MCP_URL=https://<固定内网IP>/mcp/
OPENCONTRACTS_HISTORY_CORPUS=contracts
OPENCONTRACTS_TEMPLATE_CORPUS=contract-templates
OPENCONTRACTS_CA_BUNDLE=<本机Root CA路径>
NODE_EXTRA_CA_CERTS=<同一Root CA路径>
OPENCONTRACTS_UPLOAD_WORKER_KEY=<WorkerKey>
```

旧 `.doc` 不需要新增默认服务器配置。Skill 会先让 Harness 使用本地文档能力。

## 6. `.doc` 默认处理策略

```text
.doc
  |
  v
Harness 本地读取/转换
  |
  +-- 成功 --> 直接分析，或使用本地 PDF 工作副本入库
  |
  +-- 失败 --> optional remote converter（仅显式启用时）
                  |
                  +-- 未启用 --> 请用户提供 DOCX/PDF
```

如果 Harness 已经能可靠取得正文，分析任务无需为了统一格式再生成 PDF。

正式入库时，如果 OpenContracts 不能可靠处理源 `.doc`，应使用 Harness 本地生成的 PDF 工作副本；不要直接提交旧 `.doc`。

## 7. Optional server-side converter

`deploy/opencontracts/converter/` 保留了从旧 AstrBot 方案抽出的轻量转换代码。

如需要中央兜底，可单独启动：

```powershell
cd deploy/opencontracts/converter
.\manage.ps1 up
```

它会加入现有 `legal-network`，内部调用：

```text
gotenberg:3000/forms/libreoffice/convert
```

但 optional compose **没有宿主机 `ports:` 映射**，默认 Caddyfile **也没有转换路由**。因此仅启动该容器不会向 LAN/Harness 暴露转换能力。

如果未来明确决定启用远程 fallback，再单独增加受控 Caddy route，并给 Harness 配置完整的 `OPENCONTRACTS_CONVERTER_URL`。当前默认部署不配置该变量。

## 8. WorkerKey

正式入库 WorkerKey 继续按现有方式绑定历史合同 Corpus：

```text
opencontracts-admin.sh mint-worker-key
```

转换逻辑不接触 WorkerKey。

## 9. 日常 Caddy 操作

```powershell
.\manage.ps1 up
.\manage.ps1 logs
.\manage.ps1 export-ca
.\manage.ps1 down
```

`caddy_data` volume 保存内部 CA，普通 `down` / `up` 不会更换 CA。
