# Windows-friendly Lambda layer builder. Requires Docker Desktop running.
# Run from repo root: powershell layers/build-layers.ps1
$ErrorActionPreference = "Stop"

$RuntimeImage = "public.ecr.aws/sam/build-python3.12:latest"

function Build-Layer {
    param([string]$Name, [string[]]$Packages)

    $out = "layers/$Name-layer.zip"
    $stage = "layers/.stage-$Name"

    if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
    if (Test-Path $out) { Remove-Item -Force $out }
    New-Item -ItemType Directory -Force -Path "$stage/python" | Out-Null

    $pipArgs = "pip install --target /asset/python " + ($Packages -join " ") + " && find /asset -name __pycache__ -type d -exec rm -rf {} +"
    docker run --rm --entrypoint /bin/bash `
        -v "${PWD}/${stage}:/asset" $RuntimeImage -c $pipArgs

    Compress-Archive -Path "$stage/python" -DestinationPath $out -Force
    Remove-Item -Recurse -Force $stage
    Write-Host "built $out"
}

Build-Layer -Name "pydata" -Packages @("pandas==2.2.3", "pyarrow==17.0.0", "yfinance==0.2.51")
Build-Layer -Name "prophet" -Packages @("prophet==1.1.6")
