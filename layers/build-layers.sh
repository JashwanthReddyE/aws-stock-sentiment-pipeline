#!/usr/bin/env bash
# Build Lambda layers. Run from repo root: bash layers/build-layers.sh
# Uses Docker (lambci/amazonlinux image) to match Lambda runtime — required for binary wheels (pyarrow, prophet).
set -euo pipefail

REGION=${AWS_REGION:-us-east-1}
PY=python3.12
RUNTIME_IMAGE=public.ecr.aws/sam/build-python3.12:latest

build_layer () {
  local name=$1
  shift
  local out="layers/${name}-layer.zip"
  local stage="layers/.stage-${name}"
  rm -rf "$stage" "$out"
  mkdir -p "$stage/python"
  docker run --rm --entrypoint /bin/bash \
    -v "$PWD/$stage:/asset" \
    "$RUNTIME_IMAGE" -c "pip install --target /asset/python $* && find /asset -name '__pycache__' -type d -exec rm -rf {} +"
  (cd "$stage" && zip -qr "../../$out" python)
  rm -rf "$stage"
  echo "built $out ($(du -h "$out" | cut -f1))"
}

build_layer pydata "pandas==2.2.3" "pyarrow==17.0.0" "yfinance==0.2.51"
build_layer prophet "prophet==1.1.6"
