# System Context

## Goal

Provide a portable contract-assistant capability that can be installed into WorkBuddy or another capable Harness. The Harness owns the conversational runtime, local files, model access, and user experience. OpenContracts provides optional enterprise knowledge and controlled ingestion.

The MVP assumes OpenContracts is deployed inside a trusted LAN/VPN/restricted network domain. Read-side access uses public corpuses over the anonymous MCP endpoint; formal writes remain WorkerKey-authenticated.

## Context

```mermaid
flowchart LR
    U[User]
    H[WorkBuddy / Harness]
    S[Contract Skill Pack]
    L[Local Files / Artifacts]
    N[Trusted Network]
    P[HTTPS Proxy / Traefik]
    M[OpenContracts MCP /mcp/]
    R[Public-in-deployment Corpuses]
    W[WorkerKey upload helper]

    U --> H --> S
    S --> L
    S -->|historical retrieval when requested/approved| N --> P --> M --> R
    S -->|explicit formal ingestion| W --> N --> P --> R
    S -->|explicit learning consent| W
```

## Runtime ownership

The Harness owns:

- intent recognition and Skill loading;
- model/provider/token costs;
- local attachment access;
- local document editing and artifact creation;
- conversation state;
- WorkBuddy WeChat/customer-service integration when used.

The Skill Pack owns:

- contract-mode behavior;
- when to suggest historical retrieval;
- source/evidence handling;
- formal ingestion consent rules;
- contract document conventions;
- learning-material distillation and consent;
- safe helper scripts for deterministic remote writes.

OpenContracts owns:

- stored contracts/templates/knowledge;
- extraction and retrieval;
- public MCP read service for the trusted-network MVP;
- WorkerKey-bound ingestion;
- server-side processing/audit data available in the deployment.

Infrastructure owns:

- LAN/VPN/restricted-domain reachability;
- DNS;
- HTTPS certificate termination;
- firewall rules preventing untrusted-network access.

## Skill map

```text
contract
├── contract-repository
├── contract-upload
├── contract-document
└── contract-learning
```

`contract` is the normal entry for contract/tender/agreement work. Other Skills are loaded only when needed.

## Default behavior

### Local-first analysis

```text
uploaded contract/tender
→ contract
→ analyze with current Harness
→ answer user
→ when useful, offer historical comparison
```

No OpenContracts access is required for basic local analysis.

### Database-assisted drafting

```text
user asks to draft
→ contract
→ gather current facts
→ optionally suggest enterprise history/template retrieval
→ user agrees or already requested it
→ contract-repository
→ anonymous MCP over trusted network
→ Reference Pack
→ draft
→ contract-document
→ local artifact
```

### Formal ingestion

```text
local/generated contract
→ explicit user ingestion intent
→ contract-upload
→ duplicate check via MCP
→ corpus-bound WorkerKey helper
→ submitted/processing feedback
→ later MCP verification
```

### Learning

```text
valuable corrections in completed session
→ suggest learning capture
→ separate user consent
→ session facts
→ knowledge points
→ Learning Inbox WorkerKey
→ later curation process
```

## Future hardening

When the trusted-network assumption no longer holds, keep the same Skill architecture and harden OpenContracts separately:

```text
public corpuses + /mcp/
→ private corpuses + /mcp/me/
→ per-user/service OAuth/Bearer permissions
```

## Removed architecture

The active design has no Master/Operator/Builder Persona contract, AstrBot handoff policy, File Router state machine, Result Guard, Generation Flow, Draft Store, or AstrBot plugin lifecycle. The frozen `astrbot-solution` branch remains the historical implementation reference.
