# ContractBot Client

`client/` is the complete customer distribution source. Server deployment files stay under `deploy/opencontracts/`.

Prepared client layout:

```text
client/
├── .mcp.json
├── INSTALL.md
├── README.md
├── certificates/
│   └── opencontracts-caddy-root.crt
└── skills/
    ├── contract/
    ├── contract-repository/
    ├── contract-upload/
    ├── contract-document/
    └── contract-learning/
```

`.mcp.json` contains the fixed OpenContracts endpoint:

```text
https://192.168.200.69/mcp/
```

The two Corpus identities are maintained in the Skills. Formal-ingestion authentication stays on the server: Caddy injects the corpus-bound WorkerKey when proxying `/api/imports/documents/`.

The bundled `certificates/opencontracts-caddy-root.crt` is the public root certificate for Caddy `tls internal`. The installing assistant must trust this certificate for the current user before using the HTTPS MCP endpoint. The CA private key is never included in the client package.

Recommended customer flow:

1. Send the prepared `client/` archive to the customer.
2. The customer uploads the archive to a compatible Harness and asks it to install ContractBot globally.
3. The assistant follows `INSTALL.md`, installs the CA trust, MCP configuration and Skills for the current user.

The customer does not enter an IP, Corpus slug, WorkerKey, certificate path, environment variable, or PowerShell command.
