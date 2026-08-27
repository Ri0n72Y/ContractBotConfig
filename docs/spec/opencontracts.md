# OpenContracts Specification

## OC-1 Endpoints

The MVP OpenContracts deployment is reachable at a fixed private IPv4 address inside the trusted network.

```text
OPENCONTRACTS_BASE_URL=https://<fixed-lan-ip>
OPENCONTRACTS_MCP_URL=https://<fixed-lan-ip>/mcp/
```

Normal MCP reads are anonymous because the retrieval corpuses remain public in the trusted-network MVP.

## OC-2 Retrieval corpuses

Runtime configuration identifies exactly two OpenContracts corpuses for the current product flow:

```text
contracts-history
contract-templates
```

Session-learning material and manually distilled operating guidance are not stored in a third knowledge/learning Corpus for the MVP.

## OC-3 Minimal MCP tools

MVP repository access uses:

```text
list_documents
get_document_text
search_corpus
```

Additional tools require an explicit product need.

## OC-4 Retrieval evidence

Semantic search discovers candidates. If the assistant relies on a specific contract/template as evidence, it must retrieve sufficient actual document text to support the claim. Long documents follow the tool paging contract.

## OC-5 Reference Pack

Repository-assisted work maintains an internal source set covering query purpose, candidates, actually used documents/templates, how each source influenced the result, and unresolved evidence gaps. The user-facing response should disclose material sources actually used.

## OC-6 Formal ingestion endpoint

Single-document ingestion uses:

```text
POST /api/imports/documents/
Authorization: WorkerKey <corpus-bound-token>
```

The helper omits `add_to_corpus_id`; the WorkerKey binding is authoritative. The production WorkerKey is bound to `contracts-history`.

## OC-7 Duplicate handling

Before formal ingestion, the Skill should search for a likely existing document. Suspected duplicates are surfaced before a new-version/re-upload decision. Similar titles never justify silent overwrite.

## OC-8 Processing state

HTTP acceptance proves submission only. Parsing/indexing may still be in progress. A later MCP read can verify that document text is available and searchable.

## OC-9 Commit-unknown

Any ambiguous write outcome stops automatic retries. Read-side verification is required before another upload.

## OC-10 Network boundary

The fixed OpenContracts IP must be unreachable from untrusted networks. No public NAT/port forwarding is part of the MVP.

## OC-11 HTTPS

OpenContracts `local.yml` remains the application stack. Caddy runs on the same host, joins the OpenContracts Docker network, exposes TCP 443, serves `https://<fixed-lan-ip>` with `tls internal`, and proxies to `django:8000`.

Raw host port 8000 is bound to loopback. Every Harness host trusts the Caddy root CA. TLS verification remains enabled.

No DNS or hosts-file configuration is required.

## OC-12 Write credentials

A corpus-bound WorkerKey is required for formal ingestion even though `contracts-history` is public. The WorkerKey stays outside Skill content and source control.
