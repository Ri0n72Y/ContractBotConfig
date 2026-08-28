# OpenContracts + Caddy Docker Compose 部署

当前 MVP 的服务端部署拆成两个相互独立的 Compose 项目：

```text
OpenContracts upstream checkout
└── local.yml                       # 完全使用上游文件，不修改

ContractBotConfig/deploy/opencontracts
└── caddy/compose.yml               # 本项目额外启动的 Caddy
```

目标拓扑：

```text
WorkBuddy / Harness
    |
    | HTTPS https://<固定内网IP>/mcp/
    v
Caddy :443
    |
    | Docker network
    v
OpenContracts django:8000
```

Caddy 只代理当前合同 Skill Pack 需要的：

```text
/mcp/*
/api/imports/documents/*
```

其余路径返回 404。Caddy 到 Django 的请求使用 `Host: localhost:8000`，因此无需为了固定 IP 修改 OpenContracts 的 `DJANGO_ALLOWED_HOSTS`。

## 目录

```text
deploy/opencontracts/
├── .env.example
├── opencontracts-admin.sh
├── Configure-AgentOpenContracts.ps1
├── caddy/
│   ├── compose.yml
│   ├── Caddyfile
│   └── manage.sh
└── runtime/                        # 本地生成；不提交 Git
    └── caddy-root.crt
```

## 0. 前提

服务器需要：

- Docker Engine；
- Docker Compose v2；
- 已经可以正常启动的 OpenContracts checkout；
- 一个固定内网 IPv4；
- LAN/VPN 防火墙策略。

本流程不负责安装或修改 OpenContracts。继续使用你当前的上游启动方式，例如：

```bash
cd /opt/OpenContracts
docker compose -f local.yml up -d
```

如果你本来就使用 OpenContracts 的其他 local profile/参数，保持原命令即可。Caddy 只要求 `django` service 已运行并可通过其 Compose network 访问。

## 1. 准备部署环境变量

在 ContractBotConfig checkout 中：

```bash
cd deploy/opencontracts
cp .env.example .env
```

填写：

```dotenv
OPENCONTRACTS_DIR=/opt/OpenContracts
OPENCONTRACTS_LAN_IP=10.10.20.15
OPENCONTRACTS_DOCKER_NETWORK=opencontracts_default
OPENCONTRACTS_UPSTREAM=django:8000

HISTORY_CORPUS=contracts-history
TEMPLATE_CORPUS=contract-templates

CADDY_IMAGE=caddy:2-alpine
CADDY_CONTAINER_NAME=contractbot-opencontracts-caddy

WORKER_NAME=contractbot-formal-ingest
WORKER_RATE_LIMIT=30
WORKER_EXPIRES_DAYS=365
```

`.env` 不提交 Git。WorkerKey 也不要写入这个文件。

## 2. 确认 OpenContracts Docker network

先确认 OpenContracts 已运行：

```bash
sh opencontracts-admin.sh status
```

查看 `django` 所在 Docker network：

```bash
sh opencontracts-admin.sh network
```

把输出的实际 network 名写入：

```dotenv
OPENCONTRACTS_DOCKER_NETWORK=<实际 network 名>
```

通常是 `<compose-project>_default`，但不要依赖猜测值。

Caddy Compose 将这个 network 作为 `external` network 加入，因此可以直接解析 OpenContracts service name `django`，不需要把 Django 的 8000 当成 Caddy upstream 的宿主机地址。

## 3. 准备两个 Corpus

当前运行时只使用：

```text
contracts-history
contract-templates
```

先在 OpenContracts 中创建/确认这两个 Corpus。然后运行：

```bash
sh opencontracts-admin.sh corpuses
```

脚本会：

1. 检查 `.env` 中两个 slug 是否真实存在；
2. 缺少任一 Corpus 时直接失败；
3. 将这两个 Corpus 设为 `is_public=True`。

它不会创建额外 knowledge/learning Corpus。

## 4. 启动 Caddy

