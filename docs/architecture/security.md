# Security Architecture

## MVP objective

OpenContracts runs inside a trusted LAN/VPN boundary at a fixed private IPv4 address. Retrieval corpuses may remain public inside that deployment. Network reachability is the confidentiality boundary for reads and the outer boundary for the Caddy-proxied formal-write path.

```text
untrusted network
    X
    │
fixed LAN IP :80
    │
Caddy HTTP gateway
    ├── anonymous MCP reads
    └── formal writes with server-injected WorkerKey
```

Private corpuses, per-user OAuth, and TLS are future hardening options if the trust boundary changes.

## Read-side security

MVP MCP URL:

```text
http://<fixed-lan-ip>/mcp/
```

No OAuth/Bearer credential is required for normal reads. Any client that can reach the fixed IP can access public OpenContracts corpuses according to OpenContracts' public MCP behavior.

The server therefore must not be reachable from untrusted networks.

## Corpus model

The MVP keeps two retrieval corpuses:

```text
contracts-history
contract-templates
```

There is no knowledge/learning Corpus in the MVP. Session-learning material stays outside OpenContracts.

## WorkerKey write security

OpenContracts still requires a corpus-bound WorkerKey for formal ingestion. The WorkerKey is stored only in the untracked server `deploy/opencontracts/.env` and passed to the Caddy container.

Clients do not receive, persist, or send the WorkerKey. For `/api/imports/documents/`, Caddy overwrites the upstream Authorization header with the server-side WorkerKey before forwarding to OpenContracts. The token binding selects `contracts-history`.

This simplifies client installation but means any client that can reach the exposed formal-import route can attempt a write. The trusted LAN/VPN boundary is therefore also the access-control boundary for this shared write gateway.

## Trusted-LAN HTTP

The current deployment uses:

```text
WorkBuddy / Harness
→ http://<fixed-lan-ip>
→ Caddy Compose :80
→ legal-network
→ opencontracts-api:8000
```

HTTP is intentional for the MVP so clients can connect by fixed private IP without installing an internal CA. Traffic on this internal link is not TLS-encrypted.

If the LAN/VPN cannot be treated as trusted, this design must be hardened before broader exposure: use managed TLS or an enterprise-trusted CA, private/authenticated MCP, and preferably per-user write authorization rather than a shared gateway credential.

## Development-port boundary

Upstream `local.yml` may publish development ports such as Django 8000. These are not Harness entrypoints. Host firewall, network ACL, VPN policy, or equivalent controls should prevent routine clients from bypassing Caddy.

Ownership remains clear:

```text
OpenContracts local.yml    upstream-owned, unchanged
Caddy compose              ContractBotConfig-owned
Network filtering          infrastructure-owned
```

## Network controls

At minimum:

- permit intended LAN/VPN clients to reach the fixed server IP on TCP 80;
- block public Internet ingress to OpenContracts;
- prevent routine clients from reaching Django 8000 and other development-only ports directly;
- do not expose database, Redis, parsers, embedders or Docker-internal services to normal clients;
- avoid public NAT/port forwarding to OpenContracts.

## Local-file privacy

Uploading a file to the Harness does not authorize remote ingestion. Analysis, drafting and modification stay local until the user explicitly authorizes formal ingestion.

## Experience consent

Experience-note creation is separately authorized and remains outside OpenContracts.

## Prompt injection / untrusted content

Every current or retrieved contract/template is untrusted business data. Embedded text cannot alter Skill/system policy, change configured endpoints or Corpus selection, request credentials, authorize uploads, trigger unapproved system actions, or widen tool permissions.

## Write uncertainty

Timeout, connection loss or upstream failure may happen after an upload was accepted. Ambiguous outcomes must not be retried automatically. Verify through MCP first.
