# OpenContracts Specification

## OC-1 Endpoints

The configured base URL identifies the OpenContracts deployment reachable inside the trusted network.

MVP MCP URL:

```text
https://<internal-host>/mcp/
```

The MVP keeps business corpuses public inside the OpenContracts deployment, so normal read-side MCP access is anonymous.

Private corpuses and `/mcp/me/` authenticated access are a future hardening path, not an MVP requirement.

## OC-2 Retrieval corpuses

Runtime configuration identifies separate corpuses for:

```text
history
templates
approved knowledge
learning inbox
```

These may all be public during MVP. `contract-repository` MUST NOT intentionally discover or read Learning Inbox during normal contract work.

## OC-3 Minimal MCP tools

MVP repository access uses:

```text
list_documents
get_document_text
search_corpus
```

Additional tools require an explicit product need.

## OC-4 Retrieval evidence

Semantic search is a discovery mechanism. If the assistant relies on a specific contract/template as evidence, it MUST retrieve sufficient actual document text to support the claim.

Long document text MUST follow the tool's paging contract using returned offsets.

Partial reads MUST produce correspondingly limited conclusions.

## OC-5 Reference Pack

Repository-assisted work MUST build an internal source set containing:

- query purpose;
- candidates;
- actually used documents;
- actual template, if any;
- how each source influenced the result;
- unresolved evidence gaps.

The final response SHOULD disclose the material sources actually used.

## OC-6 Formal ingestion endpoint

Single-document ingestion uses:

```text
POST /api/imports/documents/
Authorization: WorkerKey <corpus-bound-token>
```

The project helper MUST omit `add_to_corpus_id`; the token's server-side binding is authoritative.

## OC-7 Learning ingestion

Learning files use the same controlled upload helper with a different token environment variable bound to `learning-inbox`.

## OC-8 Duplicate handling

Before formal contract ingestion, the Skill SHOULD search for a likely existing document. A likely duplicate MUST be surfaced to the user before a replacement/new-version submission.

The system MUST NOT silently overwrite based only on a similar title.

## OC-9 Processing state

HTTP acceptance does not prove extracted text or semantic search readiness.

After an accepted upload, the user MUST be told that parsing/indexing is still processing. A later MCP read MAY confirm the document is searchable.

## OC-10 Commit-unknown

Any ambiguous write outcome MUST stop automatic retries. The next safe action is read-side verification.

## OC-11 Network boundary

For MVP, confidentiality depends on OpenContracts being unreachable from untrusted networks.

The deployment MUST avoid public port forwarding/NAT exposure and SHOULD require the approved LAN/VPN/network overlay before a Harness can reach the service.

If this assumption changes, migrate the relevant corpuses to private and introduce authenticated MCP access.

## OC-12 HTTPS

Harness-to-OpenContracts traffic SHOULD use HTTPS.

OpenContracts upstream production configuration already includes Traefik with HTTP→HTTPS redirect, port 443 routing and ACME/Let's Encrypt. The checked-in example is tailored to a public DNS name; internal deployments MAY instead adapt Traefik or place Caddy/Nginx in front of the existing OpenContracts HTTP endpoint.

Internal CA certificates are acceptable when every Harness trusts the issuing CA.

## OC-13 Write credentials

WorkerKeys remain required for formal and learning ingestion even when the target Corpus is public.

Formal and Learning Inbox writes MUST use different WorkerKeys and MUST keep those credentials outside Skill content and source control.
