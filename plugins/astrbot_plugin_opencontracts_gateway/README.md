# OpenContracts 上传网关 0.6.0

本插件负责把 AstrBot 暂存合同写入 OpenContracts 官方文档导入端点，并保存上传审计记录。

合同发现、正文读取、语义检索和处理核验由 OpenContracts Operator 使用 corpus-scoped OpenContracts MCP 完成。Gateway 只承担 WorkerKey 写入链路。

## 职责

- 校验暂存路径、普通文件类型、文件大小和 SHA-256。
- 保留路由任务中的原始文件名。
- 验证路由器签发的重新上传确认编号。
- 使用 WorkerKey 调用 `/api/imports/documents/`。
- 标准化 `created`、`updated`、`processing`、`confirmation_required`、`blocked` 和 `failed`。
- 保存上传 receipt，供审计和运行诊断使用。

## 集成 UML

```mermaid
flowchart LR
    Operator[OpenContracts Operator]
    MCP[Corpus-scoped OpenContracts MCP]
    Gateway[OpenContracts Upload Gateway]
    FileService[FileService]
    Confirmation[ConfirmationService]
    UploadService[UploadService]
    ImportClient[ImportClient]
    ReceiptStore[ReceiptStore]
    ImportAPI[Official Document Import API]
    OC[OpenContracts]

    Operator -->|发现、正文、检索、核验| MCP
    MCP --> OC
    Operator -->|staged_path + sha256 + original_name| Gateway
    Gateway --> UploadService
    UploadService --> FileService
    UploadService --> Confirmation
    UploadService --> ImportClient
    ImportClient -->|WorkerKey + multipart| ImportAPI
    ImportAPI --> OC
    UploadService --> ReceiptStore
```

## 上传时序

```mermaid
sequenceDiagram
    participant O as OpenContracts Operator
    participant M as OpenContracts MCP
    participant G as Upload Gateway
    participant V as FileService
    participant C as ConfirmationService
    participant I as ImportClient
    participant API as OpenContracts Import API
    participant R as ReceiptStore

    O->>M: list_documents(search=原始文件名主体)
    M-->>O: 远端文档摘要
    alt 新合同或已有有效确认
        O->>G: opencontracts_upload_document
        G->>V: 校验路径、大小、SHA-256、原始文件名
        V-->>G: ValidatedFile
        opt 携带重新上传确认
            G->>C: 校验会话、文件哈希、确认编号和时效
            C-->>G: confirmed
        end
        G->>I: upload(ValidatedFile, metadata)
        I->>API: WorkerKey + multipart/form-data
        API-->>I: created / updated / error
        I-->>G: ImportResponse
        G->>R: 写入上传审计 receipt
        G-->>O: 标准化业务状态
        O->>M: get_document_text / search_corpus
        M-->>O: 处理核验结果
    end
```

## 模块结构

```text
astrbot_plugin_opencontracts_gateway/
├── main.py
├── config/
│   └── settings.py
├── domain/
│   ├── models.py
│   └── results.py
├── clients/
│   └── import_client.py
├── services/
│   ├── confirmation_service.py
│   ├── file_service.py
│   ├── import_result_service.py
│   └── upload_service.py
├── storage/
│   └── receipt_store.py
└── tests/
    ├── test_confirmation_service.py
    └── test_upload_service.py
```

`main.py` 只负责 AstrBot 生命周期和两个 LLM Tool 的注册。配置、验证、HTTP 写入和持久化分别位于独立模块。

## 配置

```text
base_url
WorkerKey（GUI 字段名 auth_token）
import_path = /api/imports/documents/
default_corpus_id
default_corpus_slug
allowed_roots
data_dir
router_state_path
max_file_bytes
timeout_seconds
confirmation_ttl_seconds
verify_tls
```

OpenContracts MCP 连接在 AstrBot MCP 管理界面配置。推荐使用目标 corpus 的 scoped endpoint：

```text
http://opencontracts-api:8000/mcp/corpus/contracts/
```

插件配置中不保存 MCP 读取凭证。

## Tool 契约

### `opencontracts_gateway_status`

返回 WorkerKey 写入配置、官方导入端点、目标 corpus、允许目录和审计 receipt 数量。

### `opencontracts_upload_document`

输入：

```text
staged_path
expected_sha256
source_filename
title
description
custom_meta
duplicate_confirmation_id
```

输出状态：

```text
processing
confirmation_required
blocked
failed
```

`complete` 由 OpenContracts Operator 在 MCP 正文读取和语义检索核验完成后产生。

## Receipt

Receipt 记录：

- 原始文件 SHA-256；
- 原始文件名；
- OpenContracts 文档 ID；
- corpus 标识；
- 服务端导入状态；
- 最近任务 ID；
- 是否使用了客户确认。

Receipt 的角色是上传审计。远端合同发现和读取结果来自 MCP。
