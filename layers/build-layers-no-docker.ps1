# Windows-friendly Lambda layer builder WITHOUT Docker
# Uses pip to download pre-built wheels from PyPI, then zips them
# Run from repo root: powershell layers/build-layers-no-docker.ps1

$ErrorActionPreference = "Stop"
$PythonVersion = "3.12"

function Build-Layer {
    param([string]$Name, [string[]]$Packages)

    $out = "layers/$Name-layer.zip"
    $stage = "layers/.stage-$Name"
    $venv_path = "layers/.venv-$Name"

    Write-Host "Building $Name layer..."

    # Clean up old artifacts
    if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
    if (Test-Path $venv_path) { Remove-Item -Recurse -Force $venv_path }
    if (Test-Path $out) { Remove-Item -Force $out }

    # Create virtual environment
    New-Item -ItemType Directory -Force -Path $venv_path | Out-Null
    python -m venv $venv_path
    $pip = "$venv_path\Scripts\pip"

    # Install packages into staging directory
    New-Item -ItemType Directory -Force -Path "$stage/python" | Out-Null
    & $pip install --target "$stage/python" --only-binary=:all: @Packages

    # Remove unnecessary files to reduce zip size
    Get-ChildItem -Path "$stage/python" -Recurse -Include @("*.pyc", "*.pyo", "__pycache__", "*.dist-info", "*.egg-info") | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

    # Zip it up
    Compress-Archive -Path "$stage/python" -DestinationPath $out -Force
    $size = (Get-Item $out).Length / 1MB
    Write-Host "[OK] built $out ($([math]::Round($size, 1)) MB)"

    # Clean up
    Remove-Item -Recurse -Force $stage
    Remove-Item -Recurse -Force $venv_path
}

# Build layers
Build-Layer -Name "pydata" -Packages @(
    "pandas==2.2.3",
    "pyarrow==17.0.0",
    "yfinance==0.2.51",
    "requests==2.32.3"
)

Build-Layer -Name "prophet" -Packages @(
    "prophet==1.1.6"
)

Write-Host ""
Write-Host "[OK] All layers built successfully!"
Write-Host "Ready to deploy with: terraform -chdir=infra apply"