```bash
cd caddy
sh manage.sh check
sh manage.sh up
```

`compose.yml` 做的事情只有：

- 启动一个独立 Caddy 容器；
- 把宿主机固定内网 IP 的 TCP 443 映射给 Caddy；
- 把 Caddy 加入现有 OpenContracts Docker network；
- 持久化 `/data` 和 `/config`，保留内部 CA；
- 读取 `Caddyfile`。

关键 Compose 配置：

```yaml
ports:
  - "${OPENCONTRACTS_LAN_IP}:443:443/tcp"

networks:
  opencontracts:
    external: true
    name: ${OPENCONTRACTS_DOCKER_NETWORK}
```

Caddyfile 通过环境变量生成站点地址和 upstream：

```caddyfile
https://{$OPENCONTRACTS_LAN_IP} {
    tls internal
    ...
    reverse_proxy {$OPENCONTRACTS_UPSTREAM}
}
```

不需要 DNS，也不需要 hosts 文件。

## 5. 导出 Caddy Root CA

Caddy 在 Docker 中使用 `tls internal` 时，客户端不会自动信任其本地 CA。导出根证书：

```bash
sh manage.sh export-ca
```

输出文件：

```text
deploy/opencontracts/runtime/caddy-root.crt
```

该证书是公开的 CA 材料，不是 WorkerKey，但仍建议按基础设施配置文件管理，不提交仓库。

测试 Caddy HTTPS：

```bash
curl --cacert ../runtime/caddy-root.crt \
  https://10.10.20.15/healthz
```

预期：

```text
ok
```

Caddy 不暴露其他 OpenContracts UI/Admin 路径。例如：

```bash
curl --cacert ../runtime/caddy-root.crt \
  -o /dev/null -w '%{http_code}\n' \
  https://10.10.20.15/admin/login/
```

预期返回 `404`。

## 6. 必须处理 OpenContracts local.yml 的开发端口暴露

本方案刻意不修改上游 `local.yml`。当前 OpenContracts upstream 的 local compose 会把 Django `8000:8000` 发布到宿主机；Flower 也会发布 `5555:5555`，使用 fullstack profile 时前端还可能发布 3000。

因此服务器或上层网络必须保证：

```text
LAN/VPN clients -> fixed-IP:443       ALLOW
LAN/VPN clients -> host:8000          DENY
LAN/VPN clients -> host:5555          DENY
Internet        -> all OpenContracts  DENY
```

如启用了 fullstack，并且前端不应供 LAN 访问，也应限制 3000。

这一步应使用你现有的宿主机防火墙、交换机 ACL、云安全组或 VPN policy。不要为了实现该策略去修改 OpenContracts `local.yml`。

验证时至少从另一台 LAN 主机执行：

```text
https://<固定IP>:443     应可达
http://<固定IP>:8000     应不可达
http://<固定IP>:5555     应不可达
```

## 7. 创建正式入库 WorkerKey

WorkerKey 只绑定 `contracts-history`。

在 `deploy/opencontracts` 下：

```bash
sh opencontracts-admin.sh mint-worker-key
```

脚本会：

1. 根据 `HISTORY_CORPUS` 找到数据库主键；
2. 调用 OpenContracts 自带 `mint_worker_token`；
3. 使用 `.env` 中的 worker name / rate limit / expiry；
4. 将 OpenContracts 生成的 plaintext token 输出一次。

示意输出：

```text
OC_WORKER_TOKEN=<secret>
OC_CORPUS_ID=<id>
```

将 `OC_WORKER_TOKEN` 保存为 Agent/Harness 的：

```text
OPENCONTRACTS_UPLOAD_WORKER_KEY
```

不要把 token 放进：

```text
Git
.mcp.json
SKILL.md
deploy/opencontracts/.env
日志/文档
```

## 8. 配置 Agent / WorkBuddy

Agent 最终需要：

