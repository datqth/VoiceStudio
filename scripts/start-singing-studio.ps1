param([switch]$Open)
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$studioRoot = Split-Path -Parent $PSScriptRoot
$studioPython = Join-Path $studioRoot ".venv\Scripts\python.exe"
$studioLogs = Join-Path $studioRoot "local-logs"
New-Item -ItemType Directory -Path $studioLogs -Force | Out-Null
$env:TORCH_COMPILE_DISABLE = "1"
$env:TORCHDYNAMO_DISABLE = "1"
$env:TORCHINDUCTOR_DISABLE = "1"
$env:OMNIVOICE_GPU_WORKERS = "1"
$env:OMNIVOICE_PRELOAD_CAPTURE_ASR = "0"
$env:OMNIVOICE_PRELOAD_WATERMARK = "0"
$env:OMNIVOICE_DATA_DIR = Join-Path $env:APPDATA "VoiceStudio-Singing"
$env:OMNIVOICE_SEED_VC_DIR = Join-Path (Split-Path -Parent $studioRoot) "Seed-VC"
$env:OMNIVOICE_ACE_STEP_DIR = Join-Path (Split-Path -Parent $studioRoot) "ACE-Step-1.5"
$env:PYTHONUTF8 = "1"
function Test-StudioEndpoint([string]$Url) {
    try { Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2 | Out-Null; return $true } catch { return $false }
}
if (-not (Test-StudioEndpoint "http://127.0.0.1:3900/system/info")) {
    Start-Process -FilePath $studioPython -ArgumentList @("-m", "uvicorn", "main:app", "--app-dir", "backend", "--host", "127.0.0.1", "--port", "3900") -WorkingDirectory $studioRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $studioLogs "backend.stdout.log") -RedirectStandardError (Join-Path $studioLogs "backend.stderr.log") | Out-Null
}
if (-not (Test-StudioEndpoint "http://localhost:3901")) {
    $studioBun = (Get-Command bun.exe).Source
    Start-Process -FilePath $studioBun -ArgumentList @("run", "--cwd", "electron", "dev:web") -WorkingDirectory $studioRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $studioLogs "frontend.stdout.log") -RedirectStandardError (Join-Path $studioLogs "frontend.stderr.log") | Out-Null
}
Write-Host "VoiceStudio cùng công cụ hát đang khởi động tại http://localhost:3901/#/tools"
if ($Open) { Start-Process "http://localhost:3901/#/tools" }
