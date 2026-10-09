# ChargeSend

## Description

ChargeSend is an unofficial modification of Codex CLI that lets you choose
reasoning effort by holding Enter before sending a prompt. It keeps the Codex
terminal interface, authentication, settings, and agent functionality.

![Illustrated ChargeSend demo: hold Enter to raise reasoning effort, keep holding to descend, then release to submit at High; the Working line shows High Reasoning.](assets/chargesend-demo.gif)

## Implementation

- `patches/` contains source patches for Codex 0.161.0 and 0.160.0.
- `module/chargesend/` contains the charge timer, terminal capability detection,
  colored bar, and running-turn reasoning indicator.
- `module/chatwidget_chargesend.rs` and `module/app_chargesend.rs` connect charging
  to the composer, prompt submission, and turn lifecycle.
- `scripts/chargesend.py` fetches a pinned upstream release, applies the patch
  and modules, runs tests, and builds the CLI with its runtime helper.

Charging uses Kitty's Enter press, repeat, and release events. A monotonic timer
and Codex's redraw scheduler drive the bar. The selected effort travels with the
submitted prompt, including Plan-mode settings, without writing to `config.toml`.
Later prompts use their intended settings.

## Setup

Use Ubuntu 26.04 and a direct Kitty terminal, outside tmux, Screen, Zellij, or SSH.
Charging requires keyboard release events; unsupported terminals use ordinary
Enter submission.

From the repository directory:

```bash
bash scripts/setup-ubuntu.sh
export PATH="$HOME/.cargo/bin:$PATH"
python3 scripts/chargesend.py build --tag rust-v0.161.0
python3 scripts/chargesend.py install \
  --bundle dist/chargesend-0.1.0-codex-0.161.0-x86_64-unknown-linux-gnu-dev \
  --as-codex
export PATH="$HOME/.local/bin:$PATH"
```

The setup script installs Rust 1.95.0, native build dependencies, and Kitty.
Installation places ChargeSend under `~/.local`. `--as-codex` makes `codex` launch
ChargeSend and saves the original command as `codex-stock`.

## Usage

Open Kitty and run:

```bash
codex
```

Resume a session with `codex resume <session-id>`. After updating ChargeSend,
exit with `/quit` and reopen it.

Type a prompt while the agent is idle:

| Action | Behavior |
| --- | --- |
| Tap Enter | Send at the configured starting effort: Extra High by default, when supported. |
| Hold Enter | Rise to the highest offered tier over two seconds, descend to the lowest over two seconds, then repeat. |
| Release Enter | Send once at the displayed effort. |
| Press Escape while holding | Cancel and retain the draft and attachments. Release Enter before trying again. |

The charge bar uses the active model's supported tiers, excluding Ultra.
Charging applies to new turns. Menus, newline shortcuts, pasting, attachments,
and steering or queueing during a running turn retain their normal behavior.

While a task runs, its submitted effort appears after the timer and cancel hint:

```text
Working (1m 34s • esc to interrupt) · xHigh Reasoning
```

Set the starting effort and charge timing when launching:

```bash
CHARGESEND_DEFAULT_EFFORT=high CHARGESEND_HALF_CYCLE_MS=1000 codex
```

Starting-effort values are `low`, `medium`, `high`, `xhigh`, and `max`, limited to
what the model supports. The example uses High and one second per direction.
