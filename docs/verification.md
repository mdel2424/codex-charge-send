# Verification record

Development machine: Ubuntu 26.04. Installed stock baseline: `codex-cli 0.161.0`.
Rust toolchain: `1.95.0 (59807616e 2026-04-14)`.

| Check | Observed result |
| --- | --- |
| Standalone Rust controller tests | 9 passed, compiled with Rust 1.95.0 |
| Standalone Rust capability tests | 1 passed, compiled with Rust 1.95.0 |
| Python patch/build/install workflow tests | 21 passed, including command mapping/restoration, updating a running executable, runtime helper packaging/version checks, and refusing changed inputs during compilation |
| Complete pinned 0.161.0 source / patch application | Obtained; all 20 integration edits rebased; full patch check passed |
| Actual 0.161.0 CLI compilation | Passed; versioned native development bundle produced and installed as `local/bin/chargesend` |
| 0.161.0 ChargeSend tests | 31 passed: controller 9, capability 1, gradient 1, app latch 1, composer/request integration 19; Extra High tap and Max peak submit without changing saved effort |
| 0.161.0 upstream regressions | 469 passed: composer 396, Plan mode 63, event stream 10 |
| Second release portability | Exact 0.160.0 source patched and native CLI built; 491 Rust tests passed: ChargeSend 31, composer 387, Plan mode 63, event stream 10 |
| Scoped Clippy on 0.161.0 | Previous revision passed; not rerun for the default/gradient change |
| Scoped Clippy on 0.160.0 | Previous revision passed; not rerun for the default/gradient change |
| Physical Kitty keyboard protocol | Passed in Kitty 0.45.0: flags 15, matching tap/hold releases, 101 repeats |
| Basic physical 0.161.0 composer UI | Passed: bar ascent/descent, Escape retains draft, release after cancellation does not submit |
| Full physical composer UI checklist | Remaining checks pending |
| Native launcher / installation / removal | Version and help passed; actual native bundle installation/removal passed; stock Codex preserved |
| GitHub Actions | Prepared locally; not run or published |

The controller tests cover configured tap/reset defaults, initial rise, holding, descending and cycle
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
Extra High tap submission, supported-default fallback, gradient endpoints,
advertised Max availability, Ultra exclusion, and inline rendering snapshots at 8, 24, and 80 columns.
The sticky-backend mock verifies the selected effort and the next prompt's
intended effort, and rejects an immediate settings reset that would disturb
automatic continuations. These assertions exercise submitted AppCommand settings;
they do not perform live model inference or a full HTTP backend round trip.

All twenty integration originals come from the complete pinned `0.161.0`
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

The default/gradient revision passes automated tests. Its physical Kitty color
and starting-effort checks remain pending; the older UI evidence does not
verify these new behaviors.
