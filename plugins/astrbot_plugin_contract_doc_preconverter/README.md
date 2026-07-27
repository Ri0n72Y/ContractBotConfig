# 旧版 Word 合同预转换 0.1.0

本插件在 `astrbot_plugin_contract_file_router` 之前处理企业微信文件事件。发现扩展名为 `.doc` 的旧版 Word 文件时，调用 Gotenberg 的 LibreOffice 转换接口生成 PDF，并把事件中的工作文件替换为该 PDF。Router、主人格和 OpenContracts Gateway 因此只会接触转换后的 PDF。

## 执行边界

- 仅转换 `.doc`；`.docx`、`.pdf` 和其他格式保持原流程。
- 转换成功后校验响应以 `%PDF` 开头，并计算源文件与工作文件 SHA-256。
- 不把文件正文、转换响应正文或原始二进制写入日志。
- 转换失败时立即结束当前事件，提示客户另存为 DOCX 或 PDF 后重新上传。
- 转换审计写入 `conversion_audit.jsonl`，只记录文件名、哈希、工作路径、格式和状态，不记录合同正文。

## Gotenberg

默认地址：

```text
http://gotenberg:3000/forms/libreoffice/convert
```

AstrBot 容器必须能通过 Docker 网络访问该地址。若实际服务名不同，在插件 WebUI 中修改 `converter_url`。

## 安装顺序

同时安装本插件和 Contract File Router。事件优先级为 `1100`，高于 Router 的 `1000`，无需修改 Router 配置。
