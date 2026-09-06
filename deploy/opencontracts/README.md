# OpenContracts + Caddy 部署流程

默认部署保持 OpenContracts 原生 `local.yml` 不变，只额外启动 Caddy。

旧版 `.doc` 默认由 Harness 本地处理；仓库中的服务器转换容器仅作为 optional fallback 保留，默认不启动，也不通过 Caddy 暴露。

## 默认拓扑

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

OpenContracts `django` 已在外部 Docker network `legal-network` 上提供 `opencontracts-api` alias。Caddy 加入同一网络并直接使用 `opencontracts-api:8000`。

## 文件

```text
deploy/opencontracts/
├── .env.example
├── opencontracts-admin.ps1
├── opencontracts-admin.sh
├── Prepare-WindowsClientBundle.ps1
├── Configure-AgentOpenContracts.ps1
├── client/
│   └── Install-ContractBot.ps1
├── caddy/
│   ├── compose.yml
│   ├── Caddyfile
│   └── manage.ps1
└── converter/                 # optional，不属于默认部署
```

Windows 主机优先使用 PowerShell 脚本。

## 1. 配置部署参数

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

## 2. OpenContracts 初始化

OpenContracts 继续按原生 `local.yml` 启动。本仓库不修改其 Compose 文件。

当前 OpenContracts 镜像在 `/entrypoint` 中根据 `POSTGRES_*` 构造 `DATABASE_URL`，因此管理脚本统一通过：

```text
django /entrypoint python manage.py ...
```

执行 Django 管理命令。

新数据库初始化：

```powershell
cd deploy/opencontracts
.\opencontracts-admin.ps1 create-corpuses
.\opencontracts-admin.ps1 publish-corpuses
```

创建：

```text
contracts-history
contract-templates
```

`create-corpuses` 是幂等操作，并调用 `CorpusService.grant_creator_permissions()` 补齐 creator 权限。

如果还没有正式入库 WorkerKey：

```powershell
.\opencontracts-admin.ps1 mint-worker-key
```

保存输出的 plaintext WorkerKey。新数据库应重新签发 WorkerKey。

# 推荐 Windows 部署流程

OpenContracts 配置完成后，管理员和普通用户都不再需要手工编辑 MCP JSON、Corpus 名称或 CA 环境变量。

## 3. 管理员：生成 Windows 客户端安装包

管理员只需要运行：

```powershell
cd deploy/opencontracts
.\Prepare-WindowsClientBundle.ps1
```

脚本会提示输入 WorkerKey，输入内容不会显示在终端。随后自动完成：

1. 启动 Caddy；
2. 导出 Caddy Root CA；
3. 打包固定服务器 IP；
4. 打包 `contracts-history` / `contract-templates`；
5. 打包共享 WorkerKey；
6. 打包 `.mcp.json`；
7. 将项目 Skills 放入 CodeBuddy/WorkBuddy 工作区使用的 `.codebuddy/skills/`；
8. 打包 OpenContracts helper scripts；
9. 生成 Windows 客户端 ZIP。

默认输出：

```text
deploy/opencontracts/runtime/ContractBot-Windows.zip
```

该目录已被 `.gitignore` 排除。

如果 WorkerKey 已存在 PowerShell 变量中，也可以：

```powershell
.\Prepare-WindowsClientBundle.ps1 -WorkerKey $workerKey
```

WorkerKey 不会打印到输出。

### Caddy 单独操作

`Prepare-WindowsClientBundle.ps1` 内部使用：

```powershell
.\caddy\manage.ps1 setup
```

`setup` 等价于：

```text
up + export-ca
```

日常操作仍支持：

```powershell
.\caddy\manage.ps1 up
.\caddy\manage.ps1 logs
.\caddy\manage.ps1 export-ca
.\caddy\manage.ps1 down
```

Caddy 默认只开放：

```text
/mcp/*
/api/imports/documents/*
```

其他路径返回 `404`。

## 4. 普通 Windows 用户：一次安装

管理员将 `ContractBot-Windows.zip` 发给授权用户。

用户操作：

```powershell
Expand-Archive .\ContractBot-Windows.zip -DestinationPath "$HOME\ContractBot"
cd "$HOME\ContractBot"
.\Install-ContractBot.ps1
```

然后重启 WorkBuddy / CodeBuddy，并使用该目录作为合同工作区。

用户无需填写 Server IP、Corpus 名称、WorkerKey、MCP URL 或 CA 路径。

安装脚本自动完成：

- 将 Caddy Root CA 导入 Windows 当前用户受信任根证书；
- 设置 OpenContracts URL、Corpus、CA、WorkerKey 等运行时环境变量；
- 配置 `NODE_EXTRA_CA_CERTS`；
- 安装 Skills 到 `.codebuddy/skills/`；
- 写入 `.codebuddy/settings.local.json`：
  - 自动批准 `opencontracts` 项目 MCP；
  - 注入运行时环境变量；
  - 保留当前 MCP 工具 deny 规则；
- 写入 `.workbuddy/mcp.json`，供 WorkBuddy 项目级 MCP 使用；
- 保留项目根 `.mcp.json`，供 CodeBuddy 项目级 MCP 使用。

默认使用 Windows `CurrentUser`，普通用户不需要管理员权限。

如果希望将 ContractBot 安装到另一个专用工作区：

```powershell
.\Install-ContractBot.ps1 -TargetDirectory 'C:\Work\Contracts'
```

## 5. Windows 客户端包的安全边界

`ContractBot-Windows.zip` 包含共享正式入库 WorkerKey，因此它本身属于凭据载体：

- 只分发给授权用户；
- 不上传公开网盘；
- 不提交到 Git；
- WorkerKey 轮换后重新生成并分发客户端包。

共享 WorkerKey 可以显著降低安装和配置成本，但所有客户端共享同一个写身份。如果以后需要按用户审计、单独撤销或细粒度权限，再改为按用户/机器签发 WorkerKey。

Skill 文件本身仍然不包含 WorkerKey；密钥只进入管理员生成的部署包和用户本地运行时配置。

## 6. WorkBuddy / CodeBuddy 配置说明

CodeBuddy 当前项目级 Skills 目录为：

```text
.codebuddy/skills/
```

项目 `.mcp.json` 中定义的服务器可通过 `enabledMcpjsonServers` 预先批准。安装脚本会自动配置，不需要用户首次进入时手工批准 `opencontracts`。

WorkBuddy 项目级 MCP 同时写入：

```text
.workbuddy/mcp.json
```

因此同一个 Windows 安装包兼容当前 WorkBuddy / CodeBuddy 两种项目配置入口。

## 7. `.doc` 默认处理策略

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

## 8. Optional server-side converter

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
