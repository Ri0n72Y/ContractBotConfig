[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$InternalHost,

    [Parameter(Mandatory = $true)]
    [string]$CaddyRootCertificate,

    [Parameter(Mandatory = $true)]
    [string]$HistoryCorpus,

    [Parameter(Mandatory = $true)]
    [string]$TemplateCorpus,

    [Parameter(Mandatory = $true)]
    [string]$KnowledgeCorpus,

    [string]$ServerIp = "",
    [string]$UploadWorkerKey = "",

    [ValidateSet("User", "Machine")]
    [string]$EnvironmentScope = "User"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if (-not (Test-Path $CaddyRootCertificate)) {
    throw "Caddy root certificate not found: $CaddyRootCertificate"
}

if ($ServerIp) {
    $hostsPath = Join-Path $env:SystemRoot "System32/drivers/etc/hosts"
    $hostsText = [System.IO.File]::ReadAllText($hostsPath)
    $pattern = "(?m)^\s*\S+\s+" + [regex]::Escape($InternalHost) + "(?:\s|$).*"
    $line = "$ServerIp`t$InternalHost"
    if ([regex]::IsMatch($hostsText, $pattern)) {
        $hostsText = [regex]::Replace($hostsText, $pattern, $line)
    }
    else {
        if (-not $hostsText.EndsWith("`n")) { $hostsText += "`r`n" }
        $hostsText += $line + "`r`n"
    }
    [System.IO.File]::WriteAllText(
        $hostsPath,
        $hostsText,
        [System.Text.UTF8Encoding]::new($false)
    )
    Write-Host "Updated hosts entry: $InternalHost -> $ServerIp"
}

$caDir = if ($EnvironmentScope -eq "Machine") {
    Join-Path $env:ProgramData "ContractBot"
}
else {
    Join-Path $env:LOCALAPPDATA "ContractBot"
}
New-Item -ItemType Directory -Force -Path $caDir | Out-Null
$caTarget = Join-Path $caDir "opencontracts-caddy-root.crt"
Copy-Item $CaddyRootCertificate $caTarget -Force

$certStore = if ($EnvironmentScope -eq "Machine") {
    "Cert:\LocalMachine\Root"
}
else {
    "Cert:\CurrentUser\Root"
}
Import-Certificate -FilePath $caTarget -CertStoreLocation $certStore | Out-Null

$baseUrl = "https://$InternalHost"
$values = [ordered]@{
    OPENCONTRACTS_BASE_URL = $baseUrl
    OPENCONTRACTS_MCP_URL = "$baseUrl/mcp/"
    OPENCONTRACTS_HISTORY_CORPUS = $HistoryCorpus
    OPENCONTRACTS_TEMPLATE_CORPUS = $TemplateCorpus
    OPENCONTRACTS_KNOWLEDGE_CORPUS = $KnowledgeCorpus
    OPENCONTRACTS_CA_BUNDLE = $caTarget
    NODE_EXTRA_CA_CERTS = $caTarget
    OPENCONTRACTS_ALLOW_INSECURE_HTTP = "0"
    OPENCONTRACTS_UPLOAD_TIMEOUT_SECONDS = "60"
}
if ($UploadWorkerKey) {
    $values.OPENCONTRACTS_UPLOAD_WORKER_KEY = $UploadWorkerKey
}

foreach ($entry in $values.GetEnumerator()) {
    [Environment]::SetEnvironmentVariable($entry.Key, [string]$entry.Value, $EnvironmentScope)
}

Write-Host ""
Write-Host "Agent/Harness OpenContracts runtime configured."
Write-Host "OPENCONTRACTS_BASE_URL=$baseUrl"
Write-Host "OPENCONTRACTS_MCP_URL=$baseUrl/mcp/"
Write-Host "OPENCONTRACTS_HISTORY_CORPUS=$HistoryCorpus"
Write-Host "OPENCONTRACTS_TEMPLATE_CORPUS=$TemplateCorpus"
Write-Host "OPENCONTRACTS_KNOWLEDGE_CORPUS=$KnowledgeCorpus"
Write-Host "OPENCONTRACTS_CA_BUNDLE=$caTarget"
Write-Host "NODE_EXTRA_CA_CERTS=$caTarget"
Write-Host "OPENCONTRACTS_UPLOAD_WORKER_KEY=" + $(if ($UploadWorkerKey) { "configured" } else { "NOT SET" })
Write-Host ""
Write-Host "Restart WorkBuddy/CodeBuddy after changing persistent environment variables."
