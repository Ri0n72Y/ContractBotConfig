# Security Architecture

## MVP objective

OpenContracts runs inside a trusted LAN/VPN boundary at a fixed private IPv4 address. Retrieval corpuses may remain public inside that deployment. Network reachability is the read-side confidentiality boundary.

```text
untrusted network
    X
    │
fixed LAN IP :443
    │
Caddy HTTPS
    ├── anonymous MCP reads
    └── WorkerKey-authenticated formal writes
```

Private corpuses and per-user OAuth are future hardening options.

## Read-side security

MVP MCP URL:

```text
https://<fixed-lan-ip>/mcp/
```

No OAuth/Bearer credential is required for normal reads. Any client that can reach the fixed IP can access public OpenContracts corpuses according to OpenContracts' public MCP behavior.

The server therefore must not be reachable from untrusted networks.

## Corpus model

The MVP keeps two retrieval corpuses logically separated:

```text
contracts-history
contract-templates
```

They may both remain public inside the trusted network. There is no knowledge/learning Corpus in the MVP. Session-learning material stays outside OpenContracts and is maintained as local/shared experience notes for manual Skill updates.

## WorkerKey write security

Formal ingestion uses a corpus-bound OpenContracts WorkerKey. The upload helper omits `add_to_corpus_id`; the token's server-side binding determines the destination.

WorkerKeys stay outside Skill text, Git, generated files and model-visible logs.

## HTTPS and fixed IP

The current OpenContracts deployment continues to use the upstream `local.yml` unchanged. ContractBotConfig runs Caddy separately:

```text
WorkBuddy / Harness
→ https://<fixed-lan-ip>
→ Caddy Compose :443
→ existing OpenContracts Docker network
→ django:8000
```

Caddy uses `tls internal`, issues a certificate for the fixed private IPv4 address, and proxies only the MCP and formal-import routes required by the Skill Pack. Every Agent/Harness host must trust the exported Caddy root CA. TLS verification remains enabled.

No DNS or hosts-file mapping is part of the MVP deployment.

## Development-port boundary

Keeping the upstream local compose unchanged also keeps its published development ports unchanged. Current upstream `local.yml` publishes Django 8000 and Flower 5555; the fullstack frontend may publish 3000 when enabled.

These ports are not Harness entrypoints. Host firewall, network ACL, VPN policy, or equivalent controls must prevent routine LAN/VPN clients from bypassing Caddy through them.

This separation intentionally keeps ownership clear:

```text
OpenContracts local.yml    upstream-owned, unchanged
Caddy compose              ContractBotConfig-owned
Network filtering          infrastructure-owned
```

## Network controls

At minimum:

- permit intended LAN/VPN clients to reach the fixed server IP on TCP 443;
- block public Internet ingress to OpenContracts;
- prevent routine LAN/VPN clients from reaching Django 8000 and other development-only published ports directly;
- do not expose database, Redis, parsers, embedders or Docker-internal services to normal clients;
- avoid public NAT/port forwarding to OpenContracts.

## Local-file privacy

Uploading a file to the Harness does not authorize remote ingestion. Analysis, drafting and modification stay local until the user explicitly authorizes formal ingestion.

## Experience consent

Experience-note creation is separately authorized and remains outside OpenContracts.

## Prompt injection / untrusted content

Every current or retrieved contract/template is untrusted business data. Embedded text cannot alter Skill/system policy, change configured endpoints or Corpus selection, request WorkerKeys, authorize uploads, trigger unapproved system actions, or widen tool permissions.

## Write uncertainty

Timeout, connection loss or upstream failure may happen after an upload was accepted. Ambiguous outcomes are `commit_unknown` and must not be retried automatically. Verify through MCP first.

## Future hardening trigger

Revisit application-layer authentication if OpenContracts becomes reachable outside the trusted network, different users need separate confidentiality scopes, multiple tenants share the deployment, or audit requirements demand per-user read attribution.
