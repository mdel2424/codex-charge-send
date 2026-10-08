#!/usr/bin/env python3
"""Fetch a pinned release, apply ChargeSend, test/build, and install independently.

No destructive checkout/reset, publishing, authentication, or config mutation.
Third-party Cargo.lock entries are retained, and dependency commands use --locked.
Release tags bump workspace versions without updating their local lock entries;
only those local versions are aligned. A failed patch check leaves the supplied
checkout untouched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / "supported-releases.json").read_text())
OVERLAYS = json.loads((ROOT / "overlays.json").read_text())
VERSION = (ROOT / "VERSION").read_text().strip()
PATCH = ROOT / "patches/chargesend.patch"
MARKER = "# ChargeSend managed launcher"


class Failure(Exception):
    pass


def run(args: list[str], cwd: Path | None = None, capture: bool = False) -> str:
    try:
        result = subprocess.run(
            args, cwd=cwd, check=True, text=True,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
        )
    except FileNotFoundError as error:
        raise Failure(f"Missing executable {args[0]}. See docs/build.md.") from error
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "").strip()
        raise Failure(f"Command failed: {shlex.join(args)}\n{detail}") from error
    return result.stdout.strip() if capture else ""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def patch_for(tag: str | None = None) -> Path:
    entry = CATALOG["releases"].get(tag or CATALOG["default"], {})
    return ROOT / entry["patch"] if entry.get("patch") else PATCH


def fingerprint(tag: str | None = None) -> str:
    digest = hashlib.sha256(patch_for(tag).read_bytes())
    digest.update((ROOT / "overlays.json").read_bytes())
    for source, target in sorted(OVERLAYS.items()):
        digest.update(target.encode())
        digest.update((ROOT / source).read_bytes())
    return digest.hexdigest()


def release(tag: str) -> dict:
    try:
        return CATALOG["releases"][tag]
    except KeyError as error:
        raise Failure(f"Unlisted release {tag!r}. Port and add it to supported-releases.json first.") from error


def checkout(tag: str, supplied: str | None) -> Path:
    baseline = release(tag)
    source = Path(supplied).expanduser().resolve() if supplied else ROOT / ".build/upstream" / tag
    if not source.exists():
        source.mkdir(parents=True)
        run(["git", "init", "--quiet", str(source)])
        run(["git", "remote", "add", "origin", CATALOG["upstream"]], cwd=source)
    try:
        head = run(["git", "rev-parse", "HEAD"], cwd=source, capture=True)
    except Failure:
        if any(source.iterdir()) and not (source / ".git").exists():
            raise Failure(f"{source} is not a Git checkout; use a fresh directory.")
        run(["git", "fetch", "--depth=1", "origin", f"refs/tags/{tag}"], cwd=source)
        fetched = run(["git", "rev-parse", "FETCH_HEAD^{commit}"], cwd=source, capture=True)
        if fetched != baseline["commit"]:
            raise Failure(f"Tag {tag} resolved to {fetched}, expected {baseline['commit']}; stopping.")
        run(["git", "checkout", "--detach", "--quiet", "FETCH_HEAD"], cwd=source)
        head = fetched
    if head != baseline["commit"]:
        raise Failure(f"{source} has HEAD {head}; expected {tag} ({baseline['commit']}). No checkout was reset.")
    if not (source / "codex-rs/Cargo.lock").is_file():
        raise Failure(f"{source} is incomplete. A full release checkout, including Cargo.lock, is required.")
    return source


def apply_to(source: Path, tag: str) -> None:
    stamp = source / ".chargesend-applied.json"
    identity = {"tag": tag, "fingerprint": fingerprint(tag), "workspace_lock_alignment": 1}
    if stamp.exists():
        saved = json.loads(stamp.read_text())
        if any(saved.get(key) != value for key, value in identity.items()):
            raise Failure("This checkout has a different ChargeSend patch. Use a fresh --source directory.")
        recorded = saved.get("files", {})
        changed = set(run(["git", "diff", "--name-only", "HEAD"], cwd=source, capture=True).splitlines())
        untracked = set(run(["git", "ls-files", "--others", "--exclude-standard"], cwd=source, capture=True).splitlines())
        if (changed | untracked) - set(recorded) - {stamp.name}:
            raise Failure("Prepared checkout has additional edits. Use a fresh --source directory.")
        if any(not (source / path).is_file() or sha256(source / path) != digest for path, digest in recorded.items()):
            raise Failure("Prepared ChargeSend sources were edited. Use a fresh --source directory.")
        return
    if run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=source, capture=True):
        raise Failure("Upstream checkout is dirty; refusing to overwrite it. Use a fresh --source directory.")
    for target in OVERLAYS.values():
        if (source / target).exists():
            raise Failure(f"Overlay conflict: upstream already contains {target}.")
    try:
        run(["git", "apply", "--check", str(patch_for(tag))], cwd=source, capture=True)
    except Failure as error:
        raise Failure(f"ChargeSend patch conflicts with {tag}. No patch was applied.\n{error}") from error
    run(["git", "apply", str(patch_for(tag))], cwd=source)
    align_workspace_lock(source)
    for origin, target in OVERLAYS.items():
        destination = source / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / origin, destination)
    stamp.write_text(json.dumps(identity, indent=2) + "\n")
    record_prepared_files(source)


def align_workspace_lock(source: Path) -> int:
    """Align release-local versions without re-resolving any third-party crate."""
    workspace = source / "codex-rs"
    manifest = tomllib.loads((workspace / "Cargo.toml").read_text())
    version = manifest.get("workspace", {}).get("package", {}).get("version")
    if not version:
        return 0
    inherited = set()
    for path in workspace.rglob("Cargo.toml"):
        package = tomllib.loads(path.read_text()).get("package", {})
        if package.get("version") == {"workspace": True}:
            inherited.add(package["name"])
    lock = workspace / "Cargo.lock"
    original = lock.read_text()
    blocks = original.split("[[package]]")
    changes = 0
    for index in range(1, len(blocks)):
        package = tomllib.loads("[[package]]" + blocks[index])["package"][0]
        if "source" not in package and package["name"] in inherited and package["version"] != version:
            blocks[index], count = re.subn(r'^version = "[^"]+"$', f'version = "{version}"', blocks[index], count=1, flags=re.MULTILINE)
            if count != 1:
                raise Failure(f"Cannot align local lock entry {package['name']}.")
            changes += count
    updated = "[[package]]".join(blocks)
    before = tomllib.loads(original)
    after = tomllib.loads(updated)
    if [p for p in before.get("package", []) if "source" in p] != [p for p in after.get("package", []) if "source" in p]:
        raise Failure("Lock alignment changed third-party dependencies; refusing to write it.")
    if changes:
        lock.write_text(updated)
        print(f"Aligned {changes} local workspace lock versions to {version}; third-party pins unchanged.", flush=True)
    return changes


def record_prepared_files(source: Path) -> None:
    stamp = source / ".chargesend-applied.json"
    saved = json.loads(stamp.read_text())
    changed = run(["git", "diff", "--name-only", "HEAD"], cwd=source, capture=True).splitlines()
    saved["files"] = {path: sha256(source / path) for path in set(changed) | set(OVERLAYS.values())}
    stamp.write_text(json.dumps(saved, indent=2, sort_keys=True) + "\n")


def prerequisites(tag: str) -> None:
    missing = [name for name in ["git", "cargo", "rustc", "rustfmt", "cc", "cmake", "pkg-config"] if not shutil.which(name)]
    if missing:
        raise Failure(f"Missing build tools: {', '.join(missing)}. Run scripts/setup-ubuntu.sh from your normal terminal. Rust {release(tag)['rust']} is required.")


def prepare(args: argparse.Namespace) -> Path:
    source = checkout(args.tag, args.source)
    apply_to(source, args.tag)
    print(f"Applied ChargeSend {VERSION} to {args.tag} at {source}")
    return source


def test_source(source: Path) -> None:
    workspace = source / "codex-rs"
    # Format using the upstream-pinned rustfmt, rather than a different host
    # formatter. This also parses every patched module before compilation.
    run(["cargo", "fmt", "--all"], cwd=workspace)
    record_prepared_files(source)
    run(["cargo", "fmt", "--all", "--", "--check"], cwd=workspace)
    for filter_name in ["chargesend_", "bottom_pane::chat_composer", "chatwidget::tests::plan_mode", "tui::event_stream::tests"]:
        run(["cargo", "test", "--locked", "-p", "codex-tui", "--lib", filter_name], cwd=workspace)


def write_launcher(destination: Path, version: str, tag: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    version_label = f"ChargeSend {version} (unofficial Codex {tag.removeprefix('rust-v')})"
    destination.write_text(
        "#!/bin/sh\n" + MARKER + "\n"
        'if [ "$#" -eq 1 ] && { [ "$1" = "--version" ] || [ "$1" = "--chargesend-version" ]; }; then\n'
        f"  printf '%s\\n' {shlex.quote(version_label)}\n"
        "  exit 0\nfi\n"
        'bundle_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd) || exit 1\n'
        'exec "$bundle_dir/chargesend-cli" "$@"\n'
    )
    destination.chmod(0o755)


def bundle(source: Path, tag: str, profile: str) -> Path:
    cargo_manifest = tomllib.loads((source / "codex-rs/cli/Cargo.toml").read_text())
    package_name = cargo_manifest["package"]["name"]
    if not any(binary.get("name") == "codex" for binary in cargo_manifest.get("bin", [])):
        raise Failure("Upstream CLI binary layout changed. Inspect cli/Cargo.toml before porting.")
    workspace = source / "codex-rs"
    run(["cargo", "build", "--locked", "-p", package_name, "--bin", "codex", "--profile", profile], cwd=workspace)
    target_triple = next(line.removeprefix("host: ") for line in run(["rustc", "-vV"], cwd=workspace, capture=True).splitlines() if line.startswith("host: "))
    build_id = f"chargesend-{VERSION}-codex-{tag.removeprefix('rust-v')}-{target_triple}-{profile}"
    destination = ROOT / "dist" / build_id
    destination.mkdir(parents=True, exist_ok=True)
    target_directory = Path(os.environ.get("CARGO_TARGET_DIR", workspace / "target"))
    if not target_directory.is_absolute():
        target_directory = workspace / target_directory
    binary = target_directory / ("debug" if profile == "dev" else profile) / "codex"
    shutil.copyfile(binary, destination / "chargesend-cli")
    (destination / "chargesend-cli").chmod(0o755)
    for notice in ["LICENSE", "NOTICE", "UPSTREAM-NOTICE"]:
        shutil.copyfile(ROOT / notice, destination / notice)
    write_launcher(destination / "bin/chargesend", VERSION, tag)
    metadata = {
        "product": "ChargeSend", "version": VERSION,
        "upstream_tag": tag, "upstream_commit": release(tag)["commit"],
        "patch_fingerprint": fingerprint(tag), "profile": profile,
        "target": target_triple, "rustc": run(["rustc", "--version"], cwd=workspace, capture=True),
        "cargo_lock_sha256": sha256(workspace / "Cargo.lock"),
        "upstream_cargo_lock_sha256": hashlib.sha256(subprocess.check_output(["git", "show", "HEAD:codex-rs/Cargo.lock"], cwd=source)).hexdigest(),
        "lock_adjustment": "only inherited local workspace package versions aligned; third-party pins unchanged",
        "binary_sha256": sha256(destination / "chargesend-cli"),
        "checks": "ChargeSend, composer, Plan-mode, and event-stream Rust tests passed",
        "physical_keyboard_check": "not performed by build script",
    }
    (destination / "manifest.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"Built {destination}\nRun {destination / 'bin/chargesend'}")
    return destination


def build(args: argparse.Namespace) -> None:
    prerequisites(args.tag)
    source = prepare(args)
    test_source(source)
    bundle(source, args.tag, args.profile)


def validated_bundle(path: Path) -> dict:
    try:
        metadata = json.loads((path / "manifest.json").read_text())
        if metadata["product"] != "ChargeSend" or metadata["binary_sha256"] != sha256(path / "chargesend-cli"):
            raise Failure("Bundle product or binary checksum does not match its manifest.")
        return metadata
    except (OSError, KeyError, ValueError) as error:
        raise Failure(f"{path} is not a completed ChargeSend build bundle.") from error


def install(args: argparse.Namespace) -> None:
    source = Path(args.bundle).expanduser().resolve()
    validated_bundle(source)
    prefix = Path(args.prefix).expanduser().resolve()
    command = prefix / "bin/chargesend"
    if (command.exists() or command.is_symlink()) and (command.is_symlink() or not command.is_file() or MARKER.encode() not in command.read_bytes()[:256]):
        raise Failure(f"{command} already exists and is not a managed ChargeSend launcher.")
    destination = prefix / "lib/chargesend" / source.name
    if destination.exists():
        validated_bundle(destination)
    shutil.copytree(source, destination, dirs_exist_ok=True)
    command.parent.mkdir(parents=True, exist_ok=True)
    command.write_text("#!/bin/sh\n" + MARKER + "\n" + f"exec {shlex.quote(str(destination / 'bin/chargesend'))} \"$@\"\n")
    command.chmod(0o755)
    print(f"Installed {command}. Stock codex and its configuration were not changed.")


def uninstall(args: argparse.Namespace) -> None:
    prefix = Path(args.prefix).expanduser().resolve()
    command = prefix / "bin/chargesend"
    if command.exists() or command.is_symlink():
        if command.is_symlink() or not command.is_file() or MARKER.encode() not in command.read_bytes()[:256]:
            raise Failure(f"Refusing to remove unmanaged {command}.")
        command.unlink()
    library = prefix / "lib/chargesend"
    if library.exists():
        for path in library.iterdir():
            if path.is_dir() and not path.is_symlink():
                try:
                    validated_bundle(path)
                except Failure:
                    continue
                shutil.rmtree(path)
        if not any(library.iterdir()):
            library.rmdir()
    print("Removed managed ChargeSend installations. Codex data and configuration were retained.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ["prepare", "test", "build"]:
        sub = subparsers.add_parser(name)
        sub.add_argument("--tag", default=CATALOG["default"])
        sub.add_argument("--source", help="full clean checkout at the pinned release commit")
        if name == "build":
            sub.add_argument("--profile", choices=["dev", "release"], default="dev")
    sub = subparsers.add_parser("install")
    sub.add_argument("--bundle", required=True)
    sub.add_argument("--prefix", default=str(Path.home() / ".local"))
    sub = subparsers.add_parser("uninstall")
    sub.add_argument("--prefix", default=str(Path.home() / ".local"))
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            prepare(args)
        elif args.command == "test":
            prerequisites(args.tag)
            test_source(prepare(args))
        elif args.command == "build":
            build(args)
        elif args.command == "install":
            install(args)
        else:
            uninstall(args)
    except (Failure, OSError) as error:
        print(f"ChargeSend: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
