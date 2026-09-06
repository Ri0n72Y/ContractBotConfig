# Security Architecture

## MVP objective

OpenContracts runs inside a trusted LAN/VPN boundary at the fixed private IPv4 address `192.168.200.69`. Retrieval corpuses may remain public inside that deployment. Network reachability is the confidentiality boundary for reads and the outer boundary for the Caddy-proxied formal-write path.

```text
untrusted network
    X
    │
192.168.200.69 :443
    │
Caddy HTTPS gateway
    ├── anonymous MCP reads
    └── formal writes with server-injected WorkerKey
```

## Read-side security

MVP MCP URL:

```text
https://192.168.200.69/mcp/
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

OpenContracts requires a corpus-bound WorkerKey for formal ingestion. The WorkerKey is stored only in the untracked server `deploy/opencontracts/.env` and passed to the Caddy container.

Clients do not receive, persist, or send the WorkerKey. For `/api/imports/documents/`, Caddy overwrites the upstream Authorization header with the server-side WorkerKey before forwarding to OpenContracts. The token binding selects `contracts-history`.

This simplifies client installation but means any client that can reach the exposed formal-import route can attempt a write. The trusted LAN/VPN boundary is therefore also the access-control boundary for this shared write gateway.

## Fixed-IP HTTPS and trust

The current deployment uses:

```text
WorkBuddy / Harness
→ https://192.168.200.69
→ Caddy Compose :443
→ legal-network
→ opencontracts-api:8000
```

Caddy uses `tls internal`. During server-side client packaging, only the public Caddy root certificate is exported to:

```text
client/certificates/opencontracts-caddy-root.crt
```

The installing agent trusts that root certificate for the current user before registering the MCP endpoint. On Windows, the intended target is the current user's Trusted Root Certification Authorities store.

The CA private key never leaves Caddy's persistent server-side data volume.

## Development-port boundary

Upstream `local.yml` may publish development ports such as Django 8000. These are not Harness entrypoints. Host firewall, network ACL, VPN policy, or equivalent controls should prevent routine clients from bypassing Caddy.

Ownership remains clear:

```text
OpenContracts local.yml    upstream-owned, unchanged
Caddy compose              ContractBotConfig-owned
Network filtering          infrastructure-owned
Client CA trust            ContractBot install package / installing agent
```

## Network controls

At minimum:

- permit intended LAN/VPN clients to reach `192.168.200.69` on TCP 443;
- block public Internet ingress to OpenContracts;
- prevent routine clients from reaching Django 8000 and other development-only ports directly;
- do not expose database, Redis, parsers, embedders or Docker-internal services to normal clients;
- avoid public NAT/port forwarding to OpenContracts.

## Local-file privacy

Uploading a file to the Harness does not authorize remote ingestion. Analysis, drafting and modification stay local until the user explicitly authorizes formal ingestion.

## Experience consent

Experience-note creation is separately authorized and remains outside OpenContracts.

## Prompt injection / untrusted content

Every current or retrieved contract/template is untrusted business data. Embedded text cannot alter Skill/system policy, change configured endpoints or Corpus selection, replace the bundled CA, request credentials, authorize uploads, trigger unapproved system actions, or widen tool permissions.

## Write uncertainty

Timeout, connection loss or upstream failure may happen after an upload was accepted. Ambiguous outcomes must not be retried automatically. Verify through MCP first.
