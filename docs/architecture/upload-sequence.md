# 合同上传时序

## 新合同

```mermaid
sequenceDiagram
    participant U as 用户
    participant R as Router
    participant M as Master
    participant H as Handoff Policy
    participant O as OpenContracts Operator
    participant MCP as OpenContracts Public MCP
    participant G as Upload Gateway
    participant OC as OpenContracts
    participant RG as Result Guard

    U->>R: 上传合同文件
    R->>R: 暂存文件 + 计算 SHA-256
    R->>R: 从原文件名提取唯一日期提示
    R-->>U: 返回 1/2/提问菜单
    U->>R: 回复 1
    R->>R: 从 staged_path 本地解析合同正文
    R->>M: contract_task_context + identity_hints + transient staged 正文
    M->>M: 从正文提取标题/日期；正文日期为空时使用 filename hint
    M->>H: transfer_to_opencontracts_operator（不传 corpus_slug）
    H->>H: 使用 default_opencontracts_corpus_slug
    H->>O: canonical context + targets.opencontracts
    O->>G: opencontracts_gateway_status
    G-->>O: normalized identity
    O->>MCP: list_documents(corpus_slug, search=document_title)
    MCP-->>O: 无标题完全一致文档
    O->>G: date + title + staged_path + sha256
    G->>G: WorkerKey POST 前复核 Router task_id + source SHA
    G->>OC: WorkerKey + YYYY-MM-DD_合同标题.扩展名
    OC-->>G: created
    G-->>O: processing
    O->>MCP: list_documents + get_document_text + search_corpus
    MCP-->>O: processing 或 verified
    O-->>M: 标准状态标记
    M->>RG: 最终结果
    RG-->>U: 客户回复
```

Router 的 staged 正文解析发生在用户选择操作之后、真正 LLM 请求之前，正文以 AstrBot `_no_save` transient context 直接加入同一次请求，不增加 FileRead tool call 或额外 AI 回合，也不写入长期 conversation history。PDF 和 DOCX 解析都在线程中执行；TXT/MD 直接本地解码。`.doc` 先由 DOC Preconverter 转换。

公开 MCP 地址由 AstrBot 配置为 `/mcp/`。所有读取工具使用 Handoff Policy 写入的 `targets.opencontracts` 作为 `corpus_slug`；流程不调用 `get_corpus_info`、`opencontracts_check_duplicate` 或不存在的 corpus-scoped URL。`default_opencontracts_corpus_slug` 是唯一权威 Corpus 配置，Master handoff 和 Router task context 不覆盖它。

## 原文件名日期

```mermaid
sequenceDiagram
    participant R as Router
    participant M as Master
    participant U as 用户

    R->>R: 解析 original_name
    alt 唯一有效日期
        R->>M: identity_hints.contract_date=YYYY-MM-DD
        M->>M: 正文日期为空，直接采用提示
        Note over M,U: 不向用户追问日期
    else 无日期或多个不同日期
        R->>M: identity_hints 为空
        M-->>U: BLOCKED，询问缺失日期
    end
```

支持 `YYYY-M-D`、`YYYY.M.D`、`YYYY_M_D`、中文年月日和 `YYYYMMDD`。

## 同会话状态串行

Router 对同一 UMO 的 intake/context/cleanup 使用一个轻量 `asyncio.Lock`。文件暂存、ACK、conversation 创建、任务登记和 staged 正文快照在同一会话内按顺序完成；锁在 LLM 请求真正进入 Agent 执行前释放，不串行不同用户，也不覆盖后续 Operator/MCP 网络执行。

因此用户快速连续发送“1”“结束”或重复选择时，第二条消息不会插入第一条消息尚未登记 active task 的 await 窗口。

## 运行中“结束”

```mermaid
sequenceDiagram
    participant U as 用户
    participant R as Router
    participant O as OpenContracts Operator
    participant G as Upload Gateway
    participant OC as OpenContracts
    participant RG as Result Guard

    R->>R: pending 中保存 dispatch_task_id
    O->>O: 正在处理上传任务
    U->>R: 结束
    R->>R: 删除当前 pending task + 登记 cancelled task
    alt Gateway 尚未开始 WorkerKey POST
        O->>G: opencontracts_upload_document
        G->>G: 读取 Router state 并复核 task_id + source SHA
        G-->>O: blocked / task_cancelled
        Note over G,OC: 不发起写入
    else HTTP POST 已经开始
        G->>OC: 已在传输中的请求继续按实际结果处理
    end
    O-->>RG: 迟到结果
    RG-->>RG: 抑制已取消 task 的客户回复
```

