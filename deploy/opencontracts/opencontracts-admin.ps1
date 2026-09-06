[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("create-corpuses", "publish-corpuses", "mint-worker-key")]
    [string]$Command,

    [string]$EnvFile = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $EnvFile) {
    $EnvFile = Join-Path $ScriptDir ".env"
}

if (-not (Test-Path $EnvFile)) {
    throw "Environment file not found: $EnvFile"
}

Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#")) { return }
    $pair = $line -split "=", 2
    if ($pair.Count -eq 2) {
        [Environment]::SetEnvironmentVariable($pair[0].Trim(), $pair[1].Trim(), "Process")
    }
}

if (-not $env:OPENCONTRACTS_LOCAL_YML) {
    throw "OPENCONTRACTS_LOCAL_YML is missing"
}
if (-not $env:HISTORY_CORPUS) {
    throw "HISTORY_CORPUS is missing"
}
if (-not $env:TEMPLATE_CORPUS) {
    throw "TEMPLATE_CORPUS is missing"
}

function Invoke-OpenContractsCompose {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)

    & docker compose -f $env:OPENCONTRACTS_LOCAL_YML @Args
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose failed"
    }
}

switch ($Command) {
    "create-corpuses" {
        $code = @'
import os
from django.contrib.auth import get_user_model
from opencontractserver.corpuses.models import Corpus
from opencontractserver.corpuses.services import CorpusService

owner = get_user_model().objects.filter(is_superuser=True).order_by("pk").first()
if owner is None:
    raise RuntimeError("No superuser found; create one before initializing ContractBot corpuses.")

specs = [
    (os.environ["HISTORY_CORPUS"], "Contract History", "Historical contracts used by ContractBot"),
    (os.environ["TEMPLATE_CORPUS"], "Contract Templates", "Contract templates used by ContractBot"),
]

for slug, title, description in specs:
    corpus, created = Corpus.objects.get_or_create(
        slug=slug,
        creator=owner,
        defaults={
            "title": title,
            "description": description,
            "auto_branding_enabled": False,
        },
    )
    CorpusService.grant_creator_permissions(owner, corpus)
    print(f"CORPUS={slug} ID={corpus.pk} CREATED={created}")
'@

        Invoke-OpenContractsCompose exec -T `
            -e "HISTORY_CORPUS=$($env:HISTORY_CORPUS)" `
            -e "TEMPLATE_CORPUS=$($env:TEMPLATE_CORPUS)" `
            django /entrypoint python manage.py shell -c $code
    }

    "publish-corpuses" {
        $code = @'
import os
from opencontractserver.corpuses.models import Corpus

for slug in [os.environ["HISTORY_CORPUS"], os.environ["TEMPLATE_CORPUS"]]:
    corpus = Corpus.objects.get(slug=slug)
    if not corpus.is_public:
        corpus.is_public = True
        corpus.save()
    print(f"PUBLIC={slug} ID={corpus.pk}")
'@

        Invoke-OpenContractsCompose exec -T `
            -e "HISTORY_CORPUS=$($env:HISTORY_CORPUS)" `
            -e "TEMPLATE_CORPUS=$($env:TEMPLATE_CORPUS)" `
            django /entrypoint python manage.py shell -c $code
    }

    "mint-worker-key" {
        $code = @'
import os
from opencontractserver.corpuses.models import Corpus
print(f"HISTORY_ID={Corpus.objects.get(slug=os.environ['HISTORY_CORPUS']).pk}")
'@

        $result = & docker compose -f $env:OPENCONTRACTS_LOCAL_YML exec -T `
            -e "HISTORY_CORPUS=$($env:HISTORY_CORPUS)" `
            django /entrypoint python manage.py shell -c $code
        if ($LASTEXITCODE -ne 0) {
            throw "docker compose failed while resolving history corpus id"
        }

        $historyLine = $result | Where-Object { $_ -match '^HISTORY_ID=\d+$' } | Select-Object -Last 1
        if (-not $historyLine) {
            throw "Could not resolve history corpus id"
        }
        $historyId = ($historyLine -split "=", 2)[1]

        Invoke-OpenContractsCompose exec -T django /entrypoint python manage.py mint_worker_token `
            --corpus $historyId `
            --worker-name $(if ($env:WORKER_NAME) { $env:WORKER_NAME } else { "contractbot-formal-ingest" }) `
            --rate-limit $(if ($env:WORKER_RATE_LIMIT) { $env:WORKER_RATE_LIMIT } else { "30" }) `
            --expires-days $(if ($env:WORKER_EXPIRES_DAYS) { $env:WORKER_EXPIRES_DAYS } else { "365" })
    }
}
