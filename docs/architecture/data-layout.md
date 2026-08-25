# OpenContracts Data Layout

## Principle

Corpus boundaries serve both business organization and MCP confidentiality. A user who can READ a Corpus through the current MCP pipeline should be assumed able to read every active document in that Corpus.

## Recommended corpuses

### `contracts-history`

Purpose: formally ingested executed/draft historical contracts that may be used for retrieval and comparison.

Rules:

- private;
- only intended contract users/hosts receive READ;
- formal ingestion uses a WorkerKey bound only to this Corpus;
- project-specific values are data, never automatic defaults for new contracts.

### `contract-templates`

Purpose: enterprise-approved contract templates.

Rules:

- private;
- only actual templates and related template guidance belong here;
- strict named-template requests require unique identity confirmation;
- templates may contain business text but never credentials or operational system instructions.

### `approved-knowledge`

Purpose: curated enterprise drafting/review knowledge that is safe for routine assistant retrieval.

Rules:

- private;
- contains reviewed, reusable knowledge;
- content should be concise and scoped;
- material reaches this Corpus only through a later curation/promotion process.

### `learning-inbox`

Purpose: raw session-learning submissions awaiting review.

Rules:

- private;
- normal assistant MCP identity has no READ;
- separate WorkerKey accepts writes;
- contains `session-facts.txt` and `knowledge-points.txt` pairs;
- raw learning does not automatically influence production drafting/review.

## Confidentiality groups

If a tenant has different populations such as legal, procurement, executive, or project teams and those populations must not see one another's documents, create separate corpuses per confidentiality group, for example:

```text
contracts-history-procurement
contracts-history-executive
```

Do not rely on private individual documents inside a broadly readable Corpus for MCP isolation.

## Cross-tenant rule

A shared OpenContracts server may host multiple tenants only when users/service accounts, corpuses, WorkerKeys, and permissions are separated per tenant. Configuration for one tenant must never contain another tenant's corpus slugs or credentials.
