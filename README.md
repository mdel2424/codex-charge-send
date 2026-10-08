# ChargeSend

An **unofficial community modification of Codex CLI**: hold Enter to choose
reasoning effort, then release to send your prompt. It uses the existing Codex
interface, authentication, and settings, with a separate `chargesend` command.

## Usage

For the project-local installation, run this from the repository directory to
open ChargeSend in Kitty:

```bash
kitty --directory "$PWD" "$PWD/local/bin/chargesend" --no-daemon
```

Already in Kitty? Run `./local/bin/chargesend --no-daemon`. After installing on
your PATH, use `chargesend --no-daemon` instead. `--no-daemon` runs without a
shared background server.

Wait until the agent is idle, then type your prompt:

| Action | Result |
| --- | --- |
| Tap Enter | Send at the lowest allowed effort. |
| Hold Enter | Watch the effort bar rise for two seconds, descend for two seconds, and repeat. |
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

Install the resulting bundle as a separate command:

```bash
python3 scripts/chargesend.py install \
  --bundle dist/chargesend-0.1.0-codex-0.161.0-x86_64-unknown-linux-gnu-dev
export PATH="$HOME/.local/bin:$PATH"
chargesend --version
```

The default location is `~/.local`. Add `--prefix ./local` to install inside the
repository instead. Stock `codex` stays installed. Remove ChargeSend with
`python3 scripts/chargesend.py uninstall`; add `--prefix ./local` to remove a
project-local installation. Removal keeps your Codex settings and conversations.

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
| 0.161.0 | Native CLI built; 495 Rust tests passed. |
| 0.160.0 | Native CLI built; 486 Rust tests passed; physical UI check pending. |

The [verification record](docs/verification.md) distinguishes automated results
from physical checks. The full [manual checklist](docs/manual-testing.md) still
needs completion, including release-to-submit in the actual UI.

## Settings and limits

Effort choices come from the active model. Max and Ultra require that exact tier
to be explicitly selected in the active settings. The charge applies to the
submitted request, including Plan mode, without writing to `config.toml`.
Later submissions explicitly use their intended effort. The backend can retain
the charged thread setting until the next submission; restart/resume and
multiple-client behavior need further testing.

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
