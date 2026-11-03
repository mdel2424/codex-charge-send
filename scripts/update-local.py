#!/usr/bin/env python3
"""Build the pinned ChargeSend release and make the local codex command use it."""

import argparse
import os
from pathlib import Path
import subprocess
import sys

import chargesend as workflow


def run_logged(arguments: list[str], log_path: Path) -> int:
    """Keep the terminal output available after a failed update."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w") as log:
        with subprocess.Popen(arguments, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as process:
            for line in process.stdout:
                sys.stdout.write(line)
                log.write(line)
                log.flush()
            return process.wait()


def install_update(bundle: Path, prefix: Path) -> None:
    # Install and verify the bundle before changing either Codex command.
    workflow.install(argparse.Namespace(bundle=str(bundle), prefix=str(prefix)))
    command = prefix / "bin/codex"
    stock = prefix / "bin/codex-stock"
    archived = None
    if (command.is_file() and not workflow.managed_launcher(command)
            and stock.is_file() and not stock.samefile(command)):
        # Official updates can restore codex while codex-stock still saves an
        # older release. Retain both originals instead of replacing a backup.
        index = 1
        while True:
            candidate = stock.with_name(f"codex-stock.previous-{index}")
            try:
                os.link(stock, candidate, follow_symlinks=False)
            except FileExistsError:
                index += 1
                continue
            archived = candidate
            break
        stock.unlink()
    try:
        workflow.link_codex(argparse.Namespace(prefix=str(prefix), launcher=None))
    except (workflow.Failure, OSError):
        if archived is not None and not (stock.exists() or stock.is_symlink()):
            archived.rename(stock)
        raise
    if archived is not None:
        print(f"Earlier stock Codex backup retained at {archived}.")


def update(args: argparse.Namespace) -> None:
    workflow.prerequisites(args.tag)
    baseline = workflow.release(args.tag)
    toolchain = baseline["rust"]
    compiler = workflow.run(["rustup", "run", toolchain, "rustc", "-vV"], capture=True)
    target = next(line.removeprefix("host: ") for line in compiler.splitlines() if line.startswith("host: "))
    build_id = f"chargesend-{workflow.VERSION}-codex-{args.tag.removeprefix('rust-v')}-{target}-dev"
    bundle = workflow.ROOT / "dist" / build_id
    try:
        metadata = workflow.validated_bundle(bundle)
        reusable = (metadata.get("upstream_tag") == args.tag
                    and metadata.get("upstream_commit") == baseline["commit"]
                    and metadata.get("patch_fingerprint") == workflow.fingerprint(args.tag))
    except workflow.Failure:
        reusable = False
    if not reusable:
        workflow.run_build_command(argparse.Namespace(
            command="build", tag=args.tag, source=None, profile="dev",
            code_mode_host=None, keep_build_cache=args.keep_build_cache,
        ))
    metadata = workflow.validated_bundle(bundle)
    if metadata.get("patch_fingerprint") != workflow.fingerprint(args.tag):
        raise workflow.Failure("The built bundle does not match the current ChargeSend patch.")
    # Exercise the actual executable before replacing the user's command.
    native_version = workflow.run([str(bundle / "chargesend-cli"), "--version"], capture=True)
    if native_version != f"codex-cli {args.tag.removeprefix('rust-v')}":
        raise workflow.Failure(f"Unexpected native CLI version: {native_version!r}.")
    workflow.run([str(bundle / "chargesend-cli"), "--help"], capture=True)
    prefix = Path(args.prefix).expanduser().resolve()
    install_update(bundle, prefix)
    installed = prefix / "lib/chargesend" / build_id
    if workflow.validated_bundle(installed) != metadata:
        raise workflow.Failure("Installed bundle metadata differs from the verified build.")
    print(workflow.run([str(prefix / "bin/codex"), "--version"], capture=True))
    print("Exit the current Codex session and reopen codex to load the update.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default=workflow.CATALOG["default"])
    parser.add_argument("--prefix", default=str(Path.home() / ".local"))
    parser.add_argument("--keep-build-cache", action="store_true")
    parser.add_argument("--log-child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    os.environ["PATH"] = str(Path.home() / ".cargo/bin") + os.pathsep + os.environ.get("PATH", "")
    os.environ.setdefault("CARGO_HOME", str(workflow.ROOT / ".build/cargo"))
    os.environ.setdefault("CARGO_BUILD_JOBS", "4")
    try:
        if not args.log_child:
            log_path = workflow.ROOT / ".build/update-local.log"
            print(f"Saving update output to {log_path}", flush=True)
            return run_logged([sys.executable, "-u", "-B", str(Path(__file__).resolve()), "--log-child", *sys.argv[1:]], log_path)
        update(args)
    except (workflow.Failure, OSError) as error:
        print(f"ChargeSend update: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
