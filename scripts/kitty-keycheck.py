#!/usr/bin/env python3
"""Physically verify Enter events in a direct Kitty window; no model requests."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import select
import subprocess
import sys
import termios
import time
import tty

CSI = re.compile(rb"\x1b\[([?]?[0-9:;]+)u")


def read_events(buffer: bytes) -> tuple[list[tuple[str, int]], bytes]:
    events = []
    consumed = 0
    for match in CSI.finditer(buffer):
        consumed = match.end()
        fields = match[1].decode("ascii")
        if fields.startswith("?"):
            events.append(("flags", int(fields[1:])))
            continue
        parts = fields.split(";")
        key = int(parts[0].split(":")[0])
        kind = int(parts[1].split(":")[1]) if len(parts) > 1 and ":" in parts[1] else 1
        if key == 13:
            events.append(("enter", kind))
        elif key == 27 and kind != 3:
            events.append(("escape", kind))
    return events, buffer[consumed:][-1024:]


def check(timeout: float) -> dict:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise RuntimeError("Run this check in an interactive Kitty terminal.")
    if os.environ.get("TMUX") or os.environ.get("TMUX_PANE") or os.environ.get("STY"):
        raise RuntimeError("Run directly in Kitty, outside a multiplexer.")
    if os.environ.get("TERM") != "xterm-kitty" or not os.environ.get("KITTY_WINDOW_ID"):
        raise RuntimeError("This first verification check targets direct Kitty only.")
    try:
        version = subprocess.check_output(["kitty", "--version"], text=True).strip()
    except (OSError, subprocess.SubprocessError):
        version = "unknown"
    report = {
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "terminal": version, "term": os.environ.get("TERM"),
        "negotiated_flags": None, "events": [], "holds_ms": [],
        "passed": False, "scope": "physical Enter protocol; no composer/backend verification",
    }
    fd = sys.stdin.fileno()
    original = termios.tcgetattr(fd)
    buffer = b""
    down = None
    deadline = time.monotonic() + timeout
    print("Tap Enter, then hold Enter for at least one second and release. Esc cancels.", flush=True)
    try:
        tty.setraw(fd)
        # Push disambiguation + event types + alternate keys + all-key reporting.
        sys.stdout.write("\x1b[>15u\x1b[?u")
        sys.stdout.flush()
        while time.monotonic() < deadline:
            if not select.select([fd], [], [], 0.1)[0]:
                continue
            buffer += os.read(fd, 4096)
            events, buffer = read_events(buffer)
            for event, value in events:
                now = time.monotonic()
                if event == "flags":
                    report["negotiated_flags"] = value
                    if value & 10 != 10:
                        report["reason"] = "Terminal did not confirm both required flags."
                        return report
                elif event == "escape":
                    report["reason"] = "Cancelled by Escape."
                    return report
                elif event == "enter":
                    report["events"].append({"kind": value, "time_remaining_ms": round((deadline - now) * 1000)})
                    if value == 1 and down is None:
                        down = now
                    elif value == 3 and down is not None:
                        report["holds_ms"].append(round((now - down) * 1000))
                        down = None
                    kinds = {item["kind"] for item in report["events"]}
                    if (report["negotiated_flags"] or 0) & 10 == 10 and {1, 2, 3} <= kinds and len(report["holds_ms"]) >= 2 and max(report["holds_ms"]) >= 500:
                        report["passed"] = True
                        return report
        report["reason"] = "Timed out before observing tap, held repeat, and matching releases."
        return report
    finally:
        sys.stdout.write("\x1b[<u")
        sys.stdout.flush()
        termios.tcsetattr(fd, termios.TCSADRAIN, original)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, help="write physical test evidence to a JSON file")
    parser.add_argument("--timeout", type=float, default=45)
    args = parser.parse_args()
    try:
        report = check(args.timeout)
    except (RuntimeError, OSError) as error:
        print(f"ChargeSend keycheck: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
