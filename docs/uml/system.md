# System UML

当前正式 ContractBot 架构，不包含 Docassemble Gateway。

```mermaid
flowchart LR
    User[企业微信用户]
    WeCom[WeCom Adapter]
    Router[Contract File Router]
    Master[Contract Master Persona]
    Handoff[Contract Handoff Policy]
    Operator[OpenContracts Operator]
    MCP[OpenContracts MCP]
    UploadGateway[OpenContracts Upload Gateway]
    ImportAPI[Official Import API]
    OpenContracts[OpenContracts]
    Builder[Contract Builder]
    Flow[Generation Flow]
    Generator[Contract DOCX Generator]
    Delivery[HTTPS Download Delivery]
    Guard[WeCom Final Result Guard]

    User --> WeCom --> Router --> Master

    Master --> Handoff --> Operator
    Operator -->|读取/搜索| MCP --> OpenContracts
    Operator -->|上传| UploadGateway -->|WorkerKey| ImportAPI --> OpenContracts

    Master --> Builder
    Handoff --> Flow --> Builder
    Builder --> Flow
    Flow -->|模板/历史只读| MCP
    Flow --> Generator --> Delivery

    Master --> Guard --> WeCom
```

## 正式路径

```text
读取：Master → Operator → OpenContracts MCP
上传：Master → Operator → OpenContracts Gateway → WorkerKey Import API → MCP 核验
生成：Master → Builder → Generation Flow → DOCX Generator → Download Delivery → Draft finalize
结果：Master → WeCom Final Result Guard → WeCom
```

Skills 只保留 `contract-direct-analysis` 和 `contract-conversation-control`；Operator 与 Builder 不绑定 Skill。
