#!/usr/bin/env bash
set -euo pipefail
chargesend_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
chargesend_tag=${1:-rust-v0.161.0}
if (( $# )); then shift; fi
exec python3 "$chargesend_root/scripts/chargesend.py" build --tag "$chargesend_tag" "$@"
