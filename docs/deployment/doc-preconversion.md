# 旧版 Word `.doc` 合同预转换

## 目标

旧版二进制 Word `.doc` 不能直接交给 AstrBot 文件读取工具。否则可能产生乱码，并把不可读的二进制解码结果写入日志。合同上传又要求主人格在写入 OpenContracts 前读取正文并提取合同日期和正式标题，因此转换必须发生在 Contract File Router 和 LLM 读取之前。

## 实现

安装 `astrbot_plugin_contract_doc_preconverter-0.1.1.zip`。插件以事件优先级 `1100` 运行，高于 Contract File Router 的 `1000`。

```text
企业微信 .doc
  → DOC Preconverter
  → Gotenberg / LibreOffice
  → PDF 魔数与大小校验
  → 替换事件工作文件为 PDF
  → Contract File Router
  → Master 读取 PDF
  → Gateway 上传 PDF
  → OpenContracts PDF 解析链路
```

`.docx` 和 `.pdf` 不经过该转换插件。

## Gotenberg 配置

插件默认调用：

```text
http://gotenberg:3000/forms/libreoffice/convert
```

OpenContracts 官方 Compose 中，Gotenberg 只在 Docker bridge 网络内监听 `3000`，没有宿主机端口映射。AstrBot 能访问 `opencontracts-api` 并不能自动证明它也能解析或访问 `gotenberg`。

先确认服务存在：

```bash
docker ps --format '{{.Names}}\t{{.Status}}\t{{.Networks}}' | grep -E '(^|[[:space:]])gotenberg([[:space:]]|$)'
```

再从 AstrBot 容器确认 DNS 和健康状态：

```bash
docker exec -it <astrbot-container> python - <<'PY'
import socket
import urllib.request

print("gotenberg_ip:", socket.gethostbyname("gotenberg"))
print(urllib.request.urlopen("http://gotenberg:3000/health", timeout=5).read().decode())
PY
```

若失败，检查网络：

```bash
docker inspect <astrbot-container> --format '{{json .NetworkSettings.Networks}}'
docker inspect gotenberg --format '{{json .NetworkSettings.Networks}}'
```

持久化做法是在 AstrBot 的 Compose 中加入 Gotenberg 所在的外部网络。例如：

```yaml
services:
  astrbot:
    networks:
      - default
      - opencontracts

networks:
  opencontracts:
    external: true
    name: <OpenContracts 实际网络名>
```

修改后重建 AstrBot 容器。临时执行 `docker network connect` 只适合验证，容器重建后可能丢失。

若使用其他可达地址，在插件 WebUI 中设置完整 `converter_url`。不要把无认证的 Gotenberg 端口暴露到公网。

## 失败语义和诊断

以下情况直接终止当前事件：

- Gotenberg DNS 解析失败、拒绝连接或超时；
- HTTP 转换失败；
- 返回内容不是 PDF；
- 原文件或转换后文件超过配置大小；
- 源文件路径不可用。

0.1.1 开始，日志记录安全错误码：

```text
Contract DOC preconversion failed before routing: code=converter_dns_failed endpoint=http://gotenberg:3000/forms/libreoffice/convert
```

常见错误码：

- `converter_dns_failed`：AstrBot 容器无法解析服务名；
- `converter_connection_refused`：Gotenberg 未启动或端口不可达；
- `converter_timeout`：连接或转换超时；
- `converter_http_<status>`：Gotenberg 返回 HTTP 错误；
- `converter_returned_non_pdf`：返回体不是 PDF；
- `source_size_invalid`：原始文件为空或超过配置限制。

服务不可用时提示客户稍后重试；文件本身无法转换时提示另存为 DOCX 或 PDF。失败后不得继续读取原始 `.doc`，也不得把转换响应正文、合同正文或二进制内容写入日志。

## 部署

重新生成发布包：

```bash
python3 -m compileall -q plugins scripts
python3 scripts/build_release.py --clean
```

安装或替换：

```text
astrbot_plugin_contract_doc_preconverter-0.1.1.zip
```

现有 Router、Handoff、Gateway、Skills 和 Personas 无需因该功能升级版本。安装后使用真实 `.doc` 文件验证：转换成功、PDF 可读、上传成功、OpenContracts 正文与检索就绪，以及日志中没有合同全文或乱码内容。
