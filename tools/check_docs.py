#!/usr/bin/env python3
"""Prüft, ob die in README.md und index.html veröffentlichten Zahlen noch stimmen.

In dieser Form ist das Wächterarbeit, die sonst niemand macht: README und
Landingpage nennen Version, Bestandszahlen, Testzahl, Paketeinträge, den
SHA-256 des reproduzierbaren Pakets und die Messwerte der Suche. Alle sind an
echte Ausgabe gekoppelt, und genau solche Kopplungen veralten still.

Read-only, nur Standardbibliothek, kein Schreibzugriff auf das Repository.
Läuft aus der Repository-Wurzel:

    python3 tools/check_docs.py

Exit 0, wenn alles übereinstimmt, sonst 1 mit einer Liste der Abweichungen.
"""

import importlib.util
import json
import re
import subprocess
import tempfile
import sys
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
SKILL = REPOSITORY / "wissenstresor"
README = REPOSITORY / "README.md"
LANDING = REPOSITORY / "index.html"
RECALL_TOOL = REPOSITORY / "tools" / "recall_check.py"
E2E_ORDNER = REPOSITORY / "tests" / "e2e"
# Zeilenbeschriftung der veröffentlichten Messtabelle je Fragengruppe.
RECALL_ZEILEN = {
    "entwicklung": "Jetzt, eigene Fragen",
    "kontrolle": "Jetzt, blinde Kontrolle",
}


def lauf(argv, cwd, timeout=120):
    ergebnis = subprocess.run(
        [sys.executable, "-B", *argv],
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
    )
    return ergebnis.returncode, ergebnis.stdout + ergebnis.stderr


def recall_stand():
    """Die Messwerte der Suche, mit demselben Werkzeug wie von Hand."""
    spec = importlib.util.spec_from_file_location("skillsafe_recall", RECALL_TOOL)
    werkzeug = importlib.util.module_from_spec(spec)
    vorher = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(werkzeug)
    finally:
        sys.dont_write_bytecode = vorher
    fragen, _ = werkzeug.lade_gold(werkzeug.STANDARD_GOLD, SKILL)
    sichtung = werkzeug.sichtung_pruefen(SKILL, fragen[0]["frage"])
    zeilen, _ = werkzeug.messe(SKILL, fragen, [], 8, sichtung["seite_von"])
    werte = {}
    for gruppe in RECALL_ZEILEN:
        zahl = werkzeug.zusammenfassung(
            [zeile for zeile in zeilen if zeile["gruppe"] == gruppe])
        werte[gruppe] = (zahl["gesamt"], zahl["treffer"], zahl["pflicht"],
                         zahl["hinweis"], zahl["still"])
    return werte


