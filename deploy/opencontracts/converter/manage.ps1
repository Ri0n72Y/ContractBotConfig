[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("up", "logs", "down")]
    [string]$Command
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ComposeFile = Join-Path $ScriptDir "compose.yml"

switch ($Command) {
    "up" {
        & docker compose -f $ComposeFile up -d --build
    }
    "logs" {
        & docker compose -f $ComposeFile logs --tail=200 -f doc-converter
    }
    "down" {
        & docker compose -f $ComposeFile down
    }
}

if ($LASTEXITCODE -ne 0) {
    throw "docker compose failed"
}
