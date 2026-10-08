# ChargeSend

ChargeSend is an **unofficial community modification of Codex CLI**. Hold Enter
to choose the reasoning effort for an idle, new-turn prompt. Release Enter to
send it. The existing Codex interface, agent, authentication, and configuration
remain in use. The separate command is `chargesend`.

This repository contains a source patch, dedicated modules, and their tests.
Building it and publishing the repository
or a release are separate steps.

## Interaction

- Tap Enter: submit at the lowest effort offered by the active model.
- Hold Enter: the composer shows an effort label and a bar. The bar reaches the
  top after two seconds, descends over two seconds, and repeats.
- Release Enter: submit once at the effort label most recently drawn.
- Escape: cancel and keep the draft and attachments. Release Enter before trying
  again. Editing, focus loss, or a context transition also cancels a charge.

Charging is limited to an idle, eligible prompt composer. Menus, approval dialogs,
completion popups, slash commands, newline shortcuts, paste classification,
external editing, and steering or queuing during a running turn use Codex's
existing input paths. Charging cannot change a turn that is already running.

Effort choices come from the active model's advertised choices. Max and Ultra
remain excluded unless that exact advanced tier is already explicitly selected
in the active settings. A charge changes one submitted request, including its
Plan-mode collaboration settings; it does not write the selection to
`config.toml`. Later requests explicitly restore their intended effort.
The backend can retain the charged thread setting until that next request;
restart/resume and multiple-client behavior need further verification.

## Terminal requirements

The initial target is **Kitty directly**, outside tmux, GNU Screen, Zellij, or SSH. Both
keyboard-protocol event-type reporting and reporting all keys as escape codes
must be negotiated and confirmed by Codex's startup query. Without confirmation,
Enter submits normally and the UI explains that hold-to-charge is unavailable.
See [Kitty's keyboard protocol](https://sw.kovidgoyal.net/kitty/keyboard-protocol/).

Set `CHARGESEND_DISABLE=1` to use ordinary Enter submission. Codex's existing
`CODEX_TUI_DISABLE_KEYBOARD_ENHANCEMENT` setting also prevents charging.
Additional terminals and multiplexers require their own keyboard and UI tests.

| Terminal | Status |
| --- | --- |
| Direct Kitty 0.45.0 / Ubuntu 26.04 | Physical key protocol, bar ascent/descent, and Escape cancellation passed on Codex 0.161.0; remaining manual checklist pending |
| GNOME Terminal / Ptyxis with VTE 0.84.0 | Unavailable: this VTE baseline does not forward key releases; normal Enter fallback |
| Kitty through tmux / GNU Screen / Zellij / SSH | Charging disabled; unverified transport |
| Other terminals, SSH and remote transports | Unverified; normal Enter fallback |

## Build and install

Ubuntu 26.04 is the development target. Python 3.11+, Git, Rust 1.95.0, and native
build dependencies are required. Run the setup in your normal terminal:

```bash
bash scripts/setup-ubuntu.sh
export PATH="$HOME/.cargo/bin:$PATH"
python3 scripts/chargesend.py build --tag rust-v0.161.0
```

The build checks the pinned upstream commit, applies the patch, runs focused and
regression tests, and compiles the actual Codex CLI. A patch conflict stops before
changing the checkout. The default development build is faster than a release
build; add `--profile release` for an optimized binary.

The output is a versioned directory under `dist/`, containing the native binary,
`bin/chargesend` launcher, notices, and a manifest recording its exact upstream
baseline and checksums. Select that directory explicitly:

```bash
python3 scripts/chargesend.py install --bundle dist/chargesend-0.1.0-codex-0.161.0-x86_64-unknown-linux-gnu-dev
chargesend --version
chargesend
```

Installation defaults to `~/.local/bin/chargesend` and a versioned bundle under
`~/.local/lib/chargesend`. Put `~/.local/bin` on your PATH if needed. Use
`--prefix ./local` for a project-local installation. It does not replace `codex`.
ChargeSend uses your ordinary Codex settings and conversation data.

Remove the separate command and its managed bundles:

```bash
python3 scripts/chargesend.py uninstall
```

This retains Codex, authentication, configuration, and conversation data. Full
build, offline download, and update instructions are in [docs/build.md](docs/build.md).

## Adjustable timing

| Environment variable | Default | Meaning |
| --- | --- | --- |
| `CHARGESEND_HALF_CYCLE_MS` | `2000` | Duration of each ascent or descent; 250–60000 ms |
| `CHARGESEND_TAP_MS` | `150` | Tap always selects the lowest effort; less than half the ascent duration |
| `CHARGESEND_FRAME_MS` | `33` | Redraw interval; 10–100 ms |

Invalid timing values log a warning and use all defaults. Time comes from a
monotonic clock, so key repeats and changes to the wall clock do not drive charge.
At narrow terminal widths the effort label appears before the clipped bar.

## Compatibility and verification

| Codex release | Pinned commit | Patch / compile / tests |
| --- | --- | --- |
| `0.161.0` | `979011409de0a60b52f179721948e65531d26144` | Native CLI built; 495 Rust tests passed; basic physical Kitty UI passed |
| `0.160.0` | `a956835d020762cb2b570053af06f643a11c0ecc` | Native CLI built; 486 Rust tests passed; physical UI not tested on this baseline |

[docs/verification.md](docs/verification.md) records what actually ran and what
remains outstanding. [docs/manual-testing.md](docs/manual-testing.md) covers
physical keys and full terminal behavior. A passing CI build alone does not
verify physical key releases.

The integration is intentionally small but touches upstream composer, app, and
submission code that changes frequently. See [docs/architecture.md](docs/architecture.md)
and the porting procedure before adding another release. GitHub Actions checks
both catalogued release tags; those jobs only run after the repository is pushed.

## License and attribution

ChargeSend and its modifications are licensed under [Apache 2.0](LICENSE), the
same license as Codex. [NOTICE](NOTICE) identifies the changes and reproduces
upstream attribution; [UPSTREAM-NOTICE](UPSTREAM-NOTICE) preserves the original
notice. The Codex UI and help retain upstream names. The launcher reports
ChargeSend's version and its upstream baseline with `--version`.

ChargeSend is independently distributed and is not an OpenAI product or plugin.
Contributions belong here; follow [CONTRIBUTING.md](CONTRIBUTING.md). See
[docs/publishing.md](docs/publishing.md) for preparing the separate GitHub project.
