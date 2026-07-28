#!/usr/bin/env python3
"""Prüft, ob die in README.md und index.html veröffentlichten Zahlen noch stimmen.

In dieser Form ist das Wächterarbeit, die sonst niemand macht: README und
Landingpage nennen Version, Bestandszahlen, Testzahl, Paketeinträge und den
SHA-256 des reproduzierbaren Pakets. Alle sechs sind an echte Ausgabe
gekoppelt, und genau solche Kopplungen veralten still.

Read-only, nur Standardbibliothek, kein Schreibzugriff auf das Repository.
Läuft aus der Repository-Wurzel:

    python3 tools/check_docs.py

Exit 0, wenn alles übereinstimmt, sonst 1 mit einer Liste der Abweichungen.
"""

import re
import subprocess
import tempfile
import sys
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
SKILL = REPOSITORY / "wissenstresor"
README = REPOSITORY / "README.md"
LANDING = REPOSITORY / "index.html"


def lauf(argv, cwd):
    ergebnis = subprocess.run(
        [sys.executable, "-B", *argv],
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=120,
    )
    return ergebnis.returncode, ergebnis.stdout + ergebnis.stderr


def ist_stand():
    """Die echten Werte einsammeln. Kein Schreibkommando."""
    stand = {}
    stand["version"] = (SKILL / "VERSION").read_text(encoding="utf-8").strip()

    rc, stats = lauf(["scripts/vault.py", "stats"], SKILL)
    if rc != 0:
        raise SystemExit(f"stats ist rot, erst den Bestand reparieren:\n{stats}")
    treffer = re.search(
        r"(\d+) Seiten, (\d+) Claims, (\d+) Quellen, (\d+) Kanten", stats
    )
    if not treffer:
        raise SystemExit(f"stats-Ausgabe nicht lesbar:\n{stats}")
    stand["seiten"], stand["claims"], stand["quellen"], stand["kanten"] = (
        int(wert) for wert in treffer.groups()
    )

    rc, verify = lauf(["scripts/vault.py", "checksum", "--verify"], SKILL)
    if rc != 0:
        raise SystemExit(f"checksum --verify ist rot:\n{verify}")
    treffer = re.search(r"verify: (\d+) Dateien", verify)
    stand["manifest"] = int(treffer.group(1)) if treffer else None

    rc, tests = lauf(["-m", "unittest", "discover", "-s", "tests", "-t", "."],
                     REPOSITORY)
    if rc != 0:
        raise SystemExit(f"Testsuite ist rot:\n{tests[-2000:]}")
    treffer = re.search(r"Ran (\d+) tests", tests)
    stand["tests"] = int(treffer.group(1)) if treffer else None

    # Bewusst in ein Temporärverzeichnis: der Wächter ist read-only und darf
    # weder dist/ anfassen noch an einem vorhandenen Archiv scheitern.
    with tempfile.TemporaryDirectory(prefix="skillsafe-check-docs-") as temp:
        ziel = Path(temp) / "pruefpaket.skill"
        rc, paket = lauf(
            ["tools/build_skill_package.py", "--output", str(ziel)], REPOSITORY
        )
    if rc != 0:
        raise SystemExit(f"Paketbau ist rot:\n{paket}")
    stand["paket_sha"] = re.search(r"sha256: ([0-9a-f]{64})", paket).group(1)
    stand["paket_dateien"] = int(re.search(r"files: (\d+)", paket).group(1))
    return stand


def pruefe(stand):
    readme = README.read_text(encoding="utf-8")
    landing = LANDING.read_text(encoding="utf-8")
    abweichungen = []

    def verlange(text, muster, name, erwartet, datei):
        gefunden = re.search(muster, text)
        if not gefunden:
            abweichungen.append(f"{datei}: {name} nicht gefunden (Muster {muster!r})")
            return
        ist = gefunden.group(1)
        if str(ist) != str(erwartet):
            abweichungen.append(
                f"{datei}: {name} steht auf {ist!r}, echt ist {erwartet!r}"
            )

    verlange(readme, r"\*\*Aktueller Release: v([0-9.]+)\*\*", "Version",
             stand["version"], "README.md")
    verlange(readme, r"Abnahme: (\d+) Tests bestanden", "Testzahl",
             stand["tests"], "README.md")
    verlange(readme, r"Tests bestanden · (\d+) manifestierte Dateien",
             "manifestierte Dateien", stand["manifest"], "README.md")
    verlange(readme, r"manifestierte Dateien · (\d+) sichere", "Paketeinträge",
             stand["paket_dateien"], "README.md")
    verlange(readme, r"`([0-9a-f]{64})`", "Paket-SHA-256",
             stand["paket_sha"], "README.md")
    verlange(readme, r"Herkunft des Tresors mit seinen eigenen Mitteln: (\d+) Seiten",
             "Seiten", stand["seiten"], "README.md")
    verlange(readme, r"eigenen Mitteln: \d+ Seiten, (\d+) Claims", "Claims",
             stand["claims"], "README.md")

    verlange(landing, r'href="#funktionen">Was v([0-9.]+) kann</a>', "Version (CTA)",
             stand["version"], "index.html")
    verlange(landing, r"Claims<br>v([0-9.]+)</span>", "Version (Stempel)",
             stand["version"], "index.html")
    verlange(landing, r"<span>SkillSafe v([0-9.]+) ·", "Version (Footer)",
             stand["version"], "index.html")
    verlange(landing, r"verify: (\d+) Dateien unverändert", "manifestierte Dateien",
             stand["manifest"], "index.html")
    verlange(landing, r"(\d+) Seiten / \d+ Claims / \d+ Quellen", "Seiten (doctor)",
             stand["seiten"], "index.html")
    verlange(landing, r"\d+ Seiten / (\d+) Claims / \d+ Quellen", "Claims (doctor)",
             stand["claims"], "index.html")
    verlange(landing, r"\d+ Seiten / \d+ Claims / (\d+) Quellen", "Quellen (doctor)",
             stand["quellen"], "index.html")
    return abweichungen


def main():
    stand = ist_stand()
    abweichungen = pruefe(stand)
    if abweichungen:
        print("🔴 check-docs: veröffentlichte Zahlen weichen ab.")
        for eintrag in abweichungen:
            print(f"   {eintrag}")
        print("\nEchter Stand:")
        for schluessel, wert in sorted(stand.items()):
            print(f"   {schluessel}: {wert}")
        return 1
    print(f"🟢 check-docs: {len(stand)} Werte geprüft, README.md und "
          f"index.html stimmen mit der echten Ausgabe überein.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
