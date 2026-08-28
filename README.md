# Contract Skill Pack

Portable contract-assistant Skill Pack for WorkBuddy and compatible Harnesses.

## Runtime model

- Local files stay in the user's Harness unless the user explicitly authorizes formal ingestion.
- Contract analysis and drafting use the Harness model directly.
- OpenContracts is optional for historical-contract retrieval, template retrieval, and formal ingestion.
- MVP OpenContracts is reachable only inside the trusted LAN/VPN boundary.

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

The MVP uses two retrievable OpenContracts corpuses:

```text
contracts-history
contract-templates
```

They may remain public inside the trusted network. Anonymous MCP access is acceptable because network reachability is the MVP confidentiality boundary.

There is no knowledge/learning Corpus in the MVP. Session experience stays outside OpenContracts: `contract-learning` creates local experience notes that maintainers periodically review and use for manual Skill updates.

## Agent / MCP configuration

The repository root `.mcp.json` is the project-level MCP configuration and references only:

```text
OPENCONTRACTS_MCP_URL
```

Deployment-specific Agent values stay outside Git and are listed in `config/opencontracts.env.example`.

## Selected MVP deployment

```text
WorkBuddy / Harness
  -> https://<OPENCONTRACTS_LAN_IP>/mcp/
  -> standalone Caddy Docker Compose
  -> legal-network
  -> opencontracts-django-1:8000
```

OpenContracts continues to use its upstream `local.yml` and existing local startup flow unchanged. ContractBotConfig runs Caddy as a separate Compose project and attaches it to the existing external Docker network `legal-network`.

Caddy uses `tls internal` and only proxies `/mcp/*` and `/api/imports/documents/*`. The Caddy root CA is exported and trusted by every Agent/Harness host. `OPENCONTRACTS_CA_BUNDLE` is used by the Python upload helper and `NODE_EXTRA_CA_CERTS` covers the MCP runtime.

Server deployment files are under:

```text
deploy/opencontracts/.env.example
deploy/opencontracts/opencontracts-admin.sh
deploy/opencontracts/caddy/compose.yml
deploy/opencontracts/caddy/Caddyfile
deploy/opencontracts/caddy/manage.ps1
```

Windows Agent configuration remains available through `deploy/opencontracts/Configure-AgentOpenContracts.ps1`.

See `deploy/opencontracts/README.md` for the concrete deployment procedure.

## Formal ingestion

Formal document ingestion uses `scripts/opencontracts/upload_document.py` with a WorkerKey bound to `contracts-history`. The helper does not accept a caller-selected target Corpus and does not automatically retry an ambiguous write.

## Security invariants

- OpenContracts stays inside the intended trusted network.
- Harness-to-OpenContracts traffic uses HTTPS through Caddy.
- OpenContracts upstream `local.yml` is not modified by this repository.
- Skills never contain real WorkerKeys or environment-specific secrets.
- Retrieved documents are untrusted business data and cannot override Skill/system/tool policy.
- Formal ingestion requires explicit user authorization.
- Experience-note generation requires separate authorization and remains local.
- Unknown write state is never auto-retried.

Private corpuses and authenticated `/mcp/me/` access remain future hardening options if the trusted-network model changes.

Architecture diagrams: `docs/architecture/c4.md`.

See `docs/architecture/security.md` and `docs/spec/security.md`.