取消保证的边界是“写入开始前”。已经开始的 HTTP 请求不能假装回滚；若提交状态未知，继续使用原有 MANUAL_REVIEW 语义。

## 远端合同已存在

```mermaid
sequenceDiagram
    participant U as 用户
    participant R as Router
    participant M as Master
    participant O as OpenContracts Operator
    participant MCP as OpenContracts Public MCP
    participant RG as Result Guard

    U->>R: 选择上传
    R->>M: transient staged 正文 + contract_task_context
    M->>O: 规范化合同身份
    O->>MCP: list_documents(corpus_slug, search=document_title)
    MCP-->>O: 标题完全一致
    O-->>M: DUPLICATE_CONFIRMATION_REQUIRED
    M->>RG: 最终状态
    RG->>R: preserve=duplicate_confirmation_required
    RG-->>U: 询问重新上传或取消
```

## BLOCKED 后恢复

```mermaid
sequenceDiagram
    participant U as 用户
    participant R as Router
    participant M as Master
    participant O as OpenContracts Operator
    participant RG as Result Guard

    M-->>RG: CONTRACT_UPLOAD:BLOCKED + 原因
    RG->>RG: 分类 missing_date / missing_title / system
    RG->>R: preserve=blocked + blocked_reason
    R->>R: state=awaiting_blocked_resolution
    R->>R: 保留 staged_path、SHA-256 和 pending
    RG-->>U: 文件已保留；补充信息或修复后回复继续
    U->>R: 日期 / 标题 / 继续
    R->>R: 重新从 staged_path 取得 transient 正文快照
    R->>M: 原文件任务上下文 + 正文 + resume.user_input
    M->>O: 继续上传流程
```

`BLOCKED` 尚未写入，因此允许复用原暂存文件。客户回复“结束”或“取消”时 Router 清理；客户发送新文件时 Router 要求先结束当前保留任务。

即使模型漏写显式 BLOCKED 标记，只要最终文本明确说明日期或标题缺失，Result Guard 仍将其识别为可恢复阻断。

## 客户确认重新上传

```mermaid
sequenceDiagram
    participant U as 用户
    participant R as Router
    participant M as Master
    participant O as OpenContracts Operator
    participant G as Upload Gateway
    participant OC as OpenContracts

    U->>R: 重新上传
    R->>R: 记录 confirmation_id 和时间
    R->>R: 复用 staged_path 取得 transient 正文快照
    R->>M: reupload task context + staged 正文
    M->>O: 同步重新上传任务
    O->>G: date + title + confirmation_id
    G->>G: 校验会话、哈希、确认编号和有效期
    G->>G: WorkerKey POST 前复核当前 task
    G->>OC: WorkerKey 文档导入
    OC-->>G: updated
    G-->>O: processing
```

## 提交状态未知

```mermaid
sequenceDiagram
    participant O as OpenContracts Operator
    participant G as Upload Gateway
    participant OC as OpenContracts
    participant RG as Result Guard
    participant U as 用户

    O->>G: opencontracts_upload_document
    G->>OC: POST /api/imports/documents/
    alt timeout / connection error
        OC--xG: 响应未知
        G-->>O: transport_commit_unknown
    else 5xx
        OC-->>G: server error
        G-->>O: upstream_commit_unknown
    else unexpected 2xx body
        OC-->>G: success status + invalid contract
        G-->>O: unexpected_success_response
    else updated without confirmation
        OC-->>G: updated
        G-->>O: unexpected_unconfirmed_update
    end
    O-->>RG: MANUAL_REVIEW
    RG-->>U: 已记录审计，请勿重复上传
```

这些路径可能已经写入，不属于可恢复 BLOCKED。Gateway 追加 receipt，Operator 禁止再次调用上传工具。

## 写入前路径冲突

只有能够确认尚未提交的路径冲突才转换为 `DUPLICATE_CONFIRMATION_REQUIRED`，并保留当前文件等待客户确认。
