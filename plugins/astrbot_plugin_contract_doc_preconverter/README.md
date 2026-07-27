# 旧版 Word 合同预转换 0.1.1

本插件在 `astrbot_plugin_contract_file_router` 之前处理企业微信文件事件。发现扩展名为 `.doc` 的旧版 Word 文件时，调用 Gotenberg 的 LibreOffice 转换接口生成 PDF，并把事件中的工作文件替换为该 PDF。Router、主人格和 OpenContracts Gateway 因此只会接触转换后的 PDF。

## 执行边界

- 仅转换 `.doc`；`.docx`、`.pdf` 和其他格式保持原流程。
- 转换成功后校验响应以 `%PDF` 开头，并计算源文件与工作文件 SHA-256。
- 不把文件正文、转换响应正文或原始二进制写入日志。
- 转换失败时立即结束当前事件，不把原始 `.doc` 交给 LLM。
- 失败日志记录安全错误码和转换端点，不记录合同内容。
- 转换审计写入 `conversion_audit.jsonl`，只记录哈希、工作路径、格式、状态和错误码。

## Gotenberg

默认地址：

```text
http://gotenberg:3000/forms/libreoffice/convert
```

该地址只在 AstrBot 与 Gotenberg 位于同一 Docker 网络时可用。OpenContracts 官方 Compose 不为 Gotenberg 映射宿主机端口，因此仅能访问 `opencontracts-api` 并不代表能够访问 `gotenberg`。

从 AstrBot 容器验证：

```bash
docker exec -it <astrbot-container> python - <<'PY'
import socket
import urllib.request

print("gotenberg_ip:", socket.gethostbyname("gotenberg"))
print(urllib.request.urlopen("http://gotenberg:3000/health", timeout=5).read().decode())
PY
```

若 DNS 或连接失败，请把 AstrBot 服务加入 Gotenberg 所在的 Docker 网络，或在插件 WebUI 中把 `converter_url` 改为 AstrBot 容器实际可访问的完整地址。不要直接把 Gotenberg 暴露到公网。

## 错误码

日志示例：

```text
Contract DOC preconversion failed before routing: code=converter_dns_failed endpoint=http://gotenberg:3000/forms/libreoffice/convert
```

常见错误码：

- `converter_dns_failed`：AstrBot 容器无法解析 `gotenberg`；
- `converter_connection_refused`：服务未启动或端口不可达；
- `converter_timeout`：转换服务超时；
- `converter_http_4xx/5xx`：Gotenberg 返回 HTTP 错误；
- `converter_returned_non_pdf`：返回体不是 PDF；
- `source_size_invalid`：原始文件为空或超过大小限制。

## 安装顺序

同时安装本插件和 Contract File Router。事件优先级为 `1100`，高于 Router 的 `1000`，无需修改 Router 配置。
