#!/usr/bin/env python3
"""Sicherheits- und Regressionstests für den portablen Wissenstresor."""

import contextlib
import importlib.util
import io
import os
import shutil
import subprocess
import tempfile
import unittest
import stat
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
SOURCE_SKILL = REPOSITORY / "wissenstresor"
RELEASE_TARGETS = (
    "INDEX.md",
    "graph/graph.json",
    "VERSION",
    "log.md",
    "MANIFEST.sha256",
)


class VaultSecurityTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory(prefix="wissenstresor-tests-")
        self.work = Path(self.tempdir.name)
        self.copy_number = 0
        self.root = self.new_vault()

    def tearDown(self):
        self.tempdir.cleanup()

    def new_vault(self):
        self.copy_number += 1
        root = self.work / f"wissenstresor-{self.copy_number}"
        shutil.copytree(SOURCE_SKILL, root, symlinks=True)
        result = self.run_cli("checksum", root=root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return root

    def run_cli(self, *args, root=None):
        root = root or self.root
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run(
            ["python3", "-B", str(root / "scripts" / "vault.py"), *args],
            cwd=root,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=15,
        )

    def replace_text(self, relative, old, new, root=None):
        root = root or self.root
        path = root / relative
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    @staticmethod
    def snapshot(root):
        return {
            relative: (root / relative).read_bytes()
            for relative in RELEASE_TARGETS
        }

    @staticmethod
    def load_vault(root, suffix):
        spec = importlib.util.spec_from_file_location(
            f"vault_security_test_{suffix}",
            root / "scripts/vault.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def assert_validate_fails(self, fragment):
        result = self.run_cli("validate")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(fragment, result.stdout)

    def test_source_paths_fail_closed(self):
        original = "sources/raw/S-0001__google-okf-announcement.md"
        for unsafe in (
            "/etc/hosts",
            "../outside.md",
            "sources/quarantine/README.md",
            "sources/raw/../raw/S-0001__google-okf-announcement.md",
        ):
            with self.subTest(unsafe=unsafe):
                root = self.new_vault()
                self.replace_text("sources/REGISTER.md", original, unsafe, root=root)
                result = self.run_cli("validate", root=root)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("REGISTER S-0001", result.stdout)

    def test_source_symlink_is_rejected(self):
        source = self.root / "sources/raw/S-0001__google-okf-announcement.md"
        outside = self.work / "outside-source.md"
        outside.write_bytes(source.read_bytes())
        source.unlink()
        source.symlink_to(outside)
        self.assert_validate_fails("Symlink")

    def test_unregistered_raw_source_is_rejected(self):
        (self.root / "sources/raw/unregistered.md").write_text(
            "nicht registriert\n", encoding="utf-8"
        )
        self.assert_validate_fails("nicht eindeutig im REGISTER")

    def test_unclear_rights_are_rejected(self):
        self.replace_text(
            "sources/REGISTER.md",
            "Nur Verweis/Paraphrase, kein Volltext",
            "TODO",
        )
        self.assert_validate_fails("Rechte müssen")

    def test_relation_traversal_is_rejected(self):
        self.replace_text(
            "knowledge/demo-okf/okf.md",
            "formalisiert -> demo-okf/llm-wiki-muster.md",
            "formalisiert -> ../../outside.md",
        )
        self.assert_validate_fails("Relationsziel")

    def test_relation_to_non_markdown_file_is_rejected(self):
        (self.root / "knowledge/demo-okf/not-a-page.txt").write_text(
            "keine Wissensseite\n", encoding="utf-8"
        )
        self.replace_text(
            "knowledge/demo-okf/okf.md",
            "formalisiert -> demo-okf/llm-wiki-muster.md",
            "formalisiert -> demo-okf/not-a-page.txt",
        )
        self.assert_validate_fails("domäne/seite.md")

    def test_markdown_link_traversal_with_title_is_rejected(self):
        page = self.root / "knowledge/demo-okf/okf.md"
        page.write_text(
            page.read_text(encoding="utf-8")
            + '\n[unsicher](../../outside.md "Titel mit Leerzeichen")\n',
            encoding="utf-8",
        )
        self.assert_validate_fails("Markdown-Link")

    def test_reference_and_html_links_cannot_bypass_link_validation(self):
        variants = (
            "\n[ziel]: ../../outside.md\n[Text][ziel]\n",
            '\n<a href="../../outside.md">Text</a>\n',
        )
        for n, addition in enumerate(variants):
            with self.subTest(addition=addition):
                root = self.new_vault()
                page = root / "knowledge/demo-okf/okf.md"
                page.write_text(
                    page.read_text(encoding="utf-8") + addition,
                    encoding="utf-8",
                )
                result = self.run_cli("validate", root=root)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(
                    "Markdown-Link" if n == 0 else "HTML-Links",
                    result.stdout,
                )

    def test_route_rejects_traversing_router_entry(self):
        self.replace_text(
            "ROUTER.md",
            "- knowledge/demo-okf/okf.md",
            "- knowledge/demo-okf/../../../outside.md",
        )
        result = self.run_cli("route", "okf")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("→ knowledge/demo-okf/../../../outside.md", result.stdout)
        self.assertIn("fail-closed", result.stdout)

    def test_search_never_reads_symlinked_register(self):
        register = self.root / "sources/REGISTER.md"
        outside = self.work / "outside-register.md"
        marker = "TOPSECRET_SEARCH_ESCAPE"
        outside.write_text(marker + "\n", encoding="utf-8")
        register.unlink()
        register.symlink_to(outside)
        result = self.run_cli("search", marker)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn(marker, result.stdout)

    def test_empty_type_registry_is_rejected(self):
        (self.root / "schema/types.yaml").write_text(
            "# absichtlich leer\n", encoding="utf-8"
        )
        self.assert_validate_fails("keine Typen registriert")

    def test_incomplete_type_is_rejected(self):
        (self.root / "schema/types.yaml").write_text(
            "_relationstypen: [verweist_auf]\n\n"
            "konzept:\n"
            "  beschreibung: Test\n",
            encoding="utf-8",
        )
        self.assert_validate_fails("ohne Pflichtfelder")

    def test_missing_relation_types_are_rejected(self):
        types = self.root / "schema/types.yaml"
        types.write_text(
            types.read_text(encoding="utf-8").replace(
                "_relationstypen: [formalisiert, basiert_auf, praezisiert, "
                "ersetzt, verweist_auf, widerspricht]\n",
                "",
            ),
            encoding="utf-8",
        )
        self.assert_validate_fails("_relationstypen fehlt oder ist leer")

    def test_quarantine_payload_variants_block_validation_and_release(self):
        variants = ("hidden", "directory", "dangling-symlink")
        for variant in variants:
            with self.subTest(variant=variant):
                root = self.new_vault()
                quarantine = root / "sources/quarantine"
                if variant == "hidden":
                    (quarantine / ".payload").write_text("x", encoding="utf-8")
                elif variant == "directory":
                    (quarantine / "nested").mkdir()
                else:
                    (quarantine / "payload-link").symlink_to(self.work / "missing")
                before = self.snapshot(root)
                validate = self.run_cli("validate", root=root)
                release = self.run_cli("release", "patch", root=root)
                self.assertNotEqual(validate.returncode, 0, validate.stdout + validate.stderr)
                self.assertNotEqual(release.returncode, 0, release.stdout + release.stderr)
                self.assertEqual(before, self.snapshot(root))
                self.assertFalse((root / ".vault-release.lock").exists())
                checksum = self.run_cli("checksum", root=root)
                self.assertNotEqual(checksum.returncode, 0, checksum.stdout + checksum.stderr)

    def test_manifest_includes_only_trusted_quarantine_readme(self):
        manifest = (self.root / "MANIFEST.sha256").read_text(encoding="utf-8")
        quarantine_entries = [
            line for line in manifest.splitlines() if "sources/quarantine/" in line
        ]
        self.assertEqual(len(quarantine_entries), 1)
        self.assertTrue(quarantine_entries[0].endswith("sources/quarantine/README.md"))
        readme = self.root / "sources/quarantine/README.md"
        readme.write_text(
            readme.read_text(encoding="utf-8") + "\nveraendert\n",
            encoding="utf-8",
        )
        doctor = self.run_cli("doctor")
        self.assertNotEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)
        self.assertIn("GEÄNDERT sources/quarantine/README.md", doctor.stdout)

    def test_doctor_fails_for_missing_changed_new_and_malformed_manifest(self):
        cases = ("missing", "changed", "new", "malformed")
        for case in cases:
            with self.subTest(case=case):
                root = self.new_vault()
                if case == "missing":
                    (root / "MANIFEST.sha256").unlink()
                elif case == "changed":
                    with open(root / "KONZEPT.md", "a", encoding="utf-8") as stream:
                        stream.write("\nDrift\n")
                elif case == "new":
                    (root / "unexpected.md").write_text("neu\n", encoding="utf-8")
                else:
                    with open(root / "MANIFEST.sha256", "a", encoding="utf-8") as stream:
                        stream.write("keine-gueltige-zeile\n")
                result = self.run_cli("doctor", root=root)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("MANIFEST.sha256", result.stdout)
                self.assertIn("doctor:", result.stdout)

    def test_duplicate_manifest_path_is_rejected(self):
        manifest = self.root / "MANIFEST.sha256"
        first = manifest.read_text(encoding="utf-8").splitlines()[0]
        with open(manifest, "a", encoding="utf-8") as stream:
            stream.write(first + "\n")
        result = self.run_cli("checksum", "--verify")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("doppelt", result.stdout)

    def test_checksum_does_not_follow_manifest_symlink(self):
        manifest = self.root / "MANIFEST.sha256"
        outside = self.work / "outside-manifest"
        outside.write_text("nicht überschreiben\n", encoding="utf-8")
        manifest.unlink()
        manifest.symlink_to(outside)
        result = self.run_cli("checksum")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(outside.read_text(encoding="utf-8"), "nicht überschreiben\n")

    def test_checksum_rejects_nonportable_filename_and_hardlink(self):
        root = self.new_vault()
        old_manifest = (root / "MANIFEST.sha256").read_bytes()
        (root / "notes/bad\\name.md").write_text("nicht portabel\n", encoding="utf-8")
        result = self.run_cli("checksum", root=root)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((root / "MANIFEST.sha256").read_bytes(), old_manifest)

        root = self.new_vault()
        outside = self.work / "hardlink-source.md"
        outside.write_text("hardlink\n", encoding="utf-8")
        os.link(outside, root / "notes/hardlink.md")
        result = self.run_cli("checksum", root=root)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("hart verlinkte", result.stdout)

    def test_doctor_handles_non_utf8_manifest_without_traceback(self):
        (self.root / "MANIFEST.sha256").write_bytes(b"\xff\xfe\x00")
        result = self.run_cli("doctor")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("nicht als UTF-8 lesbar", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_unreadable_tree_error_cannot_create_partial_manifest(self):
        module = self.load_vault(self.root, "scandir_error")
        old_manifest = (self.root / "MANIFEST.sha256").read_bytes()
        original_scandir = module.os.scandir

        def deny_notes(path):
            if Path(path) == self.root / "notes":
                raise PermissionError("injected unreadable directory")
            return original_scandir(path)

        module.os.scandir = deny_notes
        output = io.StringIO()
        try:
            with contextlib.redirect_stdout(output):
                result = module.cmd_checksum(verify=False)
        finally:
            module.os.scandir = original_scandir
        self.assertEqual(result, 1, output.getvalue())
        self.assertEqual((self.root / "MANIFEST.sha256").read_bytes(), old_manifest)
        self.assertFalse((self.root / ".vault-release.lock").exists())

    def test_mutating_commands_respect_existing_lock(self):
        lock = self.root / ".vault-release.lock"
        lock.write_text("pid=someone-else\n", encoding="utf-8")
        for args in (
            ("index",),
            ("graph",),
            ("checksum",),
            ("log", "note", "test"),
            ("release", "patch"),
        ):
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(lock.read_text(encoding="utf-8"), "pid=someone-else\n")

    def test_log_rejects_header_injection(self):
        before = (self.root / "log.md").read_bytes()
        result = self.run_cli(
            "log", "note", "legitim\n## [2099-01-01] release | fake"
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.root / "log.md").read_bytes(), before)

    def test_invalid_version_leaves_release_outputs_unchanged(self):
        (self.root / "VERSION").write_text("nicht-semver\n", encoding="utf-8")
        before = self.snapshot(self.root)
        doctor = self.run_cli("doctor")
        self.assertNotEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)
        self.assertIn("kein SemVer", doctor.stdout)
        result = self.run_cli("release", "patch")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(before, self.snapshot(self.root))
        self.assertFalse((self.root / ".vault-release.lock").exists())

    def test_release_rolls_back_each_commit_position(self):
        for fail_at in range(1, len(RELEASE_TARGETS) + 1):
            with self.subTest(fail_at=fail_at):
                root = self.new_vault()
                before = self.snapshot(root)
                module = self.load_vault(root, f"replace_{fail_at}")
                original_replace = module.os.replace
                calls = {"count": 0}

                def fail_once(source, target, *args, **kwargs):
                    calls["count"] += 1
                    if calls["count"] == fail_at:
                        raise OSError(f"injected failure {fail_at}")
                    return original_replace(source, target, *args, **kwargs)

                output = io.StringIO()
                module.os.replace = fail_once
                try:
                    with contextlib.redirect_stdout(output):
                        result = module.cmd_release("patch")
                finally:
                    module.os.replace = original_replace

                self.assertEqual(result, 1, output.getvalue())
                self.assertEqual(before, self.snapshot(root))
                self.assertFalse((root / ".vault-release.lock").exists())
                verify = self.run_cli("checksum", "--verify", root=root)
                self.assertEqual(verify.returncode, 0, verify.stdout + verify.stderr)

    def test_release_detects_change_during_validation(self):
        before = self.snapshot(self.root)
        module = self.load_vault(self.root, "validation_race")
        original_validate = module.cmd_validate
        calls = {"count": 0}

        def mutate_after_validate(*args, **kwargs):
            result = original_validate(*args, **kwargs)
            calls["count"] += 1
            if calls["count"] == 1:
                with open(self.root / "KONZEPT.md", "a", encoding="utf-8") as stream:
                    stream.write("\nRace nach validate\n")
            return result

        module.cmd_validate = mutate_after_validate
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = module.cmd_release("patch")
        self.assertEqual(result, 1, output.getvalue())
        self.assertEqual(before, self.snapshot(self.root))
        self.assertIn("während der Validierung", output.getvalue())
        self.assertNotIn("transaktional veröffentlicht", output.getvalue())

    def test_release_postcheck_rolls_back_change_during_commit(self):
        before = self.snapshot(self.root)
        module = self.load_vault(self.root, "commit_race")
        original_replace = module.os.replace
        changed = {"done": False}

        def mutate_after_first_replace(source, target, *args, **kwargs):
            result = original_replace(source, target, *args, **kwargs)
            if target == "INDEX.md" and not changed["done"]:
                changed["done"] = True
                with open(self.root / "KONZEPT.md", "a", encoding="utf-8") as stream:
                    stream.write("\nRace im Commit\n")
            return result

        module.os.replace = mutate_after_first_replace
        output = io.StringIO()
        try:
            with contextlib.redirect_stdout(output):
                result = module.cmd_release("patch")
        finally:
            module.os.replace = original_replace
        self.assertEqual(result, 1, output.getvalue())
        self.assertEqual(before, self.snapshot(self.root))
        self.assertFalse((self.root / ".vault-release.lock").exists())
        self.assertNotIn("transaktional veröffentlicht", output.getvalue())

    def test_incomplete_rollback_keeps_recovery_lock(self):
        module = self.load_vault(self.root, "incomplete_rollback")
        original_replace = module.os.replace
        calls = {"count": 0}

        def fail_commit_and_rollback(source, target, *args, **kwargs):
            calls["count"] += 1
            if calls["count"] in {5, 7}:
                raise OSError(f"injected failure {calls['count']}")
            return original_replace(source, target, *args, **kwargs)

        module.os.replace = fail_commit_and_rollback
        output = io.StringIO()
        try:
            with contextlib.redirect_stdout(output):
                result = module.cmd_release("patch")
        finally:
            module.os.replace = original_replace
        self.assertEqual(result, 1, output.getvalue())
        self.assertIn("Rollback unvollständig", output.getvalue())
        self.assertNotIn("Vorheriger Stand bleibt erhalten", output.getvalue())
        lock = self.root / ".vault-release.lock"
        self.assertTrue(lock.exists())
        self.assertIn("recovery_required=", lock.read_text(encoding="utf-8"))
        doctor = self.run_cli("doctor")
        self.assertNotEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)

    def test_parent_directory_swap_never_writes_through_symlink(self):
        module = self.load_vault(self.root, "parent_swap")
        original_replace = module.os.replace
        graph_dir = self.root / "graph"
        saved_graph = self.root / "graph-original"
        outside = self.work / "outside-graph"
        outside.mkdir()
        outside_graph = outside / "graph.json"
        outside_graph.write_text("AUSSEN UNVERÄNDERT\n", encoding="utf-8")
        swapped = {"done": False}

        def swap_parent(source, target, *args, **kwargs):
            if target == "graph.json" and not swapped["done"]:
                swapped["done"] = True
                graph_dir.rename(saved_graph)
                graph_dir.symlink_to(outside, target_is_directory=True)
            return original_replace(source, target, *args, **kwargs)

        module.os.replace = swap_parent
        output = io.StringIO()
        try:
            with contextlib.redirect_stdout(output):
                result = module.cmd_release("patch")
        finally:
            module.os.replace = original_replace
        self.assertEqual(result, 1, output.getvalue())
        self.assertEqual(
            outside_graph.read_text(encoding="utf-8"),
            "AUSSEN UNVERÄNDERT\n",
        )
        self.assertTrue((self.root / ".vault-release.lock").exists())

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO nur auf POSIX")
    def test_fifo_release_target_is_rejected_without_blocking(self):
        index = self.root / "INDEX.md"
        index.unlink()
        os.mkfifo(index)
        result = self.run_cli("release", "patch")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("transaktional veröffentlicht", result.stdout)

    def test_successful_release_is_self_consistent(self):
        old = tuple(int(part) for part in (self.root / "VERSION").read_text().split("."))
        release = self.run_cli("release", "patch")
        self.assertEqual(release.returncode, 0, release.stdout + release.stderr)
        new = tuple(int(part) for part in (self.root / "VERSION").read_text().split("."))
        self.assertEqual(new, (old[0], old[1], old[2] + 1))
        verify = self.run_cli("checksum", "--verify")
        doctor = self.run_cli("doctor")
        self.assertEqual(verify.returncode, 0, verify.stdout + verify.stderr)
        self.assertEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)
        self.assertFalse((self.root / ".vault-release.lock").exists())

    def test_release_preserves_restrictive_file_modes(self):
        log = self.root / "log.md"
        log.chmod(0o600)
        release = self.run_cli("release", "patch")
        self.assertEqual(release.returncode, 0, release.stdout + release.stderr)
        self.assertEqual(stat.S_IMODE(log.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