def e2e_stand():
    """Die Zahlen der Ende-zu-Ende-Läufe, aus den Protokollen unter tests/e2e/.

    Nachrechnen lassen sie sich nur gegen den Stand, an den ihre Siegel
    gebunden sind (tests/e2e/LIESMICH.md). Hier wird deshalb nicht neu
    gemessen, sondern gebunden: Was README und Landingpage nennen, muss dem
    'ergebnis' entsprechen, das tools/antwort_check.py zum Messzeitpunkt in
    das Protokoll geschrieben hat.
    """
    werte = {}
    for datei in sorted(E2E_ORDNER.glob("runde-*.json")):
        daten = json.loads(datei.read_text(encoding="utf-8"))
        ergebnis = daten["ergebnis"]
        werte[int(daten["runde"])] = tuple(ergebnis[feld] for feld in (
            "antworten", "positiv", "positiv_gefunden", "vom_ranking_verfehlt",
            "davon_gefunden", "negativ", "negativ_korrekt", "verstoesse"))
    if not werte:
        raise SystemExit(f"Unter {E2E_ORDNER} liegt kein Protokoll runde-*.json")
    return werte


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

    # Die Suite braucht länger als jedes einzelne Kommando; auf einem
    # langsamen Runner lag sie schon vor der Recall-Messung nahe an 120 s.
    rc, tests = lauf(["-m", "unittest", "discover", "-s", "tests", "-t", "."],
                     REPOSITORY, timeout=900)
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

    # Externe Zaehler stehen bewusst auf einer eigenen stats-Zeile: ein
    # zusaetzliches Feld in der Kopfzeile haette den Waechter an der eigenen
    # Erweiterung brechen lassen.
    treffer = re.search(
        r"Externe Bezugsquellen: (\d+), Satzanker: (\d+), Kataloge: (\d+)", stats
    )
    if not treffer:
        raise SystemExit(f"stats nennt keine externen Zahlen:\n{stats}")
    stand["extern"], stand["anker"], stand["kataloge"] = (
        int(wert) for wert in treffer.groups()
    )
    for gruppe, werte in recall_stand().items():
        stand[f"recall_{gruppe}"] = werte
    for runde, werte in e2e_stand().items():
        stand[f"e2e_runde_{runde}"] = werte
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
    verlange(readme, r"(\d+) aufgeführte externe Bezugsquellen",
             "externe Bezugsquellen", stand["extern"], "README.md")
    verlange(readme, r"externe Bezugsquellen · (\d+) Satzanker", "Satzanker",
             stand["anker"], "README.md")

    # Messwerte der Suche: Fragen, direkt gefunden, Pflicht-Vollsichtung, nur
    # Hinweis, still verfehlt. Die Zeile "Vorher" steht bewusst nicht hier:
    # sie ist ein einmaliger Messwert des abgelösten Rankings.
    def verlange_zeile(text, muster, name, erwartet, datei):
        gefunden = re.search(muster, text)
        if not gefunden:
            abweichungen.append(f"{datei}: {name} nicht gefunden (Muster {muster!r})")
            return
        ist = tuple(int(wert) for wert in gefunden.groups())
        if ist != tuple(erwartet):
            abweichungen.append(
                f"{datei}: {name} steht auf {ist!r}, echt ist {tuple(erwartet)!r}"
            )

    zahlen = r" \| (\d+) \| (\d+) \| (\d+) \| (\d+) \| \*\*(\d+)\*\* \|"
    zellen = "".join([r"<td>(\d+)</td>"] * 5)
    for gruppe, beschriftung in RECALL_ZEILEN.items():
        erwartet = stand[f"recall_{gruppe}"]
        verlange_zeile(readme, r"\| " + re.escape(beschriftung) + zahlen,
                       f"Messwerte {gruppe!r}", erwartet, "README.md")
        verlange_zeile(landing, "<td>" + re.escape(beschriftung) + "</td>" + zellen,
                       f"Messwerte {gruppe!r}", erwartet, "index.html")

    # Ende-zu-Ende-Läufe. README führt alle acht Zahlen je Runde, die
    # Landingpage fünf davon: Fragen, gefunden, davon nach verfehltem Ranking,
    # korrekt abgelehnt, Verstöße. Dort heißt die Zeile nur "Runde n", damit
    # die Tabelle auf einem Telefon nicht umbricht.
    acht = (r" \| v[0-9.]+" + r" \| (\d+)" * 7 + r" \| \*\*(\d+)\*\* \|")
    for schluessel in sorted(key for key in stand if key.startswith("e2e_runde_")):
        runde = schluessel.rsplit("_", 1)[1]
        werte = stand[schluessel]
        beschriftung = f"Ende zu Ende, Runde {runde}"
        verlange_zeile(readme, r"\| " + re.escape(beschriftung) + acht,
                       f"Ende-zu-Ende-Runde {runde}", werte, "README.md")
        verlange_zeile(landing, f"<td>Runde {runde}</td>" + zellen,
                       f"Ende-zu-Ende-Runde {runde}",
                       (werte[0], werte[2], werte[4], werte[6], werte[7]),
                       "index.html")
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
