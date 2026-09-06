[CmdletBinding()]
param(
    [string]$WorkerKey = "",
    [string]$OutputZip = "",
    [string]$EnvFile = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $ScriptDir)
$CaddyDir = Join-Path $ScriptDir "caddy"
$ClientInstaller = Join-Path $ScriptDir "client\Install-ContractBot.ps1"

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

if (-not $env:OPENCONTRACTS_LAN_IP) { throw "OPENCONTRACTS_LAN_IP is missing" }
if (-not $env:HISTORY_CORPUS) { throw "HISTORY_CORPUS is missing" }
if (-not $env:TEMPLATE_CORPUS) { throw "TEMPLATE_CORPUS is missing" }
if (-not $env:CADDY_CA_OUTPUT) { throw "CADDY_CA_OUTPUT is missing" }

$parsedIp = $null
if (-not [System.Net.IPAddress]::TryParse($env:OPENCONTRACTS_LAN_IP, [ref]$parsedIp) -or
    $parsedIp.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) {
    throw "OPENCONTRACTS_LAN_IP must be an IPv4 address"
}

if (-not $WorkerKey) {
    $secureWorkerKey = Read-Host "OpenContracts WorkerKey for Windows clients" -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureWorkerKey)
    try {
        $WorkerKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}
if (-not $WorkerKey) { throw "WorkerKey is required" }

& (Join-Path $CaddyDir "manage.ps1") setup
if ($LASTEXITCODE -ne 0) {
    throw "Caddy setup failed"
}

$caPath = $env:CADDY_CA_OUTPUT
if (-not [System.IO.Path]::IsPathRooted($caPath)) {
    $caPath = Join-Path $ScriptDir $caPath
}
$caPath = [System.IO.Path]::GetFullPath($caPath)
if (-not (Test-Path $caPath)) {
    throw "Exported Caddy root certificate not found: $caPath"
}

$runtimeDir = Join-Path $ScriptDir "runtime"
$bundleDir = Join-Path $runtimeDir "ContractBot-Windows"
if (-not $OutputZip) {
    $OutputZip = Join-Path $runtimeDir "ContractBot-Windows.zip"
}
elseif (-not [System.IO.Path]::IsPathRooted($OutputZip)) {
    $OutputZip = Join-Path $ScriptDir $OutputZip
}
$OutputZip = [System.IO.Path]::GetFullPath($OutputZip)

if (Test-Path $bundleDir) {
    Remove-Item $bundleDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $bundleDir | Out-Null

Copy-Item $ClientInstaller (Join-Path $bundleDir "Install-ContractBot.ps1") -Force
Copy-Item $caPath (Join-Path $bundleDir "opencontracts-caddy-root.crt") -Force
Copy-Item (Join-Path $RepoRoot ".mcp.json") (Join-Path $bundleDir ".mcp.json") -Force
Copy-Item (Join-Path $RepoRoot "skills") (Join-Path $bundleDir "skills") -Recurse -Force
Copy-Item (Join-Path $RepoRoot "scripts\opencontracts") (Join-Path $bundleDir "scripts\opencontracts") -Recurse -Force
Copy-Item (Join-Path $RepoRoot "config\workbuddy.settings.example.json") (Join-Path $bundleDir "workbuddy.settings.example.json") -Force

$clientConfig = [ordered]@{
    serverIp = $env:OPENCONTRACTS_LAN_IP
    historyCorpus = $env:HISTORY_CORPUS
    templateCorpus = $env:TEMPLATE_CORPUS
    uploadWorkerKey = $WorkerKey
}
$clientConfig | ConvertTo-Json | Set-Content (Join-Path $bundleDir "contractbot-client.json") -Encoding UTF8

$readme = @"
ContractBot Windows Client
==========================

1. Open PowerShell in this directory.
2. Run:

   .\Install-ContractBot.ps1

3. Restart WorkBuddy/CodeBuddy.
4. Open this directory as the contract workspace.

The installer trusts the bundled OpenContracts CA and configures the current
Windows user with the server URL, corpus names, and shared formal-ingestion
WorkerKey. The WorkerKey is contained in contractbot-client.json, so distribute
this ZIP only to authorized users.

To copy the Skill Pack into another project directory instead, run:

   .\Install-ContractBot.ps1 -TargetDirectory 'C:\path\to\project'
"@
$readme | Set-Content (Join-Path $bundleDir "README.txt") -Encoding UTF8

$outputDir = Split-Path -Parent $OutputZip
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
if (Test-Path $OutputZip) {
    Remove-Item $OutputZip -Force
}
Compress-Archive -Path (Join-Path $bundleDir "*") -DestinationPath $OutputZip -Force

Write-Host ""
Write-Host "Windows client bundle created."
Write-Host "Server: https://$($env:OPENCONTRACTS_LAN_IP)"
Write-Host "History corpus: $($env:HISTORY_CORPUS)"
Write-Host "Template corpus: $($env:TEMPLATE_CORPUS)"
Write-Host "WorkerKey: embedded"
Write-Host "Bundle: $OutputZip"
Write-Host ""
Write-Host "Distribute this ZIP only to authorized users."
