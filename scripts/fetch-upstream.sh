#!/usr/bin/env bash
# Download sources/dependencies from a normal terminal when the agent is offline.
set -euo pipefail
chargesend_root=$(cd -- "$(dirname -- "$0")/.." && pwd)
export PATH="${HOME}/.cargo/bin:${PATH}"
export CARGO_HOME="${chargesend_root}/.build/cargo"
cd -- "$chargesend_root"
python3 - "$@" <<'PY'
import importlib.util
from pathlib import Path
import sys

spec = importlib.util.spec_from_file_location("chargesend_build", "scripts/chargesend.py")
workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflow)
tags = sys.argv[1:] or list(workflow.CATALOG["releases"])
try:
    for tag in tags:
        source = workflow.checkout(tag, None)
        lock = source / "codex-rs/Cargo.lock"
        original = lock.read_bytes()
        try:
            workflow.align_workspace_lock(source)
            workflow.run(["cargo", "fetch", "--locked"], cwd=source / "codex-rs")
        finally:
            lock.write_bytes(original)
        print(f"Downloaded {tag} and its locked dependencies: {source}", flush=True)
except workflow.Failure as error:
    raise SystemExit(f"ChargeSend download: {error}")
PY
printf '%s\n' 'Source and dependency downloads complete. The agent can build offline now.'
