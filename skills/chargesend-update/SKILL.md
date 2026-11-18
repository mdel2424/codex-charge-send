---
name: chargesend-update
description: "Port, verify and build this ChargeSend repository for a newer Codex CLI release. Use for ChargeSend release upgrades or failures in its update workflow; not for ordinary Codex settings or API questions."
---

# Update ChargeSend

Use the repository's `scripts/port-release.py` pipeline. Run commands from the
repository root; replace `TAG` below with the full `rust-v...` tag reported by
`start`. The installed CLI is independent of the port checkout.

## Stage the release

Inspect the working tree and preserve existing edits. `supported-releases.json`
defines the current baseline. The default target is GitHub's newest stable
release, not a prerelease:

```bash
python3 scripts/port-release.py start --fetch
```

If the newest tag is already the default and the installed bundle's commit,
fingerprint and checksums match, verify the active command and report it current.
Do not rebuild an unchanged release unless the user requested a rebuild or there
is an unresolved failure. Missing pipeline receipts are not proof of passing
checks; never create them from an old README or console recollection.

If the target is specified, use `start --tag TAG --fetch`. This fetches and pins
the full public commit, reads its Rust toolchain, downloads locked dependencies,
and stages the previous patch in `.build/updates/TAG/source`. Re-running it
retains edits. Rejected hunks are a normal porting task; inspect the reported
`.rej` files and staging logs. An interrupted `applying` phase needs inspection,
not another blind patch application.

If the build session cannot download, use an available official release source
to verify the stable tag, then request that same `start --tag TAG --fetch`
command in the user's normal terminal. Continue independent review while it
downloads. Do not generate a one-off fetch script or assume network access can
be obtained by changing execution permissions.

## Port and export

Read applicable upstream `AGENTS.md` files and inspect current integration
points; names and ownership change between releases. Keep the dedicated modules
shared where practical. Release-specific test/API adaptations can live in the
supplementary overlay patch rather than copied module variants.
Edit the staged module copies during a port. If a fix belongs in a shared root
module, synchronize that intentional change into the staged copy as well;
otherwise export correctly records the difference as a release-specific override.

Preserve the established interaction: start at selected model/mode effort;
constant-speed monotonic charging; matching release sends once; cancellation
retains the draft and images. Preserve idle-only eligibility, release draining
across thread/view changes, model-advertised tiers, prompt-local overrides and
Plan-mode consistency. Check new upstream menu, focus, queue and submission
guards before interception. Do not write charge selections to config.

Resolve and remove reviewed `.rej` files. Review snapshot differences before
editing expectations; never enable blanket snapshot acceptance to make a port
pass. Preserve third-party lock pins. Then:

```bash
python3 scripts/port-release.py export --tag TAG
python3 scripts/port-release.py check --tag TAG
```

Export writes the integration patch, any overlay adaptation, and a candidate
catalog entry without changing the default. `export --dry-run` previews it.
Check formats the TUI, exports formatting changes and independently reconstructs
the patch in a fresh temporary checkout. It certifies the editable source only
when the complete diff and module hashes match. It never resets that source or
rewrites unchanged Rust files to refresh a marker.

## Fix failures without starting over

The order is workflow tests, Clippy, test compilation, all focused test filters,
then native packaging/startup checks. The pipeline reports every failing filter
in one pass. Read `.build/updates/TAG/*.log`; the preceding attempt is retained
as `*.previous.log`. Re-run `check` after fixes, using the same checkout and
shared `.build/target` cache. Do not repeatedly clone compiler workspaces,
reverse/reapply patches, or clean caches between lint, tests and packaging.

Use `check --through lint` or `check --through tests` for a shorter iteration.
Successful checks are reused only for matching source, toolchain, flags and
pipeline inputs. External `.snap` changes rerun tests without repeating Clippy;
Rust changes invalidate both. `--force` reruns checks when external conditions
changed. `status --tag TAG` shows the saved session and check receipts.

The local tests use fixed colors, no snapshot writes and an 8 MiB test stack.
HTTP mock tests that require binding localhost run separately in CI. Record a
denied localhost bind as an environment limitation, not a product failure or a
passing test. Existing request-capture/sticky-backend tests need no live model.
If integration changes extend beyond the TUI, extend the scoped checks before
claiming that the additional crate is verified.

## Finish

```bash
python3 scripts/port-release.py promote --tag TAG
```

Promotion requires current lint, test and bundle receipts and fresh native
startup/checksum checks. It changes the default and removes managed compiled
caches. `--keep-build-cache` opts into faster later builds at the cost of disk
space. Failures and intermediate checks retain the cache automatically.

Update README examples, provenance and verification records using the pinned
commit, current manifest and logs. Distinguish local checks from remote CI,
physical Kitty and live Cloud checks. The CI matrix and Rust version come from
the catalog, so do not hand-maintain another tag list.

Use `python3 scripts/update-local.py` to activate the verified bundle when
installation is within the user's request and filesystem permissions permit.
If `~/.local` is read-only to the session, finish the build first, then provide
that one normal-terminal command. Verify the actual command mapping, version,
fingerprint and checksums afterward. Retain stock backups and tell the user to
quit and reopen Codex. Do not publish or push unless requested.
