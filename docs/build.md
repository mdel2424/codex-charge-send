# Reproducible source workflow

The release catalog pins both a public tag and its peeled commit. Rust comes from
upstream's `rust-toolchain.toml`; all third-party Cargo.lock entries are retained
and dependency commands use `--locked`. The public release tags bump the local
workspace version while their lock entries remain at `0.0.0`. The workflow
deterministically aligns only inherited local package versions, without resolving
or upgrading dependencies, and records original and adjusted lock checksums.
Builds are repeatable from the specified inputs, but
binary bytes can still vary with native compilers, OS libraries, and paths.

## Prepare, test, build

Run `bash scripts/setup-ubuntu.sh` once in a normal Ubuntu terminal. It installs
Rust 1.95.0 with rustfmt, clippy and rust-src, native development packages, and
Kitty. It does not install or replace a Codex binary.

```bash
export PATH="$HOME/.cargo/bin:$PATH"
python3 scripts/chargesend.py prepare --tag rust-v0.161.0
python3 scripts/chargesend.py test --tag rust-v0.161.0
python3 scripts/chargesend.py build --tag rust-v0.161.0 --profile dev
```

`prepare` obtains a full checkout in `.build/upstream/<tag>`, verifies the commit,
checks the entire patch before applying it, and copies `overlays.json` modules.
`test` uses pinned rustfmt and runs ChargeSend, existing composer, Plan-mode, and
event-stream tests. `build` repeats those checks before compiling `codex-cli`.
It reuses `codex-code-mode-host` from an installed official package of the exact
baseline version when available; otherwise it compiles the helper separately
from the pinned source. The bundle records the helper's origin and checksum.
Pass `--code-mode-host /path/to/compatible/codex-code-mode-host` to supply one
explicitly. This avoids the JavaScript engine's separate V8 archive download
when rebuilding for personal use; Cargo's offline mode does not cache that archive.
The test runner uses an 8 MiB thread stack, matching upstream's test workflow.
The standalone patch workflow uses Cargo's lib-test runner with focused filters.
During local verification, upstream's `just`, nextest, and cargo-insta frontends
were unavailable in the offline cache; inline snapshots were reviewed directly.
Only Rust sources change in upstream, so the workflow runs its pinned rustfmt
without the unrelated Python, Bazel, and justfile formatters.

Use `--source /path/to/clean/upstream` to supply a full checkout already at the
expected commit. A dirty checkout, unexpected commit, edited prepared sources,
or overlay collision stops with a diagnostic. The workflow never resets a
supplied checkout. An unchanged prepared checkout can be reused after interruption.
Inputs and source hashes are rechecked after compilation so an edit during the
build cannot produce a bundle with a misleading patch fingerprint.
After changing the patch or modules, use a fresh checkout.

For constrained machines, the following keeps memory and debug output smaller:

```bash
export CARGO_BUILD_JOBS=2 CARGO_INCREMENTAL=0
export CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_TEST_DEBUG=0
export CARGO_TARGET_DIR="$PWD/.build/target"
```

## Download for an offline agent

When an agent session has no network but your normal terminal does, run:

```bash
bash scripts/fetch-upstream.sh
export CARGO_HOME="$PWD/.build/cargo"
export CARGO_NET_OFFLINE=true
python3 scripts/chargesend.py build --tag rust-v0.161.0
```

The download script fetches both catalogued release checkouts and their locked
Cargo dependencies into the workspace. Pass a tag to download only that release.
Sources are left unpatched. Rust must already be installed for both releases.
Some dependencies have build-time downloads outside Cargo; if an offline build
reports one, obtain that exact artifact in your normal terminal as well.

## Output and installation

Each bundle name includes ChargeSend version, Codex release, host triple, and
profile. Its `manifest.json` contains the upstream commit, patch/module
fingerprint, Rust version, original and adjusted lock checksums, binary checksum, automated
checks, the runtime helper checksum, and a separate physical keyboard status. The `chargesend-cli` file is the
actual compiled native binary. `bin/chargesend` forwards arguments unchanged,
except for its single-argument version reporting.

