# OpenContracts + Caddy + DOC Converter 部署流程

当前部署保持 OpenContracts 原生 `local.yml` 不变。本仓库只额外提供 Caddy 和一个轻量 `.doc` → PDF 适配服务。

## 实际依赖

现有 OpenContracts 环境已经提供：

- 外部 Docker network：`legal-network`；
- Django 在该网络上的 alias：`opencontracts-api`；
- Gotenberg 服务：`gotenberg:3000`。

本仓库新增：

- Caddy：固定内网 IP 的 HTTPS 入口；
- `doc-converter`：只接受旧版 `.doc`，复用现有 Gotenberg LibreOffice route 转成 PDF；
- Harness helper：把源 `.doc` 发给转换端点并保存 PDF 工作副本。

实际链路：

```text
WorkBuddy / Harness
        |
        | HTTPS
        v
Caddy :443
   |                 \
   |                  \ POST /contract-files/convert-to-pdf
   |                   v
   |              doc-converter:8080
   |                   |
   |                   | legal-network
   |                   v
   |              gotenberg:3000
   |                   |
   |                   +---- PDF ----> Harness
   |
   +---- /mcp/* ---------------------> opencontracts-api:8000
   +---- /api/imports/documents/* ---> opencontracts-api:8000
```

`doc-converter` 没有宿主机端口，不直接暴露给 LAN；只有 Caddy 的 HTTPS 路径可访问它。

## 文件

```text
deploy/opencontracts/
├── .env.example
├── opencontracts-admin.sh
├── Configure-AgentOpenContracts.ps1
├── converter/
│   ├── Dockerfile
│   └── app.py
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

DOC_CONVERTER_CONTAINER_NAME=contractbot-doc-converter
DOC_CONVERTER_TIMEOUT_SECONDS=90
DOC_CONVERTER_MAX_FILE_BYTES=104857600

HISTORY_CORPUS=contracts
TEMPLATE_CORPUS=contract-templates

WORKER_NAME=contractbot-formal-ingest
WORKER_RATE_LIMIT=30
WORKER_EXPIRES_DAYS=365
```

`OPENCONTRACTS_LAN_IP` 是 Windows 宿主机用于局域网访问的固定 IPv4。

`legal-network`、`opencontracts-api` 和 `gotenberg` 已由现有 OpenContracts 环境提供，不重复做部署变量。

## 2. OpenContracts 保持原样

继续按现有方式使用 OpenContracts `local.yml`。本仓库不修改它。

Django 的相关网络定义保持：

```yaml
networks:
  default:
  legal-network:
    aliases:
      - opencontracts-api
```

Caddy 和转换服务都加入同一个外部 `legal-network`。

## 3. Caddy + Converter Compose

`caddy/compose.yml` 同时启动两个服务：

- `caddy`：发布 `${OPENCONTRACTS_LAN_IP}:443`；
- `doc-converter`：仅在 Docker 网络内监听 `8080`，不发布宿主机端口。

转换容器使用 `deploy/opencontracts/converter/Dockerfile` 本地构建。容器中只有简单 Python HTTP 脚本及 `Flask/httpx` 运行依赖；转换本身仍由现有 Gotenberg 完成。

默认内部转换地址固定为：

```text
http://gotenberg:3000/forms/libreoffice/convert
```

## 4. Caddy 路由

Caddy 只开放当前业务需要的三个入口：

```text
/mcp/*
    -> opencontracts-api:8000

/api/imports/documents/*
    -> opencontracts-api:8000

POST /contract-files/convert-to-pdf
    -> doc-converter:8080
    -> gotenberg:3000/forms/libreoffice/convert
```

其他路径返回 `404`。

转换接口约束：

- multipart 字段名：`file`；
- 只接受扩展名 `.doc`；
- 默认最大源文件和结果文件：100 MiB；
- 默认 Gotenberg 超时：90 秒；
- Gotenberg 返回结果必须以 `%PDF` 开头；
- 不保存长期转换副本；
- 不记录正文、响应正文或原始二进制；
- 只记录安全错误码和转换哈希。

这些边界沿用旧 AstrBot `contract_doc_preconverter` 已验证的转换逻辑，但已经移除所有 AstrBot event / File component / staging 依赖。

## 5. 启动

```powershell
cd deploy/opencontracts/caddy
.\manage.ps1 up
```

`up` 会执行：

```powershell
docker compose `
  --env-file ..\.env `
  -f .\compose.yml `
  up -d --build
```

因此修改 `converter/app.py` 后再次运行 `up` 即可重新构建轻量转换容器。

## 6. 导出 Caddy Root CA

```powershell
.\manage.ps1 export-ca
```

默认输出：

```text
deploy/opencontracts/runtime/opencontracts-caddy-root.crt
```

把该 CA 分发给需要访问服务的 WorkBuddy / Harness 主机。

## 7. Agent / Harness 环境

```text
OPENCONTRACTS_BASE_URL=https://<固定内网IP>
OPENCONTRACTS_MCP_URL=https://<固定内网IP>/mcp/
OPENCONTRACTS_HISTORY_CORPUS=contracts
OPENCONTRACTS_TEMPLATE_CORPUS=contract-templates
OPENCONTRACTS_CA_BUNDLE=<本机Root CA路径>
NODE_EXTRA_CA_CERTS=<同一Root CA路径>
OPENCONTRACTS_UPLOAD_WORKER_KEY=<WorkerKey>
```

`.doc` 转换不需要额外服务器地址；helper 直接复用 `OPENCONTRACTS_BASE_URL`。

## 8. `.doc` 转换

在 Harness 工作区：

```powershell
python scripts/opencontracts/convert_doc_to_pdf.py `
  --file 'C:\path\某合同.doc'
```

默认生成：

```text
C:\path\某合同.converted.pdf
```

原 `.doc` 不覆盖。后续分析使用 PDF 工作副本。

如果用户已明确授权正式入库，则继续：

```powershell
python scripts/opencontracts/upload_document.py `
  --file 'C:\path\某合同.converted.pdf' `
  --title '某合同'
```

转换本身不是 OpenContracts 写操作，也不构成入库授权。

## 9. WorkerKey

正式入库 WorkerKey 仍按现有方式绑定历史合同 Corpus：

```text
opencontracts-admin.sh mint-worker-key
```

转换服务完全不接触 WorkerKey。

## 10. 日常操作

```powershell
.\manage.ps1 up
.\manage.ps1 logs
.\manage.ps1 export-ca
.\manage.ps1 down
```

`logs` 同时显示 Caddy 和 `doc-converter` 日志。`caddy_data` volume 保存内部 CA，普通 `down` / `up` 不会更换 CA。
