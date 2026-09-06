# ContractBot Client

`client/` is the only client distribution directory in this repository. It contains the complete ContractBot Skill Pack, OpenContracts MCP definition, deterministic helper scripts, assistant installation instructions, and the Windows fallback installer.

Server-specific files are generated locally and ignored by Git:

```text
client/
├── INSTALL.md
├── README.md
├── bundle.example.json
├── bundle.json                         # generated, ignored
├── client-setup.ps1
├── client-setup.cmd
├── mcp/
│   └── opencontracts.json
├── skills/
├── scripts/
│   └── opencontracts/
├── certificates/
│   └── opencontracts-caddy-root.crt    # generated, ignored
└── config/
    ├── README.md
    ├── opencontracts.env.example
    ├── workbuddy.settings.example.json
    └── contractbot-client.json         # generated secret, ignored
```

On the OpenContracts host, run `deploy/opencontracts/Prepare-WindowsClientBundle.ps1`. It starts/updates Caddy, exports the CA, reads the deployment WorkerKey from the untracked server `.env`, and writes the three generated client files above. It can also create a ZIP.

You may then distribute only the `client/` directory (or its ZIP) to authorized users. The preferred user flow is to upload the archive to a compatible assistant and ask it to install ContractBot globally. The assistant follows `INSTALL.md`.

`client-setup.ps1` is the Windows fallback. It installs the runtime under `%LOCALAPPDATA%\ContractBot`, configures user environment variables and CA trust, installs CodeBuddy user-level Skills/MCP when CodeBuddy is available, and configures WorkBuddy's user-level MCP file.

The prepared client directory and ZIP contain a formal-ingestion WorkerKey. Treat them as credential-bearing internal artifacts and do not commit or publish the generated files.
