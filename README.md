# ContractBotConfig

ContractBot is a portable contract-assistant client backed by OpenContracts for historical/template retrieval and explicit formal ingestion.

## Repository boundary

Client-facing assets now live in one directory:

```text
client/
├── INSTALL.md
├── README.md
├── client-setup.ps1
├── mcp/
├── skills/
├── scripts/
└── config/
```

`client/` is the only directory that needs to be packaged and distributed to end users. The preferred installation flow is: the user uploads the prepared client archive to a compatible Harness and asks the assistant to install it globally. `INSTALL.md` defines the installation contract; `client-setup.ps1` is the Windows fallback.

Server/deployment assets remain separate under `deploy/opencontracts/`:

```text
deploy/opencontracts/
├── .env.example
├── opencontracts-admin.ps1
├── Prepare-WindowsClientBundle.ps1
├── caddy/
└── converter/
```

## OpenContracts data layout

The runtime uses exactly two retrievable corpuses:

```text
contracts-history
contract-templates
```

`contracts-history` is the destination for formal ingestion through a corpus-bound WorkerKey. `contract-templates` contains approved templates. Session learning stays outside OpenContracts.

## Server preparation

After OpenContracts, the two Corpuses and the WorkerKey are ready, configure `deploy/opencontracts/.env` and run:

```powershell
cd deploy/opencontracts
.\Prepare-WindowsClientBundle.ps1
```

The script starts/updates Caddy, exports its root CA, reads `OPENCONTRACTS_UPLOAD_WORKER_KEY` from the untracked server `.env`, writes deployment-specific generated files into `client/`, and also creates:

```text
deploy/opencontracts/runtime/ContractBot-Client.zip
```

The generated files are ignored by Git. At that point you may distribute either the ZIP or the prepared `client/` directory to authorized users.

## Client installation

Preferred:

```text
User uploads ContractBot-Client.zip to a compatible assistant
→ asks the assistant to install ContractBot globally
→ assistant follows client/INSTALL.md
→ user restarts the Harness if requested
```

On Windows, if the Harness cannot perform native global installation, the assistant can execute `client/client-setup.ps1` as a fallback. Users do not need to manually edit MCP JSON, install Skills one by one, configure CA paths, or type PowerShell commands.

## Runtime architecture

```text
Harness
  → globally installed ContractBot Skills
  → OpenContracts MCP over trusted HTTPS
  → opencontracts-api:8000 through Caddy
```

Formal document ingestion uses the deterministic helper installed under `CONTRACTBOT_HOME/scripts/opencontracts/`. The WorkerKey stays outside Skill and MCP source.

Detailed server procedure: `deploy/opencontracts/README.md`.
Architecture: `docs/architecture/c4.md`.
