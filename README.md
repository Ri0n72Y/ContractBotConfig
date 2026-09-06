# ContractBotConfig

ContractBot is a portable contract-assistant client backed by OpenContracts for historical/template retrieval and explicit formal ingestion.

## Repository boundary

Customer-facing assets live only under:

```text
client/
├── .mcp.json
├── INSTALL.md
├── README.md
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

The script starts/updates the HTTPS Caddy gateway and creates:

```text
deploy/opencontracts/runtime/ContractBot-Client.zip
```

The WorkerKey remains only on the server and is never copied into `client/` or the ZIP.

## Runtime architecture

```text
Harness
  → globally installed ContractBot Skills
  → https://192.168.200.69/mcp/
  → Caddy HTTPS gateway
  → opencontracts-api:8000
```

For formal ingestion, the Skill derives `https://192.168.200.69/api/imports/documents/` from the same MCP origin and submits without credentials. Caddy injects the server-side corpus-bound WorkerKey before proxying the request to OpenContracts.

TLS trust for the internal Caddy certificate is handled by host/infrastructure policy and is outside the client bundle.

Detailed server procedure: `deploy/opencontracts/README.md`.
Architecture: `docs/architecture/c4.md`.
