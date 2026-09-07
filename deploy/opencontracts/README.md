# OpenContracts + Caddy server deployment

This directory contains server-side deployment/admin assets. Client Skills and the fixed MCP configuration live only under the repository-root `client/` directory.

## Server layout

```text
deploy/opencontracts/
├── .env.example
├── opencontracts-admin.ps1
├── opencontracts-admin.sh
├── Prepare-WindowsClientBundle.ps1
└── caddy/
    ├── compose.yml
    ├── Caddyfile
    └── manage.ps1
```

OpenContracts continues to use its upstream `local.yml`. ContractBot adds a separate Caddy project on the existing `legal-network`, targeting `opencontracts-api:8000`.

ContractBot does not run a server-side DOC/DOCX/PDF converter. File reading, conversion and editable-document generation are handled by the customer's Harness and local machine capabilities according to the client Skills.

## 1. Server `.env`

Copy `.env.example` to `.env` and configure:

```text
OPENCONTRACTS_LOCAL_YML=C:/path/to/OpenContracts/local.yml
OPENCONTRACTS_LAN_IP=192.168.200.69
HISTORY_CORPUS=contracts-history
TEMPLATE_CORPUS=contract-templates
OPENCONTRACTS_UPLOAD_WORKER_KEY=<minted WorkerKey>
```

The `.env` file is untracked. `OPENCONTRACTS_UPLOAD_WORKER_KEY` stays on the server and is passed only to Caddy for formal-ingestion proxy authentication.

## 2. Corpuses

On a fresh OpenContracts database:

```powershell
.\opencontracts-admin.ps1 create-corpuses
.\opencontracts-admin.ps1 publish-corpuses
```

If a WorkerKey still needs to be minted:

```powershell
.\opencontracts-admin.ps1 mint-worker-key
```

Copy the plaintext result into `OPENCONTRACTS_UPLOAD_WORKER_KEY` in `.env`.

## 3. Caddy HTTPS gateway

Caddy exposes the fixed private IP on TCP 443:

```text
https://192.168.200.69/mcp/
https://192.168.200.69/api/imports/documents/
```

The current Caddyfile uses `tls internal`. Caddy's root CA public certificate is exported into the client package so each installing agent can trust it on the customer machine. The CA private key remains only in Caddy's persistent data volume.

Caddy proxies only the MCP and single-document import routes. The formal-import route overwrites the upstream `Authorization` header with:

```text
WorkerKey <server-side corpus-bound token>
```

The client therefore never stores or sends a WorkerKey.

Start/update Caddy:

```powershell
.\caddy\manage.ps1 setup
```

Export the public root CA manually when needed:

```powershell
.\caddy\manage.ps1 export-ca -Output ..\..\..\client\certificates\opencontracts-caddy-root.crt
```

All other Caddy routes return 404.

## 4. Package the client directory

`client/.mcp.json` is a normal versioned file with the fixed MCP URL.

Run:

```powershell
.\Prepare-WindowsClientBundle.ps1
```

This starts/updates Caddy, exports its public root CA to:

```text
client/certificates/opencontracts-caddy-root.crt
```

and creates:

```text
deploy/opencontracts/runtime/ContractBot-Client.zip
```

The ZIP contains:

- `.mcp.json` with `https://192.168.200.69/mcp/`;
- the ContractBot Skills;
- `INSTALL.md` / `README.md`;
- the public Caddy root CA certificate.

It contains no WorkerKey and no CA private key.

## 5. End-user flow

The customer uploads the `client/` ZIP to a compatible Harness and asks the assistant to install ContractBot globally. The assistant follows `client/INSTALL.md` and:

1. trusts `certificates/opencontracts-caddy-root.crt` for the current user;
2. installs the `opencontracts` MCP definition from `.mcp.json`;
3. installs the Skills under `skills/`.

On Windows, the intended trust scope is the current user's Trusted Root Certification Authorities store, so the agent can normally install the CA without machine-wide administrator configuration.

There is no client setup script, WorkerKey configuration, helper runtime, ContractBot environment-variable setup, or server-side document-conversion service.

## Caddy operations

```powershell
.\caddy\manage.ps1 setup
.\caddy\manage.ps1 up
.\caddy\manage.ps1 export-ca -Output <path>
.\caddy\manage.ps1 logs
.\caddy\manage.ps1 down
```

## Trust boundary

The service remains restricted to the intended LAN/VPN. HTTPS protects client-to-Caddy traffic. Because the deployment uses Caddy `tls internal`, client machines must trust the bundled public root CA. The private CA key never leaves the server.
