#!/usr/bin/env python3
"""Abnahme des tatsächlich ausgelieferten, nicht neu manifestierten Skills."""

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
SOURCE_SKILL = REPOSITORY / "wissenstresor"
PACKAGE_BUILDER = REPOSITORY / "tools/build_skill_package.py"


class PackagedVaultTests(unittest.TestCase):
    def test_checked_in_skill_and_claude_style_install_are_green(self):
        direct = subprocess.run(
            [sys.executable, "-B", str(SOURCE_SKILL / "scripts/vault.py"), "doctor"],
            cwd=SOURCE_SKILL,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=15,
        )
        self.assertEqual(direct.returncode, 0, direct.stdout + direct.stderr)
        self.assertIn("🟢 doctor:", direct.stdout)

        with tempfile.TemporaryDirectory(prefix="claude-skill-smoke-") as temp:
            temp_root = Path(temp)
            installed = temp_root / ".claude/skills/wissenstresor"
            project = temp_root / "fremdes projekt"
            installed.parent.mkdir(parents=True)
            project.mkdir()
            shutil.copytree(SOURCE_SKILL, installed)
            env = os.environ.copy()
            env["CLAUDE_SKILL_DIR"] = str(installed)
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            claude_style = subprocess.run(
                [
                    "/bin/sh",
                    "-c",
                    'python3 -B "$CLAUDE_SKILL_DIR/scripts/vault.py" doctor',
                ],
                cwd=project,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=15,
            )
            self.assertEqual(
                claude_style.returncode,
                0,
                claude_style.stdout + claude_style.stderr,
            )
            self.assertIn("🟢 doctor:", claude_style.stdout)

    def test_skill_archives_are_reproducible_and_query_from_claude_path(self):
        with tempfile.TemporaryDirectory(prefix="skillsafe-package-test-") as temp:
            temp_root = Path(temp)
            first = temp_root / "first.skill"
            second = temp_root / "second.skill"
            for target in (first, second):
                built = subprocess.run(
                    [
                        sys.executable, "-B", str(PACKAGE_BUILDER),
                        "--skill", str(SOURCE_SKILL),
                        "--output", str(target),
                    ],
                    cwd=REPOSITORY,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                    timeout=30,
                )
                self.assertEqual(
                    built.returncode, 0, built.stdout + built.stderr
                )
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(
                hashlib.sha256(first.read_bytes()).hexdigest(),
                hashlib.sha256(second.read_bytes()).hexdigest(),
            )
            with zipfile.ZipFile(first) as archive:
                self.assertIsNone(archive.testzip())
                names = archive.namelist()
                self.assertTrue(names)
                self.assertEqual(len(names), len(set(names)))
                self.assertTrue(all(name.startswith("wissenstresor/") for name in names))
                self.assertFalse(any("/tests/" in name for name in names))
                self.assertFalse(any("__pycache__" in name for name in names))
                self.assertFalse(any(".vault-release.lock" in name for name in names))

                claude_skills = temp_root / "install/.claude/skills"
                claude_skills.mkdir(parents=True)
                archive.extractall(claude_skills)
            installed = claude_skills / "wissenstresor"
            project = temp_root / "foreign-project"
            trap = project / "scripts/vault.py"
            trap.parent.mkdir(parents=True)
            trap.write_text(
                "from pathlib import Path\nPath('TRAP_RAN').write_text('bad')\n",
                encoding="utf-8",
            )
            query = subprocess.run(
                [
                    sys.executable, "-B", str(installed / "scripts/vault.py"),
                    "query", "OKF",
                ],
                cwd=project,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=20,
            )
            self.assertEqual(query.returncode, 0, query.stdout + query.stderr)
            payload = json.loads(query.stdout)
            self.assertEqual(payload["state"], "candidates_found")
            self.assertEqual(payload["evidence"][0]["claim_id"], "C-0001")
            self.assertFalse((project / "TRAP_RAN").exists())


    def test_package_allowlist_is_an_independent_second_gate(self):
        """Der Paketbau prüft Dateiarten selbst, ohne das verpackte Script."""
        spec = importlib.util.spec_from_file_location(
            "skillsafe_builder", PACKAGE_BUILDER
        )
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        with tempfile.TemporaryDirectory(prefix="skillsafe-allowlist-") as temp:
            skill = Path(temp) / "wissenstresor"
            shutil.copytree(SOURCE_SKILL, skill)
            self.assertTrue(builder.collect_files(skill))

            attester = skill / "references/attesters/revenue.py"
            attester.parent.mkdir(parents=True)
            attester.write_text("print('attester')\n", encoding="utf-8")
            with self.assertRaises(ValueError) as fremd:
                builder.collect_files(skill)
            self.assertIn("gehört nicht ins Paket", str(fremd.exception))
            attester.unlink()
            attester.parent.rmdir()

            os.chmod(skill / "SKILL.md", 0o755)
            with self.assertRaises(ValueError) as ausfuehrbar:
                builder.collect_files(skill)
            self.assertIn("ausführbare Datei", str(ausfuehrbar.exception))


    def test_binding_never_reaches_the_package_and_never_moves_the_hash(self):
        """Zweites, unabhaengiges Gate: host-lokale Dateien bleiben draussen.

        Rutscht .vault-extern.json in Manifest ODER Archiv, wird die
        reproduzierbare Paket-SHA-256 maschinenabhaengig — und check_docs.py
        schlaegt dann ueberall fehl.
        """
        spec = importlib.util.spec_from_file_location(
            "skillsafe_builder_binding", PACKAGE_BUILDER
        )
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        with tempfile.TemporaryDirectory(prefix="skillsafe-binding-") as temp:
            skill = Path(temp) / "wissenstresor"
            shutil.copytree(SOURCE_SKILL, skill)
            vorher = [relativ for relativ, _ in builder.collect_files(skill)]
            (skill / ".vault-extern.json").write_text(
                '{"schema": "skillsafe.bindung/v1", "bindings": [], '
                '"cache_ttl_seconds": 21600}\n',
                encoding="utf-8",
            )
            nachher = [relativ for relativ, _ in builder.collect_files(skill)]
            self.assertEqual(vorher, nachher)
            self.assertNotIn(".vault-extern.json", nachher)

    def test_unbound_external_source_answers_offline_with_exit_code_zero(self):
        """Ein frisch entpacktes Paket ist ungebunden — und trotzdem gruen."""
        with tempfile.TemporaryDirectory(prefix="skillsafe-unbound-") as temp:
            ziel = Path(temp) / "projekt/.claude/skills"
            ziel.mkdir(parents=True)
            skill = ziel / "wissenstresor"
            shutil.copytree(SOURCE_SKILL, skill)
            # Ein Paket enthaelt die host-lokale Bindung nie; im Arbeitsbaum
            # kann sie liegen, deshalb hier den Auslieferungszustand herstellen.
            binding = skill / ".vault-extern.json"
            if binding.exists():
                binding.unlink()
            umgebung = os.environ.copy()
            umgebung["PYTHONDONTWRITEBYTECODE"] = "1"
            umgebung["SKILLSAFE_OFFLINE"] = "1"

            def lauf(*args):
                return subprocess.run(
                    [sys.executable, "-B", str(skill / "scripts/vault.py"), *args],
                    cwd=skill, env=umgebung, text=True, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, check=False, timeout=30,
                )

            regulaer = lauf("query", "Was ist OKF?")
            self.assertEqual(regulaer.returncode, 0, regulaer.stdout + regulaer.stderr)
            payload = json.loads(regulaer.stdout)
            self.assertEqual(payload["state"], "candidates_found")
            self.assertEqual(payload["external"]["state"], "not_requested")

            extern = lauf("query", "--extern", "Was ist OKF?")
            self.assertEqual(extern.returncode, 0, extern.stdout + extern.stderr)
            block = json.loads(extern.stdout)["external"]
            self.assertIn(block["state"],
                          {"no_external_candidates", "external_candidates_found"})
            hinweise = " ".join(block["notes"])
            self.assertTrue(
                "nicht gebunden" in hinweise or "SKILLSAFE_OFFLINE" in hinweise,
                hinweise,
            )


if __name__ == "__main__":
    unittest.main()
