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

正式 Builder 只调用：

```text
generate_and_publish_contract
```

Generation Flow 在该工具内部确定性执行：

```text
generate_contract_docx
→ output_path + output_filename + generation_id
→ publish_contract_download
→ data/public_downloads/<48-hex-token>/<safe_filename>.docx
→ https://download.ri0n72y.top/contracts/<token>/<filename>
→ finalize_contract_draft（仅发布成功后）
```

模型不再在 Generator、Delivery 与草稿持久化之间处理文件路径，因此不增加额外 LLM API 往返。DOCX 已生成但发布失败时，不会把该版本设为用户后续“修改上一版”的来源。

Delivery 只允许发布 `allowed_source_dirs` 下的真实 DOCX。迁移期默认允许：

```text
data/plugins_data/astrbot_plugin_contract_docx_generator/output
data/plugins_data/astrbot_plugin_docassemble_gateway/output
```

第一项是当前正式生成来源；第二项仅用于迁移期兼容，Docassemble 完全下线后可以删除。

DOCX Generator 的 `_drafts/` 位于同一个 output 根目录，但 Delivery 只接受 `.docx`。正式生成时要求 `generation_id + output_path + output_filename` 与当前 Generator output 一致。

同一 generation 对同一 `source_path + filename` 已经发布成功时，Delivery 0.2.4 直接返回原 publication 和原 HTTPS URL，标记 `idempotent=true`；不会重新复制文件，也不会创建新的 token 目录。Publication audit JSONL 的进程内追加写入使用线程锁。

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
allowed_source_dirs = [
  data/plugins_data/astrbot_plugin_contract_docx_generator/output,
  data/plugins_data/astrbot_plugin_docassemble_gateway/output
]
ttl_seconds = 1800
cleanup_interval_seconds = 60
max_file_bytes = 31457280
```

`contract_docassemble_builder` 的 WebUI 静态 Tools 必须为空。Generation Flow 0.6.1 在 handoff 时动态注入 `generate_and_publish_contract` 等领域工具；裸 `generate_contract_docx`、`publish_contract_download` 和内部 `finalize_contract_draft` 不直接暴露给正式 Builder。`contract_docx_generator_status` 与 `contract_download_delivery_status` 仅作为管理员排障工具。

不得绑定 Shell、Python、通用 HTTP 或任意文件写入工具作为后备生成/交付路径。

## 验收

正常新生成的最后阶段应只出现 Builder 工具：

```text
generate_and_publish_contract
→ status=ready
→ https download_url
```

内部日志可以看到 Generator → Delivery → draft finalize，但 Builder 不应再单独调用 `publish_contract_download` 或 `finalize_contract_draft`。

Delivery 返回 `status=ready`、HTTPS `download_url` 和有效期后，Builder 才返回 `[CONTRACT_GENERATION:READY]`。Master 只向客户展示公网 URL、文件名和有效期，不展示本地 `output_path`。