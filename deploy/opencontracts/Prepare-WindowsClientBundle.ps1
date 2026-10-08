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

# The versioned MCP URL is fixed. Fail the release if it does not match
# this host, rather than distributing a client ZIP pointing to another IP.
$mcpFile = Join-Path $ClientDir ".mcp.json"
$mcpConfig = Get-Content -LiteralPath $mcpFile -Raw | ConvertFrom-Json
$actualMcpUrl = [string]$mcpConfig.mcpServers.opencontracts.url
$expectedMcpUrl = "https://$([Environment]::GetEnvironmentVariable('OPENCONTRACTS_LAN_IP', 'Process'))/mcp/"
if ($actualMcpUrl -cne $expectedMcpUrl) {
    throw "Client MCP URL ($actualMcpUrl) does not match server ($expectedMcpUrl). Update the versioned client/.mcp.json before packaging."
}

# Start/update the HTTPS gateway. The WorkerKey stays on the server and is
# passed only to Caddy, which injects it for the formal-ingestion route.
& (Join-Path $CaddyDir "manage.ps1") setup

# Export only the public Caddy root certificate into the client package.
# The CA private key remains inside Caddy's persistent data volume.
$clientCa = Join-Path $ClientDir "certificates\opencontracts-caddy-root.crt"
& (Join-Path $CaddyDir "manage.ps1") export-ca -Output $clientCa

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

# Confirm the release archive actually contains every installable resource.
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::OpenRead($OutputZip)
try {
    $entryNames = @($archive.Entries | ForEach-Object { $_.FullName.Replace('\', '/') })
    $required = @(
        ".mcp.json",
        "INSTALL.md",
        "README.md",
        "certificates/opencontracts-caddy-root.crt",
        "skills/contract/SKILL.md",
        "skills/contract-repository/SKILL.md",
        "skills/contract-upload/SKILL.md",
        "skills/contract-document/SKILL.md",
        "skills/contract-learning/SKILL.md"
    )
    foreach ($name in $required) {
        if ($entryNames -cnotcontains $name) {
            throw "Client ZIP is missing required file: $name"
        }
    }
}
finally {
    $archive.Dispose()
}

Write-Host "Caddy HTTPS gateway started."
Write-Host "Caddy root CA added to client/certificates/."
Write-Host "Client ZIP: $OutputZip"
Write-Host "The WorkerKey remains on the server."
