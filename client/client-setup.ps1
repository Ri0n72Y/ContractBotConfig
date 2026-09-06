[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$BundleDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$McpFile = Join-Path $BundleDir ".mcp.json"
$SkillsDir = Join-Path $BundleDir "skills"

if (-not (Test-Path $McpFile)) { throw "Prepared MCP configuration not found: $McpFile" }
if (-not (Test-Path $SkillsDir)) { throw "Skills directory not found: $SkillsDir" }

$mcpConfig = Get-Content $McpFile -Raw | ConvertFrom-Json
$mcpUrl = [string]$mcpConfig.mcpServers.opencontracts.url
if (-not $mcpUrl) { throw "opencontracts MCP URL is missing" }

function Set-McpServerInFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Url
    )

    $parent = Split-Path -Parent $Path
    New-Item -ItemType Directory -Force -Path $parent | Out-Null

    $cfg = $null
    if (Test-Path $Path) {
        $cfg = Get-Content $Path -Raw | ConvertFrom-Json
    }
    if (-not $cfg) {
        $cfg = New-Object PSObject
        $cfg | Add-Member -NotePropertyName mcpServers -NotePropertyValue (New-Object PSObject)
    }
    elseif (-not $cfg.PSObject.Properties["mcpServers"]) {
        $cfg | Add-Member -NotePropertyName mcpServers -NotePropertyValue (New-Object PSObject)
    }

    $server = [pscustomobject]@{
        type = "http"
        url = $Url
        description = "OpenContracts MCP on the trusted internal network"
    }

    if ($cfg.mcpServers.PSObject.Properties["opencontracts"]) {
        $cfg.mcpServers.opencontracts = $server
    }
    else {
        $cfg.mcpServers | Add-Member -NotePropertyName opencontracts -NotePropertyValue $server
    }

    $cfg | ConvertTo-Json -Depth 8 | Set-Content $Path -Encoding UTF8
}

# CodeBuddy user-wide Skills and MCP.
$codeBuddyHome = if ($env:CODEBUDDY_CONFIG_DIR) { $env:CODEBUDDY_CONFIG_DIR } else { Join-Path $HOME ".codebuddy" }
$codeBuddySkills = Join-Path $codeBuddyHome "skills"
New-Item -ItemType Directory -Force -Path $codeBuddySkills | Out-Null
Copy-Item (Join-Path $SkillsDir "*") $codeBuddySkills -Recurse -Force

$codeBuddy = Get-Command codebuddy -ErrorAction SilentlyContinue
if ($codeBuddy) {
    $serverJson = [ordered]@{
        type = "http"
        url = $mcpUrl
        description = "OpenContracts MCP on the trusted internal network"
    } | ConvertTo-Json -Compress
    & $codeBuddy.Source mcp add-json --scope user opencontracts $serverJson | Out-Null
}
else {
    Set-McpServerInFile -Path (Join-Path $codeBuddyHome ".mcp.json") -Url $mcpUrl
}

# WorkBuddy user-wide MCP. Skill installation should use WorkBuddy's native
# import/install mechanism when the assistant has access to it.
Set-McpServerInFile -Path (Join-Path $HOME ".workbuddy\mcp.json") -Url $mcpUrl

Write-Host "ContractBot client setup completed."
Write-Host "Restart the current Harness if it does not reload global MCP/Skills automatically."
