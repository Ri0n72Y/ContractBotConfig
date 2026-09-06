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
$BundledSkillsDir = Join-Path $ScriptDir ".codebuddy\skills"
$BundledScriptsDir = Join-Path $ScriptDir "scripts"

if (-not (Test-Path $ConfigFile)) {
    throw "Client configuration not found: $ConfigFile"
}
if (-not (Test-Path $CertificateFile)) {
    throw "Caddy root certificate not found: $CertificateFile"
}
if (-not (Test-Path $McpFile)) {
    throw "MCP configuration not found: $McpFile"
}
if (-not (Test-Path $BundledSkillsDir)) {
    throw "Bundled Skills not found: $BundledSkillsDir"
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

$projectRoot = if ($TargetDirectory) {
    [System.IO.Path]::GetFullPath($TargetDirectory)
}
else {
    $ScriptDir
}
New-Item -ItemType Directory -Force -Path $projectRoot | Out-Null

if ([System.IO.Path]::GetFullPath($McpFile) -ne [System.IO.Path]::GetFullPath((Join-Path $projectRoot ".mcp.json"))) {
    Copy-Item $McpFile (Join-Path $projectRoot ".mcp.json") -Force
}

$codeBuddyDir = Join-Path $projectRoot ".codebuddy"
$targetSkillsDir = Join-Path $codeBuddyDir "skills"
New-Item -ItemType Directory -Force -Path $targetSkillsDir | Out-Null
Copy-Item (Join-Path $BundledSkillsDir "*") $targetSkillsDir -Recurse -Force

if (Test-Path $BundledScriptsDir) {
    $targetScriptsDir = Join-Path $projectRoot "scripts"
    New-Item -ItemType Directory -Force -Path $targetScriptsDir | Out-Null
    Copy-Item (Join-Path $BundledScriptsDir "*") $targetScriptsDir -Recurse -Force
}

$settingsLocal = [ordered]@{
    enabledMcpjsonServers = @("opencontracts")
    permissions = [ordered]@{
        deny = @(
            "mcp__opencontracts__list_threads",
            "mcp__opencontracts__get_thread_messages",
            "mcp__opencontracts__create_thread_message",
            "mcp__opencontracts__list_annotations",
            "mcp__opencontracts__list_relationships"
        )
    }
    env = $values
}
$settingsLocal | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $codeBuddyDir "settings.local.json") -Encoding UTF8

$workBuddyDir = Join-Path $projectRoot ".workbuddy"
New-Item -ItemType Directory -Force -Path $workBuddyDir | Out-Null
$workBuddyMcp = [ordered]@{
    mcpServers = [ordered]@{
        opencontracts = [ordered]@{
            type = "http"
            url = "$baseUrl/mcp/"
        }
    }
}
$workBuddyMcp | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $workBuddyDir "mcp.json") -Encoding UTF8

$gitDir = Join-Path $projectRoot ".git"
if (Test-Path $gitDir) {
    $excludeFile = Join-Path $gitDir "info\exclude"
    $excludeDir = Split-Path -Parent $excludeFile
    New-Item -ItemType Directory -Force -Path $excludeDir | Out-Null
    if (-not (Test-Path $excludeFile)) {
        New-Item -ItemType File -Path $excludeFile | Out-Null
    }
    $excludeLines = Get-Content $excludeFile -ErrorAction SilentlyContinue
    if ($excludeLines -notcontains ".codebuddy/settings.local.json") {
        Add-Content $excludeFile ".codebuddy/settings.local.json"
    }
}

Write-Host ""
Write-Host "ContractBot OpenContracts client installed."
Write-Host "OpenContracts: $baseUrl"
Write-Host "History corpus: $historyCorpus"
Write-Host "Template corpus: $templateCorpus"
Write-Host "CA: $caTarget"
Write-Host "WorkerKey: configured"
Write-Host "Workspace: $projectRoot"
Write-Host "CodeBuddy Skills: $targetSkillsDir"
Write-Host "CodeBuddy MCP approval: configured"
Write-Host "WorkBuddy MCP: configured"
Write-Host ""
Write-Host "Restart WorkBuddy/CodeBuddy, then use this workspace."
