# Optimized Lambda layer builder for Windows — removes unnecessary files to stay under 70MB limit
# Run from repo root: powershell layers/build-layers-optimized.ps1

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

    Write-Host "  Before cleanup: $('{0:F1}' -f ((Get-ChildItem -Path "$stage/python" -Recurse | Measure-Object -Sum Length).Sum / 1MB)) MB"

    # Aggressive cleanup to reduce size
    $patterns = @(
        "*.pyc", "*.pyo", "*.so.debug",
        "__pycache__", ".dist-info", ".egg-info",
        "*.egg-info", "*.egg",
        "tests", "test", "testing",
        "*.md", "*.txt", "*.rst",
        "examples", "docs",
        "*.c", "*.cpp", "*.h",
        ".gitignore", ".git", ".github",
        "*.so"  # Remove compiled libs except ones we need
    )

    foreach ($pattern in $patterns) {
        Get-ChildItem -Path "$stage/python" -Recurse -Include $pattern -ErrorAction SilentlyContinue |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    }

    # Keep only essential compiled libs
    Get-ChildItem -Path "$stage/python" -Recurse -Name "*.so*" |
        Where-Object { $_ -notmatch "(pandas|pyarrow|prophet|numpy|statsmodels)" } |
        ForEach-Object { Remove-Item -Force -ErrorAction SilentlyContinue "$stage/python/$_" }

    Write-Host "  After cleanup: $('{0:F1}' -f ((Get-ChildItem -Path "$stage/python" -Recurse | Measure-Object -Sum Length).Sum / 1MB)) MB"

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
Write-Host "If layers are still >70MB, try the minimal approach:"
Write-Host "  - Remove version pins and use --only-binary"
Write-Host "  - Or split into multiple smaller layers"
