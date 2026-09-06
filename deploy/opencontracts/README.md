# OpenContracts + Caddy server deployment

This directory contains server-side deployment/admin assets. Client Skills and MCP installation files live only under the repository-root `client/` directory.

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
OPENCONTRACTS_LAN_IP=10.10.20.15
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

## 3. Caddy

Caddy exposes the fixed private IP on TCP 80 inside the trusted LAN/VPN:

```text
http://<fixed-lan-ip>/mcp/
http://<fixed-lan-ip>/api/imports/documents/
```

It proxies only the MCP and single-document import routes. The formal-import route overwrites the upstream `Authorization` header with:

```text
WorkerKey <server-side corpus-bound token>
```

The client therefore never stores or sends a WorkerKey.

Start/update Caddy:

```powershell
.\caddy\manage.ps1 setup
```

All other Caddy routes return 404.

## 4. Prepare the client directory

Run:

```powershell
.\Prepare-WindowsClientBundle.ps1
```

The command starts Caddy and writes two ignored deployment-specific files into `client/`:

```text
client/.mcp.json
client/skills/contract-upload/DEPLOYMENT.md
```

It also creates:

```text
deploy/opencontracts/runtime/ContractBot-Client.zip
```

The generated client directory and ZIP contain no WorkerKey and no CA certificate.

## 5. End-user flow

The customer uploads the prepared client ZIP to a compatible Harness and asks the assistant to install ContractBot globally. The assistant installs only:

- the `opencontracts` MCP definition from `.mcp.json`;
- the Skills under `skills/`.

No client environment variables, certificates, WorkerKey, helper runtime, or `CONTRACTBOT_HOME` are required.

For Windows Harnesses without native global installation, the assistant may execute `client-setup.ps1` itself. `client-setup.cmd` remains a manual fallback.

## Caddy operations

```powershell
.\caddy\manage.ps1 setup
.\caddy\manage.ps1 up
.\caddy\manage.ps1 logs
.\caddy\manage.ps1 down
```

## Trust boundary

This MVP intentionally uses HTTP on the trusted LAN/VPN so clients can connect using only the fixed IP without installing a private CA. Traffic is not TLS-encrypted on that internal link. If the network boundary is no longer trusted, move to authenticated/private MCP plus a managed TLS certificate or an enterprise-trusted CA.
