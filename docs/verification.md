# Verification record

Development machine: Ubuntu 26.04. Installed stock baseline: `codex-cli 0.161.0`.
Rust toolchain: `1.95.0 (59807616e 2026-04-14)`.

| Check | Observed result |
| --- | --- |
| Standalone Rust controller tests | 8 passed, compiled with Rust 1.95.0 |
| Standalone Rust capability tests | 1 passed, compiled with Rust 1.95.0 |
| Python patch/build/install workflow tests | 11 passed, including release-local lock version alignment |
| Complete pinned 0.161.0 source / patch application | Obtained; all 20 integration edits rebased; full patch check passed |
| Actual CLI compilation | In progress; awaiting locked dependencies |
| Mock-backend submission and Plan-mode integration tests | Written; execution pending actual TUI compilation |
| Second release portability | Full versioned 0.160.0 patch applies; compilation pending |
| Physical Kitty keyboard protocol | Passed in Kitty 0.45.0: flags 15, matching tap/hold releases, 101 repeats |
| Full physical composer UI checklist | Pending |
| GitHub Actions | Prepared locally; not run or published |

The controller tests cover tap boundaries, holding, descending and cycle
boundaries, repeats, exactly-once release, cancellation, context invalidation,
fallback, model-dependent choices, monotonic regression protection, adjustable
timing, and last-painted selection. The capability test requires both flag bits
and the direct-terminal gate.

The Python tests use temporary Git repositories and executable fixtures. They
verify pinned commits, clean-checkout protections, no partial patch on conflict,
prepared-source hashes, argument forwarding, version labels, bundle checksums,
installation/removal, and stock command preservation. They do not compile Codex.

The integration tests use the actual ChatWidget/composer and capture UserTurn and
OverrideTurnContext operations with a mock sticky backend. They require no live
model inference. Assertions cover per-request effort, restored defaults, Plan
precedence, image preparation/cancellation, paste, menus, newlines, busy input,
advanced opt-in, and rendering at narrow widths.

All twenty integration originals now come from the complete pinned `0.161.0`
release checkout. [source-provenance.json](source-provenance.json) records the
commit. Earlier cached originals were replaced before checking the full patch.
Patch application alone does not establish compilation or runtime behavior.

Record automated and manual checks separately. A compiled binary or a terminal
capability reply does not establish physical key-release delivery.

On 2026-10-08 the user ran the direct-Kitty diagnostic with a physical keyboard.
It observed flags `15` (including event types and all-key reporting), two presses,
two matching releases, an 88 ms tap, and a 3536 ms hold with repeats. The compact
evidence is [kitty-0.45.0-enter.json](kitty-0.45.0-enter.json). This verifies the
terminal transport, not the full interactive composer or live request path.
