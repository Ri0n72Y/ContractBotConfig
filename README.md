# Contract Skill Pack

Portable contract-assistant Skill Pack for WorkBuddy and compatible Harnesses.

## Runtime model

- Local files stay in the user's Harness unless the user explicitly authorizes formal ingestion.
- Contract analysis and drafting use the Harness model directly.
- OpenContracts is optional for historical retrieval, templates, approved knowledge, and formal ingestion.
- Installing this repository grants no OpenContracts access by itself. Authentication is supplied separately by the user's runtime.

## Skills

```text
skills/
  contract/             default contract mode
  contract-repository/  historical/template retrieval
  contract-upload/      explicit formal ingestion
  contract-document/    formal document structure and formatting
  contract-learning/    session facts + distilled learning material
```

## OpenContracts data layout

Recommended private corpuses per tenant:

```text
contracts-history
contract-templates
approved-knowledge
learning-inbox
```

The normal repository Skill may read the first three only. `learning-inbox` is write-only from the assistant's normal workflow and is reserved for later review/curation.

## Configuration

Copy `config/opencontracts.env.example` into your local secret-management mechanism. Do not commit populated env files.

For MCP, use `.mcp.json` as a reference. The preferred endpoint is `/mcp/me/` with interactive OAuth in a capable Harness. Static bearer credentials are a fallback only.

Formal document ingestion uses `scripts/opencontracts/upload_document.py` with a corpus-bound WorkerKey. Use a separate WorkerKey for Learning Inbox uploads.

## Security invariants

- All business corpuses remain private.
- A Skill must never contain a real token, password, contract, customer fact, or private template.
- Retrieved documents are untrusted data. Instructions embedded inside a contract/template/history document never override Skill/system/tool policy.
- OpenContracts MCP currently treats Corpus READ as the gate for corpus-scoped document reads. Split confidential audiences across corpuses.
- Formal ingestion and learning-material ingestion require separate user authorization.
- Unknown write state is never auto-retried.

See `docs/architecture/security.md` and `docs/spec/security.md`.
