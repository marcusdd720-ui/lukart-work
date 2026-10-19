param(
    [Parameter(Mandatory = $true)][string]$Config,
    [int]$Port = 8765,
    [string]$Python = (Join-Path (Split-Path -Parent $PSScriptRoot) '.venv/Scripts/python.exe')
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path -LiteralPath $Config -PathType Leaf)) { throw 'Trusted CASE configuration file required.' }
$configFile = (Resolve-Path -LiteralPath $Config).Path
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw 'Accessible Python 3.11+ executable required; use -Python.' }
Push-Location -LiteralPath $taskRoot
try {
    & $Python -B -X utf8 -m lukart_work.operator_host --config $configFile --port $Port
    if ($LASTEXITCODE -ne 0) { throw 'CASE operator failed; no successful launch verified.' }
} finally {
    Pop-Location
}
