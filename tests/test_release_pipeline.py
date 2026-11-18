"""Exercise release staging and verification receipts using real Git and executable fixtures."""

from contextlib import redirect_stdout
import difflib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("chargesend", ROOT / "scripts/chargesend.py")
workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflow)
spec = importlib.util.spec_from_file_location("release_pipeline", ROOT / "scripts/port-release.py")
pipeline = importlib.util.module_from_spec(spec)
with mock.patch.dict(sys.modules, {"chargesend": workflow}):
    spec.loader.exec_module(pipeline)


class ReleasePipelineTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="chargesend-pipeline-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "project with spaces"
        self.root.mkdir()
        self.previous = "rust-v9.0.0"
        self.tag = "rust-v9.1.0"
        self.repository = Path(temporary.name) / "upstream"
        self.repository.mkdir()
        self.git("init", "--quiet")
        files = {
            "codex-rs/Cargo.toml": '[workspace.package]\nversion = "9.1.0"\n',
            "codex-rs/Cargo.lock": 'version = 4\n[[package]]\nname = "codex-tui"\nversion = "0.0.0"\n',
            "codex-rs/rust-toolchain.toml": '[toolchain]\nchannel = "1.95.0"\n',
            "codex-rs/tui/Cargo.toml": '[package]\nname = "codex-tui"\nversion.workspace = true\n',
            "codex-rs/tui/src/lib.rs": 'mod old;\n\n// final context\n\n',
            "codex-rs/tui/src/snapshots/working.snap": 'old snapshot\n',
            "codex-rs/cli/Cargo.toml": '[package]\nname = "codex-cli"\n[[bin]]\nname = "codex"\n',
        }
        for name, content in files.items():
            path = self.repository / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        self.git("add", ".")
        self.git("-c", "user.name=ChargeSend tests", "-c", "user.email=tests@example.invalid", "commit", "--quiet", "-m", "release fixture")
        self.git("tag", self.tag)
        commit = self.git("rev-parse", "HEAD")
        (self.root / "patches").mkdir()
        patch = self.root / "patches/old.patch"
        before = files["codex-rs/tui/src/lib.rs"]
        patch.write_text("".join(difflib.unified_diff(before.splitlines(True), before.replace('mod old;', 'mod old;\nmod chargesend;').splitlines(True),
                                                      fromfile="a/codex-rs/tui/src/lib.rs", tofile="b/codex-rs/tui/src/lib.rs")))
        self.catalog = {"default": self.previous, "upstream": str(self.repository), "releases": {
            self.previous: {"commit": commit, "rust": "1.95.0", "patch": "patches/old.patch"},
        }}
        self.overlay = "codex-rs/tui/src/chargesend.rs"
        (self.root / "module").mkdir()
        (self.root / "module/helper.rs").write_text("// dedicated helper\n")
        (self.root / "scripts").mkdir()
        (self.root / "scripts/chargesend.py").write_bytes((ROOT / "scripts/chargesend.py").read_bytes())
        (self.root / "overlays.json").write_text(json.dumps({"module/helper.rs": self.overlay}))
        for name in ["LICENSE", "NOTICE", "UPSTREAM-NOTICE"]:
            (self.root / name).write_text("fixture notice\n")
        self.helper = self.root / "official-helper"
        self.helper.write_text("#!/bin/sh\nexit 0\n")
        self.helper.chmod(0o755)
        for patcher in [
            mock.patch.object(workflow, "ROOT", self.root),
            mock.patch.object(workflow, "CATALOG", self.catalog),
            mock.patch.object(workflow, "OVERLAYS", {"module/helper.rs": self.overlay}),
            mock.patch.object(workflow, "PATCH", patch),
            mock.patch.dict(os.environ, {"CARGO_TARGET_DIR": str(self.root / ".build/target"), "CARGO_INCREMENTAL": "0"}),
        ]:
            patcher.start()
            self.addCleanup(patcher.stop)
        pipeline.save(self.root / "supported-releases.json", self.catalog)
        self.events = []
        self.failures = set()
        original_run = workflow.run

        def run(arguments, **kwargs):
            if arguments[:2] == ["rustc", "-vV"]:
                return "rustc fixture\nhost: x86_64-unknown-linux-gnu"
            if arguments == ["rustc", "--version"]:
                return "rustc fixture"
            if arguments == ["cargo", "clippy", "--version"]:
                return "clippy fixture"
            return original_run(arguments, **kwargs)

        patcher = mock.patch.object(workflow, "run", side_effect=run)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(workflow, "installed_code_mode_host", return_value=self.helper)
        patcher.start()
        self.addCleanup(patcher.stop)

    def git(self, *arguments):
        return subprocess.check_output(["git", "-c", "core.fsmonitor=false", *arguments], cwd=self.repository, text=True).strip()

    @property
    def source(self):
        return pipeline.update_dir(self.tag) / "source"

    def stage(self):
        pipeline.start(self.tag, None, False)
        pipeline.export(self.tag)
        pipeline.certify(self.tag)

    def fake_logged(self, path, arguments, **kwargs):
        self.events.append(tuple(arguments))
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as stream:
            stream.write(" ".join(arguments) + "\n")
        if tuple(arguments[:2]) in self.failures or arguments[-1] in self.failures:
            raise workflow.Failure("fixture stage failed")
        if arguments[:2] == ["cargo", "build"]:
            binary = self.root / ".build/target/debug/codex"
            binary.parent.mkdir(parents=True, exist_ok=True)
            binary.write_text('#!/bin/sh\nif [ "$1" = "--version" ]; then printf "codex-cli 9.1.0\\n"; fi\nif [ "$1" = "exec-server" ]; then exit 2; fi\n')
            binary.chmod(0o755)
        if kwargs.get("capture"):
            return workflow.run(arguments, **kwargs)
        return ""

    def check(self, **kwargs):
        with mock.patch.object(pipeline, "logged_run", side_effect=self.fake_logged), mock.patch.object(workflow, "prerequisites"):
            pipeline.check(self.tag, **kwargs)

    def test_stages_pinned_release_and_resumes_without_overwriting_edits(self):
        pipeline.start(self.tag, None, False)
        state = pipeline.session(self.tag)
        self.assertEqual(state["commit"], self.git("rev-parse", "HEAD"))
        self.assertEqual(state["rust"], "1.95.0")
        target = self.source / self.overlay
        target.write_text("// developer work\n")
        pipeline.start(self.tag, None, False)
        self.assertEqual(target.read_text(), "// developer work\n")
        self.assertEqual(workflow.CATALOG["default"], self.previous)

    def test_export_and_independent_proof_preserve_source_mtimes(self):
        pipeline.start(self.tag, None, False)
        pipeline.export(self.tag)
        targets = [self.source / "codex-rs/tui/src/lib.rs", self.source / self.overlay]
        times = [path.stat().st_mtime_ns for path in targets]
        pipeline.certify(self.tag)
        self.assertEqual(times, [path.stat().st_mtime_ns for path in targets])
        workflow.apply_to(self.source, self.tag)
        self.assertEqual(workflow.CATALOG["default"], self.previous)
        self.assertTrue(workflow.CATALOG["releases"][self.tag]["development"])

    def test_export_preserves_blank_context_and_overlay_adaptations(self):
        pipeline.start(self.tag, None, False)
        (self.source / self.overlay).write_text("// adapted release helper\n")
        pipeline.export(self.tag)
        self.assertTrue(workflow.overlay_patch_for(self.tag).is_file())
        pipeline.certify(self.tag)
        self.assertEqual((self.source / self.overlay).read_text(), "// adapted release helper\n")

    def test_proof_refuses_unexported_changes_and_leaves_marker_unchanged(self):
        self.stage()
        stamp = self.source / ".chargesend-applied.json"
        saved = stamp.read_bytes()
        (self.source / "codex-rs/tui/src/lib.rs").write_text("// unexported edit\n")
        with self.assertRaisesRegex(workflow.Failure, "differs"):
            pipeline.certify(self.tag)
        self.assertEqual(stamp.read_bytes(), saved)

    def test_rejects_dependency_changes_and_leftover_snapshots(self):
        pipeline.start(self.tag, None, False)
        unexpected = self.source / "codex-rs/tui/src/failed.snap.new"
        unexpected.write_text("review me")
        with self.assertRaisesRegex(workflow.Failure, "Unexported"):
            pipeline.export(self.tag)
        unexpected.unlink()
        (self.source / "codex-rs/Cargo.lock").write_text("unexpected dependency edit")
        with self.assertRaisesRegex(workflow.Failure, "Cargo.lock changed"):
            pipeline.export(self.tag)

    def test_dry_run_does_not_write_catalog_or_new_patches(self):
        pipeline.start(self.tag, None, False)
        original = (self.root / "supported-releases.json").read_bytes()
        pipeline.export(self.tag, dry_run=True)
        self.assertEqual((self.root / "supported-releases.json").read_bytes(), original)
        self.assertNotIn(self.tag, workflow.CATALOG["releases"])

    def test_lint_precedes_compilation_and_failed_lint_stops_the_pipeline(self):
        self.stage()
        self.failures.add(("cargo", "clippy"))
        with self.assertRaisesRegex(workflow.Failure, "fixture"):
            self.check()
        self.assertFalse(any(command[:2] in [("cargo", "test"), ("cargo", "build")] for command in self.events))

    def test_collects_all_failing_filters_and_does_not_build_after_failure(self):
        self.stage()
        filters = workflow.focused_test_filters(self.source)
        self.failures.update(filters[:2])
        with self.assertRaisesRegex(workflow.Failure, "Failing test filters") as caught:
            self.check()
        self.assertIn(filters[0], str(caught.exception))
        self.assertIn(filters[1], str(caught.exception))
        self.assertTrue(any(command[-1] == filters[-1] for command in self.events))
        self.assertFalse(any(command[:2] == ("cargo", "build") for command in self.events))
        receipts = json.loads((pipeline.update_dir(self.tag) / "checks.json").read_text())
        self.assertIn("lint", receipts)
        self.assertNotIn("tests", receipts)

    def test_test_compilation_failure_stops_before_repeating_compile_for_filters(self):
        self.stage()
        self.failures.add("--no-run")
        with self.assertRaises(workflow.Failure):
            self.check()
        commands = [command for command in self.events if command[:2] == ("cargo", "test")]
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0][-1], "--no-run")

    def test_successful_checks_resume_and_package_the_actual_executable_fixture(self):
        self.stage()
        self.check()
        first = list(self.events)
        self.assertLess(next(i for i, cmd in enumerate(first) if cmd[:2] == ("cargo", "clippy")), next(i for i, cmd in enumerate(first) if cmd[:2] == ("cargo", "test")))
        self.events.clear()
        self.check()
        self.assertFalse(any(cmd[:2] in [("cargo", "clippy"), ("cargo", "test"), ("cargo", "build")] for cmd in self.events))
        receipt = json.loads((pipeline.update_dir(self.tag) / "checks.json").read_text())["bundle"]
        metadata = workflow.validated_bundle(self.root / receipt["path"])
        self.assertEqual(metadata["upstream_commit"], self.git("rev-parse", "HEAD"))
        self.assertEqual(metadata["patch_fingerprint"], workflow.fingerprint(self.tag))

    def test_external_snapshot_change_retests_without_repeating_lint(self):
        self.stage()
        self.check()
        self.events.clear()
        (self.source / "codex-rs/tui/src/snapshots/working.snap").write_text("reviewed snapshot\n")
        self.check()
        self.assertFalse(any(command[:2] == ("cargo", "clippy") for command in self.events))
        self.assertTrue(any(command[:2] == ("cargo", "test") for command in self.events))

    def test_rust_change_invalidates_lint_and_test_receipts(self):
        self.stage()
        self.check()
        self.events.clear()
        with (self.source / self.overlay).open("a") as stream:
            stream.write("// changed Rust\n")
        self.check()
        self.assertTrue(any(command[:2] == ("cargo", "clippy") for command in self.events))
        self.assertTrue(any(command[:2] == ("cargo", "test") for command in self.events))

    def test_compiler_flag_change_invalidates_receipts(self):
        self.stage()
        self.check()
        self.events.clear()
        with mock.patch.dict(os.environ, {"RUSTFLAGS": "--cfg changed_build"}):
            self.check()
        self.assertTrue(any(command[:2] == ("cargo", "clippy") for command in self.events))

    def test_corrupt_bundle_cannot_be_promoted_and_is_rebuilt(self):
        self.stage()
        self.check()
        receipts = json.loads((pipeline.update_dir(self.tag) / "checks.json").read_text())
        (self.root / receipts["bundle"]["path"] / "chargesend-cli").write_text("corrupt")
        with self.assertRaisesRegex(workflow.Failure, "checksum"):
            pipeline.promote(self.tag, True)
        self.assertEqual(workflow.CATALOG["default"], self.previous)
        self.events.clear()
        self.check()
        self.assertTrue(any(command[:2] == ("cargo", "build") for command in self.events))

    def test_force_failure_cannot_leave_a_reusable_success_receipt(self):
        self.stage()
        self.check()
        self.failures.add(("cargo", "clippy"))
        with self.assertRaises(workflow.Failure):
            self.check(force=True)
        receipts = json.loads((pipeline.update_dir(self.tag) / "checks.json").read_text())
        self.assertNotIn("lint", receipts)

    def test_stale_or_tampered_inputs_cannot_be_promoted(self):
        self.stage()
        self.check(through="lint")
        with self.assertRaisesRegex(workflow.Failure, "every check"):
            pipeline.promote(self.tag, True)
        self.check()
        with (self.source / self.overlay).open("a") as stream:
            stream.write("// edit after verification\n")
        with self.assertRaises(workflow.Failure):
            pipeline.promote(self.tag, True)
        self.assertEqual(workflow.CATALOG["default"], self.previous)

    def test_source_edit_during_final_smoke_prevents_promotion(self):
        self.stage()
        self.check()
        original = pipeline.smoke

        def edit(bundle, tag):
            original(bundle, tag)
            with (self.source / self.overlay).open("a") as stream:
                stream.write("// concurrent edit\n")

        with mock.patch.object(pipeline, "smoke", side_effect=edit):
            with self.assertRaises(workflow.Failure):
                pipeline.promote(self.tag, True)
        self.assertEqual(workflow.CATALOG["default"], self.previous)

    def test_cached_bundle_check_detects_source_edit_without_starting_another_build(self):
        self.stage()
        self.check()
        self.events.clear()
        original = pipeline.smoke

        def edit(bundle, tag):
            original(bundle, tag)
            with (self.source / self.overlay).open("a") as stream:
                stream.write("// concurrent edit\n")

        with mock.patch.object(pipeline, "smoke", side_effect=edit):
            with self.assertRaises(workflow.Failure):
                self.check()
        self.assertFalse(any(command[:2] == ("cargo", "build") for command in self.events))

    def test_promote_changes_default_only_after_all_checks_and_cleans_cache(self):
        self.stage()
        self.check()
        with mock.patch.object(workflow, "clean_build_cache") as clean:
            pipeline.promote(self.tag, False)
        clean.assert_called_once()
        self.assertEqual(workflow.CATALOG["default"], self.tag)
        self.assertFalse(workflow.CATALOG["releases"][self.tag]["development"])

    def test_editing_a_verified_port_marks_its_catalog_entry_pending_again(self):
        self.stage()
        self.check()
        pipeline.promote(self.tag, True)
        with (self.source / self.overlay).open("a") as stream:
            stream.write("// next edit\n")
        pipeline.export(self.tag)
        self.assertTrue(workflow.CATALOG["releases"][self.tag]["development"])
        self.assertIn("pending", workflow.CATALOG["releases"][self.tag]["status"])

    def test_tag_validation_and_symlinked_update_directories(self):
        for value in ["main", "rust-v1.2.3-alpha.1", "../../other"]:
            with self.assertRaises(workflow.Failure):
                pipeline.tag_name(value)
        directory = self.root / ".build/updates"
        directory.parent.mkdir()
        directory.symlink_to(self.repository)
        with self.assertRaisesRegex(workflow.Failure, "symlinked"):
            pipeline.update_dir(self.tag)


class LoggedCommandTests(unittest.TestCase):
    def test_latest_release_resolution_rejects_prereleases(self):
        response = lambda value: io.BytesIO(json.dumps(value).encode())
        with mock.patch.object(pipeline, "urlopen", return_value=response({"tag_name": "rust-v9.1.0", "draft": False, "prerelease": False})):
            self.assertEqual(pipeline.latest_tag(), "rust-v9.1.0")
        with mock.patch.object(pipeline, "urlopen", return_value=response({"tag_name": "rust-v9.2.0", "prerelease": True})):
            with self.assertRaisesRegex(workflow.Failure, "not a stable"):
                pipeline.latest_tag()

    def test_output_and_failure_are_recorded_without_losing_the_exit_status(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "failure.log"
            with redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(workflow.Failure, "failed \\(17\\)"):
                    pipeline.logged_run(log, [sys.executable, "-u", "-c", "import sys; print('stdout'); print('stderr', file=sys.stderr); sys.exit(17)"])
            self.assertIn("stdout\nstderr\n", log.read_text())


if __name__ == "__main__":
    unittest.main()
