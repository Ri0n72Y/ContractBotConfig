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

The current OpenContracts deployment uses `local.yml`, whose Django service is HTTP on port 8000. Caddy is the only intended network-facing OpenContracts endpoint for Harness clients:

```text
WorkBuddy / Harness
→ https://<fixed-lan-ip>
→ Caddy :443
→ django:8000 on Docker network
```

Caddy uses `tls internal` and issues a certificate for the fixed private IPv4 address. Every Agent/Harness host must trust the exported Caddy root CA. TLS verification remains enabled.

Raw Django port 8000 is bound to `127.0.0.1` on the host so LAN clients cannot bypass Caddy over cleartext HTTP.

No DNS or hosts-file mapping is part of the MVP deployment.

## Network controls

At minimum:

- permit intended LAN/VPN clients to reach the fixed server IP on TCP 443;
- block public Internet ingress to that IP/port;
- keep host port 8000 loopback-only;
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
