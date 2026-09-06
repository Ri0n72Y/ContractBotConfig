[CmdletBinding()]
param(
    [string]$TargetDirectory = "",

    [ValidateSet("User", "Machine")]
    [string]$EnvironmentScope = "User"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ConfigFile = Join-Path $ScriptDir "contractbot-client.json"
$CertificateFile = Join-Path $ScriptDir "opencontracts-caddy-root.crt"
$McpFile = Join-Path $ScriptDir ".mcp.json"
$SkillsDir = Join-Path $ScriptDir "skills"
$ScriptsDir = Join-Path $ScriptDir "scripts"
$WorkBuddySettings = Join-Path $ScriptDir "workbuddy.settings.example.json"

if (-not (Test-Path $ConfigFile)) {
    throw "Client configuration not found: $ConfigFile"
}
if (-not (Test-Path $CertificateFile)) {
    throw "Caddy root certificate not found: $CertificateFile"
}

$config = Get-Content $ConfigFile -Raw | ConvertFrom-Json
$serverIp = [string]$config.serverIp
$historyCorpus = [string]$config.historyCorpus
$templateCorpus = [string]$config.templateCorpus
$workerKey = [string]$config.uploadWorkerKey

$parsedIp = $null
if (-not [System.Net.IPAddress]::TryParse($serverIp, [ref]$parsedIp) -or
    $parsedIp.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) {
    throw "Invalid OpenContracts server IPv4 address in client configuration."
}
if (-not $historyCorpus) { throw "historyCorpus is missing from client configuration" }
if (-not $templateCorpus) { throw "templateCorpus is missing from client configuration" }

if (-not $workerKey) {
    $secureWorkerKey = Read-Host "OpenContracts WorkerKey" -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureWorkerKey)
    try {
        $workerKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}
if (-not $workerKey) { throw "OpenContracts WorkerKey is required" }

$caDir = if ($EnvironmentScope -eq "Machine") {
    Join-Path $env:ProgramData "ContractBot"
}
else {
    Join-Path $env:LOCALAPPDATA "ContractBot"
}
New-Item -ItemType Directory -Force -Path $caDir | Out-Null
$caTarget = Join-Path $caDir "opencontracts-caddy-root.crt"
Copy-Item $CertificateFile $caTarget -Force

$certStore = if ($EnvironmentScope -eq "Machine") {
    "Cert:\LocalMachine\Root"
}
else {
    "Cert:\CurrentUser\Root"
}
Import-Certificate -FilePath $caTarget -CertStoreLocation $certStore | Out-Null

$baseUrl = "https://$serverIp"
$values = [ordered]@{
    OPENCONTRACTS_BASE_URL = $baseUrl
    OPENCONTRACTS_MCP_URL = "$baseUrl/mcp/"
    OPENCONTRACTS_HISTORY_CORPUS = $historyCorpus
    OPENCONTRACTS_TEMPLATE_CORPUS = $templateCorpus
    OPENCONTRACTS_CA_BUNDLE = $caTarget
    NODE_EXTRA_CA_CERTS = $caTarget
    OPENCONTRACTS_UPLOAD_WORKER_KEY = $workerKey
    OPENCONTRACTS_ALLOW_INSECURE_HTTP = "0"
    OPENCONTRACTS_UPLOAD_TIMEOUT_SECONDS = "60"
}

foreach ($entry in $values.GetEnumerator()) {
    [Environment]::SetEnvironmentVariable($entry.Key, [string]$entry.Value, $EnvironmentScope)
    [Environment]::SetEnvironmentVariable($entry.Key, [string]$entry.Value, "Process")
}

if ($TargetDirectory) {
    $target = [System.IO.Path]::GetFullPath($TargetDirectory)
    New-Item -ItemType Directory -Force -Path $target | Out-Null

    if (Test-Path $McpFile) {
        Copy-Item $McpFile (Join-Path $target ".mcp.json") -Force
    }
    if (Test-Path $SkillsDir) {
        Copy-Item $SkillsDir (Join-Path $target "skills") -Recurse -Force
    }
    if (Test-Path $ScriptsDir) {
        Copy-Item $ScriptsDir (Join-Path $target "scripts") -Recurse -Force
    }
    if (Test-Path $WorkBuddySettings) {
        Copy-Item $WorkBuddySettings (Join-Path $target "workbuddy.settings.example.json") -Force
    }
}

Write-Host ""
Write-Host "ContractBot OpenContracts client installed."
Write-Host "OpenContracts: $baseUrl"
Write-Host "History corpus: $historyCorpus"
Write-Host "Template corpus: $templateCorpus"
Write-Host "CA: $caTarget"
Write-Host "WorkerKey: configured"
if ($TargetDirectory) {
    Write-Host "Project files copied to: $target"
}
else {
    Write-Host "Use this extracted directory directly as the WorkBuddy project, or rerun with -TargetDirectory <project-path>."
}
Write-Host ""
Write-Host "Restart WorkBuddy/CodeBuddy after installation."
