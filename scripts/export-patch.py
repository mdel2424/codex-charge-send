#!/usr/bin/env python3
"""Export integration edits only; dedicated modules are copied via overlays.json."""

import argparse
import difflib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--base", type=Path, required=True)
parser.add_argument("--modified", type=Path, required=True)
parser.add_argument("--output", type=Path, default=ROOT / "patches/chargesend.patch")
args = parser.parse_args()
patch = []
for original in sorted(args.base.rglob("*.rs")):
    relative = original.relative_to(args.base)
    modified = args.modified / relative
    if not modified.is_file():
        raise SystemExit(f"Missing integration file: {modified}")
    before, after = original.read_text(), modified.read_text()
    if before != after:
        patch.extend(difflib.unified_diff(
            before.splitlines(keepends=True), after.splitlines(keepends=True),
            fromfile=f"a/{relative}", tofile=f"b/{relative}", n=3,
        ))
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text("".join(patch))
print(f"Wrote {args.output}")
