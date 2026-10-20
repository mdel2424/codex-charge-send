#!/usr/bin/env bash
set -euo pipefail
chargesend_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if (( $# )) && [[ "$1" != -* ]]; then
  chargesend_tag=$1
  shift
  exec python3 "$chargesend_root/scripts/chargesend.py" build --tag "$chargesend_tag" "$@"
fi
exec python3 "$chargesend_root/scripts/chargesend.py" build "$@"
