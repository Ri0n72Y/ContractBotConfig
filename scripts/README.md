# 发布打包工具

`build_release.py` 将仓库中的 AstrBot Plugins、Skills 和 Personas 打包为可上传文件。

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
│   ├── astrbot_plugin_contract_file_router-0.5.0.zip
│   ├── astrbot_plugin_contract_handoff_policy-0.4.2.zip
│   ├── astrbot_plugin_opencontracts_gateway-0.5.1.zip
│   └── astrbot_plugin_wecom_final_result_guard-0.2.3.zip
├── skills/
│   ├── contract-orchestrator-1.14.zip
│   ├── contract-opencontracts-1.15.1.zip
│   └── ...
├── personas/
│   └── contract-personas.zip
└── MANIFEST.json
```

每个插件和 Skill ZIP 都保留组件目录作为压缩包根目录，便于 AstrBot 安装器识别。

## 版本来源

- Plugin 版本读取各插件的 `metadata.yaml`。
- Skill 版本读取根目录 `VERSIONS.md` 的 `## Skills` 段落。
- Persona 使用一个组合包；Persona 文件名保留自身版本。

## 构建校验

构建前会检查：

- Plugin 目录包含 `main.py` 和 `metadata.yaml`；
- `metadata.yaml` 包含版本；
- Skill 目录包含 `SKILL.md`。

构建产物使用排序后的文件列表和固定 ZIP 时间戳，使相同源码产生稳定的压缩包。`MANIFEST.json` 记录文件大小和 SHA-256。

## 排除文件

打包过程忽略：

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

1. 检查 `VERSIONS.md` 与组件 metadata。
2. 运行 `python scripts/build_release.py --clean`。
3. 检查 `dist/MANIFEST.json`。
4. 在 AstrBot WebUI 中逐个上传 `dist/plugins/` 和 `dist/skills/` 中的 ZIP。
5. 导入 Persona JSON，并在 GUI 中重新核对 Tools 和 Skills 分配。