```bash
python3 scripts/chargesend.py install --bundle /absolute/path/to/bundle --prefix "$HOME/.local" --as-codex
codex --version
codex-stock --version
python3 scripts/chargesend.py restore-codex --prefix "$HOME/.local"
python3 scripts/chargesend.py uninstall --prefix "$HOME/.local"
```

`--as-codex` saves the existing command as `codex-stock` and links `codex` to the
installed ChargeSend launcher. Arguments are forwarded unchanged. Repeating the
same mapping is safe; an existing conflicting backup is never overwritten.
Uninstall restores the original command when its `codex` points to this install.
Omit `--as-codex` to leave the `codex` command alone.

For a project-local install, map the launcher without copying the bundle again:

```bash
python3 scripts/chargesend.py link-codex --launcher "$PWD/local/bin/chargesend"
```

This maps `~/.local/bin/codex`; `restore-codex` reverses it. Restore this mapping
before uninstalling the project-local bundle. Keep `~/.local/bin` first on PATH.
The installer refuses an unmanaged `chargesend` launcher. The uninstaller removes
only managed launchers and validated bundles, retaining settings and conversations.
Old versioned bundles remain available until uninstall. Older bundles missing the
runtime helper or its manifest checksum need rebuilding before installation.
Reinstall replaces executable files atomically, so an open ChargeSend session
keeps running. Exit and resume it to load the rebuilt interface.

## Timing options

Set these environment variables before launching ChargeSend:

| Environment variable | Default | Meaning |
| --- | --- | --- |
| `CHARGESEND_DEFAULT_EFFORT` | `xhigh` | Tap and initial charge effort: low, medium, high, xhigh, max. Invalid values use xhigh; unsupported tiers use the nearest supported lower tier. |
| `CHARGESEND_HALF_CYCLE_MS` | `2000` | Duration of initial default-to-peak rise and each subsequent full ascent or descent; 250–60000 ms. |
| `CHARGESEND_TAP_MS` | `150` | Tap always selects the configured starting effort; less than half the ascent duration. |
| `CHARGESEND_FRAME_MS` | `33` | Redraw interval; 10–100 ms. |

For example, in Kitty with the project-local installation:

```bash
CHARGESEND_HALF_CYCLE_MS=1000 codex
```

Invalid timing values log a warning and use all defaults. A monotonic clock
drives charging, independent of key repeats and changes to the wall clock.
At narrow terminal widths the effort label appears before the clipped bar.

Set `CHARGESEND_DISABLE=1` for ordinary Enter submission. Codex's existing
`CODEX_TUI_DISABLE_KEYBOARD_ENHANCEMENT` setting also prevents charging.

## Port to another release

1. Inspect installed `codex --version` and obtain its exact public release source.
   Read root and nested `AGENTS.md` instructions in that checkout.
2. Confirm keyboard setup/probe order, event dispatch, composer eligibility,
   redraw scheduling, model effort restrictions, submission settings, and
   asynchronous image preparation. Do not assume function names stayed stable.
3. Add the tag, peeled commit, and toolchain to `supported-releases.json` with a
   candidate status. Attempt `prepare` in a fresh checkout. Resolve conflicts by
   inspecting the current upstream behavior, without fuzzy or forced application.
4. Keep the controller/capability modules independent. Make necessary glue edits
   in a scratch copy of exact upstream files. Export the integration diff:

   ```bash
   python3 scripts/export-patch.py --base /path/to/original-files --modified /path/to/edited-files
   ```

5. Build and run the focused tests and existing composer/Plan/event regressions
   on both the new tag and the previous supported tag. If integration differs,
   maintain an explicitly selected versioned patch instead of assuming one patch
   applies everywhere. Update the CI matrix and provenance.
6. Complete the physical Kitty checklist. Record versions and failures in
   `docs/verification.md`; then update the compatibility table and VERSION.

Preparing or testing a release does not publish it. Repository creation, remote
configuration, pushing, and releases are separate actions.
GitHub Actions also runs a scoped Clippy check against each supported baseline.
