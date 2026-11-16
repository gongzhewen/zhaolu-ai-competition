param(
    [string]$ModelPath = 'D:\models\qwen2.5-coder-3b\qwen2.5-coder-3b-instruct-q4_k_m.gguf',
    [string]$Alias = 'qwen2.5-coder-3b',
    [string]$ServerExe = 'D:\models\llama.cpp\runtime\llama-server.exe',
    [string]$RunDir = 'D:\models\llama.cpp\run-3b',
    [int]$Port = 11434,
    [int]$Threads = 2,
    [int]$ContextSize = 4096
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $ModelPath)) { throw "模型文件不存在：$ModelPath" }
if (-not (Test-Path -LiteralPath $ServerExe)) { throw "llama-server 不存在：$ServerExe" }
New-Item -ItemType Directory -Path $RunDir -Force | Out-Null
try {
    $existing = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/v1/models" -TimeoutSec 2
    [pscustomobject]@{status='already_running';models=($existing.data.id -join ',')} | ConvertTo-Json
    exit 0
} catch {}
$args = @(
    '--model', $ModelPath, '--alias', $Alias,
    '--host', '127.0.0.1', '--port', "$Port",
    '--threads', "$Threads", '--threads-batch', "$Threads",
    '--ctx-size', "$ContextSize", '--parallel', '1', '--no-webui', '--jinja'
)
$process = Start-Process -FilePath $ServerExe -ArgumentList $args `
    -WorkingDirectory (Split-Path -Parent $ServerExe) -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $RunDir 'server.stdout.log') `
    -RedirectStandardError (Join-Path $RunDir 'server.stderr.log') -PassThru
$process.Id | Set-Content -LiteralPath (Join-Path $RunDir 'server.pid') -Encoding ASCII
$deadline = (Get-Date).AddSeconds(180)
$ready = $false
while ((Get-Date) -lt $deadline) {
    if ($process.HasExited) { break }
    try {
        $models = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/v1/models" -TimeoutSec 3
        $ready = $true
        break
    } catch { Start-Sleep -Seconds 2 }
}
[pscustomobject]@{
    status = if ($ready) { 'ready' } else { 'failed' }
    pid = $process.Id
    model = $ModelPath
    runtime = $ServerExe
    run_dir = $RunDir
    base_url = "http://127.0.0.1:$Port/v1"
    models = if ($models) { $models.data.id -join ',' } else { '' }
} | ConvertTo-Json
