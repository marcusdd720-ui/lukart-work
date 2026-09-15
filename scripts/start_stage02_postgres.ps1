param([int]$Port = 55432)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$localRoot = Join-Path $taskRoot '.local-stage02'
$pgBin = Join-Path $localRoot 'runtime/pgsql/bin'
$dataRoot = Join-Path $localRoot 'data'
if (-not (Test-Path -LiteralPath (Join-Path $pgBin 'initdb.exe'))) { throw 'Extract the official PostgreSQL archive into .local-stage02/runtime first.' }
$configPath = Join-Path $localRoot 'connection.json'
if (-not (Test-Path -LiteralPath $configPath)) {
    $adminSecret = [Convert]::ToHexString([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
    $runtimeSecret = [Convert]::ToHexString([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
    @{
        admin_dsn = "host=127.0.0.1 port=$Port dbname=postgres user=lw_test_admin password=$adminSecret"
        runtime_dsn = "host=127.0.0.1 port=$Port dbname=lukart_stage02_test user=lw_core_runtime password=$runtimeSecret"
        runtime_password = $runtimeSecret
    } | ConvertTo-Json | Set-Content -LiteralPath $configPath -Encoding utf8
    $passwordFile = Join-Path $localRoot 'init-password.txt'
    [System.IO.File]::WriteAllText($passwordFile, $adminSecret)
    try {
        $init = Start-Process -FilePath (Join-Path $pgBin 'initdb.exe') -ArgumentList @('-D', "`"$dataRoot`"", '-U', 'lw_test_admin', '-A', 'scram-sha-256', '--encoding=UTF8', '--locale=C', "--pwfile=`"$passwordFile`"") -WindowStyle Hidden -Wait -PassThru -RedirectStandardOutput (Join-Path $localRoot 'init.log') -RedirectStandardError (Join-Path $localRoot 'init-error.log')
        if ($init.ExitCode -ne 0) { throw 'initdb failed; see local init logs.' }
    } finally { Remove-Item -LiteralPath $passwordFile }
}
if (-not (Test-Path -LiteralPath (Join-Path $dataRoot 'PG_VERSION'))) { throw 'Incomplete local cluster; inspect the init log. No automatic reset is performed.' }
$status = Start-Process -FilePath (Join-Path $pgBin 'pg_ctl.exe') -ArgumentList @('-D', "`"$dataRoot`"", 'status') -WindowStyle Hidden -Wait -PassThru -RedirectStandardOutput (Join-Path $localRoot 'status.log') -RedirectStandardError (Join-Path $localRoot 'status-error.log')
if ($status.ExitCode -ne 0) {
    $start = Start-Process -FilePath (Join-Path $pgBin 'pg_ctl.exe') -ArgumentList @('-D', "`"$dataRoot`"", '-l', "`"$(Join-Path $localRoot 'server.log')`"", '-o', "`"-h 127.0.0.1 -p $Port`"", '-w', 'start') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $localRoot 'start.log') -RedirectStandardError (Join-Path $localRoot 'start-error.log')
    # Start-Process -Wait waits for descendants, including the long-running server.
    $start.WaitForExit()
    if ($start.ExitCode -ne 0) { throw 'PostgreSQL failed to start; see local server log.' }
}
Write-Output "Local PostgreSQL test cluster ready on loopback port $Port. No Windows service was installed."
