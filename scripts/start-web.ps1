param(
    [switch]$Preview
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$web = Join-Path $root "apps\web"
Set-Location $web

if ($Preview) {
    $env:VITE_API_BASE_URL = $env:VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1"
    npm run build
    npm run preview -- --host 0.0.0.0 --port 3000
} else {
    npm run dev -- --host 0.0.0.0
}
