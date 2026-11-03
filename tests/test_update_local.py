"""Exercise the one-command updater without downloading or compiling Codex."""

import argparse
from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("chargesend", ROOT / "scripts/chargesend.py")
workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflow)
spec = importlib.util.spec_from_file_location("update_local", ROOT / "scripts/update-local.py")
updater = importlib.util.module_from_spec(spec)
with mock.patch.dict("sys.modules", {"chargesend": workflow}):
    spec.loader.exec_module(updater)


class LocalUpdateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="chargesend-update-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.prefix = self.root / "installation with spaces"
        (self.prefix / "bin").mkdir(parents=True)
        self.command = self.prefix / "bin/codex"
        self.command.write_text("current stock")
        self.stock = self.prefix / "bin/codex-stock"
        self.stock.write_text("earlier stock")
        self.tag = workflow.CATALOG["default"]
        self.bundle = self.root / "dist" / f"chargesend-{workflow.VERSION}-codex-{self.tag.removeprefix('rust-v')}-x86_64-unknown-linux-gnu-dev"
        self.bundle.mkdir(parents=True)
        for name in ("chargesend-cli", "codex-code-mode-host"):
            binary = self.bundle / name
            binary.write_text(f'#!/bin/sh\nif [ "$1" = "--version" ]; then\n  printf "codex-cli {self.tag.removeprefix("rust-v")}\\n"\nfi\n')
            binary.chmod(0o755)
        workflow.write_launcher(self.bundle / "bin/chargesend", workflow.VERSION, self.tag)
        self.metadata = {
            "product": "ChargeSend", "upstream_tag": self.tag,
            "upstream_commit": workflow.release(self.tag)["commit"],
            "patch_fingerprint": "fixture",
            "binary_sha256": workflow.sha256(self.bundle / "chargesend-cli"),
            "code_mode_host_sha256": workflow.sha256(self.bundle / "codex-code-mode-host"),
        }
        self.write_metadata()

    def write_metadata(self):
        (self.bundle / "manifest.json").write_text(json.dumps(self.metadata))

    def test_failed_update_output_is_saved_with_the_failure_exit_code(self):
        log = self.root / ".build/update-local.log"
        output = io.StringIO()
        with redirect_stdout(output):
            status = updater.run_logged([
                sys.executable, "-u", "-c",
                "import sys; print('building'); print('compiler error', file=sys.stderr); sys.exit(17)",
            ], log)
        self.assertEqual(status, 17)
        self.assertEqual(log.read_text(), "building\ncompiler error\n")
        self.assertEqual(output.getvalue(), log.read_text())

    def test_update_preserves_both_stock_versions_without_overwriting_older_archives(self):
        previous = self.stock.with_name("codex-stock.previous-1")
        previous.write_text("oldest stock")
        updater.install_update(self.bundle, self.prefix)
        self.assertEqual(self.command.resolve(), self.prefix / "bin/chargesend")
        self.assertEqual(self.stock.read_text(), "current stock")
        self.assertEqual(previous.read_text(), "oldest stock")
        self.assertEqual(self.stock.with_name("codex-stock.previous-2").read_text(), "earlier stock")
        workflow.restore_codex(argparse.Namespace(prefix=str(self.prefix)))
        self.assertEqual(self.command.read_text(), "current stock")

    def test_relative_symlink_backup_survives_archiving_and_repeated_updates(self):
        old = self.prefix / "bin/old-release"
        old.write_text("earlier stock")
        self.stock.unlink()
        self.stock.symlink_to(old.name)
        updater.install_update(self.bundle, self.prefix)
        updater.install_update(self.bundle, self.prefix)
        previous = self.stock.with_name("codex-stock.previous-1")
        self.assertEqual(os.readlink(previous), old.name)
        self.assertEqual(previous.read_text(), "earlier stock")
        self.assertEqual(self.stock.read_text(), "current stock")
        self.assertFalse(self.stock.with_name("codex-stock.previous-2").exists())

    def test_failed_mapping_restores_the_earlier_backup_and_leaves_codex_unchanged(self):
        (self.prefix / "bin/.codex-chargesend-link.tmp").write_text("conflict")
        with self.assertRaisesRegex(workflow.Failure, "already exists"):
            updater.install_update(self.bundle, self.prefix)
        self.assertEqual(self.command.read_text(), "current stock")
        self.assertEqual(self.stock.read_text(), "earlier stock")
        self.assertFalse(self.stock.with_name("codex-stock.previous-1").exists())

    def test_bad_bundle_leaves_all_commands_unchanged(self):
        (self.bundle / "chargesend-cli").write_text("corrupt")
        with self.assertRaisesRegex(workflow.Failure, "checksum"):
            updater.install_update(self.bundle, self.prefix)
        self.assertEqual(self.command.read_text(), "current stock")
        self.assertEqual(self.stock.read_text(), "earlier stock")
        self.assertFalse((self.prefix / "bin/chargesend").exists())

    def run_update(self, build):
        original_run = workflow.run

        def run(arguments, **kwargs):
            if arguments[0] == "rustup":
                return "host: x86_64-unknown-linux-gnu"
            return original_run(arguments, **kwargs)

        with (mock.patch.object(workflow, "ROOT", self.root),
              mock.patch.object(workflow, "prerequisites"),
              mock.patch.object(workflow, "fingerprint", return_value="fixture"),
              mock.patch.object(workflow, "run", side_effect=run),
              mock.patch.object(workflow, "run_build_command", side_effect=build) as build_call):
            updater.update(argparse.Namespace(tag=self.tag, prefix=str(self.prefix), keep_build_cache=False))
            return build_call

    def test_verified_current_bundle_is_reused_without_compilation(self):
        build = self.run_update(lambda args: self.fail("should reuse the current bundle"))
        build.assert_not_called()
        self.assertEqual(self.command.resolve(), self.prefix / "bin/chargesend")

    def test_changed_patch_rebuilds_before_installing(self):
        self.metadata["patch_fingerprint"] = "older patch"
        self.write_metadata()

        def build(args):
            self.assertEqual(self.command.read_text(), "current stock")
            self.assertEqual(args.tag, self.tag)
            self.assertFalse(args.keep_build_cache)
            self.metadata["patch_fingerprint"] = "fixture"
            self.write_metadata()

        self.run_update(build).assert_called_once()
        self.assertEqual(self.command.resolve(), self.prefix / "bin/chargesend")

    def test_failed_build_does_not_change_either_stock_command(self):
        self.metadata["patch_fingerprint"] = "older patch"
        self.write_metadata()

        def build(args):
            raise workflow.Failure("build failed")

        with self.assertRaisesRegex(workflow.Failure, "build failed"):
            self.run_update(build)
        self.assertEqual(self.command.read_text(), "current stock")
        self.assertEqual(self.stock.read_text(), "earlier stock")

    def test_incorrect_native_version_is_rejected_before_installation(self):
        binary = self.bundle / "chargesend-cli"
        binary.write_text('#!/bin/sh\nprintf "codex-cli 0.1.0\\n"\n')
        self.metadata["binary_sha256"] = workflow.sha256(binary)
        self.write_metadata()
        with self.assertRaisesRegex(workflow.Failure, "Unexpected native CLI version"):
            self.run_update(lambda args: self.fail("bundle should be reused"))
        self.assertEqual(self.command.read_text(), "current stock")
        self.assertEqual(self.stock.read_text(), "earlier stock")
        self.assertFalse((self.prefix / "bin/chargesend").exists())


if __name__ == "__main__":
    unittest.main()
