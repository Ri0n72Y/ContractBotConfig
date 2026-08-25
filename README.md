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

## Configuration

Copy `config/opencontracts.env.example` into your local runtime configuration. Do not commit populated env files.

For MCP, use `.mcp.json` as a reference. MVP uses the anonymous public endpoint:

```text
https://<internal-opencontracts-host>/mcp/
```

Formal document ingestion uses `scripts/opencontracts/upload_document.py` with a corpus-bound WorkerKey.

## Network / HTTPS

The selected MVP deployment is:

```text
OpenContracts local.yml
+ Caddy on the OpenContracts host
+ internal DNS / trusted LAN
```

OpenContracts `local.yml` exposes Django over HTTP on port 8000 and does not include TLS. Caddy is the canonical HTTPS entrypoint for Harness MCP/API traffic and proxies to the local Django endpoint.

For an internal-only hostname, the provided Caddy example uses `tls internal`. Every WorkBuddy/Harness host must trust the Caddy root CA. TLS verification stays enabled.

See `deploy/reverse-proxy/`.

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
