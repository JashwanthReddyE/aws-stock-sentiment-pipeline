# Build Lambda functions with LINUX-compatible dependencies bundled.
# Uses pip's --platform flag to fetch manylinux wheels even when building on Windows.
# Run from infra/ directory: powershell .\build-lambdas.ps1

$ErrorActionPreference = "Stop"

function Build-Lambda {
    param([string]$Name)

    $lambda_dir = "../lambdas/$Name"
    $build_dir = "build/$Name"
    $output_zip = "build/${Name}.zip"

    Write-Host "Building Lambda: $Name"

    # Clean
    if (Test-Path $build_dir) { Remove-Item -Recurse -Force $build_dir }
    if (Test-Path $output_zip) { Remove-Item -Force $output_zip }
    New-Item -ItemType Directory -Force -Path $build_dir | Out-Null

    # Copy Lambda code
    Copy-Item -Path "$lambda_dir\*.py" -Destination $build_dir -Force

    # Install dependencies — Linux-compatible wheels only
    $req_file = "$lambda_dir\requirements.txt"
    if (Test-Path $req_file) {
        Write-Host "  Installing dependencies for Linux x86_64 / Python 3.12..."
        py -m pip install `
            -r $req_file `
            --target $build_dir `
            --platform manylinux2014_x86_64 `
            --python-version 3.12 `
            --implementation cp `
            --only-binary=:all: `
            --upgrade `
            --quiet
    }

    # Cleanup
    Get-ChildItem -Path $build_dir -Recurse -Include @("*.pyc", "*.pyo", "__pycache__", "*.dist-info", "*.egg-info", "tests", "*.md", "examples", "docs") -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

    # Zip
    Compress-Archive -Path "$build_dir\*" -DestinationPath $output_zip -Force
    $size = (Get-Item $output_zip).Length / 1MB
    Write-Host "  [OK] $output_zip ($([math]::Round($size, 1)) MB)"
}

Build-Lambda -Name "ingest"
Build-Lambda -Name "enrich"
Build-Lambda -Name "forecast"

Write-Host ""
Write-Host "[OK] All Lambdas built with Linux wheels. Now run: terraform apply -auto-approve"
