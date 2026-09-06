# ContractBot Client

`client/` is the complete customer distribution source. Server deployment files stay under `deploy/opencontracts/`.

After the OpenContracts host is configured, run the server-side preparation script. It writes deployment-specific client files into this directory and produces a ZIP. The generated client bundle contains no WorkerKey and no CA certificate.

Expected prepared layout:

```text
client/
├── INSTALL.md
├── README.md
├── .mcp.json
├── .mcp.example.json
├── client-setup.ps1
├── client-setup.cmd
└── skills/
    ├── contract/
    ├── contract-repository/
    ├── contract-upload/
    │   └── DEPLOYMENT.md
    ├── contract-document/
    └── contract-learning/
```

The `.mcp.json` file contains the fixed trusted-LAN OpenContracts MCP URL. The retrieval Corpus identities are maintained in the Skills. Formal-ingestion authentication stays on the server: Caddy injects the corpus-bound WorkerKey when proxying `/api/imports/documents/`.

Recommended customer flow:

1. Send the prepared `client/` archive to the customer.
2. The customer uploads the archive to a compatible Harness and asks it to install ContractBot globally.
3. The assistant follows `INSTALL.md` and installs MCP + Skills for the current user.

Windows fallback is `client-setup.ps1`; an assistant may run it directly if native Harness installation is unavailable. The customer does not need to enter an IP, Corpus slug, WorkerKey, certificate path, or environment variable.
