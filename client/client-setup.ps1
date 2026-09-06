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

# Install the deterministic Python helper dependency when Python is available.
$requirements = Join-Path $runtimeScripts "requirements.txt"
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 -m pip install --user -r $requirements | Out-Null
}
elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python -m pip install --user -r $requirements | Out-Null
}

function Set-McpServerInJsonFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][object]$Server
    )

    if (Test-Path $Path) {
        try {
            $cfg = Get-Content $Path -Raw | ConvertFrom-Json
        }
        catch {
            throw "Existing MCP configuration cannot be safely merged: $Path"
        }
    }
    else {
        $cfg = [pscustomobject]@{}
    }

    if (-not $cfg.PSObject.Properties["mcpServers"]) {
        Add-Member -InputObject $cfg -MemberType NoteProperty -Name "mcpServers" -Value ([pscustomobject]@{})
    }
    elseif ($null -eq $cfg.mcpServers) {
        $cfg.mcpServers = [pscustomobject]@{}
    }

    $property = $cfg.mcpServers.PSObject.Properties["opencontracts"]
    if ($property) {
        $property.Value = $Server
    }
    else {
        Add-Member -InputObject $cfg.mcpServers -MemberType NoteProperty -Name "opencontracts" -Value $Server
    }

    $parent = Split-Path -Parent $Path
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    $cfg | ConvertTo-Json -Depth 10 | Set-Content $Path -Encoding UTF8
}

# CodeBuddy: official user scope is ~/.codebuddy (or CODEBUDDY_CONFIG_DIR).
$codeBuddyHome = if ($env:CODEBUDDY_CONFIG_DIR) { $env:CODEBUDDY_CONFIG_DIR } else { Join-Path $HOME ".codebuddy" }
New-Item -ItemType Directory -Force -Path $codeBuddyHome | Out-Null
$codeBuddySkills = Join-Path $codeBuddyHome "skills"
New-Item -ItemType Directory -Force -Path $codeBuddySkills | Out-Null
Copy-Item (Join-Path $SkillsDir "*") $codeBuddySkills -Recurse -Force

$server = [pscustomobject]@{
    type = "http"
    url = $mcpUrl
    description = "OpenContracts MCP over trusted internal HTTPS"
}

$codeBuddy = Get-Command codebuddy -ErrorAction SilentlyContinue
if ($codeBuddy) {
    $mcpJson = $server | ConvertTo-Json -Compress
    & $codeBuddy.Source mcp remove opencontracts --scope user 2>$null | Out-Null
    & $codeBuddy.Source mcp add-json --scope user opencontracts $mcpJson | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "CodeBuddy global MCP registration failed"
    }
}
else {
    Set-McpServerInJsonFile -Path (Join-Path $codeBuddyHome ".mcp.json") -Server $server
}

# WorkBuddy: official user-level MCP path is ~/.workbuddy/mcp.json.
$workBuddyServer = [pscustomobject]@{ type = "http"; url = $mcpUrl }
Set-McpServerInJsonFile -Path (Join-Path (Join-Path $HOME ".workbuddy") "mcp.json") -Server $workBuddyServer

# The secret is now persisted in the Windows user environment; remove the plaintext extracted copy.
Remove-Item $SecretFile -Force

Write-Host "ContractBot installation completed."
Write-Host "Restart the current Harness before using the globally installed configuration."
