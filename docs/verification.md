# Verification record

Current default: **Codex 0.163.0**, ported and installed on 2026-10-17.
The 0.161.0 bundle remains available for rollback. Earlier records below retain
their original baseline and physical-test scope.

| 0.163.0 check | Result |
| --- | --- |
| Exact source and patch | Pinned commit `83086188ae0614bd882818ff1aa23f3194962012`; clean patch application; third-party dependency pins unchanged |
| Native CLI and runtime helper | CLI compiled with Rust 1.95.0; matching installed official 0.163.0 helper reused; version, help, fingerprints, and executable checksums passed |
| ChargeSend and upstream regressions | 566 passed: ChargeSend 43, composer 397, Plan mode 61, event stream 10, Working status 10, activation guard 1, settings panel 19, app input 2, key chords 22, view-transition guard 1 |
| Scoped Clippy and formatting | Passed; only existing upstream app-server `let_and_return` warning |
| Python workflow tests | 24 passed |
| Installed command | `~/.local/bin/codex` resolves to the project-local launcher and the 0.163.0 bundle; native version and checksums verified |
| Rollback | Existing 0.161.0 installed and distribution bundles preserved; original binary checksum verified |
| Physical Kitty / live inference | Not repeated on 0.163.0; no live inference used |
| GitHub Actions | Matrix updated for 0.163.0, 0.161.0, and 0.160.0; remote CI not run during this local verification |

The 0.163.0 patch hooks the production activation-key-aware ChatWidget entry point.
Consumed key releases still retire settings-editor activation guards and notify
covered views without dispatching another action. A new regression test checks
this release path; upstream settings-editor chord handoff tests also pass.
The charge controller, selected-effort starting behavior, immediate constant
speed, and prompt-local settings envelope are unchanged.