```text
OPENCONTRACTS_BASE_URL=https://10.10.20.15
OPENCONTRACTS_MCP_URL=https://10.10.20.15/mcp/
OPENCONTRACTS_HISTORY_CORPUS=contracts-history
OPENCONTRACTS_TEMPLATE_CORPUS=contract-templates
OPENCONTRACTS_CA_BUNDLE=<Agent本地caddy-root.crt路径>
NODE_EXTRA_CA_CERTS=<同一个根证书路径>
OPENCONTRACTS_UPLOAD_WORKER_KEY=<WorkerKey>
```

Windows WorkBuddy 主机可以直接使用：

```powershell
.\Configure-AgentOpenContracts.ps1 `
  -ServerIp '10.10.20.15' `
  -CaddyRootCertificate 'C:\Temp\caddy-root.crt' `
  -HistoryCorpus 'contracts-history' `
  -TemplateCorpus 'contract-templates' `
  -UploadWorkerKey '<WorkerKey>' `
  -EnvironmentScope Machine
```

脚本会：

- 安装 Caddy root CA 到 Windows Trusted Root；
- 设置 MCP/base URL；
- 设置两个 Corpus slug；
- 设置 Python/Node CA 环境；
- 设置 WorkerKey（如果传入）。

修改持久环境变量后重启 WorkBuddy/CodeBuddy。

项目根目录 `.mcp.json` 已使用：

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

## 9. E2E 验证

### 服务端

```bash
cd deploy/opencontracts/caddy
sh manage.sh status
curl --cacert ../runtime/caddy-root.crt https://<固定IP>/healthz
```

查看日志：

```bash
sh manage.sh logs
```

### Agent 配置

在 ContractBotConfig 根目录：

```bash
python scripts/opencontracts/check_config.py
```

应确认：

- Base URL / MCP URL 为 HTTPS；
- history/template slug 已配置；
- CA 文件存在；
- `NODE_EXTRA_CA_CERTS` 已配置；
- 正式入库 WorkerKey 已配置。

### MCP

重启 Harness 后验证：

```text
list_documents
get_document_text
search_corpus
```

并分别确认可以读取：

```text
contracts-history
contract-templates
```

### 正式入库

仅用准备好的测试合同执行：

```bash
python scripts/opencontracts/upload_document.py \
  --file ./test.docx \
  --title 'MVP入库测试'
```

确认：

1. 请求通过 `https://<固定IP>/api/imports/documents/`；
2. 文档进入 WorkerKey 绑定的 `contracts-history`；
3. 处理完成后 MCP 可读；
4. timeout/5xx 等不确定结果不会自动重试。

## 10. 日常管理

Caddy：

```bash
cd deploy/opencontracts/caddy
sh manage.sh status
sh manage.sh logs
sh manage.sh down
sh manage.sh up
```

OpenContracts 仍完全按上游自己的方式维护：

```bash
cd /opt/OpenContracts
docker compose -f local.yml ...
```

两套 Compose 生命周期互不绑定。只要 OpenContracts Docker network 名没有变化，Caddy 不需要跟着 OpenContracts 重建。

## 11. 固定 IP / Docker network 发生变化

### IP 变化

修改：

```dotenv
OPENCONTRACTS_LAN_IP=<新IP>
```

然后：

```bash
cd caddy
sh manage.sh down
sh manage.sh up
```

Caddy 的 named volume 保留，因此内部 Root CA 通常不会变化；Agent 需要更新 Base/MCP URL。

### OpenContracts Compose project/network 变化

重新执行：

```bash
sh opencontracts-admin.sh network
```

修改：

```dotenv
OPENCONTRACTS_DOCKER_NETWORK=<新network>
```

再重启 Caddy。

## 设计边界

当前部署明确保持：

```text
OpenContracts local.yml    上游拥有，不修改
Caddy compose              ContractBotConfig 拥有
Corpus 内容/WorkerKey      OpenContracts 运行态数据
Agent env / CA trust       Harness 主机配置
Skill                      ContractBotConfig 版本化资源
```

这样 OpenContracts 可以独立升级，Caddy/Agent/Skill 配置也可以独立迭代。