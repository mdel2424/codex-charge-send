# Contributing to ChargeSend

ChargeSend is an independent, unofficial Apache-2.0 modification. Prepare changes
locally and direct proposed contributions to this project. Upstream Codex's
current contribution policy declines external pull requests; do not present
ChargeSend as an upstream-endorsed extension.

Keep charging mechanics in the dedicated modules and upstream hooks narrow.
Preserve upstream terminal and agent behavior, and read the targeted release's
repository instructions before editing. Update composer state-machine docs when
changing Enter, newline, paste, or eligibility behavior.

Run `python3 -m unittest discover -s tests -v`, build/test every catalogued release,
and record relevant physical Kitty checks. Add behavior tests that exercise the
request path when effort handling changes. No live inference is required for
the automated suite.

For release ports, follow [docs/build.md](docs/build.md). Include source
provenance, the exact upstream commit/toolchain, automated results, and remaining
manual limitations. Keep original licensing notices and mark modified upstream
files. Publishing the repository or a release requires a separate decision.
