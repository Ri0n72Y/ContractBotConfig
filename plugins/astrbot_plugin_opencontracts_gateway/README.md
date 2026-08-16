# OpenContracts 上传网关 0.6.2

本插件负责把 AstrBot 暂存合同写入 OpenContracts 官方文档导入端点，并保存追加式上传审计记录。

OpenContracts 合同库读取由 OpenContracts Operator 使用公开 MCP `/mcp/` 完成。Gateway 只承担合同身份规范化、本地文件校验、重新上传确认校验、运行中任务取消复核和 WorkerKey 文件导入。

## 职责

- 校验暂存路径、普通文件类型、文件大小和 SHA-256。
- 要求合同日期和合同标题，生成稳定远端身份。
- 保留原始文件名及扩展名，远端文件名规范为 `YYYY-MM-DD_合同标题.原扩展名`。
- 远端文档标题规范为 `YYYY-MM-DD 合同标题`。
- 验证路由器签发的重新上传确认编号。
- WorkerKey POST 前复核 Router 当前 `dispatch_task_id + source SHA-256`；用户已结束的任务不继续提交写入。
- 使用 WorkerKey 调用 `/api/imports/documents/`，写入目标由 WorkerKey 绑定。
- 标准化 `processing`、`confirmation_required`、`blocked`、`manual_review_required` 和 `failed`。
- 对传输异常、服务端 5xx、成功响应结构异常和未确认版本写入返回人工核查状态，禁止自动重试。
- 追加保存每次上传 receipt，供审计和运行诊断使用。

取消复核不是新的用户确认。它只消费 Router 已经存在的任务状态：如果用户在 HTTP 写入开始前回复“结束”，Router 会删除当前 pending task，Gateway 随后在写入边界返回 `failure_stage=task_cancelled`，不会调用导入 API。HTTP 请求已经开始后不能假装回滚远端提交，仍按实际传输结果处理。

## 集成 UML

```mermaid
flowchart LR
    Operator[OpenContracts Operator]
    MCP[OpenContracts Public MCP]
    Gateway[OpenContracts Upload Gateway]
    FileService[FileService]
    RouterState[Router State]
    Confirmation[ConfirmationService]
    UploadService[UploadService]
    ResponsePolicy[ImportResponsePolicy]
    ResultService[ImportResultService]
    ImportClient[ImportClient]
    ReceiptStore[ReceiptStore]
    ImportAPI[Official Document Import API]
    OC[OpenContracts]

    Operator -->|Corpus、文档、正文、检索| MCP
    MCP --> OC
    Operator -->|日期 + 标题 + staged_path + sha256| Gateway
    Gateway --> UploadService
    UploadService --> FileService
    UploadService --> Confirmation
    Confirmation --> RouterState
    UploadService --> ImportClient
    ImportClient -->|WorkerKey + multipart| ImportAPI
    ImportAPI --> OC
    UploadService --> ResultService
    ResultService --> ResponsePolicy
    ResultService --> ReceiptStore
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

    O->>M: 按规范化 document_title 精确查重
    M-->>O: 远端合同结果
    O->>G: date + title + staged_path + sha256
    G->>V: 校验身份、路径、大小和 SHA-256
    V-->>G: ValidatedFile + 规范化文件名
    opt 携带重新上传确认
        G->>C: 校验会话、文件哈希、确认编号和时效
        C-->>G: confirmed
    end
    G->>C: 复核当前 dispatch_task_id + source SHA-256
    C-->>G: active / cancelled
    alt task 已结束
        G-->>O: blocked / task_cancelled
    else task 仍有效
        G->>I: upload(ValidatedFile, metadata)
        I->>API: WorkerKey + multipart/form-data
        API-->>I: created / updated / error
        I-->>G: ImportResponse
        G->>R: append 上传审计 receipt
        G-->>O: 标准化业务状态
        O->>M: 读取正文并核验检索
        M-->>O: 处理结果
    end
```

## 状态图

