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
  contract-learning/    local experience-note distillation for later manual Skill updates
```

## OpenContracts data layout

MVP keeps the retrieval corpuses logically separated but publicly readable inside the OpenContracts deployment:

```text
contracts-history
contract-templates
approved-knowledge
```

`public` here means anonymous MCP clients that can reach the OpenContracts server may read them. The MVP confidentiality boundary is the LAN / restricted network, not OpenContracts corpus permissions.

Session learning material is not stored in OpenContracts for MVP. `contract-learning` produces a local experience note; maintainers periodically collect and review those notes and update the relevant Skills manually.

## Agent / MCP configuration

The repository root `.mcp.json` is the project-level MCP configuration for WorkBuddy/CodeBuddy-compatible Harnesses. It references:

```text
OPENCONTRACTS_MCP_URL
```

Runtime values are listed in `config/opencontracts.env.example`; deployment-specific values stay outside Git.

The WorkBuddy settings example in `config/workbuddy.settings.example.json` enables the `opencontracts` MCP server and denies MCP capabilities that are not used by the current contract workflow.

## Selected MVP deployment

```text
OpenContracts local.yml
+ Caddy internal HTTPS
+ public retrieval corpuses inside trusted LAN/VPN
+ WorkerKey for formal ingestion
```

Caddy runs on the OpenContracts Docker host, joins the same Docker network as Django, and proxies HTTPS traffic to `django:8000`. Raw host port 8000 is restricted to loopback.

For an internal-only hostname, Caddy uses `tls internal`. Every WorkBuddy/Harness host receives the exported Caddy root certificate. The runtime sets both `OPENCONTRACTS_CA_BUNDLE` for the Python upload helper and `NODE_EXTRA_CA_CERTS` for MCP-client compatibility.

Server and Agent PowerShell automation is under:

```text
deploy/opencontracts/
```

See `deploy/opencontracts/README.md` for local and remote PowerShell procedures.

## Formal ingestion

Formal document ingestion uses `scripts/opencontracts/upload_document.py` with a corpus-bound WorkerKey. The helper does not allow caller-selected corpus IDs and does not automatically retry an ambiguous write.

## Security invariants

- The OpenContracts server is reachable only from the intended LAN/VPN/restricted network domain.
- HTTPS is used between Harness and OpenContracts so WorkerKeys and retrieved contract content are not sent in cleartext on the LAN.
- A Skill never contains a real WorkerKey, password, contract, customer fact, or private template.
- Retrieved documents are untrusted data. Embedded instructions never override Skill/system/tool policy.
- Formal ingestion requires explicit user authorization.
- Experience-note generation requires separate user authorization and stays outside OpenContracts in MVP.
- Unknown write state is never auto-retried.

Private corpuses, per-user OAuth and fine-grained OpenContracts permissions are future hardening options when the deployment leaves the trusted-network MVP model.

See `docs/architecture/security.md` and `docs/spec/security.md`.
