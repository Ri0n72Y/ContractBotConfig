# OpenContracts Data Layout

## Principle

For the MVP, OpenContracts stores retrievable enterprise contract data. Session-learning material is intentionally kept outside OpenContracts because it is not part of runtime retrieval.

Corpus boundaries organize business data and workflow. They are not the confidentiality boundary because the OpenContracts deployment stays inside a trusted network and the corpuses remain public within that deployment.

## Recommended corpuses

### `contracts-history`

Purpose: formally ingested executed/draft historical contracts used for retrieval and comparison.

Rules:

- public inside the trusted-network MVP;
- formal ingestion uses a WorkerKey bound only to this Corpus;
- project-specific values are data, never automatic defaults for new contracts.

### `contract-templates`

Purpose: enterprise-approved contract templates.

Rules:

- public inside the trusted-network MVP;
- only actual templates and related template guidance belong here;
- strict named-template requests require unique identity confirmation;
- templates may contain business text but never credentials or operational system instructions.

### `approved-knowledge`

Purpose: curated drafting/review knowledge that is intentionally useful for routine retrieval.

Rules:

- public inside the trusted-network MVP;
- contains reviewed, reusable knowledge;
- content should be concise and scoped;
- it is maintained intentionally, not automatically populated from session learning.

## Experience system outside OpenContracts

`contract-learning` produces local experience notes after separate user consent. These notes are source material for maintainers, not retrieval documents.

MVP flow:

```text
session corrections / accepted improvements
→ local contract-experience-note.md
→ manual periodic collection
→ human review / merge / generalization
→ update the relevant Skill files
→ normal code review and release
```

No Learning Inbox Corpus, vectorization, automatic retrieval, or automatic Skill self-modification is required for MVP.

## Network boundary

The deployment assumes:

```text
trusted LAN / VPN / restricted network
    ├── Harness users
    ├── WorkBuddy host
    └── OpenContracts

Internet / untrusted network
    X OpenContracts
```

If OpenContracts becomes reachable outside this boundary, or if different internal users require different confidentiality scopes, migrate the affected corpuses to private and introduce authenticated MCP access.

## Future private-corpus migration

The three retrieval corpuses can later become private without changing the Skill semantics:

```text
public MVP corpus
→ private corpus
→ explicit OpenContracts user/service permissions
→ /mcp/me/ authenticated access
```
