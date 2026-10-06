param([string]$EngineRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)))
$ErrorActionPreference = "Stop"
$studioRoot = Split-Path -Parent $PSScriptRoot
$seedRoot = Join-Path $EngineRoot "Seed-VC"
$aceRoot = Join-Path $EngineRoot "ACE-Step-1.5"
$studioPython = Join-Path $studioRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $seedRoot)) { git clone --depth 1 https://github.com/Plachtaa/seed-vc.git $seedRoot; if ($LASTEXITCODE) { throw "Không tải được Seed-VC." } }
$seedPython = Join-Path $seedRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $seedPython)) {
    uv venv --python $studioPython (Join-Path $seedRoot ".venv")
    if ($LASTEXITCODE) { throw "Không tạo được môi trường Seed-VC." }
}
uv pip install --python $seedPython torch==2.8.0 torchvision==0.23.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128
if ($LASTEXITCODE) { throw "Không cài được runtime CUDA Seed-VC." }
uv pip install --python $seedPython torch==2.8.0+cu128 torchaudio==2.8.0+cu128 numpy==1.26.4 scipy==1.13.1 librosa==0.10.2 soundfile==0.12.1 transformers==4.46.3 "huggingface-hub>=0.28.1,<1" munch einops pyyaml pydub python-dotenv "accelerate<2" pillow importlib-resources flatten-dict argbind pyloudnorm julius ffmpy ipython rich matplotlib pystoi torch-stoi markdown2 randomname tensorboard==2.11.0 protobuf==3.19.6 hf-xet
if ($LASTEXITCODE) { throw "Không cài được thư viện Seed-VC." }
uv pip install --python $seedPython --no-deps descript-audio-codec==1.0.0 descript-audiotools==0.7.2
if ($LASTEXITCODE) { throw "Không cài được bộ codec Seed-VC." }
if (-not (Test-Path -LiteralPath $aceRoot)) { git clone --depth 1 https://github.com/ace-step/ACE-Step-1.5.git $aceRoot; if ($LASTEXITCODE) { throw "Không tải được ACE-Step." } }
Push-Location -LiteralPath $aceRoot
try { uv sync --python $studioPython; if ($LASTEXITCODE) { throw "Không cài được ACE-Step." } } finally { Pop-Location }
Write-Host "Đã cài engine hát. Model sẽ được tải khi Anh Đạt chạy công việc đầu tiên."
