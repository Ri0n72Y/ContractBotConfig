# ContractBotConfig

ContractBot is a portable contract-assistant client backed by OpenContracts for historical/template retrieval and explicit formal ingestion.

## Repository boundary

Customer-facing assets live only under:

```text
client/
├── .mcp.json
├── INSTALL.md
├── README.md
├── certificates/
│   └── opencontracts-caddy-root.crt   # generated during server preparation
└── skills/
```

`client/.mcp.json` is versioned and contains the fixed MCP endpoint:

```text
https://192.168.200.69/mcp/
```

`client/` is the only directory that needs to be packaged and distributed to end users. The preferred flow is: the user uploads an archive of `client/` to a compatible Harness and asks the assistant to install it globally. `INSTALL.md` defines that installation contract.

Server/deployment assets remain separate under `deploy/opencontracts/`.

## OpenContracts data layout

The runtime uses exactly two corpuses:

```text
contracts-history
contract-templates
```

`contracts-history` is the formal-ingestion destination. `contract-templates` contains approved templates. Session learning stays outside OpenContracts.

## Server preparation

After OpenContracts, the Corpuses and WorkerKey are ready, configure the untracked `deploy/opencontracts/.env` and run:

```powershell
cd deploy/opencontracts
.\Prepare-WindowsClientBundle.ps1
```

The script starts/updates the HTTPS Caddy gateway, exports Caddy's public root CA into `client/certificates/`, and creates:

```text
deploy/opencontracts/runtime/ContractBot-Client.zip
```

The WorkerKey and Caddy CA private key remain only on the server. The client package contains only the public root certificate needed to trust the internal HTTPS endpoint.

## Runtime architecture

```text
Harness
  → globally installed ContractBot Skills
  → https://192.168.200.69/mcp/
  → Caddy HTTPS gateway
  → opencontracts-api:8000
```

For formal ingestion, the Skill derives `https://192.168.200.69/api/imports/documents/` from the same MCP origin and submits without credentials. Caddy injects the server-side corpus-bound WorkerKey before proxying the request to OpenContracts.

During installation, the agent trusts `client/certificates/opencontracts-caddy-root.crt` for the current user before registering the MCP endpoint. Users do not manually configure certificates or WorkerKeys.

Detailed server procedure: `deploy/opencontracts/README.md`.
Architecture: `docs/architecture/c4.md`.
