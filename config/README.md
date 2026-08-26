# OpenContracts runtime configuration

This directory contains examples only. Real WorkerKeys stay in the user's Harness secret store, host environment, or an untracked local env file.

## Values to fill

Copy the names from `opencontracts.env.example` into the Agent/Harness runtime and fill:

```text
OPENCONTRACTS_BASE_URL=https://<internal-host>
OPENCONTRACTS_MCP_URL=https://<internal-host>/mcp/
OPENCONTRACTS_HISTORY_CORPUS=<history corpus slug>
OPENCONTRACTS_TEMPLATE_CORPUS=<template corpus slug>
OPENCONTRACTS_KNOWLEDGE_CORPUS=<approved-knowledge corpus slug>
OPENCONTRACTS_CA_BUNDLE=<path to caddy-root.crt>
NODE_EXTRA_CA_CERTS=<same caddy-root.crt path>
OPENCONTRACTS_UPLOAD_WORKER_KEY=<history-corpus WorkerKey>
```

The example file intentionally leaves deployment-specific values empty.

## MVP MCP access

The MVP assumes OpenContracts is reachable only inside a trusted LAN/VPN/restricted network domain and keeps its retrieval corpuses public inside that deployment.

Normal MCP reads use:

```text
https://<internal-host>/mcp/
```

No OAuth/Bearer credential is required for normal read-side MCP access in this mode. Network reachability is the confidentiality boundary.

Future deployments may move to private corpuses and `/mcp/me/` OAuth without changing the Skill behavior.

## Upload authentication

Formal contract ingestion uses a `CorpusAccessToken` / `WorkerKey` bound to the intended history corpus. OpenContracts' `mint_worker_token` command prints the plaintext token once; copy that value into `OPENCONTRACTS_UPLOAD_WORKER_KEY` on the Agent/Harness host.

Recommended policy:

- revoke/rotate the key when a host is retired or a key is exposed;
- use expiry/rate limits when practical;
- do not send `add_to_corpus_id` from the helper: the WorkerKey binding selects the destination;
- never place a real WorkerKey in `SKILL.md`, `.mcp.json`, or committed configuration.

Contract-learning material is not uploaded to OpenContracts in MVP and therefore requires no second WorkerKey.

## Caddy internal CA

The selected MVP deployment is OpenContracts `local.yml` behind Caddy with `tls internal`.

`deploy/opencontracts/Setup-OpenContractsLocalCaddy.ps1` exports Caddy's root certificate. Distribute it to every Agent/Harness host.

`Configure-AgentOpenContracts.ps1` imports the certificate into Windows trust and sets:

```text
OPENCONTRACTS_CA_BUNDLE=<certificate path>
NODE_EXTRA_CA_CERTS=<certificate path>
```

The first value is consumed by the Python upload helper; the second covers the WorkBuddy/CodeBuddy MCP client runtime. TLS verification remains enabled.

See `deploy/opencontracts/README.md` for the complete local/remote PowerShell procedure.
