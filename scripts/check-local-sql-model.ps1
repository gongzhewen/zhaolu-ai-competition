param([string]$BaseUrl = 'http://127.0.0.1:11434/v1')
$ErrorActionPreference = 'Stop'
$models = Invoke-RestMethod -Uri "$($BaseUrl.TrimEnd('/'))/models" -TimeoutSec 10
[pscustomobject]@{
    status = 'ok'
    base_url = $BaseUrl
    models = ($models.data.id -join ',')
} | ConvertTo-Json
