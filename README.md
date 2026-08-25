# Contract Skill Pack

Portable contract-assistant Skill Pack for WorkBuddy and compatible Harnesses.

## Runtime model

- Local files stay in the user's Harness unless the user explicitly authorizes formal ingestion.
- Contract analysis and drafting use the Harness model directly.
- OpenContracts is optional for historical retrieval, templates, approved knowledge, and formal ingestion.
- MVP OpenContracts is deployed inside a trusted LAN / restricted network domain. Harnesses can reach it only while they are inside that network boundary.

## Skills

```text
skills/
  contract/             default contract mode
  contract-repository/  historical/template retrieval
  contract-upload/      explicit formal ingestion
  contract-document/    formal document structure and formatting
  contract-learning/    session facts + distilled learning material
```

## OpenContracts data layout

MVP keeps the corpuses logically separated but publicly readable inside the OpenContracts deployment:

```text
contracts-history
contract-templates
approved-knowledge
learning-inbox
```

`public` here means anonymous MCP clients that can reach the OpenContracts server may read them. The MVP confidentiality boundary is the LAN / restricted network, not OpenContracts corpus permissions.

The repository Skill uses history/templates/approved knowledge for normal retrieval. `learning-inbox` remains logically excluded from normal retrieval and is reserved for later review/curation.

## Configuration

Copy `config/opencontracts.env.example` into your local runtime configuration. Do not commit populated env files.

For MCP, use `.mcp.json` as a reference. MVP uses the anonymous public endpoint:

```text
https://<internal-opencontracts-host>/mcp/
```

Formal document ingestion uses `scripts/opencontracts/upload_document.py` with a corpus-bound WorkerKey. Learning material uses a separate WorkerKey.

## Network / HTTPS

OpenContracts production configuration already includes Traefik with HTTP→HTTPS redirect and ACME/Let's Encrypt. Its checked-in Traefik example is oriented toward a public DNS name and must be adapted for an internal deployment.

For the MVP, a small Caddy/Nginx reverse proxy in front of the existing OpenContracts HTTP endpoint is acceptable and often simpler. See `deploy/reverse-proxy/`.

## Security invariants

- The OpenContracts server is reachable only from the intended LAN/VPN/restricted network domain.
- HTTPS is used between Harness and OpenContracts so WorkerKeys and retrieved contract content are not sent in cleartext on the LAN.
- A Skill never contains a real WorkerKey, password, contract, customer fact, or private template.
- Retrieved documents are untrusted data. Embedded instructions never override Skill/system/tool policy.
- Formal ingestion and learning-material ingestion require separate user authorization.
- Unknown write state is never auto-retried.

Private corpuses, per-user OAuth and fine-grained OpenContracts permissions are future hardening options when the deployment leaves the trusted-network MVP model.

See `docs/architecture/security.md` and `docs/spec/security.md`.
