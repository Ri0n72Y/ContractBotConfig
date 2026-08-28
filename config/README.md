# OpenContracts runtime configuration

This directory contains Agent/Harness runtime examples only. Real WorkerKeys and deployment-specific values stay in the Harness secret store, host environment, or an untracked local env file.

## Values to fill

For a server whose fixed LAN IPv4 is `10.10.20.15`, configure:

```text
OPENCONTRACTS_BASE_URL=https://10.10.20.15
OPENCONTRACTS_MCP_URL=https://10.10.20.15/mcp/
OPENCONTRACTS_HISTORY_CORPUS=<history corpus slug>
OPENCONTRACTS_TEMPLATE_CORPUS=<template corpus slug>
OPENCONTRACTS_CA_BUNDLE=<path to caddy-root.crt>
NODE_EXTRA_CA_CERTS=<same caddy-root.crt path>
OPENCONTRACTS_UPLOAD_WORKER_KEY=<history-corpus WorkerKey>
```

`opencontracts.env.example` intentionally leaves environment-specific values blank.

## MCP reads

The MVP uses the anonymous public MCP endpoint over the trusted network:

```text
https://<fixed-lan-ip>/mcp/
```

No OAuth/Bearer credential is required for normal reads in this deployment model.

Only two OpenContracts Corpus identities are configured by the Skill Pack: history and templates. Session experience/learning material stays outside OpenContracts and is handled through local notes plus manual Skill updates.

## Formal ingestion

Formal contract ingestion uses a Corpus-bound WorkerKey bound to the history Corpus. OpenContracts' `mint_worker_token` command prints the plaintext token once. Copy it to `OPENCONTRACTS_UPLOAD_WORKER_KEY` on the Agent/Harness host.

The upload helper deliberately omits `add_to_corpus_id`; the WorkerKey's server-side binding decides the destination.

## Caddy internal CA

OpenContracts keeps its existing `local.yml` and startup flow. The separate Caddy Compose under `deploy/opencontracts/caddy/` joins the existing external Docker network `legal-network` and reaches OpenContracts at `opencontracts-django-1:8000`.

Caddy serves the fixed private IP with `tls internal` and proxies only the MCP and formal-import paths needed by the Skill Pack. There is no DNS/hosts configuration step.

On the Windows OpenContracts host, export the Caddy root CA with:

```powershell
cd deploy/opencontracts/caddy
.\manage.ps1 export-ca
```

Distribute that certificate to every Agent/Harness host. `Configure-AgentOpenContracts.ps1` imports it into Windows trust and sets both CA environment variables. TLS verification remains enabled.

See `deploy/opencontracts/README.md` for the concrete Docker Compose deployment and Agent procedure.
