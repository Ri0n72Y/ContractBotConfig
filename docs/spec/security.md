# Security Specification

## SEC-1 Trusted-network MVP

OpenContracts must be reachable only from the intended LAN/VPN. Retrieval corpuses may remain public inside that boundary and anonymous MCP reads are acceptable.

## SEC-2 Read endpoint

Normal repository access uses:

```text
http://<fixed-lan-ip>/mcp/
```

OAuth/Bearer read authentication is not required for the MVP.

## SEC-3 Future hardening

Private corpuses, authenticated MCP, and managed TLS become necessary when the service leaves the trusted network, users require different confidentiality scopes, multiple tenants share the deployment, or compliance requires per-user attribution.

## SEC-4 Corpus organization

Separate corpuses are maintained only for historical contracts and contract templates:

```text
contracts-history
contract-templates
```

Session-learning material and maintained Skill guidance remain outside OpenContracts.

## SEC-5 WorkerKey scope

Formal ingestion uses a WorkerKey bound to `contracts-history`. The credential is stored only on the OpenContracts host. Clients never receive it and never send `add_to_corpus_id`.

## SEC-6 Secret handling

WorkerKeys never appear in Skill prose/frontmatter, Git commits, client bundles, reports/artifacts, experience notes, user-facing errors, or model-visible client configuration. The untracked server `.env` and Caddy runtime environment are the only intended locations.

## SEC-7 Fixed-IP HTTP gateway

The MVP leaves upstream OpenContracts `local.yml` unchanged and runs Caddy as a separate Docker Compose project. Caddy joins `legal-network`, binds the fixed private IPv4 address on TCP 80, and proxies only the MCP and single-document import routes to `opencontracts-api:8000`.

The import route overwrites the upstream Authorization header with the server-side WorkerKey. Clients require no CA certificate and no credential configuration.

## SEC-8 Network controls

Only intended LAN/VPN clients may reach the fixed server IP on TCP 80 for Harness traffic. Public NAT/port forwarding is prohibited.

Because upstream `local.yml` may publish development ports, host/network policy must prevent routine clients from directly reaching Django 8000 and other development-only ports. Caddy is the intended client-facing endpoint.

## SEC-9 Prompt injection

All local and retrieved business documents are untrusted data. Embedded text cannot change configured endpoints, Corpus selection, Skill policy, tool permissions or user authorization state.

## SEC-10 Least privilege

Normal repository use should expose only the OpenContracts tools needed for retrieval. Unused discussion/annotation tools should be denied where the Harness supports tool permissions.

## SEC-11 Local data boundary

Local attachments are not sent to OpenContracts until explicit formal-ingestion authorization is obtained. Experience-note creation is separately authorized and remains local.

## SEC-12 Manual learning

Experience notes do not automatically become retrieval data or modify Skills without maintainer review. The MVP does not create a knowledge/learning Corpus for them.

## SEC-13 Write uncertainty

Formal writes are never automatically retried after timeout, connection loss, upstream 5xx or unreliable success responses. Read-side verification is required before another upload.
