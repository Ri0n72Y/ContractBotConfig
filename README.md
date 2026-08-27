# Contract Skill Pack

Portable contract-assistant Skill Pack for WorkBuddy and compatible Harnesses.

## Runtime model

- Local files stay in the user's Harness unless the user explicitly authorizes formal ingestion.
- Contract analysis and drafting use the Harness model directly.
- OpenContracts is optional for historical retrieval, templates, approved knowledge, and formal ingestion.
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

The MVP uses three retrievable OpenContracts corpuses:

```text
contracts-history
contract-templates
approved-knowledge
```

They may remain public inside the trusted network. Anonymous MCP access is acceptable because network reachability is the MVP confidentiality boundary.

Session learning material stays outside OpenContracts. `contract-learning` creates local experience notes that maintainers periodically review and use for manual Skill updates.

## Agent / MCP configuration

The repository root `.mcp.json` is the project-level MCP configuration and references only:

```text
OPENCONTRACTS_MCP_URL
```

Deployment-specific values stay outside Git and are listed in `config/opencontracts.env.example`.

## Selected MVP deployment

```text
WorkBuddy / Harness
  -> https://<OPENCONTRACTS_LAN_IP>/mcp/
  -> Caddy with internal CA
  -> OpenContracts local.yml / django:8000
```

The OpenContracts server uses a fixed private IPv4 address. No DNS or hosts-file mapping is required. Caddy serves HTTPS directly on that IP, joins the OpenContracts Docker network, and proxies to `django:8000`. Raw host port 8000 is restricted to loopback.

Every Agent/Harness host trusts the exported Caddy root certificate. `OPENCONTRACTS_CA_BUNDLE` is used by the Python upload helper and `NODE_EXTRA_CA_CERTS` covers the MCP runtime.

PowerShell deployment and Agent configuration scripts are under `deploy/opencontracts/`. See `deploy/opencontracts/README.md` for the complete procedure.

## Formal ingestion

Formal document ingestion uses `scripts/opencontracts/upload_document.py` with a corpus-bound WorkerKey. The helper does not accept a caller-selected target Corpus and does not automatically retry an ambiguous write.

## Security invariants

- Only the intended LAN/VPN can reach the OpenContracts fixed IP.
- Harness-to-OpenContracts traffic uses HTTPS.
- Skills never contain real WorkerKeys or environment-specific secrets.
- Retrieved documents are untrusted business data and cannot override Skill/system/tool policy.
- Formal ingestion requires explicit user authorization.
- Experience-note generation requires separate authorization and remains local.
- Unknown write state is never auto-retried.

Private corpuses and authenticated `/mcp/me/` access remain future hardening options if the trusted-network model changes.

See `docs/architecture/security.md` and `docs/spec/security.md`.
