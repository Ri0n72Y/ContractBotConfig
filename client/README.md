# ContractBot Client

`client/` is the complete customer distribution source. Server deployment files stay under `deploy/opencontracts/`.

```text
client/
├── .mcp.json
├── INSTALL.md
├── README.md
└── skills/
    ├── contract/
    ├── contract-repository/
    ├── contract-upload/
    ├── contract-document/
    └── contract-learning/
```

The packaged MCP endpoint is fixed:

```text
https://192.168.200.69/mcp/
```

The two Corpus identities are maintained in the Skills. Formal-ingestion authentication stays on the server: Caddy injects the corpus-bound WorkerKey when proxying `/api/imports/documents/`.

The formal import endpoint uses the same HTTPS origin as the MCP endpoint, so no second client URL or environment configuration is required.

Recommended customer flow:

1. Zip and send only the `client/` directory.
2. The customer uploads the archive to a compatible Harness and asks it to install ContractBot globally.
3. The assistant follows `INSTALL.md` and installs `.mcp.json` plus all Skills using the Harness's native global/user installation mechanisms.

The customer does not configure an IP, Corpus slug, WorkerKey, certificate path, environment variable, helper, or setup script.
