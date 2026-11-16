[CmdletBinding()]
param([switch]$NoStart)

$ErrorActionPreference = 'Stop'
$local = 'C:\Users\Administrator\AppData\Local'
$runLink = Join-Path $local 'Docker\run'
$secretsLink = Join-Path $local 'docker-secrets-engine'
$targetRoot = 'F:\DockerDesktop\runtime'
$runTarget = Join-Path $targetRoot 'run'
$secretsTarget = Join-Path $targetRoot 'docker-secrets-engine'

function Test-JunctionTarget([string]$Path, [string]$Target) {
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    $item = Get-Item -LiteralPath $Path -Force
    if (-not ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { return $false }
    return ($item.Target -contains $Target -or $item.Target -eq $Target)
}

function Stop-DockerDesktop {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -in @('Docker Desktop.exe','com.docker.backend.exe','com.docker.proxy.exe','com.docker.buildkit.exe','com.docker.dev-envs.exe') } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    $service = Get-Service -Name 'com.docker.service' -ErrorAction SilentlyContinue
    if ($service -and $service.Status -ne 'Stopped') {
        Stop-Service -Name 'com.docker.service' -Force
    }
    Start-Sleep -Seconds 2
}

$runOk = Test-JunctionTarget $runLink $runTarget
$secretsOk = Test-JunctionTarget $secretsLink $secretsTarget
if (-not ($runOk -and $secretsOk)) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    Stop-DockerDesktop
    if (Test-Path -LiteralPath $runLink) {
        $backup = "$runLink.bad-$stamp"
        Move-Item -LiteralPath $runLink -Destination $backup
        Write-Host "Preserved runtime directory: $backup"
    }
    if (Test-Path -LiteralPath $secretsLink) {
        $backup = "$secretsLink.bad-$stamp"
        Move-Item -LiteralPath $secretsLink -Destination $backup
        Write-Host "Preserved secrets directory: $backup"
    }
    New-Item -ItemType Directory -Path $runTarget -Force | Out-Null
    New-Item -ItemType Directory -Path $secretsTarget -Force | Out-Null
    New-Item -ItemType Junction -Path $runLink -Target $runTarget | Out-Null
    New-Item -ItemType Junction -Path $secretsLink -Target $secretsTarget | Out-Null
    Write-Host "Redirected runtime directory: $runLink -> $runTarget"
    Write-Host "Redirected secrets directory: $secretsLink -> $secretsTarget"
}

$service = Get-Service -Name 'com.docker.service' -ErrorAction SilentlyContinue
if ($service -and $service.Status -eq 'Stopped') { Start-Service -Name 'com.docker.service' }

& docker info *> $null
if ($LASTEXITCODE -ne 0 -and -not $NoStart) {
    Start-Process -FilePath 'F:\DockerDesktop\Program\Docker Desktop.exe' -WindowStyle Hidden
    $ready = $false
    for ($i = 1; $i -le 60; $i++) {
        Start-Sleep -Seconds 2
        & docker info *> $null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    }
    if (-not $ready) { throw 'Docker Engine did not become ready within 120 seconds.' }
} elseif ($LASTEXITCODE -ne 0 -and $NoStart) {
    throw 'Docker Engine is unavailable. Retry without -NoStart.'
}

Write-Host 'Docker runtime repair passed.'
& docker desktop status
& docker info --format 'ServerVersion={{.ServerVersion}} OSType={{.OSType}} Containers={{.Containers}} Images={{.Images}}'