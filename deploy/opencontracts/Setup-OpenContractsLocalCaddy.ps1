[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$OpenContractsPath,

    [Parameter(Mandatory = $true)]
    [string]$InternalHost,

    [string[]]$PublicCorpusSlugs = @(
        "contracts-history",
        "contract-templates",
        "approved-knowledge"
    ),

    [string]$CaddyImage = "caddy:2-alpine",
    [string]$CaddyContainerName = "opencontracts-caddy",
    [switch]$StartFullStack
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Invoke-DockerChecked {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
    & docker @Args
    if ($LASTEXITCODE -ne 0) {
        throw "docker command failed: docker $($Args -join ' ')"
    }
}

function Set-DotEnvValue {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Value
    )

    $content = if (Test-Path $Path) { [System.IO.File]::ReadAllText($Path) } else { "" }
    $pattern = "(?m)^" + [regex]::Escape($Name) + "=.*$"
    $line = "$Name=$Value"

    if ([regex]::IsMatch($content, $pattern)) {
        $content = [regex]::Replace($content, $pattern, $line)
    }
    else {
        if ($content.Length -gt 0 -and -not $content.EndsWith("`n")) {
            $content += "`r`n"
        }
        $content += $line + "`r`n"
    }

    [System.IO.File]::WriteAllText(
        $Path,
        $content,
        [System.Text.UTF8Encoding]::new($false)
    )
}

$resolvedPath = (Resolve-Path $OpenContractsPath).Path
$composePath = Join-Path $resolvedPath "local.yml"
$djangoEnvPath = Join-Path $resolvedPath ".envs/.local/.django"

if (-not (Test-Path $composePath)) {
    throw "local.yml not found under $resolvedPath"
}
if (-not (Test-Path $djangoEnvPath)) {
    throw ".envs/.local/.django not found under $resolvedPath"
}

Push-Location $resolvedPath
try {
    Invoke-DockerChecked version
    Invoke-DockerChecked compose -f local.yml config --services

    # Keep the raw local HTTP port host-local so LAN clients cannot bypass Caddy.
    $composeText = [System.IO.File]::ReadAllText($composePath)
    if ($composeText -notmatch '127\.0\.0\.1:8000:8000') {
        if ($composeText -notmatch '"8000:8000"') {
            throw "Could not find the expected django port mapping \"8000:8000\" in local.yml"
        }

        $backupPath = "$composePath.contractbot-backup-$((Get-Date).ToString('yyyyMMdd-HHmmss'))"
        Copy-Item $composePath $backupPath
        $composeText = $composeText -replace '"8000:8000"', '"127.0.0.1:8000:8000"'
        [System.IO.File]::WriteAllText(
            $composePath,
            $composeText,
            [System.Text.UTF8Encoding]::new($false)
        )
        Write-Host "Updated django port binding; backup: $backupPath"
    }

    # Django rejects unknown Host headers by default; allow the internal Caddy hostname.
    Set-DotEnvValue -Path $djangoEnvPath -Name "DJANGO_ALLOWED_HOSTS" -Value "localhost,127.0.0.1,0.0.0.0,$InternalHost"

    if ($StartFullStack) {
        Invoke-DockerChecked compose -f local.yml --profile fullstack up -d
    }
    else {
        Invoke-DockerChecked compose -f local.yml up -d
    }

    $djangoId = (& docker compose -f local.yml ps -q django).Trim()
    if (-not $djangoId) {
        throw "Could not resolve the running django container."
    }

    $inspect = (& docker inspect $djangoId) | ConvertFrom-Json
    $networkNames = @($inspect[0].NetworkSettings.Networks.PSObject.Properties.Name)
    if ($networkNames.Count -lt 1) {
        throw "Could not resolve the OpenContracts compose network."
    }
    $networkName = $networkNames[0]

    # Keep the three MVP retrieval corpuses public and fail if the configured slugs are wrong.
    $slugJson = $PublicCorpusSlugs | ConvertTo-Json -Compress
    $python = @"
import json
from opencontractserver.corpuses.models import Corpus
slugs = json.loads(r'''$slugJson''')
qs = Corpus.objects.filter(slug__in=slugs)
found = list(qs.values_list('slug', flat=True))
missing = sorted(set(slugs) - set(found))
print('FOUND=' + ','.join(found))
print('MISSING=' + ','.join(missing))
if missing:
    raise SystemExit(3)
qs.update(is_public=True)
print('PUBLIC=OK')
"@
    & docker compose -f local.yml exec -T django python manage.py shell -c $python
    if ($LASTEXITCODE -ne 0) {
        throw "Corpus validation/public update failed. Check the slugs passed to -PublicCorpusSlugs."
    }

    $stateDir = Join-Path $resolvedPath ".contractbot-caddy"
    New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
    $caddyFilePath = Join-Path $stateDir "Caddyfile"
    $caddyFile = @"
$InternalHost {
    tls internal
    reverse_proxy django:8000
}
"@
    [System.IO.File]::WriteAllText(
        $caddyFilePath,
        $caddyFile,
        [System.Text.UTF8Encoding]::new($false)
    )

    $existing = (& docker ps -a --filter "name=^/${CaddyContainerName}$" --format "{{.ID}}").Trim()
    if ($existing) {
        Invoke-DockerChecked rm -f $CaddyContainerName
    }

    Invoke-DockerChecked volume create opencontracts_caddy_data
    Invoke-DockerChecked volume create opencontracts_caddy_config
    Invoke-DockerChecked create `
        --name $CaddyContainerName `
        --restart unless-stopped `
        --network $networkName `
        -p 80:80 `
        -p 443:443 `
        -v opencontracts_caddy_data:/data `
        -v opencontracts_caddy_config:/config `
        $CaddyImage

    Invoke-DockerChecked cp $caddyFilePath "${CaddyContainerName}:/etc/caddy/Caddyfile"
    Invoke-DockerChecked start $CaddyContainerName

    Start-Sleep -Seconds 2
    Invoke-DockerChecked exec $CaddyContainerName caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile

    $caPath = Join-Path $stateDir "caddy-root.crt"
    $copied = $false
    for ($i = 0; $i -lt 20; $i++) {
        & docker cp "${CaddyContainerName}:/data/caddy/pki/authorities/local/root.crt" $caPath 2>$null
        if ($LASTEXITCODE -eq 0 -and (Test-Path $caPath)) {
            $copied = $true
            break
        }
        Start-Sleep -Seconds 1
    }
    if (-not $copied) {
        throw "Caddy started but its internal root certificate could not be exported."
    }

    Write-Host ""
    Write-Host "OpenContracts local.yml + Caddy configured."
    Write-Host "BASE_URL=https://$InternalHost"
    Write-Host "MCP_URL=https://$InternalHost/mcp/"
    Write-Host "CA_ROOT=$caPath"
    Write-Host "RAW_DJANGO=http://127.0.0.1:8000"
    Write-Host "CADDY_CONTAINER=$CaddyContainerName"
    Write-Host ""
    Write-Host "Next: make $InternalHost resolve to this server from every Agent host, distribute CA_ROOT, then mint a WorkerKey for the history corpus."
}
finally {
    Pop-Location
}
