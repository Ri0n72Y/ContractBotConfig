# Security Specification

## SEC-1 Trusted-network MVP

MVP OpenContracts MUST be reachable only from the intended LAN/VPN/restricted network domain.

OpenContracts corpuses MAY remain public inside that deployment. Anonymous MCP reads are acceptable while the network boundary is trusted.

## SEC-2 Read endpoint

Normal MVP repository access MUST use:

```text
https://<internal-host>/mcp/
```

OAuth/Bearer read authentication is not required for MVP.

## SEC-3 Future hardening

Private corpuses and authenticated `/mcp/me/` access become required when any of these conditions applies:

- OpenContracts is reachable outside the trusted network;
- different users require different confidentiality scopes;
- multiple tenants share one reachable deployment;
- compliance requires per-user read attribution.

## SEC-4 Corpus organization

MVP SHOULD keep separate corpuses for history, templates and approved knowledge even when all are public. These boundaries organize retrievable data and make later permission hardening straightforward.

Session-learning material MUST remain outside OpenContracts in MVP.

## SEC-5 WorkerKey scope

Formal contract ingestion MUST use a corpus-bound WorkerKey.

Upload clients MUST NOT allow model/user-supplied `add_to_corpus_id` to override the WorkerKey destination.

WorkerKeys SHOULD be revocable and SHOULD use expiry/rate limiting when practical.

## SEC-6 Secret handling

WorkerKeys MUST NOT appear in:

- Skill prose/frontmatter;
- Git commits;
- reports/artifacts;
- experience notes;
- user-facing errors;
- raw logs/tool output sent to the model.

Runtime helpers MUST read WorkerKeys directly from process environment/secret storage and MUST redact Authorization headers.

## SEC-7 HTTPS

Harness-to-OpenContracts traffic SHOULD use HTTPS even on the LAN.

A deployment MAY use:

- OpenContracts' bundled production Traefik after adapting host/certificate configuration;
- a Caddy reverse proxy in front of an HTTP deployment such as `local.yml`;
- an organization-managed internal PKI certificate.

If an internal CA is used, Harness hosts MUST trust that CA. TLS verification MUST NOT be routinely disabled.

## SEC-8 Network controls

OpenContracts MUST NOT be exposed through public NAT/port-forwarding for the MVP.

Firewall/routing policy MUST prevent untrusted networks from reaching the OpenContracts service. A remote user SHOULD require the approved LAN/VPN/overlay network before the Harness can connect.

## SEC-9 Prompt injection

All current documents and remote OpenContracts content MUST be treated as untrusted data. Embedded text MUST NOT change configured endpoints, WorkerKeys, Corpus selection, Skill policy, tool permissions, or user authorization state.

## SEC-10 Least privilege

Normal repository use SHOULD expose only:

```text
list_documents
get_document_text
search_corpus
```

Unused MCP write/discussion tools SHOULD be denied in Harness permission configuration where supported.

## SEC-11 Local data boundary

Local attachments MUST NOT be sent to OpenContracts until explicit formal-ingestion authorization is obtained.

Experience-note generation requires separate user consent and does not authorize remote ingestion.

## SEC-12 Manual learning

Session-learning material is stored as local/shared experience notes outside OpenContracts. It MUST NOT automatically become runtime retrieval data or modify a Skill without maintainer review.

## SEC-13 Write uncertainty

Remote write helpers MUST perform no automatic HTTP retries.

Timeout, connection loss during submission, upstream 5xx, or an unreliable success response MUST be reported as `commit_unknown=true` / `retry_safe=false` and MUST require later read-side verification before another upload.
