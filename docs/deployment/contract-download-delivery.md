# ContractBot 临时合同下载交付

## 当前链路

```text
generate_and_publish_contract
→ generate_contract_docx
→ publish_contract_download
→ https://download.ri0n72y.top/contracts/<token>/<filename>
→ finalize_contract_draft
```

正式链只接受 Contract DOCX Generator 输出，不保留旧生成网关兼容来源。

## 网络基线

```text
bot.ri0n72y.top
→ AstrBot

download.ri0n72y.top/contracts/*
→ 只读合同下载服务
```

AstrBot 下载发布目录：

```text
data/public_downloads
```

## Delivery 0.2.5

`allowed_source_dirs` 只配置：

```text
data/plugins_data/astrbot_plugin_contract_docx_generator/output
```

默认配置：

```text
public_root = data/public_downloads
public_base_url = https://download.ri0n72y.top/contracts
allowed_source_dirs = [
  data/plugins_data/astrbot_plugin_contract_docx_generator/output
]
ttl_seconds = 1800
cleanup_interval_seconds = 60
max_file_bytes = 31457280
```

Delivery 只发布当前 generation 中已经由 DOCX Generator 验证过的 `output_path + output_filename`。不识别旧 Gateway output proof，不接受旧 Gateway output 目录，也不识别旧 `[CONTRACT_DOCASSEMBLE:READY]` 标记。

同一 generation 对同一 source/filename 已经发布成功时，幂等返回原 publication 和 HTTPS URL，不创建第二个 token 目录。

## READY / PARTIAL

完整 READY 由 Generation Flow 组合工具判定：

```text
DOCX ready
+ HTTPS publication ready
+ finalize_contract_draft ready
+ draft_saved=true
+ draft_id 非空
```

只有满足全部条件时 Builder 返回：

```text
[CONTRACT_GENERATION:READY]
```

如果 HTTPS 已发布但 Draft Store 持久化失败，组合工具返回：

```text
status=partial
delivery_committed=true
draft_saved=false
retry_safe=false
manual_recovery_required=true
```

Builder 返回 `[CONTRACT_GENERATION:PARTIAL]`，Master 仍可把已确认的下载链接交给客户，但不得声称该版本可以作为下一轮“上一版”，也不得重跑整条生成链。

写操作 timeout/cancel/commit-unknown 同样禁止自动重试。

## 下载服务

生产环境建议使用独立 Nginx 容器只读挂载 `public_downloads`。仓库配置：

```text
docs/deployment/contract-download-nginx.conf
```

Windows 示例：

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

公网入口由既有反向代理/Tunnel 提供；下载服务本身只读。

## AstrBot WebUI

Builder 静态 Tools/Skills 为空。Generation Flow 注入 `generate_and_publish_contract`，裸 `generate_contract_docx`、`publish_contract_download` 和 `finalize_contract_draft` 不直接绑定 Builder。

管理员可保留 `contract_download_delivery_status` 用于排障，但不要把它作为 Builder 正常流程工具。
