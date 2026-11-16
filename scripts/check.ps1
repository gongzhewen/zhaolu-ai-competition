$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
$alembic = Join-Path $root ".venv\Scripts\alembic.exe"

if (-not (Test-Path $python)) {
    throw "未找到 .venv，请先创建 Python 3.10 虚拟环境并安装 pyproject.toml 依赖。"
}

& $python -m pytest -q

$schemaFile = Join-Path $env:TEMP "zhaolu-ai-v2-schema.sql"
& $alembic -c apps\api\alembic.ini upgrade head --sql | Set-Content -LiteralPath $schemaFile -Encoding UTF8
$lineCount = (Get-Content -LiteralPath $schemaFile).Count
Write-Host "数据库离线迁移 SQL 已生成：$schemaFile"
Write-Host "SQL 行数：$lineCount"
