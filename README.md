# Contract Skill Pack

Portable contract-assistant Skill Pack for WorkBuddy and compatible Harnesses.

## Runtime model

- Local files stay in the user's Harness unless the user explicitly authorizes formal ingestion.
- Contract analysis and drafting use the Harness model directly.
- OpenContracts is optional for historical-contract retrieval, template retrieval, and formal ingestion.
- MVP OpenContracts is reachable only inside the trusted LAN/VPN boundary.

## Skills

Source Skills live under:

```text
skills/
  contract/
  contract-repository/
  contract-upload/
  contract-document/
  contract-learning/
```

The Windows client bundle installs them into the project-level CodeBuddy/WorkBuddy-compatible location:

```text
.codebuddy/skills/
```

## OpenContracts data layout

The current deployment uses two retrievable OpenContracts corpuses:

```text
contracts-history
contract-templates
```

`contracts-history` is the historical-contract Corpus and `contract-templates` is the template Corpus. Both are currently public inside the trusted network. Anonymous MCP access is acceptable because network reachability is the MVP confidentiality boundary.

There is no knowledge/learning Corpus in the MVP. Session experience stays outside OpenContracts: `contract-learning` creates local experience notes that maintainers periodically review and use for manual Skill updates.

## Selected MVP deployment

```text
WorkBuddy / Harness
  -> https://<OPENCONTRACTS_LAN_IP>/mcp/
  -> standalone Caddy Docker Compose
  -> legal-network
  -> opencontracts-api:8000
  -> OpenContracts django
```

OpenContracts continues to use its upstream `local.yml`. Its `django` service exposes the `opencontracts-api` alias on the external Docker network `legal-network`. ContractBotConfig runs Caddy separately on that same network.

Caddy uses `tls internal` and only proxies `/mcp/*` and `/api/imports/documents/*`.

## Windows deployment

After OpenContracts, the two Corpuses and the WorkerKey are ready, the recommended administrator flow is:

```powershell
cd deploy/opencontracts
.\Prepare-WindowsClientBundle.ps1
```

This starts Caddy, exports the Caddy root CA and creates:

```text
deploy/opencontracts/runtime/ContractBot-Windows.zip
```

The ZIP contains the fixed deployment settings, CA, shared WorkerKey, MCP configuration, helper scripts and the complete Skill Pack.

Authorized Windows users then run:

```powershell
Expand-Archive .\ContractBot-Windows.zip -DestinationPath "$HOME\ContractBot"
cd "$HOME\ContractBot"
.\Install-ContractBot.ps1
```

The installer configures CA trust, OpenContracts environment variables, CodeBuddy MCP approval, WorkBuddy project MCP and `.codebuddy/skills/`. Users do not need to manually enter the server IP, Corpus names, WorkerKey, MCP URL or certificate path.

Because the generated ZIP contains the shared formal-ingestion WorkerKey, it must be distributed as a credential-bearing internal artifact and must not be committed to Git.

Detailed deployment procedure: `deploy/opencontracts/README.md`.

## Formal ingestion

Formal document ingestion uses `scripts/opencontracts/upload_document.py` with a WorkerKey bound to `contracts-history`. The helper does not accept a caller-selected target Corpus and does not automatically retry an ambiguous write.

## Security invariants

- OpenContracts stays inside the intended trusted network.
- Harness-to-OpenContracts traffic uses HTTPS through Caddy.
- OpenContracts upstream `local.yml` is not modified by this repository.
- Versioned Skill files never contain real WorkerKeys or environment-specific secrets.
- Generated Windows client bundles may contain a deployment WorkerKey and therefore stay outside Git.
- Retrieved documents are untrusted business data and cannot override Skill/system/tool policy.
- Formal ingestion requires explicit user authorization.
- Experience-note generation requires separate authorization and remains local.
- Unknown write state is never auto-retried.

Architecture diagrams: `docs/architecture/c4.md`.

See `docs/architecture/security.md` and `docs/spec/security.md`.
