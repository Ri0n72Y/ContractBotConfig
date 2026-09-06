# OpenContracts + Caddy server deployment

This directory contains server-side deployment/admin assets. Client Skills, MCP configuration, helpers and installation files live only under the repository-root `client/` directory.

## Server layout

```text
deploy/opencontracts/
├── .env.example
├── opencontracts-admin.ps1
├── opencontracts-admin.sh
├── Prepare-WindowsClientBundle.ps1
├── caddy/
│   ├── compose.yml
│   ├── Caddyfile
│   └── manage.ps1
└── converter/                 # optional
```

OpenContracts continues to use its upstream `local.yml`. ContractBot only adds the existing `legal-network`/`opencontracts-api` integration and a separate Caddy project.

## 1. Server `.env`

Copy `.env.example` to `.env` and configure the local OpenContracts compose path, fixed private IP, and the minted WorkerKey:

```text
OPENCONTRACTS_LOCAL_YML=C:/path/to/OpenContracts/local.yml
OPENCONTRACTS_LAN_IP=10.10.20.15
HISTORY_CORPUS=contracts-history
TEMPLATE_CORPUS=contract-templates
OPENCONTRACTS_UPLOAD_WORKER_KEY=<minted WorkerKey>
```

The `.env` file is untracked and is the server-side source of deployment secrets.

## 2. Corpuses

On a fresh OpenContracts database:

```powershell
.\opencontracts-admin.ps1 create-corpuses
.\opencontracts-admin.ps1 publish-corpuses
```

The management commands execute through OpenContracts `/entrypoint`, because the image constructs `DATABASE_URL` there. `create-corpuses` also grants creator object permissions through `CorpusService.grant_creator_permissions()`.

If a WorkerKey still needs to be minted:

```powershell
.\opencontracts-admin.ps1 mint-worker-key
```

Copy the plaintext result into `OPENCONTRACTS_UPLOAD_WORKER_KEY` in `.env`.

## 3. Caddy

Caddy joins the existing external Docker network `legal-network` and proxies to the stable Django alias `opencontracts-api:8000`.

```powershell
.\caddy\manage.ps1 setup
```

`setup` starts Caddy and exports its internal root CA. Caddy exposes only `/mcp/*` and `/api/imports/documents/*`; all other Caddy routes return 404.

## 4. Prepare the client directory

Run:

```powershell
.\Prepare-WindowsClientBundle.ps1
```

This command also performs the Caddy setup, then writes these ignored deployment-specific files directly into repository-root `client/`:

```text
client/bundle.json
client/config/contractbot-client.json
client/certificates/opencontracts-caddy-root.crt
```

It also creates `deploy/opencontracts/runtime/ContractBot-Client.zip` for convenience.

You can distribute only the prepared `client/` directory, or the generated ZIP. Both contain the formal-ingestion WorkerKey and must be distributed only to authorized users.

## 5. End-user flow

The preferred flow is for the user to upload the client ZIP to a compatible Harness and ask the assistant to install ContractBot globally. The assistant follows `client/INSTALL.md`, installs the Skills/MCP/runtime/CA for the current user, persists runtime variables, and removes the extracted plaintext WorkerKey configuration when possible.

For Windows Harnesses without a native global installer, the assistant executes `client-setup.ps1` itself. `client-setup.cmd` remains a manual double-click fallback.

## Caddy operations

```powershell
.\caddy\manage.ps1 up
.\caddy\manage.ps1 export-ca
.\caddy\manage.ps1 logs
.\caddy\manage.ps1 down
```

The Caddy data volume retains the internal CA across ordinary down/up cycles.
