[CmdletBinding()]
param(
    [string]$OutputZip = "",
    [string]$EnvFile = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $ScriptDir)
$ClientDir = Join-Path $RepoRoot "client"
$CaddyDir = Join-Path $ScriptDir "caddy"

if (-not $EnvFile) { $EnvFile = Join-Path $ScriptDir ".env" }
if (-not (Test-Path $EnvFile)) { throw "Environment file not found: $EnvFile" }

Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#")) { return }
    $pair = $line -split "=", 2
    if ($pair.Count -eq 2) {
        [Environment]::SetEnvironmentVariable($pair[0].Trim(), $pair[1].Trim(), "Process")
    }
}

foreach ($name in @("OPENCONTRACTS_LAN_IP", "OPENCONTRACTS_UPLOAD_WORKER_KEY")) {
    if (-not [Environment]::GetEnvironmentVariable($name, "Process")) {
        throw "$name is missing from $EnvFile"
    }
}
if (-not (Test-Path $ClientDir)) { throw "Client directory not found: $ClientDir" }

# Start/update the HTTPS gateway. The WorkerKey stays on the server and is
# passed only to Caddy, which injects it for the formal-ingestion route.
& (Join-Path $CaddyDir "manage.ps1") setup

$runtimeDir = Join-Path $ScriptDir "runtime"
if (-not $OutputZip) {
    $OutputZip = Join-Path $runtimeDir "ContractBot-Client.zip"
}
elseif (-not [System.IO.Path]::IsPathRooted($OutputZip)) {
    $OutputZip = Join-Path $ScriptDir $OutputZip
}
$OutputZip = [System.IO.Path]::GetFullPath($OutputZip)
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutputZip) | Out-Null
if (Test-Path $OutputZip) { Remove-Item $OutputZip -Force }

$items = Get-ChildItem -Force $ClientDir
Compress-Archive -Path $items.FullName -DestinationPath $OutputZip -Force

Write-Host "Caddy HTTPS gateway started."
Write-Host "Client ZIP: $OutputZip"
Write-Host "Client bundle contains only the fixed MCP configuration, Skills and installation instructions."
Write-Host "The WorkerKey remains on the server."