```mermaid
stateDiagram-v2
    [*] --> IdentityValidation
    IdentityValidation --> Blocked: 日期或标题缺失
    IdentityValidation --> FileValidation: 身份有效
    FileValidation --> Blocked: 配置、路径、大小、SHA或确认无效
    FileValidation --> CancelCheck: 本地校验通过
    CancelCheck --> Blocked: task 已结束
    CancelCheck --> Importing: task 仍有效
    Importing --> Processing: created
    Importing --> Processing: updated + confirmed
    Importing --> ManualReview: updated + unconfirmed
    Importing --> ManualReview: timeout / 5xx / unexpected 2xx
    Importing --> ConfirmationRequired: 写入前路径冲突 + unconfirmed
    Importing --> Failed: 已确认未提交的请求失败
    Processing --> [*]
    ManualReview --> [*]
    ConfirmationRequired --> [*]
    Blocked --> [*]
    Failed --> [*]
```

## 模块结构

```text
astrbot_plugin_opencontracts_gateway/
├── main.py
├── config/settings.py
├── domain/models.py
├── domain/results.py
├── clients/import_client.py
├── services/confirmation_service.py
├── services/file_service.py
├── services/import_response_policy.py
├── services/import_result_service.py
├── services/upload_service.py
└── storage/receipt_store.py
```

`main.py` 只负责 AstrBot 生命周期和两个 LLM Tool 的注册。配置、验证、HTTP 写入、响应策略和持久化分别位于独立模块。

## OpenContracts MCP

Operator 使用 AstrBot 已配置的公开 MCP：

```text
/mcp/
```

上传链路使用：

```text
list_documents
get_document_text
search_corpus
```

目标 `corpus_slug` 由 Handoff Policy 的 `default_opencontracts_corpus_slug` 统一注入 Operator canonical context；Gateway 不决定读取 Corpus，也不调用 `get_corpus_info`、`opencontracts_check_duplicate` 或 `list_public_corpuses` 猜测目标。WorkerKey 自身的 Corpus 绑定决定写入目标，写入后 Operator 使用同一个 canonical `corpus_slug` 通过公开 MCP 核验实际落库状态。

## 配置

```text
base_url
WorkerKey（GUI 字段名 auth_token）
import_path = /api/imports/documents/
default_make_public
allowed_roots
data_dir
router_state_path
require_expected_sha256
max_file_bytes
timeout_seconds
confirmation_ttl_seconds
verify_tls
```

`router_state_path` 同时用于重新上传确认和写入前 task 活跃状态复核，不新增第二份 cancellation 配置。Gateway 不要求或显示配置 Corpus ID。

## Tool 契约

### `opencontracts_gateway_status`

返回 WorkerKey 是否配置、官方导入端点、允许目录和追加式 receipt 数量。

### `opencontracts_upload_document`

输入：

```text
staged_path
expected_sha256
contract_date
contract_title
source_filename
description
custom_meta
duplicate_confirmation_id
```

其中：

```text
document_title = YYYY-MM-DD 合同标题
normalized_filename = YYYY-MM-DD_合同标题.原扩展名
```

输出状态：

```text
processing
confirmation_required
blocked
manual_review_required
failed
```

`blocked + failure_stage=task_cancelled` 表示该 Router task 在 WorkerKey POST 前已经结束，没有执行本次写入。`complete` 由 OpenContracts Operator 根据 MCP 正文读取和检索结果产生。

## Receipt

Receipt 采用 append-only 记录，每次写入形成独立记录，包括：

- receipt ID 和记录时间；
- 原始文件名、规范化文件名和 SHA-256；
- 合同日期、合同标题和远端文档标题；
- OpenContracts 文档 ID 和服务端导入状态；
- 任务 ID、确认状态和 HTTP 状态；
- `write_committed`、`manual_review_required` 和 failure stage。

Receipt 只用于上传审计，不能作为远端合同存在或不存在的依据。被取消且未提交的 task 不产生远端导入 receipt。

## MVP 验证

```bash
python3 -m compileall -q plugins scripts
python scripts/build_release.py --clean
```

随后在 AstrBot WebUI 中加载插件、Skills 和 Persona，并验证首次上传、重复确认、写入前结束、人工核查和正文/检索状态。当前阶段不新增测试目录。
