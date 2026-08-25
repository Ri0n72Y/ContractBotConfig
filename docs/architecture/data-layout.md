# OpenContracts Data Layout

## Principle

For the MVP, Corpus boundaries organize business data and workflow. They are not the confidentiality boundary because the OpenContracts deployment stays inside a trusted network and the corpuses remain public within that deployment.

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

Purpose: curated drafting/review knowledge suitable for routine retrieval.

Rules:

- public inside the trusted-network MVP;
- contains reviewed, reusable knowledge;
- content should be concise and scoped;
- material reaches this Corpus only through a later curation/promotion process.

### `learning-inbox`

Purpose: raw session-learning submissions awaiting review.

Rules:

- public inside the trusted-network MVP;
- normal Skill behavior must not query it during routine contract retrieval;
- a separate WorkerKey accepts writes;
- contains session facts and distilled knowledge-point materials;
- raw learning does not automatically influence production drafting/review.

Because the Corpus is public in the MVP, this Skill-level exclusion is not a confidentiality guarantee. A technically capable client on the trusted network may query the Corpus directly.

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

The existing logical split is intentionally compatible with future hardening. The same four corpuses can later become private without changing the Skill semantics:

```text
public MVP corpus
→ private corpus
→ explicit OpenContracts user/service permissions
→ /mcp/me/ authenticated access
```
