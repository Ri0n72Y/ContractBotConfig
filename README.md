# ContractBotConfig

ContractBot is a portable contract-assistant client backed by OpenContracts for historical/template retrieval and explicit formal ingestion.

## Repository boundary

Customer-facing assets live only under:

```text
client/
├── INSTALL.md
├── README.md
├── .mcp.example.json
├── client-setup.ps1
├── client-setup.cmd
└── skills/
```

After server preparation, two ignored deployment files are added:

```text
client/.mcp.json
client/skills/contract-upload/DEPLOYMENT.md
```

`client/` is the only directory that needs to be packaged and distributed to end users. The preferred flow is: the user uploads the prepared archive to a compatible Harness and asks the assistant to install it globally. `INSTALL.md` defines that installation contract; `client-setup.ps1` is the Windows fallback.

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

The script starts/updates Caddy, reads the fixed LAN IP, generates the client `.mcp.json` and formal-upload endpoint, and creates:

```text
deploy/opencontracts/runtime/ContractBot-Client.zip
```

The WorkerKey remains only on the server and is never copied into `client/` or the ZIP.

## Runtime architecture

```text
Harness
  → globally installed ContractBot Skills
  → http://<fixed-lan-ip>/mcp/
  → Caddy on the trusted LAN/VPN
  → opencontracts-api:8000
```

For formal ingestion, the client submits to Caddy without credentials. Caddy injects the server-side corpus-bound WorkerKey before proxying the request to OpenContracts.

No client CA, WorkerKey, ContractBot environment variables, or `CONTRACTBOT_HOME` are required.

Detailed server procedure: `deploy/opencontracts/README.md`.
Architecture: `docs/architecture/c4.md`.
