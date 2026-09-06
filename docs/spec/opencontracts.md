# OpenContracts Specification

## OC-1 Endpoints

The MVP OpenContracts deployment is reachable at the fixed private IPv4 address inside the trusted LAN/VPN.

```text
MCP:    https://192.168.200.69/mcp/
Import: https://192.168.200.69/api/imports/documents/
```

Normal MCP reads are anonymous because the retrieval corpuses remain public inside the trusted-network MVP.

## OC-2 Retrieval corpuses

The client Skills identify exactly two OpenContracts corpuses:

```text
contracts-history
contract-templates
```

Session-learning material is not stored in a third knowledge/learning Corpus.

## OC-3 Minimal MCP tools

MVP repository access uses:

```text
list_documents
get_document_text
search_corpus
```

Additional tools require an explicit product need.

## OC-4 Retrieval evidence

Semantic search discovers candidates. If the assistant relies on a specific contract/template as evidence, it must retrieve sufficient actual document text to support the claim.

## OC-5 Reference Pack

Repository-assisted work maintains an internal source set covering query purpose, candidates, actually used documents/templates, how each source influenced the result, and unresolved evidence gaps.

## OC-6 Formal ingestion

Single-document ingestion reaches Caddy at:

```text
POST /api/imports/documents/
```

The client sends no WorkerKey and no `add_to_corpus_id`. Caddy injects the server-side `Authorization: WorkerKey ...` header before proxying to OpenContracts. The production WorkerKey is bound to `contracts-history`, so the server-side token binding is authoritative.

## OC-7 Duplicate handling

Before formal ingestion, the Skill should search for a likely existing document. Suspected duplicates are surfaced before a new-version/re-upload decision. Similar titles never justify silent overwrite.

## OC-8 Processing state

HTTP acceptance proves submission only. Parsing/indexing may still be in progress. A later MCP read can verify that document text is available and searchable.

## OC-9 Commit-unknown

Any ambiguous write outcome stops automatic retries. Read-side verification is required before another upload.

## OC-10 Network boundary

The fixed OpenContracts IP must be unreachable from untrusted networks. No public NAT/port forwarding is part of the MVP.

## OC-11 HTTPS gateway

OpenContracts continues to use upstream `local.yml` unchanged. Its `django` service exposes the stable Docker alias `opencontracts-api` on `legal-network`. ContractBotConfig runs Caddy as a separate Compose project on the same host and network.

Caddy binds `192.168.200.69` on TCP 443, serves HTTPS with `tls internal`, proxies only `/mcp/*` and `/api/imports/documents/*`, and returns 404 for other paths.

Server-side client preparation exports Caddy's public root certificate to:

```text
client/certificates/opencontracts-caddy-root.crt
```

The installing agent trusts this certificate for the current user before using the HTTPS endpoint. The CA private key remains only in Caddy's persistent data volume.

## OC-12 Write credentials

A corpus-bound WorkerKey is required by OpenContracts for formal ingestion, but the credential stays only in the untracked server `deploy/opencontracts/.env` and Caddy runtime environment. It is never packaged into client MCP, Skills, ZIPs, certificates, or user environment variables.
