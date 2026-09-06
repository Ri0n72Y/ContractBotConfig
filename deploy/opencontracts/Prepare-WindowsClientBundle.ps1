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

$parsedIp = $null
if (-not [System.Net.IPAddress]::TryParse($env:OPENCONTRACTS_LAN_IP, [ref]$parsedIp) -or
    $parsedIp.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) {
    throw "OPENCONTRACTS_LAN_IP must be an IPv4 address"
}

# Start the HTTP gateway. The WorkerKey stays in the server .env and is passed
# only to Caddy, which injects it for the formal-ingestion route.
& (Join-Path $CaddyDir "manage.ps1") setup

$baseUrl = "http://$($env:OPENCONTRACTS_LAN_IP)"
$mcp = [ordered]@{
    mcpServers = [ordered]@{
        opencontracts = [ordered]@{
            type = "http"
            url = "$baseUrl/mcp/"
            description = "OpenContracts MCP on the trusted internal network"
        }
    }
}
$mcp | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $ClientDir ".mcp.json") -Encoding UTF8

$deployment = @"
# Contract Upload Deployment

IMPORT_URL=$baseUrl/api/imports/documents/

The client must not send an Authorization header. Caddy injects the corpus-bound WorkerKey server-side.
"@
$deployment | Set-Content (Join-Path $ClientDir "skills\contract-upload\DEPLOYMENT.md") -Encoding UTF8

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

Write-Host "Client directory prepared: $ClientDir"
Write-Host "Client ZIP: $OutputZip"
Write-Host "Client bundle contains MCP + Skills only; the WorkerKey remains on the server."
