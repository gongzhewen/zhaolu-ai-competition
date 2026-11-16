param(
    [switch]$Live,
    [switch]$Vector
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:PYTHONPATH = @(
    (Join-Path $root "packages\agent_core"),
    (Join-Path $root "packages\data_contracts"),
    (Join-Path $root "apps\api")
) -join [IO.Path]::PathSeparator

$python = $env:PYTHON_EXE
if (-not $python) {
    $python = Join-Path $root ".venv\Scripts\python.exe"
}
if (-not (Test-Path -LiteralPath $python)) {
    throw "Python 解释器不存在：$python。请设置 PYTHON_EXE。"
}
if ($Live) {
    if (-not $env:DATABASE_URL) {
        throw "运行 MySQL 全量回归前必须设置 DATABASE_URL。"
    }
    $env:LIVE_MYSQL_TESTS = "1"
} else {
    $env:LIVE_MYSQL_TESTS = "0"
}
if ($Vector) {
    $env:LIVE_VECTOR_RAG_TESTS = "1"
} else {
    $env:LIVE_VECTOR_RAG_TESTS = "0"
    if (-not $env:RAG_VECTOR_ENABLED) {
        $env:RAG_VECTOR_ENABLED = "false"
    }
}

& $python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "pytest failed" }

if ($Live) {
    & $python scripts\mysql\ensure_compat_indexes.py
    if ($LASTEXITCODE -ne 0) { throw "compat index check failed" }
    & $python scripts\mysql\verify_data_consistency.py
    if ($LASTEXITCODE -ne 0) { throw "data consistency check failed" }
    & $python scripts\mysql\verify_rollup_self_heal.py
    if ($LASTEXITCODE -ne 0) { throw "rollup self-heal check failed" }
    & $python scripts\mysql\verify_regression.py
    if ($LASTEXITCODE -ne 0) { throw "HTTP and intent regression failed" }
}

Write-Host "full_regression=ok live=$Live vector=$Vector"