The first 521 tests ran through Cargo's focused lib-test filters. The additional
45 input/settings tests ran directly from the same compiled test executable with
upstream's 8 MiB test stack and workspace working directory. All filters are now
part of `chargesend.py test/build`. The exact CI Clippy command was also rerun
from the upstream workspace. Full workspace/Bazel tests were not run.
[source-provenance-0.163.0.json](source-provenance-0.163.0.json) records the source
commit; [build-results.json](build-results.json) records bundle identity and counts.
See [build.md](build.md#revert-a-project-local-update) for rollback instructions.

Development machine: Ubuntu 26.04. Installed stock baseline: `codex-cli 0.161.0`.
Rust toolchain: `1.95.0 (59807616e 2026-04-14)`.

| Check | Observed result |
| --- | --- |
| Standalone Rust controller tests | 11 passed, including immediate constant-speed motion from every starting tier, shortened first ascent, immediate Max descent, and tap-label consistency |
| Standalone Rust capability tests | 1 passed, compiled with Rust 1.95.0 |
| Python patch/build/install workflow tests | 23 passed, including command mapping/restoration, updating a running executable, runtime helper packaging/version checks, and refusing changed inputs during compilation |
| Complete pinned 0.161.0 source / patch application | Obtained; all 22 integration edits rebased; full patch check passed |
| Actual 0.161.0 CLI compilation | Passed for selected-effort start and constant-speed charging; native bundle rebuilt and installed in `local/`; existing `codex` mapping verified against current source and executable checksums |
| 0.161.0 ChargeSend tests | 42 passed: controller 11, capability 1, bar/gradient 2, working indicator 6, app latch 1, composer/request integration 21; queued-turn effort, inline placement, tight-width rendering and UI snapshots verified |
| 0.161.0 upstream regressions | 479 passed: composer 396, Plan mode 63, event stream 10, working status 10 |
| Second release portability | Previous inline-indicator revision: exact 0.160.0 source patched and native CLI built; 510 Rust tests passed. Selected-effort start change not rerun locally; full source unavailable in this session |
| Scoped Clippy on 0.161.0 | Passed for selected-effort start and constant-speed charging with `cargo clippy --locked -p codex-tui --lib --tests`; only the existing app-server warning |
| Scoped Clippy on 0.160.0 | Previous revision passed; not rerun for the inline working indicator |
| Physical Kitty keyboard protocol | Passed in Kitty 0.45.0: flags 15, matching tap/hold releases, 101 repeats |
| Basic physical 0.161.0 composer UI | Passed: bar ascent/descent, Escape retains draft, release after cancellation does not submit |
| Full physical composer UI checklist | Remaining checks pending |
| Native launcher / installation / removal | Version and help passed; actual native bundle installation/removal passed; stock Codex preserved |
| GitHub Actions | Not run as part of this local verification |

The controller tests cover tap/reset starting tiers, initial rise, holding, descending and cycle
boundaries, repeats, exactly-once release, cancellation, context invalidation,
fallback, model-dependent choices, monotonic regression protection, adjustable
timing, and last-painted selection. The capability test requires both flag bits
and the direct-terminal gate.

The Python tests use temporary Git repositories and executable fixtures. They
verify pinned commits, clean-checkout protections, no partial patch on conflict,
prepared-source hashes, argument forwarding, version labels, bundle checksums,
installation/removal, stock command preservation, and a patch edit during a
simulated compilation. They do not compile Codex.

The integration tests use the actual ChatWidget/composer and capture UserTurn
operations with a mock sticky backend. They require no live
model inference. Assertions cover per-request effort, restored defaults, Plan
precedence, image preparation/cancellation, paste, menus, newlines, busy input,
selected-effort tap submission and initial bar snapshots, model-default and supported-tier fallback, gradient endpoints, fixed charge-bar position, active-turn reasoning labels,
queued-turn transitions, restored labels, inline placement, Unicode clipping,
advertised Max availability, Ultra exclusion, and inline rendering snapshots at 8, 24, and 80 columns.
The sticky-backend mock verifies the selected effort and the next prompt's
intended effort, and rejects an immediate settings reset that would disturb
automatic continuations. These assertions exercise submitted AppCommand settings;
they do not perform live model inference or a full HTTP backend round trip.

All twenty-two integration originals come from the complete pinned `0.161.0`
release checkout. [source-provenance.json](source-provenance.json) records the
commit; [source-provenance-0.160.0.json](source-provenance-0.160.0.json) records
the second baseline. [build-results.json](build-results.json) records the final
binary hashes, patch fingerprints, test counts, and lint results.
Patch application alone does not establish compilation or runtime behavior.
Both native development bundles were built from their full pinned release
checkouts, with third-party dependencies locked. The current runtime helpers
were reused from installed official packages matching each baseline exactly;
their origins and checksums are recorded in the bundle manifests. The source
helper build's pinned V8 archive was unavailable at its upstream download URL.
The 0.160.0 source has an
existing unused-import warning in `core/src/tools/registry.rs`; ChargeSend does
not modify that file. The 0.161.0 scoped lint check also reports an existing
app-server `let_and_return` warning outside the patch.

The `cargo clippy --fix` frontend could not bind its local TCP lock listener in
this sandbox. Lint corrections were applied manually, then verified with the
non-mutating scoped Clippy command. The upstream `just`/nextest frontend and
full workspace/Bazel checks were not run; focused Cargo tests and pinned rustfmt
were used as documented in [build.md](build.md).

Record automated and manual checks separately. A compiled binary or a terminal
capability reply does not establish physical key-release delivery.

On 2026-10-08 the user ran the direct-Kitty diagnostic with a physical keyboard.
It observed flags `15` (including event types and all-key reporting), two presses,
two matching releases, an 88 ms tap, and a 3536 ms hold with repeats. The compact
evidence is [kitty-0.45.0-enter.json](kitty-0.45.0-enter.json). This verifies the
terminal transport.

The user then ran the actual compiled 0.161.0 UI in direct Kitty with
`--no-daemon`. Bar ascent/descent and Escape while Enter remained held worked;
releasing Enter afterward retained the draft without submission.
[kitty-0.45.0-ui.json](kitty-0.45.0-ui.json) records the tested binary checksum and
patch fingerprint. The final rebuild additionally separates test modules and
adds snapshots; its normal image path also retains the original upstream wrapper.
Physical release-to-submit, attachment cancellation, fallback terminals, the
remaining full checklist, and 0.160.0 physical UI are outstanding.

The backend's saved thread effort may retain the charged value until the next
request explicitly restores the current widget's intended effort. Restart/resume
and multiple-client synchronization need further verification. See
[architecture.md](architecture.md) for this limitation and notification matching.

The previous inline working-indicator revision passed 519 Rust tests on 0.161.0 and
510 on 0.160.0, with native CLI builds for both. That 0.161.0 bundle was installed
in `local/`. Physical Kitty checks for
the reasoning suffix, fixed bar position, colors and starting effort remain
pending; the older UI evidence does not verify these new behaviors.

On 2026-10-09 the selected-effort starting revision passed all 519 focused Rust
tests on 0.161.0. Tests change Low, High, xHigh, Medium, and Max in one widget,
snapshot each initial bar, and verify each submitted request and retained setting.
They also check the model default when unset, Plan's separate override, supported
tier fallback, and restoration after a charged Low request with High selected.
The native CLI was rebuilt, with launcher/native version, CLI/helper help,
fingerprint, and bundle checksum checks passing. The README animation was
regenerated with Low selected. The CI scoped Clippy command also passed.
Physical Kitty checks for changing the selected
effort between taps have not been repeated. The 0.160.0 results above are historical;
the existing CI matrix still targets both releases.

On 2026-10-12 the constant-speed revision passed 521 focused Rust tests and
the scoped Clippy check on 0.161.0. The first leg now uses the same full-range
speed as later traversals, with no initial motion pause. Starting at Max descends
immediately. The tap window retains the selected label while the bar moves.
Tests verify all starting tiers, turnarounds, tap consistency, and the submitted
and queued-turn efforts. The native CLI and helper startup checks passed, then
the new bundle was installed in `local/`. The existing `~/.local/bin/codex`
mapping resolves to that launcher; installed fingerprints and executable/helper
checksums match the current source. Running sessions must restart to load it.
The physical constant-speed interaction has not been checked in Kitty.
