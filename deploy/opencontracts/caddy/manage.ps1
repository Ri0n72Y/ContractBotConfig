[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("setup", "up", "export-ca", "logs", "down")]
    [string]$Command,

    [string]$Output = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DeployDir = Split-Path -Parent $ScriptDir
$EnvFile = Join-Path $DeployDir ".env"
$ComposeFile = Join-Path $ScriptDir "compose.yml"

Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#")) { return }
    $pair = $line -split "=", 2
    if ($pair.Count -eq 2) {
        [Environment]::SetEnvironmentVariable($pair[0].Trim(), $pair[1].Trim(), "Process")
    }
}

function Invoke-CaddyCompose {
    param([Parameter(Mandatory = $true)][string[]]$ComposeArgs)

    & docker compose --env-file $EnvFile -f $ComposeFile @ComposeArgs
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose failed"
    }
}

function Export-CaddyRootCa {
    param([Parameter(Mandatory = $true)][string]$Target)

    $targetPath = if ([System.IO.Path]::IsPathRooted($Target)) {
        $Target
    }
    else {
        Join-Path $DeployDir $Target
    }
    $targetPath = [System.IO.Path]::GetFullPath($targetPath)
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $targetPath) | Out-Null

    Invoke-CaddyCompose -ComposeArgs @(
        "cp",
        "caddy:/data/caddy/pki/authorities/local/root.crt",
        $targetPath
    )
    Write-Host "Caddy root CA exported: $targetPath"
}

switch ($Command) {
    "setup" {
        Invoke-CaddyCompose -ComposeArgs @("up", "-d")
    }
    "up" {
        Invoke-CaddyCompose -ComposeArgs @("up", "-d")
    }
    "export-ca" {
        if (-not $Output) { throw "-Output is required for export-ca" }
        Export-CaddyRootCa -Target $Output
    }
    "logs" {
        Invoke-CaddyCompose -ComposeArgs @("logs", "--tail=200", "-f", "caddy")
    }
    "down" {
        Invoke-CaddyCompose -ComposeArgs @("down")
    }
}
