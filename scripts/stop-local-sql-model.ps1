param(
    [string]$PidFile = 'D:\models\llama.cpp\run-3b\server.pid'
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $PidFile)) {
    [pscustomobject]@{status='not_running';reason='PID 文件不存在'} | ConvertTo-Json
    exit 0
}
$serverPid = [int](Get-Content -LiteralPath $PidFile -Raw)
$process = Get-Process -Id $serverPid -ErrorAction SilentlyContinue
if ($process) { Stop-Process -Id $serverPid -Force }
[pscustomobject]@{status='stopped';pid=$serverPid} | ConvertTo-Json
