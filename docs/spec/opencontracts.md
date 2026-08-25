# OpenContracts Specification

## OC-1 Endpoints

The configured base URL identifies one tenant-authorized OpenContracts deployment.

Preferred MCP URL:

```text
https://<host>/mcp/me/
```

The public anonymous `/mcp/` endpoint MUST NOT be used for private enterprise contract corpuses.

## OC-2 Retrieval corpuses

Runtime configuration identifies separate private corpuses for:

```text
history
templates
approved knowledge
learning inbox
```

`contract-repository` MUST NOT discover or read Learning Inbox.

## OC-3 Minimal MCP tools

MVP repository access uses:

```text
list_documents
get_document_text
search_corpus
```

Additional tools require an explicit product need and security review.

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

After an accepted upload, the user MUST be told that parsing/indexing is still processing. A later read-side check MAY confirm the document is searchable.

## OC-10 Commit-unknown

Any ambiguous write outcome MUST stop automatic retries. The next safe action is read-side verification.

## OC-11 Corpus security

MCP access follows OpenContracts' current corpus-as-gate semantics for pipeline-facing document reads. Deployment design MUST therefore place documents with different confidentiality requirements in separate corpuses.

## OC-12 Server configuration

Internet-facing production deployments SHOULD:

- enable HTTPS;
- use Auth0/OIDC/SSO where appropriate or strong non-default local credentials;
- keep business corpuses private;
- configure MCP public base URL and allowed origins intentionally;
- rate-limit import endpoints at the reverse proxy;
- create revocable, expiring, rate-limited WorkerKeys;
- retain operational audit logs needed for incident response.
