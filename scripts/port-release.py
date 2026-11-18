#!/usr/bin/env python3
"""Stage, export, verify and promote a ChargeSend release without rebuilding unchanged inputs."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import tempfile
import tomllib
from urllib.request import Request, urlopen

import chargesend as workflow


def tag_name(value: str) -> str:
    if not re.fullmatch(r"rust-v\d+\.\d+\.\d+", value):
        raise workflow.Failure(f"Expected a stable release tag, got {value!r}.")
    return value


def latest_tag() -> str:
    request = Request("https://api.github.com/repos/openai/codex/releases/latest", headers={"User-Agent": "ChargeSend"})
    with urlopen(request, timeout=20) as response:
        release = json.load(response)
    if release.get("draft") or release.get("prerelease"):
        raise workflow.Failure("Latest-release response is not a stable public release.")
    return tag_name(release["tag_name"])


def save(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(value, stream, indent=2)
        stream.write("\n")
    temporary.replace(path)


def git(source: Path, *arguments: str) -> str:
    return workflow.run(["git", "-c", "core.fsmonitor=false", *arguments], cwd=source, capture=True)


def diff(source: Path, *arguments: str) -> str:
    # Patch hunks can end with blank context lines; run() deliberately strips
    # ordinary command output, so preserve Git's exact bytes here.
    return subprocess.check_output(["git", "-c", "core.fsmonitor=false", "diff", "--no-ext-diff",
                                    "--no-color", "--binary", "HEAD", *arguments], cwd=source).decode()


def update_dir(tag: str) -> Path:
    directory = workflow.ROOT / ".build/updates" / tag_name(tag)
    for path in [directory.parent.parent, directory.parent, directory, directory / "source"]:
        if path.is_symlink():
            raise workflow.Failure(f"Refusing to manage a symlinked update path: {path}")
    return directory


def session(tag: str) -> dict:
    path = update_dir(tag) / "session.json"
    if not path.exists():
        raise workflow.Failure(f"No managed port for {tag}; run start first.")
    state = json.loads(path.read_text())
    source = update_dir(tag) / "source"
    if state["tag"] != tag or git(source, "rev-parse", "HEAD") != state["commit"]:
        raise workflow.Failure("Port checkout no longer matches its pinned session. No files changed.")
    return state


def start(tag: str, base_tag: str | None, fetch: bool) -> None:
    if base_tag:
        workflow.release(base_tag)
    directory = update_dir(tag)
    state_file = directory / "session.json"
    if state_file.exists():
        state = session(tag)
        if base_tag and base_tag != state["base"]:
            raise workflow.Failure("Existing session uses a different patch baseline; its edits were retained.")
        print(f"Resuming {directory}; existing edits retained.")
    else:
        if (directory / "source").exists():
            raise workflow.Failure(f"{directory / 'source'} already exists without a session; refusing to overwrite it.")
        cache = workflow.ROOT / ".build/upstream" / tag
        if tag in workflow.CATALOG["releases"]:
            cache = workflow.checkout(tag, None)
        else:
            if not cache.exists():
                cache.mkdir(parents=True)
                workflow.run(["git", "init", "--quiet", str(cache)])
                workflow.run(["git", "remote", "add", "origin", workflow.CATALOG["upstream"]], cwd=cache)
            elif not (cache / ".git").is_dir():
                raise workflow.Failure(f"{cache} is not a dedicated Git checkout; no files changed.")
            if git(cache, "remote", "get-url", "origin") != workflow.CATALOG["upstream"]:
                raise workflow.Failure("Cached checkout has an unexpected origin; refusing to fetch.")
            # Fetch the named tag before pinning it; never infer a full SHA from a prefix.
            workflow.run(["git", "fetch", "--depth=1", "origin", f"refs/tags/{tag}"], cwd=cache)
            commit = git(cache, "rev-parse", "FETCH_HEAD^{commit}")
            try:
                existing = git(cache, "rev-parse", "HEAD")
            except workflow.Failure:
                existing = None
            if existing and existing != commit:
                raise workflow.Failure(f"{cache} already has a different HEAD; no checkout was reset.")
            if existing is None:
                workflow.run(["git", "checkout", "--detach", "--quiet", "FETCH_HEAD"], cwd=cache)
        commit = git(cache, "rev-parse", "HEAD")
        source = directory / "source"
        directory.mkdir(parents=True, exist_ok=True)
        workflow.run(["git", "-c", "core.fsmonitor=false", "clone", "--quiet", "--shared", str(cache), str(source)])
        toolchain = tomllib.loads((source / "codex-rs/rust-toolchain.toml").read_text())["toolchain"]["channel"]
        workflow.align_workspace_lock(source)
        state = {"tag": tag, "commit": commit, "rust": toolchain,
                 "base": base_tag or (tag if tag in workflow.CATALOG["releases"] else workflow.CATALOG["default"]),
                 "lock_sha256": workflow.sha256(source / "codex-rs/Cargo.lock"), "phase": "fetching"}
        save(state_file, state)
    source = directory / "source"
    if fetch:
        workflow.run(["cargo", "fetch", "--locked"], cwd=source / "codex-rs")
    if state["phase"] == "fetching":
        collisions = [target for target in workflow.OVERLAYS.values() if (source / target).exists()]
        if collisions:
            raise workflow.Failure(f"Upstream contains overlay targets: {collisions}. No patch applied.")
        state["phase"] = "applying"
        save(state_file, state)
        patches = [workflow.patch_for(state["base"])]
        for origin, target in workflow.OVERLAYS.items():
            destination = source / target
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((workflow.ROOT / origin).read_bytes())
        if overlay := workflow.overlay_patch_for(state["base"]):
            patches.append(overlay)
        for patch in patches:
            result = subprocess.run(["git", "-c", "core.fsmonitor=false", "apply", "--reject", str(patch)], cwd=source, text=True, capture_output=True)
            (directory / f"{patch.name}.log").write_text(result.stdout + result.stderr)
            if result.returncode not in (0, 1):
                raise workflow.Failure(f"Cannot stage {patch}: {result.stderr}")
        state["phase"] = "editing"
        save(state_file, state)
    rejects = [str(path.relative_to(source)) for path in source.rglob("*.rej")]
    print(json.dumps({**state, "source": str(source), "rejected_hunks": rejects}, indent=2))
    print("Review upstream AGENTS.md files and the rebased hooks. Resolve .rej files, then export and check.")


def export(tag: str, dry_run: bool = False) -> None:
    state = session(tag)
    source = update_dir(tag) / "source"
    allowed = set(workflow.OVERLAYS.values()) | {".chargesend-applied.json"}
    extras = set(git(source, "ls-files", "--others", "--exclude-standard").splitlines()) - allowed
    if extras:
        raise workflow.Failure(f"Unexported files (resolve rejects/snapshots or add modules to overlays.json): {sorted(extras)}")
    if workflow.sha256(source / "codex-rs/Cargo.lock") != state["lock_sha256"]:
        raise workflow.Failure("Cargo.lock changed beyond the recorded local-version alignment; review it before export.")
    if git(source, "diff", "--name-only", "--diff-filter=D", "HEAD"):
        raise workflow.Failure("Deleting upstream files is not supported by the prepared-source verifier.")
    if git(source, "ls-files", "--unmerged"):
        raise workflow.Failure("Unmerged files remain; resolve them before export.")
    primary = diff(source, "--", ".", ":(exclude)codex-rs/Cargo.lock")
    if not primary:
        raise workflow.Failure("No integration changes to export.")
    primary_path = workflow.ROOT / "patches" / f"chargesend-{tag.removeprefix('rust-v')}.patch"
    overlay_changes = []
    for origin, target in workflow.OVERLAYS.items():
        overlay_changes.extend(difflib.unified_diff(
            (workflow.ROOT / origin).read_text().splitlines(keepends=True),
            (source / target).read_text().splitlines(keepends=True), fromfile=f"a/{target}", tofile=f"b/{target}"))
    if dry_run:
        print(f"Would export {len(primary.encode())} integration bytes and {len(overlay_changes)} overlay-diff lines to {primary_path}.")
        return
    previous_fingerprint = workflow.fingerprint(tag) if tag in workflow.CATALOG["releases"] else None
    primary_path.parent.mkdir(parents=True, exist_ok=True)
    primary_path.write_text(primary)
    entry = {**workflow.CATALOG["releases"].get(tag, {}), "commit": state["commit"], "rust": state["rust"],
             "patch": str(primary_path.relative_to(workflow.ROOT))}
    if overlay_changes:
        overlay_path = primary_path.with_name(primary_path.stem + "-overlays.patch")
        overlay_path.write_text("".join(overlay_changes))
        entry["overlay_patch"] = str(overlay_path.relative_to(workflow.ROOT))
    else:
        entry.pop("overlay_patch", None)
    workflow.CATALOG["releases"][tag] = entry
    if previous_fingerprint != workflow.fingerprint(tag):
        entry.update(development=True, status="candidate exported; verification pending")
    save(workflow.ROOT / "supported-releases.json", workflow.CATALOG)
    print(f"Exported {primary_path}; default release remains {workflow.CATALOG['default']}.")


def certify(tag: str) -> Path:
    """Reconstruct exported inputs independently, then certify the untouched development tree."""
    session(tag)
    source = update_dir(tag) / "source"
    with tempfile.TemporaryDirectory(prefix="chargesend-proof-") as directory:
        witness = Path(directory) / "source"
        workflow.run(["git", "-c", "core.fsmonitor=false", "clone", "--quiet", "--shared", str(source), str(witness)], capture=True)
        workflow.apply_to(witness, tag)
        # A complete tracked diff covers local lock alignment, modes and integration files.
        if diff(source) != diff(witness):
            raise workflow.Failure("Development checkout differs from the independently prepared patch. Export again.")
        actual = set(git(source, "ls-files", "--others", "--exclude-standard").splitlines())
        if actual - {".chargesend-applied.json"} != set(workflow.OVERLAYS.values()):
            raise workflow.Failure("Unexpected development files; certification refused.")
        stamp = json.loads((witness / ".chargesend-applied.json").read_text())
        for name, digest in stamp["files"].items():
            if not (source / name).is_file() or workflow.sha256(source / name) != digest:
                raise workflow.Failure(f"Development content differs from the exported patch: {name}")
        # Only the marker changes. Rust source mtimes and the compiler cache stay intact.
        save(source / ".chargesend-applied.json", stamp)
    workflow.apply_to(source, tag)
    return source


def logged_run(log_path: Path, arguments: list[str], *, cwd: Path | None = None, capture: bool = False,
               env: dict[str, str] | None = None) -> str:
    if capture:
        return workflow.run(arguments, cwd=cwd, capture=True, env=env)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Running {shlex.join(arguments)} — {log_path}", flush=True)
    with log_path.open("a") as log:
        log.write(f"\n$ {shlex.join(arguments)}\n")
        with subprocess.Popen(arguments, cwd=cwd, env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, start_new_session=True) as process:
            try:
                for line in process.stdout:
                    print(line, end="", flush=True)
                    log.write(line)
                    log.flush()
                status = process.wait()
            except BaseException:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                except ProcessLookupError:
                    pass
                raise
    if status:
        raise workflow.Failure(f"{shlex.join(arguments)} failed ({status}); output saved in {log_path}.")
    return ""


def identities(source: Path, tag: str) -> tuple[str, str]:
    workflow.apply_to(source, tag)
    files = json.loads((source / ".chargesend-applied.json").read_text())["files"]
    environment = {name: value for name, value in os.environ.items()
                   if name.startswith(("CARGO_PROFILE_", "CARGO_FEATURE_")) or name in
                   {"RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "RUSTC", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "RUST_MIN_STACK", "CC", "CXX", "CFLAGS", "CXXFLAGS", "CARGO_BUILD_TARGET"}
                   or (name.startswith("CARGO_TARGET_") and name.endswith("_RUSTFLAGS"))}
    common = {"commit": workflow.release(tag)["commit"], "source": str(source.resolve()), "compiler": workflow.run(["rustc", "-vV"], cwd=source / "codex-rs", capture=True),
              "clippy": workflow.run(["cargo", "clippy", "--version"], cwd=source / "codex-rs", capture=True),
              "pipeline": workflow.sha256(Path(__file__)), "workflow": workflow.sha256(workflow.ROOT / "scripts/chargesend.py"),
              "environment": environment, "filters": workflow.focused_test_filters(source)}
    def digest(include_snapshots):
        return hashlib.sha256(json.dumps({**common, "files": {name: value for name, value in files.items()
                                  if include_snapshots or not name.endswith(".snap")}}, sort_keys=True).encode()).hexdigest()
    return digest(False), digest(True)


def smoke(bundle: Path, tag: str) -> None:
    metadata = workflow.validated_bundle(bundle)
    if metadata["upstream_commit"] != workflow.release(tag)["commit"] or metadata["patch_fingerprint"] != workflow.fingerprint(tag):
        raise workflow.Failure("Bundle does not match the current pinned patch.")
    version = workflow.run([str(bundle / "chargesend-cli"), "--version"], capture=True)
    if version != f"codex-cli {tag.removeprefix('rust-v')}":
        raise workflow.Failure(f"Unexpected native version: {version}")
    help_text = workflow.run([str(bundle / "chargesend-cli"), "--help"], capture=True)
    if re.search(r"(?m)^\s+exec-server(?:\s|$)", help_text):
        workflow.run([str(bundle / "chargesend-cli"), "exec-server", "--help"], capture=True)
    workflow.run([str(bundle / "codex-code-mode-host"), "--help"], capture=True)


def fresh_log(path: Path) -> None:
    if path.exists():
        path.replace(path.with_suffix(".previous.log"))


def check(tag: str, through: str = "bundle", force: bool = False) -> None:
    directory = update_dir(tag)
    fresh_log(directory / "format.log")
    if (directory / "session.json").exists():
        session(tag)
        source = directory / "source"
        # Format the changed crate before export; no reset, copy or mtime manipulation.
        logged_run(directory / "format.log", ["cargo", "fmt", "-p", "codex-tui"], cwd=source / "codex-rs")
        export(tag)
        source = certify(tag)
    else:
        source = workflow.prepare(argparse.Namespace(tag=tag, source=None))
        logged_run(directory / "format.log", ["cargo", "fmt", "--all"], cwd=source / "codex-rs")
        workflow.record_prepared_files(source)
    workflow.prerequisites(tag)
    workspace = source / "codex-rs"
    fresh_log(directory / "workflow.log")
    logged_run(directory / "workflow.log", [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests"], cwd=workflow.ROOT)
    code_key, test_key = identities(source, tag)
    receipt_path = directory / "checks.json"
    receipts = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
    def unchanged():
        if identities(source, tag) != (code_key, test_key):
            raise workflow.Failure("Inputs changed while checking; no successful receipt saved.")
    def run_stage(name, key, action):
        if not force and receipts.get(name, {}).get("key") == key:
            unchanged()
            print(f"Reusing successful {name} check.")
            return
        receipts.pop(name, None)
        save(receipt_path, receipts)
        fresh_log(directory / f"{name}.log")
        action()
        unchanged()
        receipts[name] = {"key": key}
        save(receipt_path, receipts)
    run_stage("lint", code_key, lambda: logged_run(directory / "lint.log", ["cargo", "clippy", "--locked", "-p", "codex-tui", "--lib", "--tests"], cwd=workspace))
    if through == "lint":
        return
    def tests():
        test_log = directory / "tests.log"
        environment = workflow.test_environment()
        # Catch compile errors once, then collect every failing filter in one pass.
        logged_run(test_log, ["cargo", "test", "--locked", "-p", "codex-tui", "--lib", "--no-run"], cwd=workspace, env=environment)
        failures = []
        for selected in workflow.focused_test_filters(source):
            try:
                logged_run(test_log, ["cargo", "test", "--locked", "-p", "codex-tui", "--lib", selected], cwd=workspace, env=environment)
            except workflow.Failure:
                failures.append(selected)
        if failures:
            raise workflow.Failure(f"Failing test filters: {', '.join(failures)}. Review {test_log}; cache retained.")
    run_stage("tests", test_key, tests)
    if through == "tests":
        return
    bundle_key = hashlib.sha256((test_key + workflow.fingerprint(tag)).encode()).hexdigest()
    previous = receipts.get("bundle", {})
    if not force and previous.get("key") == bundle_key and previous.get("path"):
        try:
            smoke(workflow.ROOT / previous["path"], tag)
        except workflow.Failure:
            pass
        else:
            unchanged()
            print("Reusing verified bundle.")
            return
    receipts.pop("bundle", None)
    save(receipt_path, receipts)
    fresh_log(directory / "bundle.log")
    def runner(arguments, **kwargs):
        return logged_run(directory / "bundle.log", arguments, **kwargs)
    bundle = workflow.bundle(source, tag, "dev", runner=runner)
    smoke(bundle, tag)
    if identities(source, tag) != (code_key, test_key):
        raise workflow.Failure("Inputs changed during packaging; bundle has no verification receipt.")
    receipts["bundle"] = {"key": bundle_key, "path": str(bundle.relative_to(workflow.ROOT))}
    save(receipt_path, receipts)
    print(f"Verified {bundle}. Cache retained until promotion or explicit cleanup.")


def promote(tag: str, keep_cache: bool) -> None:
    directory = update_dir(tag)
    source = directory / "source" if (directory / "session.json").exists() else workflow.ROOT / ".build/upstream" / tag
    code_key, test_key = identities(source, tag)
    path = directory / "checks.json"
    receipts = json.loads(path.read_text()) if path.exists() else {}
    expected = {"lint": code_key, "tests": test_key, "bundle": hashlib.sha256((test_key + workflow.fingerprint(tag)).encode()).hexdigest()}
    if any(receipts.get(name, {}).get("key") != key for name, key in expected.items()):
        raise workflow.Failure("Current inputs have not passed every check; run check before promotion.")
    bundle = workflow.ROOT / receipts["bundle"]["path"]
    smoke(bundle, tag)
    if identities(source, tag) != (code_key, test_key):
        raise workflow.Failure("Inputs changed during final startup checks; default release unchanged.")
    workflow.CATALOG["default"] = tag
    workflow.CATALOG["releases"][tag].update(development=False, status="native bundle, focused tests and Clippy verified; physical terminal and remote CI results recorded separately")
    save(workflow.ROOT / "supported-releases.json", workflow.CATALOG)
    print(f"Promoted {tag}. Update README/verification records from {directory}; installation remains a separate step.")
    if not keep_cache and Path(os.environ["CARGO_TARGET_DIR"]) == workflow.ROOT / ".build/target":
        workflow.clean_build_cache()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    begin = commands.add_parser("start", help="fetch/pin a release and stage a reusable development checkout")
    begin.add_argument("--tag", help="stable tag; otherwise resolve GitHub's latest stable release")
    begin.add_argument("--from-tag", help="patch baseline; defaults to this tag when supported, otherwise the current default")
    begin.add_argument("--fetch", action="store_true", help="download locked Cargo dependencies (also useful for a single normal-terminal handoff)")
    for name in ["export", "check", "promote", "status"]:
        sub = commands.add_parser(name)
        sub.add_argument("--tag", default=workflow.CATALOG["default"])
        if name == "check":
            sub.add_argument("--through", choices=["lint", "tests", "bundle"], default="bundle")
            sub.add_argument("--force", action="store_true", help="rerun checks even when their input receipts match")
        if name == "export":
            sub.add_argument("--dry-run", action="store_true")
        if name == "promote":
            sub.add_argument("--keep-build-cache", action="store_true")
    args = parser.parse_args()
    os.environ["PATH"] = str(Path.home() / ".cargo/bin") + os.pathsep + os.environ.get("PATH", "")
    os.environ.setdefault("CARGO_HOME", str(workflow.ROOT / ".build/cargo"))
    os.environ.setdefault("CARGO_BUILD_JOBS", "4")
    os.environ.setdefault("RUST_MIN_STACK", "8388608")
    workflow.configure_cargo()
    try:
        tag = tag_name(args.tag or latest_tag())
        with workflow.build_cache_lock():
            if args.command == "start":
                start(tag, args.from_tag, args.fetch)
            elif args.command == "export":
                export(tag, args.dry_run)
            elif args.command == "check":
                check(tag, args.through, args.force)
            elif args.command == "promote":
                promote(tag, args.keep_build_cache)
            else:
                directory = update_dir(tag)
                print(json.dumps({name: json.loads((directory / name).read_text()) for name in ["session.json", "checks.json"] if (directory / name).exists()}, indent=2))
    except (workflow.Failure, OSError, ValueError) as error:
        print(f"ChargeSend update: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Update interrupted; logs, source and cache retained.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    def interrupted(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    raise SystemExit(main())
