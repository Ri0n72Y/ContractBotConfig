# OpenContracts local.yml + Caddy deployment

This is the selected MVP deployment path.

```text
WorkBuddy / Harness
  -> https://<internal-host>/mcp/
  -> Caddy (internal CA)
  -> OpenContracts django:8000
```

OpenContracts stays on `local.yml`. The three retrieval corpuses remain public inside the trusted network. Formal document ingestion uses a corpus-bound WorkerKey.

## 1. Agent/Harness MCP configuration

The repository root `.mcp.json` is the project-level MCP configuration:

```json
{
  "mcpServers": {
    "opencontracts": {
      "type": "http",
      "url": "${OPENCONTRACTS_MCP_URL}"
    }
  }
}
```

Fill the runtime values from `config/opencontracts.env.example` on each Agent/Harness host. The required values are:

```text
OPENCONTRACTS_BASE_URL=https://<internal-host>
OPENCONTRACTS_MCP_URL=https://<internal-host>/mcp/
OPENCONTRACTS_HISTORY_CORPUS=<actual history corpus slug>
OPENCONTRACTS_TEMPLATE_CORPUS=<actual template corpus slug>
OPENCONTRACTS_KNOWLEDGE_CORPUS=<actual approved-knowledge corpus slug>
OPENCONTRACTS_CA_BUNDLE=<local path to exported caddy-root.crt>
NODE_EXTRA_CA_CERTS=<same caddy-root.crt path>
OPENCONTRACTS_UPLOAD_WORKER_KEY=<one-time WorkerKey; formal ingestion only>
```

Restart WorkBuddy/CodeBuddy after setting persistent environment variables.

## 2. Configure the OpenContracts server

Run `Setup-OpenContractsLocalCaddy.ps1` on the OpenContracts Docker host. It:

- changes the django host mapping from `8000:8000` to `127.0.0.1:8000:8000` and creates a timestamped backup of `local.yml`;
- adds the internal hostname to `DJANGO_ALLOWED_HOSTS` in `.envs/.local/.django`;
- starts the `local.yml` stack;
- verifies the configured retrieval corpus slugs exist and sets them public;
- starts Caddy as a separate Docker container on the same Compose network;
- serves the internal hostname with `tls internal`;
- exports Caddy's root certificate to `.contractbot-caddy/caddy-root.crt`.

Example on the OpenContracts host:

```powershell
.\Setup-OpenContractsLocalCaddy.ps1 `
  -OpenContractsPath 'D:\OpenContracts' `
  -InternalHost 'contracts.internal.example' `
  -PublicCorpusSlugs 'contracts-history','contract-templates','approved-knowledge'
```

Use `-StartFullStack` only when this server also needs the OpenContracts local frontend profile.

## 3. Remote PowerShell execution

From an administrator workstation:

```powershell
$session = New-PSSession -ComputerName 'OC-SERVER'

Invoke-Command `
  -Session $session `
  -FilePath '.\deploy\opencontracts\Setup-OpenContractsLocalCaddy.ps1' `
  -ArgumentList 'D:\OpenContracts','contracts.internal.example',@('contracts-history','contract-templates','approved-knowledge')

Copy-Item `
  -FromSession $session `
  'D:\OpenContracts\.contractbot-caddy\caddy-root.crt' `
  '.\caddy-root.crt'
```

`Invoke-Command -FilePath` sends the local script for execution in the remote session; the script does not need to exist on the server beforehand.

## 4. Internal DNS / hosts resolution

Every Agent/Harness host must resolve the same internal hostname to the OpenContracts server IP. Prefer internal DNS. For an MVP without internal DNS, `Configure-AgentOpenContracts.ps1` can maintain the Windows hosts entry when `-ServerIp` is supplied.

Example:

```text
10.10.20.15 contracts.internal.example
```

Do not expose OpenContracts through public NAT/port forwarding.

## 5. Mint the formal-ingestion WorkerKey

First find the raw database ID of the history corpus:

```powershell
Set-Location 'D:\OpenContracts'
docker compose -f local.yml exec -T django python manage.py shell -c "from opencontractserver.corpuses.models import Corpus; print(list(Corpus.objects.filter(slug='contracts-history').values_list('id','slug','is_public')))"
```

Then mint a corpus-scoped token. The plaintext token is printed once only:

```powershell
docker compose -f local.yml exec -T django python manage.py mint_worker_token `
  --corpus <RAW_CORPUS_ID> `
  --worker-name contractbot-formal-ingest `
  --rate-limit 30 `
  --expires-days 365
```

Copy the printed `OC_WORKER_TOKEN=...` value into the Agent/Harness runtime as:

```text
OPENCONTRACTS_UPLOAD_WORKER_KEY=<token>
```

Do not put it in `.mcp.json`, `SKILL.md`, Git, or a checked-in env file.

## 6. Configure a Windows Agent/Harness host

Copy `caddy-root.crt` to the target machine, then run:

```powershell
.\Configure-AgentOpenContracts.ps1 `
  -InternalHost 'contracts.internal.example' `
  -ServerIp '10.10.20.15' `
  -CaddyRootCertificate 'C:\Temp\caddy-root.crt' `
  -HistoryCorpus 'contracts-history' `
  -TemplateCorpus 'contract-templates' `
  -KnowledgeCorpus 'approved-knowledge' `
  -UploadWorkerKey '<WorkerKey>' `
  -EnvironmentScope User
```

For a dedicated always-on WorkBuddy host managed remotely, `-EnvironmentScope Machine` is usually easier, but it requires an elevated session and makes the runtime variables machine-wide. For a personal workstation, run the script as the actual WorkBuddy user with `User` scope.

The script imports the Caddy root certificate and sets both `OPENCONTRACTS_CA_BUNDLE` and `NODE_EXTRA_CA_CERTS` to the installed certificate copy.

## 7. Basic checks

On the OpenContracts host:

```powershell
docker compose -f D:\OpenContracts\local.yml ps
docker ps --filter name=opencontracts-caddy
docker logs --tail 100 opencontracts-caddy
```

On an Agent/Harness host after restart:

```powershell
Resolve-DnsName contracts.internal.example
Invoke-WebRequest https://contracts.internal.example/admin/login/ -UseBasicParsing
```

Then use WorkBuddy/CodeBuddy MCP diagnostics to confirm `opencontracts` connects and exposes the expected tools.

For upload-helper validation, set the runtime variables and run `scripts/opencontracts/check_config.py`, then perform a controlled test upload with `upload_document.py`.

## 8. Firewall baseline

The selected topology expects:

- LAN/VPN clients -> Caddy `443/tcp` allowed;
- optional `80/tcp` allowed only for Caddy HTTP-to-HTTPS redirect;
- raw OpenContracts `8000/tcp` bound to `127.0.0.1` only;
- no public Internet ingress to 80/443;
- database, Redis, parsers, embedders and internal Docker networks not exposed to normal clients.
