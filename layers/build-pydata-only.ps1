# Build only pydata layer (pandas, pyarrow, yfinance, requests)
# Prophet is bundled with forecast Lambda directly
# Run from repo root: powershell layers/build-pydata-only.ps1

$ErrorActionPreference = "Stop"

Write-Host "Building pydata layer..."

$out = "layers/pydata-layer.zip"
$stage = "layers/.stage-pydata"
$venv_path = "layers/.venv-pydata"

# Clean up old artifacts
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
if (Test-Path $venv_path) { Remove-Item -Recurse -Force $venv_path }
if (Test-Path $out) { Remove-Item -Force $out }

# Create virtual environment
New-Item -ItemType Directory -Force -Path $venv_path | Out-Null
py -m venv $venv_path
$pip = "$venv_path\Scripts\pip"

# Install packages
New-Item -ItemType Directory -Force -Path "$stage/python" | Out-Null
& $pip install --target "$stage/python" --only-binary=:all: `
    "pandas==2.2.3" `
    "pyarrow==17.0.0" `
    "yfinance==0.2.51" `
    "requests==2.32.3"

Write-Host "  Before cleanup: $('{0:F1}' -f ((Get-ChildItem -Path "$stage/python" -Recurse -ErrorAction SilentlyContinue | Measure-Object -Sum Length).Sum / 1MB)) MB"

# Aggressive cleanup
Get-ChildItem -Path "$stage/python" -Recurse -Include @("*.pyc", "*.pyo", "__pycache__", "*.dist-info", "*.egg-info", "tests", "test", "*.md", "examples", "docs", ".git") -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "  After cleanup: $('{0:F1}' -f ((Get-ChildItem -Path "$stage/python" -Recurse -ErrorAction SilentlyContinue | Measure-Object -Sum Length).Sum / 1MB)) MB"

# Zip it up
Compress-Archive -Path "$stage/python" -DestinationPath $out -Force
$size = (Get-Item $out).Length / 1MB
Write-Host "[OK] built $out ($([math]::Round($size, 1)) MB)"

# Create dummy prophet-layer.zip (not used)
$dummy = "layers/prophet-layer.zip"
if (-not (Test-Path $dummy)) {
    New-Item -ItemType File -Path $dummy -Force | Out-Null
    Write-Host "[OK] created dummy $dummy (prophet bundled with forecast Lambda)"
}

# Clean up
Remove-Item -Recurse -Force $stage
Remove-Item -Recurse -Force $venv_path

Write-Host ""
Write-Host "[OK] Layer build complete!"
