# ChargeSend

An **unofficial community modification of Codex CLI**: hold Enter to choose
reasoning effort, then release to send your prompt. It uses the existing Codex
interface, authentication, and settings. This project is built for personal use
first: make your usual `codex` command launch ChargeSend, with the original CLI
available as `codex-stock`.

## Usage

For the existing project-local installation, map your command once:

```bash
python3 scripts/chargesend.py link-codex --launcher "$PWD/local/bin/chargesend"
codex --version
```

In Kitty, use `codex` or `codex resume <session-id>` as usual. Exit an existing
stock CLI with `/quit` and reopen it to activate the modified interface.
The mapping works without shell aliases, including Kitty's Bash POSIX mode.

You can also run `./local/bin/chargesend` directly. Use the shared background
server when resuming a session that is open there. `--no-daemon` starts a separate
server and cannot resume a session while another server holds its writer lock;
close the other client and allow its session to unload first.

Wait until the agent is idle, then type your prompt:

| Action | Result |
| --- | --- |
| Tap Enter | Send at the configured starting effort (Extra High by default). |
| Hold Enter | Start at Extra High, rise to Max over two seconds, then descend to Low and repeat Low–Max. |
| Release Enter | Send once using the displayed effort. |
| Press Escape while holding | Cancel and keep the draft and attachments. Release Enter before trying again. |

Menus, slash commands, newline shortcuts, paste, attachments, and input during
a running turn keep their normal Codex behavior. Charging selects effort for a
new turn; it cannot change a turn already running.

## Build and install

From the repository directory on Ubuntu 26.04:

```bash
bash scripts/setup-ubuntu.sh
export PATH="$HOME/.cargo/bin:$PATH"
python3 scripts/chargesend.py build --tag rust-v0.161.0
```

Install the resulting bundle and make it your normal `codex` command:

```bash
python3 scripts/chargesend.py install \
  --bundle dist/chargesend-0.1.0-codex-0.161.0-x86_64-unknown-linux-gnu-dev \
  --as-codex
export PATH="$HOME/.local/bin:$PATH"
codex --version
```

The default location is `~/.local`. Add `--prefix ./local` to install inside the
repository instead. Omit `--as-codex` for a separate `chargesend` command.
The native bundle includes its matching `codex-code-mode-host` runtime helper.
Restore the original command with `python3 scripts/chargesend.py restore-codex`.
Remove ChargeSend with
`python3 scripts/chargesend.py uninstall`; add `--prefix ./local` to remove a
project-local installation. Uninstall restores a mapped `codex` at that prefix
and keeps your settings and conversations. If you mapped a project-local launcher
into `~/.local/bin`, run `restore-codex` before removing that project-local install.

See the [build guide](docs/build.md) for prerequisites, offline downloads,
optimized builds, and updating to another Codex release.

## Compatibility

Charging requires **Kitty directly**, outside tmux, Screen, Zellij, or SSH.
Startup verifies the keyboard capabilities needed for Enter releases. If they
are unavailable, Enter sends normally and the UI shows an unavailable notice.

| Terminal | Status |
| --- | --- |
| Kitty 0.45.0 on Ubuntu 26.04 | Physical Enter events, bar ascent/descent, and Escape cancellation verified on Codex 0.161.0. |
| GNOME Terminal / Ptyxis with VTE 0.84.0 | No key releases; ordinary Enter fallback. |
| Other terminals, multiplexers, and SSH | Unverified; charging disabled. |

| Codex baseline | Automated verification |
| --- | --- |
| 0.161.0 | Native CLI built; 517 Rust tests passed. |
| 0.160.0 | Native CLI built; 508 Rust tests passed; physical UI check pending. |

The [verification record](docs/verification.md) distinguishes automated results
from physical checks. The full [manual checklist](docs/manual-testing.md) still
needs completion, including release-to-submit in the actual UI.

## Settings and limits

The bar uses the active model's supported efforts through Max, including Max
without first selecting it in settings. Ultra is excluded from the charge bar.
For GPT-6.1 Sol, a tap sends Extra High. Hold to the peak to send at Max.
The colored bar runs from green at Low through yellow to red at Max.
Its label has a fixed width so tier changes keep the bar anchored. During a
turn, the submitted effort appears in a fixed-width slot at the right of the
Working row, for example `xHigh Reasoning`. Queueing or steering does not
replace that active-turn label. The slot hides when the core working controls
need the available width. The charge applies to the
submitted request, including Plan mode, without writing to `config.toml`.
Later submissions explicitly use their intended effort. The backend can retain
the charged thread setting until the next submission; restart/resume and
multiple-client behavior need further testing.

Set `CHARGESEND_DEFAULT_EFFORT=xhigh` to choose the tap and initial charge
effort (`low`, `medium`, `high`, `xhigh`, or `max`). Unsupported defaults use
the closest supported lower tier, or the first advertised tier. Each new press
starts at this default.

Set `CHARGESEND_HALF_CYCLE_MS=1000` for a one-second ascent and descent, or
`CHARGESEND_DISABLE=1` for ordinary Enter submission. See the
[timing options](docs/build.md#timing-options) for all defaults and ranges.

## Development and license

The repository contains the source patch, dedicated charging modules, tests,
and GitHub Actions checks for both supported releases. See the
[architecture](docs/architecture.md), [contribution guide](CONTRIBUTING.md),
and [publishing guide](docs/publishing.md). Publishing is a separate step.

ChargeSend is independently distributed and is not an OpenAI product or plugin.
It is licensed under [Apache 2.0](LICENSE). [NOTICE](NOTICE) records the
modifications and attribution; [UPSTREAM-NOTICE](UPSTREAM-NOTICE) preserves
the original notice.
