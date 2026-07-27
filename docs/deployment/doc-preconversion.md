# 旧版 Word `.doc` 合同预转换

## 目标

旧版二进制 Word `.doc` 不能直接交给 AstrBot 文件读取工具。否则可能产生乱码，并把不可读的二进制解码结果写入日志。合同上传又要求主人格在写入 OpenContracts 前读取正文并提取合同日期和正式标题，因此转换必须发生在 Contract File Router 和 LLM 读取之前。

## 实现

安装 `astrbot_plugin_contract_doc_preconverter-0.1.0.zip`。插件以事件优先级 `1100` 运行，高于 Contract File Router 的 `1000`。

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

AstrBot 容器必须与 Gotenberg 位于可互通的 Docker 网络。若服务名不同，在插件 WebUI 中设置完整 `converter_url`。

OpenContracts 上游 Compose 已提供 Gotenberg 服务时，可以复用同一个实例；不要求 OpenContracts 再次转换，因为 Gateway 收到的工作文件已经是 PDF。

## 失败语义

以下情况直接终止当前事件：

- Gotenberg 不可达或超时；
- HTTP 转换失败；
- 返回内容不是 PDF；
- 原文件或转换后文件超过配置大小；
- 源文件路径不可用。

客户提示固定为：

```text
暂时无法读取该旧版 Word 文件。请将文件另存为 DOCX 或 PDF 后重新上传。
```

失败后不得继续读取原始 `.doc`，也不得把转换响应正文、合同正文或二进制内容写入日志。

## 部署

重新生成发布包：

```bash
python3 -m compileall -q plugins scripts
python3 scripts/build_release.py --clean
```

安装：

```text
astrbot_plugin_contract_doc_preconverter-0.1.0.zip
```

现有 Router、Handoff、Gateway、Skills 和 Personas 无需因该功能升级版本。安装后使用真实 `.doc` 文件验证：转换成功、PDF 可读、上传成功、OpenContracts 正文与检索就绪，以及日志中没有合同全文或乱码内容。
