# ContractBot 临时合同下载交付

## 已验证网络基线

```text
bot.ri0n72y.top
→ http://localhost:6185
→ AstrBot / Hypercorn

download.ri0n72y.top + ^/contracts/.*
→ http://localhost:6198
→ 只读合同下载服务
```

AstrBot `/AstrBot/data` 已通过 bind mount 映射到宿主机数据目录，下载发布目录：

```text
AstrBot: /AstrBot/data/public_downloads
配置值: data/public_downloads
```

Cloudflare 路由不负责 URL path rewrite，下载服务直接处理 `/contracts/...`。

## 发布链路

```text
docassemble_generate_document
→ output_path
→ publish_contract_download
→ data/public_downloads/<48-hex-token>/<safe_filename>.docx
→ https://download.ri0n72y.top/contracts/<token>/<filename>
→ 企业微信文本消息
```

Delivery 只允许发布 `allowed_source_dirs` 下的真实 DOCX，默认只允许：

```text
data/plugins_data/astrbot_plugin_docassemble_gateway/output
```

插件拒绝符号链接，不递归删除未知目录，不把 token 或下载 URL 写入长期审计。

## TTL

默认下载有效期 1800 秒；插件启动时清理过期 token 目录，并每 60 秒执行一次后台清理。

## 正式只读下载服务

生产环境使用独立 Nginx 容器，只读挂载 `public_downloads`。仓库配置：

```text
docs/deployment/contract-download-nginx.conf
```

Windows 宿主机示例：

```powershell
$Config = "<REPO>\docs\deployment\contract-download-nginx.conf"
$PublicRoot = "<ASTRBOT_DATA>\public_downloads"

docker rm -f contractbot-download-server 2>$null

docker run --detach `
  --name contractbot-download-server `
  --restart unless-stopped `
  --publish "127.0.0.1:6198:8080" `
  --mount "type=bind,source=$PublicRoot,target=/srv/contracts,readonly" `
  --mount "type=bind,source=$Config,target=/etc/nginx/conf.d/default.conf,readonly" `
  nginx:alpine
```

端口只绑定 `127.0.0.1`，公网入口通过 Cloudflare Tunnel。

## AstrBot WebUI

Delivery 配置：

```text
public_root = data/public_downloads
public_base_url = https://download.ri0n72y.top/contracts
allowed_source_dirs = [data/plugins_data/astrbot_plugin_docassemble_gateway/output]
ttl_seconds = 1800
cleanup_interval_seconds = 60
max_file_bytes = 31457280
```

`contract_docassemble_builder` 正常只绑定 4 个运行工具：

```text
list_documents
get_document_text
docassemble_generate_document
publish_contract_download
```

`docassemble_gateway_status` 与 `contract_download_delivery_status` 仅作为管理员排障工具，不绑定给 Builder。`search_corpus` 保留给 OpenContracts Operator 的独立数据库分析，不进入常态生成路径。

不得绑定 Shell、Python、python-docx、通用 HTTP 或任意文件写入工具作为后备生成/交付路径。

## 验收

正式端到端成功时，Builder 先读取真实参考正文，再取得 Docassemble Gateway `status=ready`，随后取得 Delivery `status=ready` 和 `download_url`。Master 只向客户展示公网 HTTPS URL、文件名和有效期，不展示 `output_path`。
