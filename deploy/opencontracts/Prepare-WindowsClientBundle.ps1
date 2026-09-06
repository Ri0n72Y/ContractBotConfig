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
    if ($pair.Count -eq 2) { [Environment]::SetEnvironmentVariable($pair[0].Trim(), $pair[1].Trim(), "Process") }
}

foreach ($name in @("OPENCONTRACTS_LAN_IP", "HISTORY_CORPUS", "TEMPLATE_CORPUS", "CADDY_CA_OUTPUT", "OPENCONTRACTS_UPLOAD_WORKER_KEY")) {
    if (-not [Environment]::GetEnvironmentVariable($name, "Process")) { throw "$name is missing from $EnvFile" }
}
if (-not (Test-Path $ClientDir)) { throw "Client directory not found: $ClientDir" }

$parsedIp = $null
if (-not [System.Net.IPAddress]::TryParse($env:OPENCONTRACTS_LAN_IP, [ref]$parsedIp) -or $parsedIp.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) {
    throw "OPENCONTRACTS_LAN_IP must be an IPv4 address"
}

& (Join-Path $CaddyDir "manage.ps1") setup

$caPath = $env:CADDY_CA_OUTPUT
if (-not [System.IO.Path]::IsPathRooted($caPath)) { $caPath = Join-Path $ScriptDir $caPath }
$caPath = [System.IO.Path]::GetFullPath($caPath)
if (-not (Test-Path $caPath)) { throw "Exported Caddy root certificate not found: $caPath" }

$certificateDir = Join-Path $ClientDir "certificates"
$configDir = Join-Path $ClientDir "config"
New-Item -ItemType Directory -Force -Path $certificateDir | Out-Null
New-Item -ItemType Directory -Force -Path $configDir | Out-Null
Copy-Item $caPath (Join-Path $certificateDir "opencontracts-caddy-root.crt") -Force

$baseUrl = "https://$($env:OPENCONTRACTS_LAN_IP)"
$bundle = [ordered]@{
    schemaVersion = 1
    name = "ContractBot"
    installScope = "user"
    server = [ordered]@{ baseUrl = $baseUrl; mcpUrl = "$baseUrl/mcp/" }
    corpuses = [ordered]@{ history = $env:HISTORY_CORPUS; templates = $env:TEMPLATE_CORPUS }
    mcp = [ordered]@{ name = "opencontracts"; type = "http" }
}
$bundle | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $ClientDir "bundle.json") -Encoding UTF8

$secret = [ordered]@{ uploadWorkerKey = $env:OPENCONTRACTS_UPLOAD_WORKER_KEY }
$secret | ConvertTo-Json | Set-Content (Join-Path $configDir "contractbot-client.json") -Encoding UTF8

$runtimeDir = Join-Path $ScriptDir "runtime"
if (-not $OutputZip) { $OutputZip = Join-Path $runtimeDir "ContractBot-Client.zip" }
elseif (-not [System.IO.Path]::IsPathRooted($OutputZip)) { $OutputZip = Join-Path $ScriptDir $OutputZip }
$OutputZip = [System.IO.Path]::GetFullPath($OutputZip)
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutputZip) | Out-Null
if (Test-Path $OutputZip) { Remove-Item $OutputZip -Force }
Compress-Archive -Path (Join-Path $ClientDir "*") -DestinationPath $OutputZip -Force

Write-Host "Client directory prepared: $ClientDir"
Write-Host "Client ZIP: $OutputZip"
Write-Host "The prepared client directory and ZIP contain a formal-ingestion WorkerKey."
