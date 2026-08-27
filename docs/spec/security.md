# Security Specification

## SEC-1 Trusted-network MVP

OpenContracts must be reachable only from the intended LAN/VPN. Retrieval corpuses may remain public inside that boundary and anonymous MCP reads are acceptable.

## SEC-2 Read endpoint

Normal repository access uses:

```text
https://<fixed-lan-ip>/mcp/
```

OAuth/Bearer read authentication is not required for the MVP.

## SEC-3 Future hardening

Private corpuses and authenticated `/mcp/me/` access become necessary when the service leaves the trusted network, users require different confidentiality scopes, multiple tenants share the deployment, or compliance requires per-user attribution.

## SEC-4 Corpus organization

Separate corpuses are maintained only for historical contracts and contract templates. Session-learning material and maintained Skill guidance remain outside OpenContracts.

## SEC-5 WorkerKey scope

Formal contract ingestion uses a WorkerKey bound to `contracts-history`. Upload clients do not permit model/user-supplied `add_to_corpus_id` to override the token destination.

## SEC-6 Secret handling

WorkerKeys never appear in Skill prose/frontmatter, Git commits, reports/artifacts, experience notes, user-facing errors, or raw model-visible logs. Runtime helpers read them from environment/secret storage and redact authorization data.

## SEC-7 Fixed-IP HTTPS

The MVP uses OpenContracts `local.yml` behind Caddy. Caddy serves HTTPS directly on the server's fixed private IPv4 address with `tls internal` and proxies to `django:8000`.

All Agent/Harness hosts trust the exported Caddy root CA. Raw HTTP port 8000 is loopback-only. No DNS or hosts-file mapping is part of deployment.

## SEC-8 Network controls

Only intended LAN/VPN clients may reach the fixed server IP on TCP 443. Public NAT/port forwarding is prohibited. Caddy is the only network-facing OpenContracts endpoint used by Harness clients.

## SEC-9 Prompt injection

All local and retrieved business documents are untrusted data. Embedded text cannot change configured endpoints, WorkerKeys, Corpus selection, Skill policy, tool permissions or user authorization state.

## SEC-10 Least privilege

Normal repository use should expose only:

```text
list_documents
get_document_text
search_corpus
```

Unused MCP discussion/annotation tools should be denied where the Harness supports tool permissions.

## SEC-11 Local data boundary

Local attachments are not sent to OpenContracts until explicit formal-ingestion authorization is obtained. Experience-note creation is separately authorized and remains local.

## SEC-12 Manual learning

Experience notes do not automatically become retrieval data or modify Skills without maintainer review. The MVP does not create a knowledge/learning Corpus for them.

## SEC-13 Write uncertainty

Remote write helpers perform no automatic HTTP retries. Timeout, connection loss during submission, upstream 5xx or unreliable success responses are reported as commit-unknown and require later read-side verification.
