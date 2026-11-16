param(
    [Parameter(Mandatory=$true)][string]$SourceRoot,
    [Parameter(Mandatory=$true)][string]$TargetRoot,
    [Parameter(Mandatory=$true)][string]$ManifestPath,
    [Parameter(Mandatory=$true)][string]$BackupRoot
)

$ErrorActionPreference = 'Stop'
$expectedTarget = 'C:\Users\Administrator\Desktop\招录智策_国赛开发'
$sourceFull = [System.IO.Path]::GetFullPath($SourceRoot)
$targetFull = [System.IO.Path]::GetFullPath($TargetRoot)
$manifestFull = [System.IO.Path]::GetFullPath($ManifestPath)
$backupFull = [System.IO.Path]::GetFullPath($BackupRoot)

if (-not $targetFull.Equals($expectedTarget, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "拒绝执行：目标目录不是预期项目目录：$targetFull"
}
if (-not (Test-Path -LiteralPath $sourceFull -PathType Container)) { throw "源目录不存在：$sourceFull" }
if (-not (Test-Path -LiteralPath $targetFull -PathType Container)) { throw "目标目录不存在：$targetFull" }
if (-not (Test-Path -LiteralPath $manifestFull -PathType Leaf)) { throw "清单不存在：$manifestFull" }
if (Test-Path -LiteralPath $backupFull) { throw "备份目录已存在，拒绝覆盖：$backupFull" }

function Assert-PathUnderRoot {
    param([string]$Path, [string]$Root, [string]$Label)
    $full = [System.IO.Path]::GetFullPath($Path)
    $rootFull = [System.IO.Path]::GetFullPath($Root).TrimEnd('\')
    if (-not $full.StartsWith($rootFull + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "$Label 路径越界：$full"
    }
}

$relativePaths = Get-Content -LiteralPath $manifestFull -Encoding UTF8 | Where-Object { $_.Trim() } | ForEach-Object { $_.Trim() }
if (-not $relativePaths) { throw "部署清单为空" }
New-Item -ItemType Directory -Path $backupFull -Force | Out-Null

$backedUp = 0
$copied = 0
foreach ($relativePath in $relativePaths) {
    $normalized = $relativePath.Replace('/', [System.IO.Path]::DirectorySeparatorChar)
    $sourceFile = Join-Path $sourceFull $normalized
    $targetFile = Join-Path $targetFull $normalized
    $backupFile = Join-Path $backupFull $normalized
    Assert-PathUnderRoot -Path $sourceFile -Root $sourceFull -Label '源文件'
    Assert-PathUnderRoot -Path $targetFile -Root $targetFull -Label '目标文件'
    Assert-PathUnderRoot -Path $backupFile -Root $backupFull -Label '备份文件'
    if (-not (Test-Path -LiteralPath $sourceFile -PathType Leaf)) { throw "清单中的源文件不存在：$sourceFile" }

    if (Test-Path -LiteralPath $targetFile -PathType Leaf) {
        $backupDirectory = Split-Path -Parent $backupFile
        New-Item -ItemType Directory -Path $backupDirectory -Force | Out-Null
        Copy-Item -LiteralPath $targetFile -Destination $backupFile -Force
        $backedUp++
    }

    $targetDirectory = Split-Path -Parent $targetFile
    New-Item -ItemType Directory -Path $targetDirectory -Force | Out-Null
    Copy-Item -LiteralPath $sourceFile -Destination $targetFile -Force
    $copied++
}

[pscustomobject]@{
    SourceRoot = $sourceFull
    TargetRoot = $targetFull
    BackupRoot = $backupFull
    ManifestEntries = $relativePaths.Count
    ExistingFilesBackedUp = $backedUp
    FilesCopied = $copied
} | ConvertTo-Json -Depth 3
