# OpenContracts + Caddy server deployment

This directory contains server-side deployment/admin assets. Client Skills and the fixed MCP configuration live only under the repository-root `client/` directory.

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

OpenContracts continues to use its upstream `local.yml`. ContractBot adds a separate Caddy project on the existing `legal-network`, targeting `opencontracts-api:8000`.

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

The current Caddyfile uses `tls internal`. TLS trust for that internal CA must already be provided by host/IT infrastructure; the customer client bundle does not install certificates.

Caddy proxies only the MCP and single-document import routes. The formal-import route overwrites the upstream `Authorization` header with:

```text
WorkerKey <server-side corpus-bound token>
```

The client therefore never stores or sends a WorkerKey.

Start/update Caddy:

```powershell
.\caddy\manage.ps1 setup
```

All other Caddy routes return 404.

## 4. Package the client directory

`client/.mcp.json` is a normal versioned file with the fixed MCP URL. No deployment-time client configuration is generated.

Run:

```powershell
.\Prepare-WindowsClientBundle.ps1
```

This starts/updates Caddy and creates:

```text
deploy/opencontracts/runtime/ContractBot-Client.zip
```

The ZIP contains only the static client MCP configuration, installation instructions, and Skills. It contains no WorkerKey.

## 5. End-user flow

The customer uploads the `client/` ZIP to a compatible Harness and asks the assistant to install ContractBot globally. The assistant installs only:

- the `opencontracts` MCP definition from `.mcp.json`;
- the Skills under `skills/`.

There is no client setup script, WorkerKey configuration, helper runtime, or ContractBot environment-variable setup.

## Caddy operations

```powershell
.\caddy\manage.ps1 setup
.\caddy\manage.ps1 up
.\caddy\manage.ps1 logs
.\caddy\manage.ps1 down
```

## Trust boundary

The service remains restricted to the intended LAN/VPN. HTTPS protects client-to-Caddy traffic. With `tls internal`, the Caddy root CA trust is an infrastructure prerequisite; it can be provisioned centrally instead of being part of the ContractBot client package.
