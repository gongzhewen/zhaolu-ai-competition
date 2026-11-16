param(
    [string]$PythonExe = "D:\Backup\Documents\ChatGPT\Desktop\zhaolu-ai-venv\Scripts\python.exe",
    [string]$DatabaseUrl = "mysql+asyncmy://root:123456@127.0.0.1:3306/zhaolu_v2",
    [string]$RedisUrl = "redis://127.0.0.1:6379/14"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$env:PYTHONUTF8 = "1"
$env:PYTHONPATH = @(
    (Join-Path $root "packages\agent_core"),
    (Join-Path $root "packages\data_contracts"),
    (Join-Path $root "apps\api")
) -join [IO.Path]::PathSeparator
$env:DATABASE_URL = $DatabaseUrl
$env:REDIS_ENABLED = "true"
$env:REDIS_URL = $RedisUrl
$env:REDIS_KEY_PREFIX = "zhaolu_http_verify"
$env:RAG_VECTOR_ENABLED = "false"
$env:MINIMIND_ENABLED = "false"
$env:ENVIRONMENT = "verification"
$env:DATABASE_NULL_POOL = "true"

$stamp = Get-Date -Format "yyyyMMddHHmmss"
$logs = @{
    1 = Join-Path $env:TEMP "zhaolu-verify-8011-$stamp.log"
    2 = Join-Path $env:TEMP "zhaolu-verify-8012-$stamp.log"
}
$errors = @{
    1 = Join-Path $env:TEMP "zhaolu-verify-8011-$stamp.err.log"
    2 = Join-Path $env:TEMP "zhaolu-verify-8012-$stamp.err.log"
}

function Start-TestInstance {
    param([int]$Port, [string]$InstanceId, [string]$LogPath, [string]$ErrorPath)
    $env:INSTANCE_ID = $InstanceId
    return Start-Process `
        -FilePath $PythonExe `
        -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$Port") `
        -WorkingDirectory $root `
        -WindowStyle Hidden `
        -PassThru `
        -RedirectStandardOutput $LogPath `
        -RedirectStandardError $ErrorPath
}

function Wait-Health {
    param([int]$Port)
    $deadline = (Get-Date).AddSeconds(90)
    while ((Get-Date) -lt $deadline) {
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/v1/health" -TimeoutSec 3
            if ($health.status -eq "ok") {
                return $health
            }
        } catch {
            Start-Sleep -Milliseconds 750
        }
    }
    throw "Instance 127.0.0.1:$Port did not become healthy within 90 seconds"
}

$process1 = $null
$process2 = $null
try {
    $process1 = Start-TestInstance -Port 8011 -InstanceId "verify-instance-1" -LogPath $logs[1] -ErrorPath $errors[1]
    $process2 = Start-TestInstance -Port 8012 -InstanceId "verify-instance-2" -LogPath $logs[2] -ErrorPath $errors[2]
    $health1 = Wait-Health -Port 8011
    $health2 = Wait-Health -Port 8012
    if (-not $health1.redis.available -or -not $health2.redis.available) {
        throw "Both instances did not connect to Redis"
    }
    & $PythonExe -m scripts.verify_multinstance_http `
        --base-url-1 "http://127.0.0.1:8011" `
        --base-url-2 "http://127.0.0.1:8012" `
        --redis-url $RedisUrl
    if ($LASTEXITCODE -ne 0) {
        throw "Two-instance HTTP verification failed"
    }
} catch {
    foreach ($path in @($logs[1], $logs[2], $errors[1], $errors[2])) {
        if (Test-Path -LiteralPath $path) {
            Write-Host "--- $path ---"
            Get-Content -LiteralPath $path -Tail 80
        }
    }
    throw
} finally {
    foreach ($process in @($process1, $process2)) {
        if ($null -ne $process) {
            $running = Get-Process -Id $process.Id -ErrorAction SilentlyContinue
            if ($running) {
                Stop-Process -Id $process.Id -Force
                $process.WaitForExit(10000)
            }
        }
    }
    foreach ($path in @($logs[1], $logs[2], $errors[1], $errors[2])) {
        if (Test-Path -LiteralPath $path) {
            Remove-Item -LiteralPath $path -Force
        }
    }
}
