# OpenContracts + Caddy 部署流程

默认部署保持 OpenContracts 原生 `local.yml` 不变，只额外启动 Caddy。

旧版 `.doc` 默认由 Harness 本地处理；仓库中的服务器转换容器仅作为 optional fallback 保留，默认不启动，也不通过 Caddy 暴露。

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
├── opencontracts-admin.ps1
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

Windows 主机优先使用 `opencontracts-admin.ps1`；`opencontracts-admin.sh` 作为 shell 环境等价入口保留。

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

HISTORY_CORPUS=contracts-history
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

### Django 管理命令与 `/entrypoint`

当前 OpenContracts 镜像在 `/entrypoint` 中根据 `POSTGRES_*` 变量构造 `DATABASE_URL`。正常 Compose 启动会执行 `/entrypoint`，但 `docker compose exec django python manage.py ...` 新建的进程不会继承 entrypoint 进程后来导出的 `DATABASE_URL`。

因此仓库中的管理脚本统一按以下形式执行 Django 管理命令：

```text
docker compose ... exec -T django /entrypoint python manage.py ...
```

## 3. 初始化 ContractBot Corpuses

新 OpenContracts 数据库先创建两个运行时 Corpus：

```text
contracts-history
contract-templates
```

Windows PowerShell：

```powershell
cd deploy/opencontracts
.\opencontracts-admin.ps1 create-corpuses
.\opencontracts-admin.ps1 publish-corpuses
```

`create-corpuses` 是幂等操作：使用第一个 superuser 作为新 Corpus 的 creator，关闭 auto branding，并调用 OpenContracts 当前的 `CorpusService.grant_creator_permissions()` 补齐 creator 的对象权限。若数据库中没有 superuser，先在 OpenContracts 中创建 superuser。

`publish-corpuses` 使用模型 `save()` 设置 public，使 OpenContracts 自己的 visibility propagation 逻辑继续生效。

## 4. 签发正式入库 WorkerKey

如果还没有 WorkerKey：

```powershell
.\opencontracts-admin.ps1 mint-worker-key
```

WorkerKey 绑定 `contracts-history`。保存 OpenContracts 输出的 plaintext WorkerKey。

新数据库需要重新签发 WorkerKey；旧机器上的 WorkerKey 不应复用。

## 5. 启动默认 Caddy

```powershell
cd deploy/opencontracts/caddy
.\manage.ps1 up
```

默认 Caddyfile 只开放：

```text
/mcp/*
/api/imports/documents/*
```

其他路径返回 `404`。

## 6. 导出 Caddy Root CA

```powershell
.\manage.ps1 export-ca
```

默认输出：

```text
deploy/opencontracts/runtime/opencontracts-caddy-root.crt
```

将该 CA 分发给需要访问 OpenContracts 的 Harness 主机。

## 7. Agent / Harness 一次性配置

`.mcp.json` 只保存 HTTP MCP 定义，并从 `OPENCONTRACTS_MCP_URL` 读取地址。正式写入使用的 WorkerKey 由 `upload_document.py` 从 `OPENCONTRACTS_UPLOAD_WORKER_KEY` 读取，因此不要把 WorkerKey 提交到版本化 `.mcp.json`。

Windows WorkBuddy / Harness 推荐一次执行：

```powershell
.\Configure-AgentOpenContracts.ps1 `
  -ServerIp '<固定内网IP>' `
  -CaddyRootCertificate '<opencontracts-caddy-root.crt路径>' `
  -UploadWorkerKey '<WorkerKey>' `
  -EnvironmentScope User
```

`contracts-history` 与 `contract-templates` 已经是脚本默认值，无需用户重复填写。

该脚本会持久设置：

```text
OPENCONTRACTS_BASE_URL
OPENCONTRACTS_MCP_URL
OPENCONTRACTS_HISTORY_CORPUS=contracts-history
OPENCONTRACTS_TEMPLATE_CORPUS=contract-templates
OPENCONTRACTS_CA_BUNDLE
NODE_EXTRA_CA_CERTS
OPENCONTRACTS_UPLOAD_WORKER_KEY
OPENCONTRACTS_ALLOW_INSECURE_HTTP=0
OPENCONTRACTS_UPLOAD_TIMEOUT_SECONDS=60
```

完成后重启 WorkBuddy / Harness，使新进程继承这些环境变量。

如果选择向多台客户端分发同一个 WorkerKey，安装最简单，但所有客户端共享同一个写身份，轮换或撤销时需要同步更新全部客户端。需要独立审计/撤销时应按机器或用户分别签发 WorkerKey。

## 8. `.doc` 默认处理策略

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

## 9. Optional server-side converter

`deploy/opencontracts/converter/` 保留轻量转换代码。如需要中央兜底，可单独启动：

```powershell
cd deploy/opencontracts/converter
.\manage.ps1 up
```

它加入现有 `legal-network`，内部调用：

```text
gotenberg:3000/forms/libreoffice/convert
```

optional compose 没有宿主机 `ports:` 映射，默认 Caddyfile 也没有转换路由。只有未来明确启用远程 fallback 时再增加受控 Caddy route 和完整的 `OPENCONTRACTS_CONVERTER_URL`。

## 10. 日常 Caddy 操作

```powershell
.\manage.ps1 up
.\manage.ps1 logs
.\manage.ps1 export-ca
.\manage.ps1 down
```

`caddy_data` volume 保存内部 CA，普通 `down` / `up` 不会更换 CA。
