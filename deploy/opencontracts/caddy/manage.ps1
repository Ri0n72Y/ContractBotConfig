[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("up", "export-ca", "logs", "down")]
    [string]$Command
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
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
    & docker compose --env-file $EnvFile -f $ComposeFile @Args
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose failed"
    }
}

switch ($Command) {
    "up" {
        Invoke-CaddyCompose up -d --build
    }
    "export-ca" {
        $output = $env:CADDY_CA_OUTPUT
        if (-not [System.IO.Path]::IsPathRooted($output)) {
            $output = Join-Path $DeployDir $output
        }
        $outputDir = Split-Path -Parent $output
        New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
        Invoke-CaddyCompose cp "caddy:/data/caddy/pki/authorities/local/root.crt" $output
        Write-Output $output
    }
    "logs" {
        Invoke-CaddyCompose logs --tail=200 -f caddy doc-converter
    }
    "down" {
        Invoke-CaddyCompose down
    }
}
