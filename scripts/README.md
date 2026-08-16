# 发布打包工具

`build_release.py` 只打包仓库中的 AstrBot Plugins、Skills 和 Personas。真实合同模板、企业参数、历史合同和其他业务数据不属于 release artifact。

## 使用

```bash
python scripts/build_release.py --clean
```

指定输出目录：

```bash
python scripts/build_release.py --clean --output /path/to/dist
```

## 输出

```text
dist/
├── plugins/
│   └── *.zip
├── skills/
│   └── *.zip
├── personas/
│   └── *.md
└── MANIFEST.json
```

每个插件和 Skill ZIP 都保留组件目录作为压缩包根目录，便于 AstrBot 安装器识别。Persona 输出为手动配置 Markdown。

## 数据边界

release build 不扫描、不复制、不导出任何 Generation Asset 或历史合同。业务资产由外部受控知识库独立管理，代码仓库只保存 `docs/contract-assets/README.md` 中的抽象资产协议。

## 版本来源

- Plugin 版本读取各插件的 `metadata.yaml`；
- Skill 版本读取根目录 `VERSIONS.md` 的 `## Skills` 段落；
- Persona 版本读取 `persona_<persona_id>_v<version>.json` 文件名。

## 构建校验

构建前会检查：

- Plugin 目录包含 `main.py` 和 `metadata.yaml`；
- `metadata.yaml` 包含版本；
- Skill 目录包含 `SKILL.md`；
- Persona source 和 `personas/bindings.json` 一一对应且 persona_id 唯一。

构建产物使用排序后的文件列表和固定 ZIP 时间戳，使相同源码产生稳定压缩包。`MANIFEST.json` 记录文件大小和 SHA-256。

## 排除文件

```text
.DS_Store
__pycache__
.git
*.pyc
*.pyo
*.log
*.tmp
```

## 发布步骤

1. 检查 `VERSIONS.md` 与组件 metadata；
2. 运行 `python -m compileall -q plugins scripts`；
3. 运行 `python scripts/build_release.py --clean`；
4. 检查 `dist/MANIFEST.json`，确认不存在业务资产；
5. 在 AstrBot WebUI 中安装/升级目标插件；
6. 按 `dist/personas/*.md` 更新 Persona Prompt、Tools、Skills；
7. 在受控外部知识库中独立准备 Generation Asset Corpus，并等待解析/embedding 完成；
8. 按 `docs/deployment/persona-manual-config.md` 核对 Generation Flow、DOCX Generator、Download Delivery 后执行 E2E。

## 遗留脚本

`scripts/deploy_docassemble_smoke.py` 只保留用于旧 Docassemble 链路回滚/历史排障。当前正式合同生成部署不执行该脚本。
