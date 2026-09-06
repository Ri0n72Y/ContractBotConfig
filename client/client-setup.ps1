[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$BundleDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BundleFile = Join-Path $BundleDir "bundle.json"
$SecretFile = Join-Path $BundleDir "config\contractbot-client.json"
$CertificateFile = Join-Path $BundleDir "certificates\opencontracts-caddy-root.crt"
$SkillsDir = Join-Path $BundleDir "skills"
$ScriptsDir = Join-Path $BundleDir "scripts\opencontracts"

foreach ($required in @($BundleFile, $SecretFile, $CertificateFile, $SkillsDir, $ScriptsDir)) {
    if (-not (Test-Path $required)) {
        throw "Required client bundle item not found: $required"
    }
}

$bundle = Get-Content $BundleFile -Raw | ConvertFrom-Json
$secret = Get-Content $SecretFile -Raw | ConvertFrom-Json
$baseUrl = [string]$bundle.server.baseUrl
$mcpUrl = [string]$bundle.server.mcpUrl
$historyCorpus = [string]$bundle.corpuses.history
$templateCorpus = [string]$bundle.corpuses.templates
$workerKey = [string]$secret.uploadWorkerKey

if (-not $baseUrl -or -not $mcpUrl -or -not $historyCorpus -or -not $templateCorpus -or -not $workerKey) {
    throw "Client bundle configuration is incomplete"
}

$runtimeRoot = Join-Path $env:LOCALAPPDATA "ContractBot"
$runtimeScripts = Join-Path $runtimeRoot "scripts\opencontracts"
$runtimeCertificates = Join-Path $runtimeRoot "certificates"
New-Item -ItemType Directory -Force -Path $runtimeScripts | Out-Null
New-Item -ItemType Directory -Force -Path $runtimeCertificates | Out-Null
Copy-Item (Join-Path $ScriptsDir "*") $runtimeScripts -Recurse -Force
$caTarget = Join-Path $runtimeCertificates "opencontracts-caddy-root.crt"
Copy-Item $CertificateFile $caTarget -Force

Import-Certificate -FilePath $caTarget -CertStoreLocation "Cert:\CurrentUser\Root" | Out-Null

$values = [ordered]@{
    CONTRACTBOT_HOME = $runtimeRoot
    OPENCONTRACTS_BASE_URL = $baseUrl.TrimEnd('/')
    OPENCONTRACTS_MCP_URL = $mcpUrl
    OPENCONTRACTS_HISTORY_CORPUS = $historyCorpus
    OPENCONTRACTS_TEMPLATE_CORPUS = $templateCorpus
    OPENCONTRACTS_CA_BUNDLE = $caTarget
    NODE_EXTRA_CA_CERTS = $caTarget
    OPENCONTRACTS_UPLOAD_WORKER_KEY = $workerKey
    OPENCONTRACTS_ALLOW_INSECURE_HTTP = "0"
    OPENCONTRACTS_UPLOAD_TIMEOUT_SECONDS = "60"
}
foreach ($entry in $values.GetEnumerator()) {
    [Environment]::SetEnvironmentVariable($entry.Key, [string]$entry.Value, "User")
    [Environment]::SetEnvironmentVariable($entry.Key, [string]$entry.Value, "Process")
}

# Install Python helper dependency when a normal Python launcher is available.
$python = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    $python = @("py", "-3")
}
elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $python = @("python")
}
if ($python) {
    $requirements = Join-Path $runtimeScripts "requirements.txt"
    & $python[0] @($python[1..($python.Count - 1)]) -m pip install --user -r $requirements | Out-Null
}

# CodeBuddy: official user scope is ~/.codebuddy (or CODEBUDDY_CONFIG_DIR).
$codeBuddyHome = if ($env:CODEBUDDY_CONFIG_DIR) { $env:CODEBUDDY_CONFIG_DIR } else { Join-Path $HOME ".codebuddy" }
New-Item -ItemType Directory -Force -Path $codeBuddyHome | Out-Null
$codeBuddySkills = Join-Path $codeBuddyHome "skills"
New-Item -ItemType Directory -Force -Path $codeBuddySkills | Out-Null
Copy-Item (Join-Path $SkillsDir "*") $codeBuddySkills -Recurse -Force

$codeBuddy = Get-Command codebuddy -ErrorAction SilentlyContinue
if ($codeBuddy) {
    $mcpObject = [ordered]@{ type = "http"; url = $mcpUrl; description = "OpenContracts MCP over trusted internal HTTPS" }
    $mcpJson = $mcpObject | ConvertTo-Json -Compress
    & $codeBuddy.Source mcp add-json --scope user opencontracts $mcpJson | Out-Null
}
else {
    $codeBuddyMcp = Join-Path $codeBuddyHome ".mcp.json"
    $cfg = [ordered]@{ mcpServers = [ordered]@{} }
    if (Test-Path $codeBuddyMcp) {
        try { $cfg = Get-Content $codeBuddyMcp -Raw | ConvertFrom-Json -AsHashtable } catch { throw "CodeBuddy MCP file exists but cannot be merged without the CodeBuddy CLI" }
        if (-not $cfg.ContainsKey("mcpServers")) { $cfg["mcpServers"] = [ordered]@{} }
    }
    $cfg["mcpServers"]["opencontracts"] = [ordered]@{ type = "http"; url = $mcpUrl; description = "OpenContracts MCP over trusted internal HTTPS" }
    $cfg | ConvertTo-Json -Depth 8 | Set-Content $codeBuddyMcp -Encoding UTF8
}

# WorkBuddy: official user-level MCP path is ~/.workbuddy/mcp.json.
$workBuddyHome = Join-Path $HOME ".workbuddy"
New-Item -ItemType Directory -Force -Path $workBuddyHome | Out-Null
$workBuddyMcp = Join-Path $workBuddyHome "mcp.json"
$workCfg = [ordered]@{ mcpServers = [ordered]@{} }
if (Test-Path $workBuddyMcp) {
    $workCfg = Get-Content $workBuddyMcp -Raw | ConvertFrom-Json -AsHashtable
    if (-not $workCfg.ContainsKey("mcpServers")) { $workCfg["mcpServers"] = [ordered]@{} }
}
$workCfg["mcpServers"]["opencontracts"] = [ordered]@{ type = "http"; url = $mcpUrl }
$workCfg | ConvertTo-Json -Depth 8 | Set-Content $workBuddyMcp -Encoding UTF8

# The secret is now persisted in the Windows user environment; remove the plaintext extracted copy.
Remove-Item $SecretFile -Force

Write-Host "ContractBot installation completed."
Write-Host "Restart the current Harness before using the globally installed configuration."
