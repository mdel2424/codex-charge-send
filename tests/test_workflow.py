"""Test real patch/file/launcher operations without a compiler or live backend."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("chargesend_workflow", ROOT / "scripts/chargesend.py")
workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflow)


class PatchWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="chargesend-workflow-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.source = self.directory / "upstream"
        self.source.mkdir()
        self.git("init", "--quiet")
        (self.source / "codex-rs/tui/src").mkdir(parents=True)
        (self.source / "codex-rs/tui/src/lib.rs").write_text("mod old;\n")
        (self.source / "codex-rs/Cargo.lock").write_text("version = 4\n")
        (self.source / "codex-rs/Cargo.toml").write_text("[workspace]\n")
        self.git("add", ".")
        self.git("-c", "user.name=ChargeSend tests", "-c", "user.email=tests@example.invalid", "commit", "--quiet", "-m", "fixture")
        self.patch = self.directory / "fixture.patch"
        self.patch.write_text("--- a/codex-rs/tui/src/lib.rs\n+++ b/codex-rs/tui/src/lib.rs\n@@ -1 +1,2 @@\n mod old;\n+mod chargesend;\n")
        patcher = mock.patch.object(workflow, "PATCH", self.patch)
        patcher.start()
        self.addCleanup(patcher.stop)

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.source, check=True, text=True, capture_output=True).stdout.strip()

    def test_patch_applies_and_modules_are_copied_and_retry_is_idempotent(self):
        workflow.apply_to(self.source, "fixture")
        self.assertEqual((self.source / "codex-rs/tui/src/lib.rs").read_text(), "mod old;\nmod chargesend;\n")
        for source, target in workflow.OVERLAYS.items():
            self.assertEqual((self.source / target).read_bytes(), (ROOT / source).read_bytes())
        workflow.apply_to(self.source, "fixture")

    def test_patch_conflict_is_clear_and_does_not_copy_modules(self):
        self.patch.write_text(self.patch.read_text().replace("mod old;", "mod absent;"))
        original = (self.source / "codex-rs/tui/src/lib.rs").read_bytes()
        with self.assertRaisesRegex(workflow.Failure, "patch conflicts.*fixture"):
            workflow.apply_to(self.source, "fixture")
        self.assertEqual((self.source / "codex-rs/tui/src/lib.rs").read_bytes(), original)
        self.assertFalse((self.source / ".chargesend-applied.json").exists())
        self.assertFalse((self.source / next(iter(workflow.OVERLAYS.values()))).exists())

    def test_dirty_source_and_changed_prepared_source_are_rejected(self):
        (self.source / "notes.txt").write_text("user work")
        with self.assertRaisesRegex(workflow.Failure, "dirty"):
            workflow.apply_to(self.source, "fixture")
        (self.source / "notes.txt").unlink()
        workflow.apply_to(self.source, "fixture")
        (self.source / "codex-rs/tui/src/lib.rs").write_text("new user work\n")
        with self.assertRaisesRegex(workflow.Failure, "sources were edited"):
            workflow.apply_to(self.source, "fixture")

    def test_changed_patch_is_rejected_without_overwriting_prepared_source(self):
        workflow.apply_to(self.source, "fixture")
        self.patch.write_text(self.patch.read_text() + "\n")
        with self.assertRaisesRegex(workflow.Failure, "different ChargeSend patch"):
            workflow.apply_to(self.source, "fixture")

    def test_patch_change_during_compile_does_not_produce_a_misleading_bundle(self):
        manifest = self.source / "codex-rs/cli/Cargo.toml"
        manifest.parent.mkdir()
        manifest.write_text('[package]\nname = "codex-cli"\n[[bin]]\nname = "codex"\n')
        self.git("add", ".")
        self.git("-c", "user.name=ChargeSend tests", "-c", "user.email=tests@example.invalid", "commit", "--quiet", "-m", "CLI fixture")
        workflow.apply_to(self.source, "fixture")
        original_run = workflow.run

        def compile_and_edit(args, cwd=None, capture=False):
            if args[:2] == ["cargo", "build"]:
                self.patch.write_text(self.patch.read_text() + "\n")
                return ""
            return original_run(args, cwd=cwd, capture=capture)

        with mock.patch.object(workflow, "run", side_effect=compile_and_edit):
            with self.assertRaisesRegex(workflow.Failure, "different ChargeSend patch"):
                workflow.bundle(self.source, "fixture", "dev")

    def test_source_commit_must_match_the_catalog(self):
        with self.assertRaisesRegex(workflow.Failure, "expected rust-v0.161.0"):
            workflow.checkout("rust-v0.161.0", str(self.source))

    def test_release_lock_alignment_only_changes_local_versions(self):
        (self.source / "codex-rs/Cargo.toml").write_text('[workspace.package]\nversion = "0.161.0"\n')
        (self.source / "codex-rs/tui/Cargo.toml").write_text('[package]\nname = "codex-tui"\nversion.workspace = true\n')
        lock = self.source / "codex-rs/Cargo.lock"
        external = '\n[[package]]\nname = "serde"\nversion = "1.0.219"\nsource = "registry+https://github.com/rust-lang/crates.io-index"\nchecksum = "unchanged"\n'
        lock.write_text('version = 4\n[[package]]\nname = "codex-tui"\nversion = "0.0.0"\ndependencies = ["serde"]\n' + external)
        self.assertEqual(workflow.align_workspace_lock(self.source), 1)
        self.assertIn('version = "0.161.0"', lock.read_text())
        self.assertTrue(lock.read_text().endswith(external))
        self.assertIn('dependencies = ["serde"]', lock.read_text())
        self.assertEqual(workflow.align_workspace_lock(self.source), 0)

    def test_unlisted_release_and_missing_tools_are_actionable(self):
        with self.assertRaisesRegex(workflow.Failure, "Unlisted release"):
            workflow.release("rust-v99.0.0")
        with mock.patch.object(workflow.shutil, "which", return_value=None):
            with self.assertRaisesRegex(workflow.Failure, "setup-ubuntu.sh"):
                workflow.prerequisites("rust-v0.161.0")


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="chargesend-install-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.bundle = self.directory / "fixture-bundle"
        self.bundle.mkdir()
        binary = self.bundle / "chargesend-cli"
        binary.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\"\n")
        binary.chmod(0o755)
        workflow.write_launcher(self.bundle / "bin/chargesend", "0.1.0", "rust-v0.161.0")
        helper = self.bundle / "codex-code-mode-host"
        helper.write_text("#!/bin/sh\nexit 0\n")
        helper.chmod(0o755)
        (self.bundle / "manifest.json").write_text(json.dumps({"product": "ChargeSend", "binary_sha256": workflow.sha256(binary), "code_mode_host_sha256": workflow.sha256(helper)}))
        self.prefix = self.directory / "prefix with spaces"
        (self.prefix / "bin").mkdir(parents=True)
        (self.prefix / "bin/codex").write_text("stock Codex")
        self.args = argparse.Namespace(bundle=str(self.bundle), prefix=str(self.prefix))

    def test_install_launcher_version_arguments_and_uninstall_preserve_stock_codex(self):
        workflow.install(self.args)
        launcher = self.prefix / "bin/chargesend"
        version = subprocess.check_output([launcher, "--version"], text=True)
        self.assertEqual(version.strip(), "ChargeSend 0.1.0 (unofficial Codex 0.161.0)")
        arguments = ["exec", "literal argument with spaces", "--model", "example"]
        self.assertEqual(subprocess.check_output([launcher, *arguments], text=True).splitlines(), arguments)
        workflow.uninstall(self.args)
        self.assertFalse(launcher.exists())
        self.assertEqual((self.prefix / "bin/codex").read_text(), "stock Codex")

    def test_unmanaged_command_is_not_overwritten_or_removed(self):
        launcher = self.prefix / "bin/chargesend"
        launcher.write_bytes(b"\x7fELF\xffexisting user binary")
        with self.assertRaisesRegex(workflow.Failure, "not a managed"):
            workflow.install(self.args)
        with self.assertRaisesRegex(workflow.Failure, "unmanaged"):
            workflow.uninstall(self.args)
        self.assertTrue(launcher.exists())

    def test_bundle_checksum_is_required(self):
        (self.bundle / "chargesend-cli").write_text("changed")
        with self.assertRaisesRegex(workflow.Failure, "checksum"):
            workflow.install(self.args)

    def test_runtime_helper_is_required_and_verified(self):
        helper = self.bundle / "codex-code-mode-host"
        helper.write_text("changed")
        with self.assertRaisesRegex(workflow.Failure, "helper checksum"):
            workflow.install(self.args)
        helper.unlink()
        with self.assertRaisesRegex(workflow.Failure, "completed ChargeSend"):
            workflow.install(self.args)

    def test_codex_mapping_forwards_arguments_is_repeatable_and_restores_on_uninstall(self):
        self.args.as_codex = True
        workflow.install(self.args)
        command = self.prefix / "bin/codex"
        stock = self.prefix / "bin/codex-stock"
        self.assertTrue(command.is_symlink())
        self.assertEqual(stock.read_text(), "stock Codex")
        arguments = ["resume", "session with spaces", "--no-daemon"]
        self.assertEqual(subprocess.check_output([command, *arguments], text=True).splitlines(), arguments)
        workflow.install(self.args)
        self.assertEqual(stock.read_text(), "stock Codex")
        workflow.uninstall(self.args)
        self.assertFalse(command.is_symlink())
        self.assertEqual(command.read_text(), "stock Codex")
        self.assertFalse(stock.exists())

    def test_project_local_mapping_preserves_relative_stock_symlink(self):
        workflow.install(self.args)
        command = self.prefix / "bin/codex"
        command.unlink()
        original = self.prefix / "bin/original-codex"
        original.write_text("stock Codex")
        command.symlink_to("original-codex")
        args = argparse.Namespace(prefix=str(self.prefix), launcher=str(self.bundle / "bin/chargesend"))
        workflow.link_codex(args)
        workflow.link_codex(args)
        self.assertEqual(os.readlink(self.prefix / "bin/codex-stock"), "original-codex")
        workflow.restore_codex(args)
        self.assertEqual(os.readlink(command), "original-codex")

    def test_mapping_and_restoration_refuse_conflicts(self):
        workflow.install(self.args)
        stock = self.prefix / "bin/codex-stock"
        stock.write_text("existing backup")
        args = argparse.Namespace(prefix=str(self.prefix), launcher=None)
        with self.assertRaisesRegex(workflow.Failure, "saved Codex"):
            workflow.link_codex(args)
        self.assertEqual((self.prefix / "bin/codex").read_text(), "stock Codex")
        self.assertEqual(stock.read_text(), "existing backup")
        with self.assertRaisesRegex(workflow.Failure, "not a ChargeSend mapping"):
            workflow.restore_codex(args)

    def test_switching_from_project_launcher_to_install_keeps_original_backup(self):
        workflow.install(self.args)
        workflow.link_codex(argparse.Namespace(prefix=str(self.prefix), launcher=str(self.bundle / "bin/chargesend")))
        self.args.as_codex = True
        workflow.install(self.args)
        self.assertEqual((self.prefix / "bin/codex").resolve(), (self.prefix / "bin/chargesend").resolve())
        self.assertEqual((self.prefix / "bin/codex-stock").read_text(), "stock Codex")
        workflow.uninstall(self.args)
        self.assertEqual((self.prefix / "bin/codex").read_text(), "stock Codex")

    def test_mapping_without_stock_is_removed_on_uninstall(self):
        (self.prefix / "bin/codex").unlink()
        self.args.as_codex = True
        workflow.install(self.args)
        workflow.uninstall(self.args)
        self.assertFalse((self.prefix / "bin/codex").is_symlink())

    def test_symlink_command_is_not_followed(self):
        target = self.directory / "unrelated"
        target.write_text("keep")
        (self.prefix / "bin/chargesend").symlink_to(target)
        with self.assertRaises(workflow.Failure):
            workflow.install(self.args)
        self.assertEqual(target.read_text(), "keep")


class BundleTests(unittest.TestCase):
    def test_bundle_copies_runtime_helper_and_records_checksum(self):
        with tempfile.TemporaryDirectory(prefix="chargesend-bundle-") as directory:
            root = Path(directory)
            source = root / "upstream"
            workspace = source / "codex-rs"
            (workspace / "cli").mkdir(parents=True)
            (workspace / "cli/Cargo.toml").write_text('[package]\nname = "codex-cli"\n[[bin]]\nname = "codex"\n')
            (workspace / "Cargo.lock").write_text("version = 4\n")
            binaries = workspace / "target/debug"
            binaries.mkdir(parents=True)
            (binaries / "codex").write_text("CLI fixture")
            (binaries / "codex-code-mode-host").write_text("helper fixture")
            for name in ["LICENSE", "NOTICE", "UPSTREAM-NOTICE"]:
                (root / name).write_text("notice fixture")
            def fake_run(args, cwd=None, capture=False):
                return "host: test-target" if args == ["rustc", "-vV"] else "rustc fixture" if args == ["rustc", "--version"] else ""
            with mock.patch.object(workflow, "ROOT", root), mock.patch.object(workflow, "run", side_effect=fake_run) as run, mock.patch.object(workflow, "apply_to"), mock.patch.object(workflow, "fingerprint", return_value="fixture"), mock.patch.object(workflow.subprocess, "check_output", return_value=b"version = 4\n"), mock.patch.dict(os.environ, {"CARGO_TARGET_DIR": str(workspace / "target")}):
                destination = workflow.bundle(source, "rust-v0.161.0", "dev")
            self.assertEqual((destination / "codex-code-mode-host").read_text(), "helper fixture")
            self.assertTrue(os.access(destination / "codex-code-mode-host", os.X_OK))
            self.assertEqual(workflow.validated_bundle(destination)["code_mode_host_sha256"], workflow.sha256(destination / "codex-code-mode-host"))
            build = run.call_args_list[0].args[0]
            self.assertIn("codex-code-mode-host", build)


if __name__ == "__main__":
    unittest.main()
