#!/usr/bin/env bash
# Run from your normal Ubuntu terminal. This provisions build tools, not Codex.
set -euo pipefail
sudo apt-get update
sudo apt-get install -y build-essential git curl cmake pkg-config libssl-dev \
  libcap-dev libclang-dev libasound2-dev libudev-dev libdbus-1-dev kitty
chargesend_installer=$(mktemp)
trap 'rm -f "$chargesend_installer"' EXIT
curl --proto '=https' --tlsv1.2 --fail --location https://sh.rustup.rs \
  --output "$chargesend_installer"
sh "$chargesend_installer" -y --profile minimal --default-toolchain 1.95.0
"${CARGO_HOME:-$HOME/.cargo}/bin/rustup" component add rustfmt clippy rust-src --toolchain 1.95.0
printf '%s\n' 'Setup complete. Open a new terminal, then run ./scripts/build.sh.'
