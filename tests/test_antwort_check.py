#!/usr/bin/env python3
"""Abnahme für tools/antwort_check.py.

Das Werkzeug wertet aus, ob ein Agent dem Antworten-Vertrag gefolgt ist. Es
darf dabei nichts glauben, was der Agent über sich selbst sagt: Geprüft wird
hier deshalb vor allem, dass es Verstöße findet, die ein Protokoll verschweigt.
"""

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
SOURCE_SKILL = REPOSITORY / "wissenstresor"
TOOL = REPOSITORY / "tools/antwort_check.py"
SCHEMA = "skillsafe.antwort-protokoll/v1"

# Eine Umschreibung, die das Ranking verfehlt: C-0002 nennt den Dateipfad
# als Identität, die Frage benutzt kein Wort davon.
UMSCHREIBUNG = ("Welche Adresse fungiert als dauerhafter Schlüssel einer "
                "Wissenseinheit?")
NEGATIV = "Wie hoch ist der Urlaubsanspruch in Teilzeit?"
BEGRIFF = "Welche Vertrauensstufen gibt es?"
# Seit v0.17.0 ist Schritt 4c Pflicht, sobald nach der Vollsichtung etwas
# ungedeckt bleibt. Im Testtresor ist X-0001 nicht gebunden und X-0002 hinter
# dem Offline-Schalter: Gelesen wird nichts, und genau das steht in der Zeile.
EXTERN = ("Extern nicht gelesen: X-0001 (nicht gebunden), X-0002 "
          "(SKILLSAFE_OFFLINE gesetzt), Zustand unreachable — kein "
          "Negativbefund")


def _cli(root, *args, umgebung=None):
    return subprocess.run(
        [sys.executable, "-B", str(root / "scripts/vault.py"), *args],
        cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False, timeout=60,
        env=dict(os.environ, **umgebung) if umgebung else None,
    )


def _extern(root, frage):
    """external aus query --extern, mit gesetztem Offline-Schalter; ohne JSON
    mit der Ausgabe der Engine als Meldung."""
    lauf = _cli(root, "query", "--extern", frage,
                umgebung={"SKILLSAFE_OFFLINE": "1"})
    try:
        return json.loads(lauf.stdout)["external"]
    except ValueError as exc:
        raise AssertionError(lauf.stdout + lauf.stderr) from exc


def _werkzeug(name):
    """Das Werkzeug als Modul, geladen ohne Bytecode."""
    spec = importlib.util.spec_from_file_location(name, TOOL)
    modul = importlib.util.module_from_spec(spec)
    vorher = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(modul)
    finally:
        sys.dont_write_bytecode = vorher
    return modul


def tool_urteil(zeile):
    """Das Urteil, wie das Werkzeug es druckt (geladen ohne Bytecode)."""
    return _werkzeug("antwort_check_urteil").urteil(zeile)


class AntwortCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tempdir = tempfile.TemporaryDirectory(prefix="skillsafe-antwort-")
        cls.basis = Path(cls._tempdir.name)
        cls.root = cls.basis / "wissenstresor"
        shutil.copytree(SOURCE_SKILL, cls.root)
        result = _cli(cls.root, "release", "patch")
        if result.returncode != 0:
            raise AssertionError(result.stdout + result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls._tempdir.cleanup()

    def sichtung(self, frage, auswahl=(), groesse=None, root=None):
        """Eine echte Vollsichtung fahren: Quittungseinträge und Ergebnis."""
        root = root or self.root
        extra = ["--size", str(groesse)] if groesse else []
        plan = json.loads(_cli(root, "sweep", frage, *extra).stdout)
        eintraege = []
        for stapel in plan["batches"]:
            ausgabe = json.loads(_cli(
                root, "sweep", frage, *extra,
                "--batch", str(stapel["batch"])).stdout)
            ids = [claim["claim_id"] for seite in ausgabe["pages"]
                   for claim in seite["claims"]]
            gewaehlt = [cid for cid in ids if cid in auswahl]
            eintraege.append(
                f"{stapel['batch']}:{ausgabe['seal']}="
                + (",".join(gewaehlt) if gewaehlt else "-"))
        fertig = json.loads(_cli(
            root, "sweep", frage, *extra, "--receipt", *eintraege).stdout)
        self.assertEqual(fertig["state"], "sweep_complete", fertig)
        return eintraege, fertig

    def zeile_sichtung(self, fertig):
        abdeckung = fertig["coverage"]
        return (f"Sichtung: {abdeckung['claims_swept']} von "
                f"{abdeckung['claims_total']} Claims, Quittung "
                f"{fertig['sweep_fingerprint'][:12]}")

    def pruefe(self, antworten, stand=None, argumente=(), ort=None,
               vault=None, cwd=None, offline=True):
        ziel = ort or (self.basis / f"protokoll-{self.id().split('.')[-1]}.json")
        daten = {"schema": SCHEMA, "antworten": antworten}
        if stand is not None:
            daten["stand"] = stand
        ziel.write_text(json.dumps(daten, ensure_ascii=False), encoding="utf-8")
        # Die Nachprüfung von Schritt 4c hängt am Offline-Schalter der
        # Umgebung; ohne Angabe läuft sie wie in der CI offline.
        umgebung = dict(os.environ)
        if offline:
            umgebung["SKILLSAFE_OFFLINE"] = "1"
        else:
            umgebung.pop("SKILLSAFE_OFFLINE", None)
        result = subprocess.run(
            [sys.executable, "-B", str(TOOL), "--vault",
             str(vault or self.root), "--antworten", str(ziel), *argumente],
            cwd=cwd or REPOSITORY, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False, timeout=180, env=umgebung,
        )
        return result

    def saubere_antworten(self):
        positiv, fertig = self.sichtung(UMSCHREIBUNG, {"C-0001", "C-0002"})
        negativ, leer = self.sichtung(NEGATIV)
        return [
            {"id": "P1", "art": "positiv", "frage": UMSCHREIBUNG,
             "erwartet": ["C-0002"], "quittung": positiv,
             "antwort": "Laut Bestand der Dateipfad: Er ist die Identität "
                        "eines Konzepts (C-0002), und jede Datei beschreibt "
                        "genau eines (C-0001).\n\n"
                        "Belege:\n- C-0002 (S-0001, How it works, Wortlaut)"
                        "\n\n" + self.zeile_sichtung(fertig)},
            {"id": "N1", "art": "negativ", "frage": NEGATIV, "quittung": negativ,
             "antwort": "Nicht im Bestand. Der Tresor enthält keine Aussage "
                        "zum Urlaubsanspruch.\n" + EXTERN + "\n"
                        + self.zeile_sichtung(leer)},
            {"id": "B1", "frage": BEGRIFF, "erwartet": ["C-0305"],
             "antwort": "Laut Bestand gibt es vier Stufen (C-0305)."},
        ]

    def test_a_clean_run_passes_and_reports_what_it_recomputed(self):
        result = self.pruefe(self.saubere_antworten())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("kein Verstoß", result.stdout)
        self.assertIn("Antworten: 3, davon ohne Verstoß 3", result.stdout)
        self.assertIn("davon vom Ranking verfehlt      1, "
                      "trotzdem gefunden 1", result.stdout)
        self.assertIn("korrekt abgelehnt 1", result.stdout)
        # Die Begriffsfrage ist 'strong': keine Pflicht, keine Quittung nötig.
        self.assertIn("Quittungen eingereicht          2, "
                      "gültig und vollständig 2", result.stdout)

        maschine = self.pruefe(self.saubere_antworten(), argumente=["--json"])
        self.assertEqual(maschine.returncode, 0, maschine.stdout)
        daten = json.loads(maschine.stdout)
        self.assertEqual(daten["zusammenfassung"]["verstoesse"], 0)
        self.assertEqual(
            [zeile["pflicht"] for zeile in daten["zeilen"]],
            [True, True, False])
        self.assertEqual(daten["zeilen"][2]["staerke"], "strong")
        self.assertEqual(daten["zeilen"][0]["ausgewaehlt"], ["C-0001", "C-0002"])
        self.assertFalse(daten["zeilen"][0]["ranking_trifft"])

    def test_abstention_needs_a_receipt_no_matter_what_the_answer_says(self):
        """Der Agent behauptet eine Sichtung, reicht aber keine Quittung ein."""
        result = self.pruefe([{
            "id": "N1", "art": "negativ", "frage": NEGATIV,
            "antwort": "Nicht im Bestand.\nSichtung: 28 von 28 Claims, "
                       "Quittung 0123456789ab",
        }])
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("ohne vollständige Quittung", result.stdout)
        self.assertIn("Vollsichtung war Pflicht", result.stdout)
        # Abgelehnt ist nicht korrekt abgelehnt: Ohne Deckung zählt die
        # Antwort auch in der Zusammenfassung nicht mit.
        self.assertIn("abgelehnt ohne Deckung", result.stdout)
        self.assertIn("korrekt abgelehnt 0", result.stdout)
        # Dasselbe mit einer gültigen Quittung über nur einen Teil des
        # Bestands: Sie erlaubt keine Abstention.
        teil = json.loads(_cli(
            self.root, "sweep", NEGATIV, "--domain", "demo-extern",
            "--batch", "1").stdout)
        teilweise = self.pruefe([{
            "id": "N1", "art": "negativ", "frage": NEGATIV,
            "sweep_args": ["--domain", "demo-extern"],
            "quittung": [f"1:{teil['seal']}=-"],
            "antwort": "Nicht im Bestand.\nSichtung: Domäne demo-extern, "
                       "2 von 28 Claims",
        }], argumente=["--json"])
        self.assertEqual(teilweise.returncode, 1, teilweise.stdout)
        daten = json.loads(teilweise.stdout)
        self.assertEqual(daten["zeilen"][0]["quittung_state"], "sweep_complete")
        self.assertFalse(daten["zeilen"][0]["abstention_erlaubt"])
        self.assertEqual(daten["zusammenfassung"]["negativ_korrekt"], 0)

    def test_a_skipped_mandatory_sweep_is_found_even_in_a_right_answer(self):
        """Richtig geraten ist nicht gesichtet: 'weak' verlangt die Quittung."""
        result = self.pruefe([{
            "id": "P1", "art": "positiv", "frage": UMSCHREIBUNG,
            "erwartet": ["C-0002"],
            "antwort": "Der Dateipfad ist die Identität (C-0002).",
        }])
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("Vollsichtung war Pflicht", result.stdout)
        self.assertIn("gefunden", result.stdout)

    def test_receipts_are_rerun_not_believed(self):
        echte, fertig = self.sichtung(NEGATIV)
        faelle = {
            "falsches Siegel": ["1:0000000000000000=-"],
            "Siegel einer anderen Frage": self.sichtung(UMSCHREIBUNG)[0],
            "kaputte Form": ["1=-"],
        }
        for name, quittung in faelle.items():
            with self.subTest(fall=name):
                result = self.pruefe([{
                    "id": "N1", "art": "negativ", "frage": NEGATIV,
                    "quittung": quittung,
                    "antwort": "Nicht im Bestand.\n" + self.zeile_sichtung(fertig),
                }])
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn("Quittung ist nicht gültig und vollständig",
                              result.stdout)
        # Nur ein Teil des Bestands gesichtet: gültig, erlaubt aber nichts.
        teil = json.loads(_cli(
            self.root, "sweep", NEGATIV, "--domain", "demo-extern",
            "--batch", "1").stdout)
        result = self.pruefe([{
            "id": "N1", "art": "negativ", "frage": NEGATIV,
            "sweep_args": ["--domain", "demo-extern"],
            "quittung": [f"1:{teil['seal']}=-"],
            "antwort": "Nicht im Bestand.\nSichtung: Domäne demo-extern, "
                       "2 von 28 Claims",
        }])
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("die eine Abstention erlaubt", result.stdout)

    def test_the_sweep_line_must_match_the_receipt(self):
        quittung, fertig = self.sichtung(NEGATIV)
        faelle = {
            "fehlt": ("Nicht im Bestand.", "Zeile „Sichtung:\" fehlt"),
            "andere Zahlen": (
                "Nicht im Bestand.\nSichtung: 27 von 28 Claims",
                "nennt 27 von 28 Claims, die Quittung belegt 28 von 28"),
            "fremde Kennung": (
                "Nicht im Bestand.\nSichtung: 28 von 28 Claims, Quittung "
                "ffffffffffff",
                "nicht zum Fingerabdruck dieser Quittung"),
        }
        for name, (antwort, meldung) in faelle.items():
            with self.subTest(fall=name):
                result = self.pruefe([{
                    "id": "N1", "art": "negativ", "frage": NEGATIV,
                    "quittung": quittung, "antwort": antwort}])
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn(meldung, result.stdout)

    def test_invented_and_missed_claims_are_violations(self):
        quittung, fertig = self.sichtung(UMSCHREIBUNG, {"C-0001"})
        result = self.pruefe([{
            "id": "P1", "art": "positiv", "frage": UMSCHREIBUNG,
            "erwartet": ["C-0002"], "quittung": quittung,
            "antwort": "Das regelt C-9999, siehe auch C-0001.\n"
                       + self.zeile_sichtung(fertig),
        }])
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("die es im Bestand nicht gibt: C-9999", result.stdout)
        self.assertIn("erwarteter Claim weder zitiert noch gewählt: C-0002",
                      result.stdout)
        # Eine Kennung, nach der gefragt wurde, ist Gegenstand und kein
        # Zitat: "C-9999 gibt es nicht" erfindet keinen Claim.
        quittung, leer = self.sichtung("Was steht in C-9999?")
        erfragt = self.pruefe([{
            "id": "N2", "art": "negativ", "frage": "Was steht in C-9999?",
            "quittung": quittung,
            "antwort": "Nicht im Bestand. Einen Claim C-9999 gibt es nicht.\n"
                       + self.zeile_sichtung(leer),
        }])
        self.assertEqual(erfragt.returncode, 0, erfragt.stdout)
        # Gefunden ist ein erwarteter Claim auch dann, wenn die Quittung ihn
        # wählt und der Antworttext ihn nicht beim Namen nennt.
        gewaehlt, voll = self.sichtung(UMSCHREIBUNG, {"C-0002"})
        ohne_nennung = self.pruefe([{
            "id": "P2", "art": "positiv", "frage": UMSCHREIBUNG,
            "erwartet": ["C-0002"], "quittung": gewaehlt,
            "antwort": "Der Dateipfad ist die Identität eines Konzepts.\n"
                       + self.zeile_sichtung(voll),
        }], argumente=["--json"])
        self.assertEqual(
            ohne_nennung.returncode, 0, ohne_nennung.stdout + ohne_nennung.stderr)
        zeile = json.loads(ohne_nennung.stdout)["zeilen"][0]
        self.assertEqual(zeile["zitiert"], [])
        self.assertEqual(zeile["ausgewaehlt"], ["C-0002"])
        self.assertTrue(zeile["gefunden"])
        # Eine Negativfrage zu beantworten ist ebenfalls ein Verstoß.
        beantwortet = self.pruefe([{
            "id": "N1", "art": "negativ", "frage": NEGATIV,
            "quittung": self.sichtung(NEGATIV)[0],
            "antwort": "30 Tage.\nSichtung: 28 von 28 Claims",
        }])
        self.assertEqual(beantwortet.returncode, 1, beantwortet.stdout)
        self.assertIn("Negativfrage wurde beantwortet", beantwortet.stdout)

    def test_an_unknown_identifier_is_answered_without_a_sweep(self):
        """Dass es C-9999 nicht gibt, weiß die Engine: keine Vollsichtung."""
        frage = "Was steht in C-9999?"
        sauber = self.pruefe([{
            "id": "K1", "art": "negativ", "frage": frage,
            "antwort": "Die Kennung C-9999 gibt es im Bestand nicht. Falls "
                       "eine andere gemeint war, bitte nennen.",
        }], argumente=["--json"])
        self.assertEqual(sauber.returncode, 0, sauber.stdout + sauber.stderr)
        daten = json.loads(sauber.stdout)
        zeile = daten["zeilen"][0]
        # Das Ranking hat nichts verstanden, die Pflicht stünde also an ...
        self.assertTrue(zeile["pflicht"])
        self.assertEqual(zeile["unbekannte_ids"], ["C-9999"])
        # ... aber die Frage gilt allein der Kennung.
        self.assertTrue(zeile["kennung_unbekannt"])
        self.assertEqual(daten["zusammenfassung"]["negativ_korrekt"], 1)
        self.assertEqual(daten["zusammenfassung"]["quittungen"], 0)

        faelle = {
            "Formel ohne Quittung": (
                frage, "Nicht im Bestand: C-9999.",
                "ohne vollständige Quittung"),
            "Kennung nicht genannt": (
                frage, "Diese Kennung gibt es nicht.",
                "Vollsichtung war Pflicht"),
            "stützt sich auf einen Claim": (
                frage, "C-9999 gibt es nicht; gemeint ist wohl C-0001.",
                "Vollsichtung war Pflicht"),
            "fragt auch nach einer Sache": (
                "Was sagt C-9999 zum Urlaubsanspruch in Teilzeit?",
                "Die Kennung C-9999 gibt es im Bestand nicht.",
                "Vollsichtung war Pflicht"),
            # Die Ziffern stehen in einer Fundstelle (A-0007): Dann kann
            # etwas anderes gemeint sein als eine Kennung.
            "Ziffern stehen im Bestand": (
                "S-0007", "Die Kennung S-0007 gibt es im Bestand nicht.",
                "Vollsichtung war Pflicht"),
            # Ein Sachwort gehört zur Frage, auch wenn das Ranking es trifft.
            "Sachwort neben der Kennung": (
                "Mietminderung C-9999",
                "Die Kennung C-9999 gibt es im Bestand nicht.",
                "Vollsichtung war Pflicht"),
            # Ein Wort, das nur als Wortteil getroffen ist, ebenso.
            "Wortteil neben der Kennung": (
                "Miete C-9999",
                "Die Kennung C-9999 gibt es im Bestand nicht.",
                "Vollsichtung war Pflicht"),
            # Zwei unbekannte Kennungen: Die Antwort nennt beide.
            "nur eine von zwei Kennungen genannt": (
                "Was steht in C-9998 und C-9999?",
                "Die Kennung C-9999 gibt es im Bestand nicht.",
                "Vollsichtung war Pflicht"),
            # Die unbekannte Kennung als Quelle geführt: erfunden.
            "Kennung als Belegzeile": (
                frage, "Laut Bestand steht dort nichts Neues.\n\nBelege:\n"
                       "- C-9999 (S-0001, Einleitung, Wortlaut) — Stand "
                       "2026-07-28",
                "die es im Bestand nicht gibt: C-9999"),
            "Kennung in Klammern": (
                frage, "Der Bestand nennt dazu eine Regel (C-9999).",
                "die es im Bestand nicht gibt: C-9999"),
        }
        for name, (gefragt, antwort, meldung) in faelle.items():
            with self.subTest(fall=name):
                result = self.pruefe([{
                    "id": "K1", "art": "negativ", "frage": gefragt,
                    "antwort": antwort}])
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn(meldung, result.stdout)
        # Beide Kennungen genannt, verschiedene Einleitungen, freie
        # Formulierungen des Fehlens: erlassen.
        for gefragt, antwort in (
                (frage, "C-9999 kommt im Bestand nicht vor."),
                (frage, "Der Bestand enthält C-9999 nicht."),
                (frage, "C-9999 ist kein gültiger Claim."),
                (frage, "Unter C-9999 ist im Bestand nichts verzeichnet."),
                (frage, "Die Kennung C-9999 ist im Bestand nicht vergeben."),
                (frage, "C-9999 ist im Bestand nicht eingetragen."),
                ("Was steht in C-9998 und C-9999?",
                 "Die Kennungen C-9998 und C-9999 gibt es im Bestand nicht."),
                ("Was sagt C-9999?",
                 "Die Kennung C-9999 gibt es im Bestand nicht."),
                ("Worum geht es in S-0099?",
                 "Die Kennung S-0099 gibt es im Bestand nicht.")):
            with self.subTest(frage=gefragt):
                result = self.pruefe([{
                    "id": "K2", "art": "negativ", "frage": gefragt,
                    "antwort": antwort}])
                self.assertEqual(
                    result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("Kennung unbekannt", result.stdout)

    def test_each_state_is_judged_by_its_own_rule(self):
        """Seit v0.16.0 entscheidet die Engine, vorher die Regel aus coverage.

        Sonst würde ein Protokoll aus v0.15.0, dessen Agent sich an die damals
        gültige Regel hielt, heute als Verstoß gemeldet.
        """
        tool = _werkzeug("antwort_check")

        def abfrage(feld, offen=("9999",), teil=(), version="0.1.0"):
            """feld None: eine Engine vor v0.16.0, die das Feld nicht kennt."""
            rueckfall = {"reason": "weak_candidates_only"}
            if feld is not None:
                rueckfall["unknown_ids_only"] = feld
            return {"vault": {"version": version}, "fallback": rueckfall,
                    "coverage": {"unknown_ids": ["C-9999"], "query_terms": {
                        "unmatched": list(offen), "partial": list(teil)}}}

        satz = "Die Kennung C-9999 gibt es im Bestand nicht."
        faelle = [
            # Ohne das Feld: abgeleitet aus coverage, wie bis v0.15.0.
            (abfrage(None), True),
            (abfrage(None, ("9999", "sagt")), False),
            (abfrage(None, teil=("miete",)), False),
            # Mit dem Feld zählt allein die Engine, gleich welche VERSION
            # der Bestand trägt: Sie ist die des Bestands, nicht der Engine.
            (abfrage(False), False),
            (abfrage(True, ("9999", "sagt")), True),
            (abfrage(True, version="0.15.0"), True),
            (abfrage(False, version="9.9.9"), False),
        ]
        for eingabe, erwartet in faelle:
            with self.subTest(feld=eingabe["fallback"].get("unknown_ids_only"),
                              offen=eingabe["coverage"]["query_terms"]):
                self.assertIs(tool._gilt_allein_der_kennung(
                    eingabe, satz, belegt=set(), abstention=False), erwartet)
        # Was die Antwort tut, zählt in jedem Stand.
        neu = abfrage(True)
        self.assertFalse(tool._gilt_allein_der_kennung(
            neu, satz, belegt={"C-0001"}, abstention=False))
        self.assertFalse(tool._gilt_allein_der_kennung(
            neu, satz, belegt=set(), abstention=True))
        self.assertFalse(tool._gilt_allein_der_kennung(
            neu, "Diese Kennung gibt es nicht.", belegt=set(),
            abstention=False))
        # Erwähnt ist eine Kennung nur in einem Satz, der ihr Fehlen
        # feststellt; jede andere Nennung führt sie als Quelle.
        erwaehnt = [
            "C-9999 gibt es nicht.", "Die Kennung C-9999 fehlt.",
            "Die gesuchte Kennung (C-9999) gibt es im Bestand nicht.",
            "Diese Kennungen gibt es im Bestand nicht:\n- C-9998\n- C-9999",
            "*C-9999* gibt es im Bestand nicht.",
            "> Die Kennung C-9999 existiert im Bestand nicht.",
            "Einen Claim C-9999 kennt der Bestand nicht.",
            "Es gibt keinen Claim C-9999. Falls eine andere gemeint war, "
            "bitte nennen.",
            # Aus den Runden 3 und 4: die Abgrenzung nach einer Sichtung und
            # die Rückfrage.
            "Nicht im Bestand: Inhalt von C-9999\nSichtung: 28 von 28 Claims",
            "Falls mit C-9999 eine andere Kennung gemeint war, bitte nennen.",
            "Die Kennung C-9999 gibt es im Bestand\nnicht.",
            "Die Kennung C-9999 gibt es im\nBestand nicht.",
            "Die Kennung C-9999 ist im Bestand nicht enthalten.",
            "C-9999 kommt im Bestand nicht vor.",
            "C-9999 ist keine gültige Kennung dieses Bestands.",
            "Der Bestand enthält C-9999 nicht.",
            "C-9999 ist kein gültiger Claim.",
            "Unter C-9999 ist im Bestand nichts verzeichnet.",
            "Die Kennung C-9999 ist im Bestand nicht vergeben.",
            "Laut Bestand gibt es C-9999 nicht.",
            "Laut Bestand gibt es keine Kennung C-9999.",
            "Gemäß dem Bestand existiert C-9999 nicht.",
            "Zu C-9999 gibt es im Bestand keinen Eintrag.",
            "Über C-9999 ist im Bestand nichts verzeichnet.",
            "C-9999 konnte ich im Bestand nicht finden.",
            "Die Kennung C-9999 ist mir nicht bekannt.",
            "Die Kennung C-9999 wurde im Bestand nicht gefunden.",
            "Die Kennung C-9999 ist im Bestand nicht zu finden.",
            "Die Kennungen C-9998 (Claim) und C-9999 (Claim) gibt es im "
            "Bestand nicht.",
            "**Ergebnis**\nDie Kennung C-9999 gibt es im Bestand nicht.",
            "Stand: 2026-08-06; Konfidenz: mittel\nNicht im Bestand: Inhalt "
            "von C-9999",
            "Nicht im Bestand (laut Sichtung): Inhalt von C-9999",
            # Aus der dritten Prüfrunde.
            "Zu C-9999 gibt es im Bestand keinen Claim.",
            "Für C-9999 gibt es keinen Claim.",
            "Einen Claim mit der Kennung C-9999 finde ich im Bestand nicht.",
            "Unter der Kennung C-9999 findet sich im Bestand nichts.",
            "C-9999 ist nicht Teil des Bestands.",
            "Eine Kennung namens C-9999 gibt es nicht.",
            "Die angefragte Kennung lautet C-9999 und existiert im Bestand "
            "nicht.",
            "Diese Kennungen gibt es im Bestand nicht:\n1. C-9998\n2. C-9999",
            # Ausdrücklich ausgeschlossen, und die wiederholte Frage.
            "Die Aussagen stammen aus X-0001, nicht aus C-9999.",
            "C-9999 ist nicht ihre Quelle.",
            "Was steht in C-9999? Die Kennung gibt es im Bestand nicht.",
            "Sie fragen nach C-9999. Diese Kennung gibt es im Bestand nicht.",
        ]
        als_quelle = [
            "- C-9999 (S-0001)", "so steht es (S-0001, c-9999).",
            "Laut C-9999 beträgt die Frist drei Monate.",
            "C-9999 besagt: Schimmel berechtigt zur Kündigung.",
            "Drei Monate.\n\nBelege:\n1. C-9999 (S-0001, Einleitung)",
            "Drei Monate.\n- **C-9999** (S-0001)", "Drei Monate.\n– C-9999",
            "Drei Monate [C-9999].", "Belege: C-9999 (S-0001)",
            "Drei Monate.\n+ C-9999 (S-0001)",
            "Laut C-9999 ist die Frist unbekannt.",
            "Die Kennung C-9999 gibt es nicht. Laut C-9999 gilt aber X.",
            "- C-99990 (S-0001)", "Hier steht keine Kennung.",
            "Die Kennung C-9999 gibt es nicht\nC-9999 (S-0001, Einleitung)",
            "Gemäß der Quelle C-9999 gibt es keine Frist, die nicht gilt.",
            "Die Frist, die es nicht gibt, steht C-9999 zufolge fest.",
            # Ein Fehlen-Wort im Satz macht die Kennung nicht zur Erwähnung:
            # Gezählt wird der Satzteil, in dem sie steht.
            "Fehlt die Anzeige an den Vermieter, entfällt die Minderung "
            "(C-9999).",
            "C-9999 regelt den Fall, dass die Anzeige fehlt.",
            "C-9999 besagt, dass es eine Minderung ohne Anzeige nicht gibt.",
            "Eine Minderung ohne Anzeige gibt es nicht (Quelle C-9999).",
            "Meinten Sie mit C-9999 vielleicht die Anzeigepflicht bei "
            "Schimmel?",
            "C-9999 ist die Quelle dieser Aussagen.",
            # "laut" vor der Kennung macht sie zur Quelle, auch im Fehlen.
            "Laut C-9999 gibt es das nicht.",
            "Laut C-9999 kann man nicht kündigen.",
            "Nach C-9999 gibt es das im Bestand nicht.",
            "Zu C-9999 gibt es eine Frist von drei Monaten.",
            "Für C-9999 gilt: keine Frist.",
            # Die Abgrenzung gilt nur für ihren eigenen Satzteil.
            "Nicht im Bestand: die Höhe der Minderung; nach C-9999 sind "
            "20 Prozent üblich.",
            "Nicht im Bestand: der Inhalt von C-9999; nach C-9999 beträgt die "
            "Minderung 20 Prozent.",
            "Nicht im Bestand: die Höhe der Minderung\nNach C-9999 sind "
            "20 Prozent üblich.",
            # Eine Klammer mit Fundstelle bleibt ein Beleg.
            "Drei Monate.\n- C-9999 (Mietrecht, Rn. 12)",
            "Die Kennung C-9999 gibt es im Bestand nicht (laut "
            "coverage.unknown_ids der Abfrage: C-9999).",
        ]
        for text in erwaehnt:
            with self.subTest(erwaehnt=text):
                self.assertTrue(tool._nur_als_fehlend(text, "C-9999"))
        for text in als_quelle:
            with self.subTest(als_quelle=text):
                self.assertFalse(tool._nur_als_fehlend(text, "C-9999"))
        # Eine Kennung, die allein hinter einer Klammer steht, gehört zum
        # Satzteil davor auf derselben Ebene, nicht zum Klammerinhalt.
        self.assertFalse(tool._nur_als_fehlend(
            "Extern (nicht im Bestand): X-0003, BGB § 536 Abs. 1, Satz 1, "
            "abgerufen 2026-11-13", "X-0003"))
        # Eine Rückfrage allein stellt das Fehlen nicht fest.
        rueckfrage = ("Falls mit C-9999 eine andere Kennung gemeint war, "
                      "bitte nennen.")
        self.assertTrue(tool._nur_als_fehlend(rueckfrage, "C-9999"))
        self.assertFalse(tool._stellt_fehlen_fest(rueckfrage, "C-9999"))
        # Die Feststellung im Satz danach gilt der eben genannten Kennung,
        # aber nur unmittelbar danach und nur, wenn der Satz nichts anderes
        # sagt.
        self.assertTrue(tool._stellt_fehlen_fest(
            "Sie fragen nach C-9999. Diese Kennung gibt es im Bestand nicht.",
            "C-9999"))
        self.assertFalse(tool._stellt_fehlen_fest(
            "Sie fragen nach C-9999. Die Frist beträgt drei Monate. Diese "
            "Kennung gibt es im Bestand nicht.", "C-9999"))
        # Typografische Striche in einer Kennung sind ein Bindestrich.
        self.assertEqual(tool._striche("(C\u20110305), C\u20139998, x-1"),
                         "(C-0305), C-9998, x-1")
        self.assertEqual(tool._zitierte_claims(
            tool._striche("C\u20110001 bis C\u20110003"),
            ["C-0001", "C-0002", "C-0003"]), ["C-0001", "C-0002", "C-0003"])
        # Die Formel auch umbrochen im Zitatblock.
        self.assertTrue(tool._sagt_nicht_im_bestand(
            "> Wer sie vergibt, ist nicht im\n> Bestand."))
        # Sichtungsangaben: nur Zeilen mit Zahlen oder Kennung, die Zahlen
        # vor "Claims", Tausendertrennzeichen gelesen.
        angaben = tool._sichtungsangaben(
            "Ergebnis der Sichtung: Kein Claim nennt das.\n"
            "Sichtung: 3 von 3 Stapeln, 1.234 von 1.234 Claims, "
            "Quittungs-ID d13bee74ba35\n"
            "Hinweise zur Sichtung: ein Stapel.\n"
            "Vollsichtung: 28 von insgesamt 28 Claims, Quittungskennung "
            "abcdef123456\n"
            "Nach einer Sichtung (5 von 5 Claims) ist das klar.")
        self.assertEqual(angaben, [
            {"zahlen": (1234, 1234), "claims": True, "kennung": "d13bee74ba35",
             "art": "zeile"},
            {"zahlen": (28, 28), "claims": True, "kennung": "abcdef123456",
             "art": "zeile"},
            {"zahlen": (5, 5), "claims": True, "kennung": None, "art": "satz"}])
        # Eine Überschrift mit der Angabe darunter, eine verneinte Zeile, ein
        # Stapelpaar und das Siegel eines Stapels.
        self.assertEqual(
            [(angabe["art"], angabe["zahlen"], angabe["kennung"])
             for angabe in tool._sichtungsangaben(
                 "## Sichtung\n28 von 28 Claims (5d029a1c6e10)")],
            [("zeile", (28, 28), "5d029a1c6e10")])
        self.assertEqual(tool._sichtungsangaben(
            "Sichtung: entfällt, die Kennung gibt es nicht."), [])
        self.assertEqual(tool._sichtungsangaben(
            "Hinweise: Stapel 1 von 1 habe ich gesichtet (Siegel "
            "76fefba0d216c21a)."), [])
        # Andere Schreibweisen derselben Behauptung, und Prosa, die keine ist.
        for text, erwartet in (
                ("Sichtung: 28/28 Claims", [(28, 28)]),
                ("Sichtung: alle 28 Claims gelesen, kein weiterer passt.",
                 [(28, 28)]),
                ("Sichtung:\n28 von 28 Claims", [(28, 28)]),
                ("Die Sichtung ergab: 0 von 28 Claims nennen das.", []),
                ("Hinweise: Eine Vollsichtung war nicht nötig, die Abfrage "
                 "traf 2 von 2 Begriffen exakt.", []),
                ("Alle 28 Claims wurden in der Sichtung gelesen.", [(28, 28)]),
                # „gesichtet" nennt den Umfang, auch einen unvollständigen ...
                ("Gesichtet habe ich 20 von 28 Claims.", [(20, 28)]),
                ("Es wurden 20 von 28 Claims gesichtet, 0 davon nennen das.",
                 [(20, 28)]),
                ("Sichtung: 28 von 28 Claims; gesichtet habe ich 20 von 28 "
                 "Claims.", [(28, 28), (20, 28)]),
                # ... ein Ergebnis daneben ist keine Angabe.
                ("Ich habe 20 von 28 Claims vollständig gesichtet.",
                 [(20, 28)]),
                ("Gesichtet wurden insgesamt alle 28 Claims.", [(28, 28)]),
                ("Gesichtet wurden alle Stapel; 0 von 28 Claims nennen das.",
                 []),
                ("In der Sichtung nannten 0 von 28 Claims einen Urlaub.", []),
                ("Von 28 gesichteten Claims nennt keiner das.", []),
                ("Nicht gesichtet wurden 8 von 28 Claims.", []),
                ("Gesichtet und 0 von 28 Claims passend gefunden.", []),
                ("Alles gesichtet: 0 von 28 Claims nennen das.", []),
                # Die Verneinung zählt nur in ihrem Satzteil ...
                ("Gesichtet habe ich alle 28 Claims; keiner nennt eine "
                 "weitere Stufe.", [(28, 28)]),
                ("In der Vollsichtung habe ich alle 28 Claims gelesen, keiner "
                 "nennt eine weitere Stufe.", [(28, 28)]),
                ("Ich habe alle 28 Claims gesichtet und keiner nennt das.",
                 [(28, 28)]),
                # ... und ein Satz über den Umfang ohne "gesichtet" zählt.
                ("Die Vollsichtung umfasste 26 von 30 Claims.", [(26, 30)]),
                ("Vollsichtung über den ganzen Bestand, alle 28 Claims "
                 "gelesen.", [(28, 28)]),
                # Ein Ergebnis ist keine Angabe, auch ohne Verb im Satzteil.
                ("Hinweise: Laut Sichtung stammen alle 10 Claims zu OKF v0.2 "
                 "aus S-0004.", []),
                ("Ergebnis der Sichtung: 3 von 28 Claims zu Fristen.", []),
                ("In der Sichtung waren 2 von 28 Claims einschlägig.", []),
                # Tausenderpunkt, "von insgesamt", "alle N" mit Verneinung
                # im nächsten Satzteil.
                ("Gesichtet habe ich 1.200 von 7.528 Claims.", [(1200, 7528)]),
                ("Gesichtet habe ich 20 von insgesamt 28 Claims.", [(20, 28)]),
                ("Gesichtet habe ich alle 30 Claims, keiner nennt das.",
                 [(30, 30)])):
            with self.subTest(sichtung=text):
                self.assertEqual(
                    [angabe["zahlen"] for angabe in tool._sichtungsangaben(text)],
                    erwartet)

    def test_an_unknown_identifier_is_never_a_source(self):
        """Wer eine Kennung, die es nicht gibt, als Quelle führt, erfindet.

        Gleich in welcher Form: "Laut C-9999 …", eine nummerierte Belegliste,
        eckige Klammern, eine S-Kennung. Vertragsgemäß ist nur der Satz, der
        ihr Fehlen feststellt, und der darf sie auch in Klammern nennen.
        """
        frage = "Was steht in C-9999?"
        als_quelle = {
            "laut": "Laut C-9999 beträgt die Kündigungsfrist drei Monate.",
            "besagt": "C-9999 besagt: Schimmel berechtigt zur Kündigung.",
            "nummeriert": "Drei Monate.\n\nBelege:\n1. C-9999 (S-0001, "
                          "Einleitung, Wortlaut) — Stand 2026-07-28",
            "fett": "Drei Monate.\n\n- **C-9999** (S-0001, Einleitung)",
            "Gedankenstrich": "Drei Monate.\n\n– C-9999 (S-0001)",
            "eckig": "Die Frist beträgt drei Monate [C-9999].",
            "Belege im Satz": "Drei Monate. Belege: C-9999 (S-0001).",
            "geschützter Strich": "Laut C\u20119999 gilt eine Frist.",
            "Fehlen-Wort im Satz": "Fehlt die Anzeige an den Vermieter, "
                                   "entfällt die Minderung (C-9999).",
        }
        erwaehnt = {
            "Vorlage": "Die Kennung C-9999 gibt es im Bestand nicht. Falls "
                       "eine andere gemeint war, bitte nennen.",
            "in Klammern": "Die gesuchte Kennung (C-9999) gibt es im "
                           "Bestand nicht.",
            "hervorgehoben": "*C-9999* gibt es im Bestand nicht.",
            "typografischer Strich": "Die Kennung C\u20119999 gibt es im "
                                     "Bestand nicht.",
            "nicht enthalten": "Die Kennung C-9999 ist im Bestand nicht "
                               "enthalten.",
        }
        antworten = [
            {"id": f"Q-{name}", "art": "negativ", "frage": frage,
             "antwort": text} for name, text in als_quelle.items()]
        antworten += [
            {"id": f"E-{name}", "art": "negativ", "frage": frage,
             "antwort": text} for name, text in erwaehnt.items()]
        antworten += [
            {"id": "S-laut", "art": "negativ",
             "frage": "Worum geht es in S-0099?",
             "antwort": "Laut S-0099 beträgt die Minderung 20 Prozent."},
            {"id": "S-Klammer", "art": "negativ",
             "frage": "Worum geht es in S-0099?",
             "antwort": "Die Minderung beträgt 20 Prozent (S-0099, "
                        "Abschnitt 2, Wortlaut)."},
            {"id": "S-sauber", "art": "negativ",
             "frage": "Worum geht es in S-0099?",
             "antwort": "Die Kennung S-0099 gibt es im Bestand nicht."},
            {"id": "Liste", "art": "negativ",
             "frage": "Was steht in C-9998 und C-9999?",
             "antwort": "Diese Kennungen gibt es im Bestand nicht:\n"
                        "- C-9998\n- C-9999"},
            {"id": "Liste nummeriert", "art": "negativ",
             "frage": "Was steht in C-9998 und C-9999?",
             "antwort": "Diese Kennungen gibt es im Bestand nicht:\n"
                        "1. C-9998\n2. C-9999"},
            {"id": "nur Rückfrage", "art": "negativ", "frage": frage,
             "antwort": "Falls mit C-9999 eine andere Kennung gemeint war, "
                        "bitte nennen."},
            {"id": "erfundene S-Quelle", "art": "negativ", "frage": frage,
             "antwort": "Die Kennung C-9999 gibt es im Bestand nicht. Laut "
                        "S-0099 betrifft sie die Anzeigepflicht."},
            {"id": "S-Quelle neben Claim", "frage": BEGRIFF,
             "erwartet": ["C-0305"],
             "antwort": "Laut Bestand gibt es vier Stufen (C-0305, S-0099)."},
            {"id": "vorhandene Quelle", "frage": BEGRIFF,
             "erwartet": ["C-0305"],
             "antwort": "Laut Bestand gibt es vier Stufen (C-0305, X-0001)."},
        ]
        result = self.pruefe(antworten, argumente=["--json"])
        zeilen = {zeile["id"]: zeile
                  for zeile in json.loads(result.stdout)["zeilen"]}
        for name in als_quelle:
            with self.subTest(als_quelle=name):
                zeile = zeilen[f"Q-{name}"]
                self.assertFalse(zeile["kennung_unbekannt"])
                self.assertIn("zitiert Claim-IDs, die es im Bestand nicht "
                              "gibt: C-9999", zeile["verstoesse"])
        for name in erwaehnt:
            with self.subTest(erwaehnt=name):
                zeile = zeilen[f"E-{name}"]
                self.assertTrue(zeile["kennung_unbekannt"], zeile)
                self.assertEqual(zeile["verstoesse"], [])
        for kennung in ("S-laut", "S-Klammer"):
            with self.subTest(quelle=kennung):
                self.assertFalse(zeilen[kennung]["kennung_unbekannt"])
                self.assertIn("führt eine Kennung, die es im Bestand nicht "
                              "gibt, als Quelle: S-0099",
                              zeilen[kennung]["verstoesse"])
        for kennung in ("S-sauber", "Liste", "Liste nummeriert"):
            with self.subTest(sauber=kennung):
                self.assertTrue(zeilen[kennung]["kennung_unbekannt"])
                self.assertEqual(zeilen[kennung]["verstoesse"], [])
        self.assertFalse(zeilen["nur Rückfrage"]["kennung_unbekannt"])
        self.assertTrue(any(m.startswith("Vollsichtung war Pflicht")
                            for m in zeilen["nur Rückfrage"]["verstoesse"]))
        for kennung in ("erfundene S-Quelle", "S-Quelle neben Claim"):
            with self.subTest(erfunden=kennung):
                self.assertFalse(zeilen[kennung]["kennung_unbekannt"])
                self.assertIn("führt eine Kennung, die es im Bestand nicht "
                              "gibt, als Quelle: S-0099",
                              zeilen[kennung]["verstoesse"])
        self.assertEqual(zeilen["vorhandene Quelle"]["verstoesse"], [])

    def test_every_statement_of_a_sweep_is_checked_and_prose_is_not(self):
        """Was eine Sichtung angibt, wird geprüft; ein Satz darüber nicht."""
        quittung, leer = self.sichtung(NEGATIV)
        kennung = leer["sweep_fingerprint"][:12]
        stapel, drei = self.sichtung(NEGATIV, groesse=10)
        andere = self.sichtung("Welche Vektordatenbank empfiehlt der Bestand?")[1]
        fremd = andere["sweep_fingerprint"][:12]
        richtig = f"Sichtung: 28 von 28 Claims, Quittung {kennung}"
        antworten = [
            # Mit Quittung: Prosa um die richtige Zeile ist kein Verstoß.
            {"id": "P1", "art": "negativ", "frage": NEGATIV,
             "quittung": quittung,
             "antwort": "Nicht im Bestand. Ergebnis der Sichtung: Kein Claim "
                        "nennt einen Urlaubsanspruch.\n\n" + richtig},
            {"id": "P2", "art": "negativ", "frage": NEGATIV,
             "quittung": quittung,
             "antwort": "Nicht im Bestand.\n\n" + richtig
                        + "\nHinweise zur Sichtung: ein Stapel."},
            # Andere Schreibweisen derselben Angabe.
            {"id": "F1", "art": "negativ", "frage": NEGATIV,
             "quittung": quittung,
             "antwort": "Nicht im Bestand.\nSichtung: 28 von 28 Claims, "
                        f"Quittungskennung {kennung}"},
            {"id": "F2", "art": "negativ", "frage": NEGATIV,
             "quittung": quittung,
             "antwort": "Nicht im Bestand.\nSichtung: 28 von insgesamt 28 "
                        f"Claims, Quittungs-ID {kennung}"},
            {"id": "F3", "art": "negativ", "frage": NEGATIV,
             "quittung": stapel, "sweep_args": ["--size", "10"],
             "antwort": "Nicht im Bestand.\nSichtung: 3 von 3 Stapeln, 28 von "
                        f"28 Claims, Quittung "
                        f"{drei['sweep_fingerprint'][:12]}"},
            # Die Angabe unter einer Überschrift, in der Zeile danach.
            {"id": "F4", "art": "negativ", "frage": NEGATIV,
             "quittung": quittung,
             "antwort": "Nicht im Bestand.\n\n**Sichtung:**\n28 von 28 "
                        f"Claims, Quittung {kennung}"},
            # Neben der richtigen Zeile eine zweite, falsche Angabe.
            {"id": "W1", "art": "negativ", "frage": NEGATIV,
             "quittung": quittung,
             "antwort": "Nicht im Bestand.\n" + richtig
                        + "\nGesichtet habe ich 20 von 28 Claims."},
        ]
        antworten += [
            {"id": "P3", "art": "negativ", "frage": NEGATIV,
             "quittung": quittung,
             "antwort": "Nicht im Bestand. Die Sichtung ergab: 0 von 28 Claims "
                        "nennen einen Urlaubsanspruch.\n\n" + richtig},
            {"id": "P4", "frage": BEGRIFF, "erwartet": ["C-0305"],
             "antwort": "Laut Bestand gibt es vier Stufen (C-0305).\n\n"
                        "Hinweise: Eine Vollsichtung war nicht nötig, die "
                        "Abfrage traf 2 von 2 Begriffen exakt."},
        ]
        # Ohne Quittung: jede Form einer behaupteten Sichtung.
        ohne = (f"Vollsichtung: 28 von 28 Claims, Quittung {fremd}",
                f"Sichtung – 28 von 28 Claims, Quittung {fremd}",
                f"SICHTUNG: 28 von 28 Claims, Quittung {fremd}",
                f"Nach einer Sichtung (28 von 28 Claims, Quittung {fremd}) "
                f"ist das vollständig.",
                "Sichtung: 28/28 Claims",
                "Sichtung: alle 28 Claims gelesen, kein weiterer nennt eine "
                "Stufe.",
                "Sichtung:\n28 von 28 Claims")
        for nummer, angabe in enumerate(ohne, 1):
            antworten.append({
                "id": f"O{nummer}", "frage": BEGRIFF, "erwartet": ["C-0305"],
                "antwort": "Laut Bestand gibt es vier Stufen (C-0305).\n\n"
                           + angabe})
        # Ohne Vollsichtung beschreibt „gesichtet" mit weniger als allen
        # Claims das Lesen der Kandidaten; das behauptet keine Sichtung.
        antworten.append({
            "id": "P5", "frage": BEGRIFF, "erwartet": ["C-0305"],
            "antwort": "Laut Bestand gibt es vier Stufen (C-0305). Gesichtet "
                       "habe ich 3 von 8 Claims der Kandidaten."})
        # Schritt 4c ist jeweils ausgewiesen; geprüft werden hier nur die
        # Angaben zur Sichtung.
        for eintrag in antworten:
            if eintrag.get("art") == "negativ":
                eintrag["antwort"] += "\n" + EXTERN
        result = self.pruefe(antworten, argumente=["--json"])
        zeilen = {zeile["id"]: zeile
                  for zeile in json.loads(result.stdout)["zeilen"]}
        for kennung_antwort in ("P1", "P2", "P3", "P4", "P5", "F1", "F2", "F3",
                                "F4"):
            with self.subTest(sauber=kennung_antwort):
                self.assertEqual(zeilen[kennung_antwort]["verstoesse"], [])
        self.assertEqual(zeilen["W1"]["verstoesse"], [
            "Zeile „Sichtung:\" nennt 20 von 28 Claims, die Quittung belegt "
            "28 von 28 Claims"])
        for nummer in range(1, len(ohne) + 1):
            with self.subTest(ohne_quittung=nummer):
                self.assertTrue(any(
                    "ohne eingereichte Quittung" in meldung
                    for meldung in zeilen[f"O{nummer}"]["verstoesse"]),
                    zeilen[f"O{nummer}"])

    def test_a_declared_scope_satisfies_the_sweep_for_that_scope(self):
        """Gibt der Mensch einen Umfang vor, genügt dessen Sichtung.

        Die Antwort sagt dann „in diesem Umfang nicht gefunden", nie „Nicht
        im Bestand". Ohne die Angabe im Protokoll bleibt die eingeschränkte
        Sichtung eine ausgelassene Pflicht.
        """
        frage = "Welche Vektordatenbank empfiehlt der Bestand?"
        argumente = ["--domain", "demo-okf"]
        plan = json.loads(_cli(self.root, "sweep", frage, *argumente).stdout)
        eintraege = []
        for stapel in plan["batches"]:
            ausgabe = json.loads(_cli(
                self.root, "sweep", frage, *argumente,
                "--batch", str(stapel["batch"])).stdout)
            eintraege.append(f"{stapel['batch']}:{ausgabe['seal']}=-")
        fertig = json.loads(_cli(self.root, "sweep", frage, *argumente,
                                 "--receipt", *eintraege).stdout)
        self.assertEqual(fertig["state"], "sweep_complete", fertig)
        self.assertFalse(fertig["coverage"]["scope_complete"])
        abdeckung = fertig["coverage"]
        zeile_umfang = (
            f"Sichtung: Domäne demo-okf, {abdeckung['claims_swept']} von "
            f"{abdeckung['claims_total']} Claims, Quittung "
            f"{fertig['sweep_fingerprint'][:12]}")
        antwort = "In diesem Umfang nicht gefunden.\n" + zeile_umfang
        basis = {"art": "negativ", "frage": frage, "quittung": eintraege,
                 "sweep_args": argumente, "antwort": antwort}
        result = self.pruefe([
            dict(basis, id="U1", umfang_vorgegeben=True),
            dict(basis, id="U2"),
            dict(basis, id="U3", umfang_vorgegeben=True,
                 antwort="Nicht im Bestand.\n" + zeile_umfang),
            dict(basis, id="U6", umfang_vorgegeben=True,
                 antwort="In demo-okf habe ich dazu nichts gefunden.\n"
                         + zeile_umfang),
        ], argumente=["--json"])
        daten = json.loads(result.stdout)
        zeilen = {zeile["id"]: zeile for zeile in daten["zeilen"]}
        self.assertEqual(zeilen["U1"]["verstoesse"], [])
        self.assertEqual(tool_urteil(zeilen["U1"]), "im Umfang abgelehnt")
        self.assertTrue(any(
            m.startswith("Vollsichtung war Pflicht") and m.endswith(
                "keine vollständige Quittung über den ganzen Bestand vor")
            for m in zeilen["U2"]["verstoesse"]), zeilen["U2"])
        self.assertTrue(any("ohne vollständige Quittung, die eine Abstention "
                            "erlaubt" in m for m in zeilen["U3"]["verstoesse"]))
        self.assertTrue(any("nur „in diesem Umfang\" abgelehnt" in m
                            for m in zeilen["U2"]["verstoesse"]), zeilen["U2"])
        # Wer der Meldung folgt, schreibt die Formel des Umfangs, nicht
        # „Nicht im Bestand", das hier selbst ein Verstoß wäre.
        self.assertIn("Negativfrage wurde beantwortet statt als „in diesem "
                      "Umfang nicht gefunden\" ausgewiesen",
                      zeilen["U6"]["verstoesse"])
        self.assertFalse(any("„Nicht im Bestand\" ausgewiesen" in m
                             for m in zeilen["U6"]["verstoesse"]))
        self.assertEqual(daten["zusammenfassung"]["negativ_korrekt"], 1)
        # Die Formel ohne jede Quittung ist eine Abstention ohne Deckung.
        ohne = self.pruefe([{
            "id": "U5", "frage": BEGRIFF, "erwartet": ["C-0305"],
            "antwort": "Laut Bestand gibt es vier Stufen (C-0305). Wer eine "
                       "Stufe vergibt: in diesem Umfang nicht gefunden."}],
            argumente=["--json"])
        zeile_u5 = json.loads(ohne.stdout)["zeilen"][0]
        self.assertIn("„in diesem Umfang nicht gefunden\" ohne vollständige "
                      "Quittung über diesen Umfang", zeile_u5["verstoesse"])
        # Ein vorgegebener Umfang ohne Umfang im Protokoll ist kein Protokoll.
        kaputt = self.pruefe([dict(basis, id="U4", umfang_vorgegeben=True,
                                   sweep_args=[])])
        self.assertEqual(kaputt.returncode, 2, kaputt.stdout)

    def test_envelope_lines_proposals_and_denials(self):
        """Befunde der dritten Prüfrunde, Ende zu Ende.

        Die Zeilen des Envelopes setzen keinen Satz fort, die Abgrenzung gilt
        nur für ihren eigenen Satzteil, ein Vorschlag im Kennungsfall ist ein
        Zitat, und wer eine vorhandene Kennung bestreitet, verstößt.
        """
        quittung, fertig = self.sichtung(
            "Berechtigt Schimmelbefall zur Mietminderung?", {"C-0401"})
        quittung_frage, fertig_frage = self.sichtung(
            "Was regelt C-9999 zur Mietminderung?")
        quittung_neg, leer = self.sichtung(NEGATIV)
        zeile_neg = self.zeile_sichtung(leer)
        kern = ("Laut Bestand berechtigt Schimmel zur Minderung (C-0401).\n\n"
                "Belege:\n- C-0401 (S-0002, Mängel, Wortlaut) — Stand "
                "2026-08-06\n\nStand: 2026-08-06; Konfidenz: mittel\n")
        schimmel = {"frage": "Berechtigt Schimmelbefall zur Mietminderung?",
                    "erwartet": ["C-0401"], "quittung": quittung}
        antworten = [
            # Erfundene X-Kennung in der Zeile für externe Hinweise.
            {"id": "A1", "art": "negativ", "frage": NEGATIV,
             "quittung": quittung_neg,
             "antwort": "Nicht im Bestand.\n\n" + zeile_neg + "\n\nExtern "
                        "(nicht im Bestand): X-0003, BGB § 536 Abs. 1, Satz 1, "
                        "abgerufen 2026-11-13 10:12"},
            # Nachsatz in der Abgrenzung, auch in der Zeile darunter.
            dict(schimmel, id="A2", antwort=kern + "Nicht im Bestand: die Höhe "
                 "der Minderung; nach S-0005 sind bei Schimmel 20 Prozent "
                 "üblich.\n" + self.zeile_sichtung(fertig)),
            dict(schimmel, id="A3", antwort=kern + "Nicht im Bestand: die Höhe "
                 "der Minderung\nNach S-0005 sind bei Schimmel 20 Prozent "
                 "üblich.\n" + self.zeile_sichtung(fertig)),
            {"id": "A7", "frage": "Was regelt C-9999 zur Mietminderung?",
             "erwartet": ["C-0401"], "quittung": quittung_frage,
             "antwort": "Laut Bestand berechtigt Schimmel zur Minderung "
                        "(C-0401).\nNicht im Bestand: der Inhalt von C-9999; "
                        "nach C-9999 beträgt die Minderung 20 Prozent.\n"
                        + self.zeile_sichtung(fertig_frage)},
            # Ohne die Zeile "Hinweise:" verschmilzt die Abgrenzung nicht mit
            # der Zeile "Stand:".
            {"id": "D1", "frage": "Was regelt C-9999 zur Mietminderung?",
             "erwartet": ["C-0401"], "quittung": quittung_frage,
             "antwort": kern + "Nicht im Bestand: Inhalt von C-9999\n"
                        + EXTERN + "\n" + self.zeile_sichtung(fertig_frage)},
            # Kennungsfall: ein Vorschlag ist ein Zitat.
            {"id": "C1", "art": "negativ", "frage": "Was steht in C-9999?",
             "antwort": "Die Kennung C-9999 gibt es im Bestand nicht. "
                        "Meinten Sie S-0005?"},
            {"id": "A4", "art": "negativ", "frage": "Worum geht es in S-0099?",
             "antwort": "Die Kennung S-0099 gibt es im Bestand nicht. Gemeint "
                        "ist vermutlich S-0004."},
            {"id": "V1", "art": "negativ", "frage": "Worum geht es in S-0099?",
             "antwort": "Die Kennung S-0099 gibt es im Bestand nicht. Meinten "
                        "Sie S-0001?"},
            {"id": "V2", "art": "negativ", "frage": "Was steht in C-9999?",
             "antwort": "Die Kennung C-9999 gibt es im Bestand nicht. Falls "
                        "der Begriff B-0001 gemeint war, bitte nennen."},
            {"id": "V3", "art": "negativ", "frage": "Was steht in C-9999?",
             "antwort": "Die Kennung C-9999 gibt es im Bestand nicht. Meinten "
                        "Sie die externe Quelle X-0001?"},
            # Freie Formulierungen, Typklammern, Überschrift.
            {"id": "B3", "art": "negativ", "frage": "Was steht in C-9999?",
             "antwort": "Die Kennung C-9999 wurde im Bestand nicht gefunden."},
            {"id": "B4", "art": "negativ", "frage": "Worum geht es in S-0099?",
             "antwort": "Eine Quelle S-0099 ist im Quellenregister nicht "
                        "verzeichnet."},
            {"id": "B8", "art": "negativ",
             "frage": "Was steht in C-9998 und S-0099?",
             "antwort": "Die Kennungen C-9998 (Claim) und S-0099 (Quelle) gibt "
                        "es im Bestand nicht."},
            {"id": "C3", "art": "negativ", "frage": "Was steht in C-9999?",
             "antwort": "**Ergebnis**\nDie Kennung C-9999 gibt es im Bestand "
                        "nicht."},
            # Eine vorhandene Kennung bestreiten.
            {"id": "G1", "frage": "Was steht in C-0401?", "erwartet": ["C-0401"],
             "antwort": "Die Kennung C-0401 gibt es im Bestand nicht."},
            {"id": "F2", "frage": "Worum geht es in S-0004?",
             "antwort": "Die Kennung S-0004 gibt es im Bestand nicht."},
            # Behauptete Sichtung ohne Quittung, mit Verneinung im Ergebnis.
            {"id": "S1", "frage": BEGRIFF, "erwartet": ["C-0305"],
             "antwort": "Laut Bestand gibt es vier Stufen (C-0305). Gesichtet "
                        "habe ich alle 28 Claims; keiner nennt eine weitere "
                        "Stufe."},
            # Neben der richtigen Zeile eine falsche Angabe zum Umfang ...
            {"id": "S2", "art": "negativ", "frage": NEGATIV,
             "quittung": quittung_neg,
             "antwort": "Nicht im Bestand.\n" + zeile_neg + "\nDie "
                        "Vollsichtung umfasste 26 von 30 Claims."},
            # ... und ein Ergebnis über eine Teilmenge, das keine ist.
            {"id": "S3", "art": "negativ", "frage": NEGATIV,
             "quittung": quittung_neg,
             "antwort": "Nicht im Bestand.\n" + zeile_neg + "\nHinweise: "
                        "Laut Sichtung stammen alle 10 Claims zu OKF v0.2 aus "
                        "S-0004.\n" + EXTERN},
            # Im Kennungsfall eine Zeile "Sichtung: entfällt".
            {"id": "E1", "art": "negativ", "frage": "Was steht in C-9999?",
             "antwort": "Die Kennung C-9999 gibt es im Bestand nicht.\n\n"
                        "Sichtung: entfällt, die Kennung gibt es nicht."},
        ]
        result = self.pruefe(antworten, argumente=["--json"])
        zeilen = {zeile["id"]: zeile
                  for zeile in json.loads(result.stdout)["zeilen"]}

        def meldet(kennung, teil):
            self.assertTrue(any(teil in meldung for meldung
                                in zeilen[kennung]["verstoesse"]),
                            (kennung, zeilen[kennung]["verstoesse"]))

        meldet("A1", "führt eine Kennung, die es im Bestand nicht gibt, als "
                     "Quelle: X-0003")
        meldet("A2", "als Quelle: S-0005")
        meldet("A3", "als Quelle: S-0005")
        meldet("A7", "zitiert Claim-IDs, die es im Bestand nicht gibt: C-9999")
        self.assertEqual(zeilen["D1"]["verstoesse"], [])
        for kennung in ("C1", "A4", "V1", "V2", "V3"):
            with self.subTest(vorschlag=kennung):
                self.assertFalse(zeilen[kennung]["kennung_unbekannt"])
                meldet(kennung, "Vollsichtung war Pflicht")
        meldet("C1", "als Quelle: S-0005")
        for kennung in ("B3", "B4", "B8", "C3", "E1"):
            with self.subTest(fehlen=kennung):
                self.assertEqual(zeilen[kennung]["verstoesse"], [])
                self.assertEqual(tool_urteil(zeilen[kennung]),
                                 "Kennung unbekannt")
        meldet("G1", "bestreitet eine Kennung, die es im Bestand gibt: C-0401")
        self.assertFalse(zeilen["G1"]["gefunden"])
        self.assertEqual(zeilen["G1"]["zitiert"], [])
        meldet("F2", "bestreitet eine Kennung, die es im Bestand gibt: S-0004")
        meldet("S1", "ohne eingereichte Quittung")
        meldet("S2", "nennt 26 von 30 Claims, die Quittung belegt 28 von 28")
        self.assertEqual(zeilen["S3"]["verstoesse"], [])

        # Vorgegebener Umfang ohne Quittung: Die Meldung nennt den Umfang.
        umfang = self.pruefe([{
            "id": "U7", "art": "negativ", "frage": NEGATIV,
            "umfang_vorgegeben": True, "sweep_args": ["--domain", "demo-okf"],
            "antwort": "In diesem Umfang nicht gefunden."}],
            argumente=["--json"])
        verstoesse = json.loads(umfang.stdout)["zeilen"][0]["verstoesse"]
        self.assertIn("Vollsichtung war Pflicht (weak), es liegt aber keine "
                      "vollständige Quittung über den vorgegebenen Umfang vor",
                      verstoesse)
        self.assertFalse(any("ohne dass das Protokoll einen Umfang vorgibt"
                             in meldung for meldung in verstoesse), verstoesse)

    def test_a_truncated_page_list_makes_the_sweep_mandatory(self):
        """Reicht die Liste omitted_pages nicht aus, ist 4b Pflicht.

        antworten.md, „Gekürzte Treffer": auch bei partial und strong. Die
        Demo hat zu wenige Seiten, um die Obergrenze zu erreichen; eine Kopie
        mit der Obergrenze 1 zeigt den Fall.
        """
        frage = "S-0004 OKF B-0004"
        antwort = ("Laut Bestand ist OKF ein offenes Format für Wissen "
                   "(C-0301).")
        kopie = self.basis / "gekuerzt" / "wissenstresor"
        shutil.copytree(self.root, kopie)
        engine = kopie / "scripts/vault.py"
        quelltext = engine.read_text(encoding="utf-8")
        self.assertEqual(quelltext.count("\nMAX_OMITTED_PAGES = 20\n"), 1)
        engine.write_text(quelltext.replace(
            "\nMAX_OMITTED_PAGES = 20\n", "\nMAX_OMITTED_PAGES = 1\n"),
            encoding="utf-8")
        gepinnt = _cli(kopie, "checksum")
        self.assertEqual(gepinnt.returncode, 0, gepinnt.stdout + gepinnt.stderr)
        abfrage = json.loads(_cli(kopie, "query", frage).stdout)
        self.assertTrue(abfrage["coverage"]["omitted_pages_truncated"])
        self.assertEqual(abfrage["coverage"]["match_strength"], "partial")
        self.assertFalse(abfrage["fallback"]["exhaustive_review_required"])

        ohne = self.pruefe([{"id": "G1", "frage": frage, "antwort": antwort}],
                           vault=kopie, argumente=["--json"])
        zeile = json.loads(ohne.stdout)["zeilen"][0]
        self.assertTrue(zeile["pflicht"])
        self.assertIn("Vollsichtung war Pflicht (partial, Liste der gekürzten "
                      "Seiten gekürzt), es liegt aber keine vollständige "
                      "Quittung über den ganzen Bestand vor",
                      zeile["verstoesse"])
        # Mit der Vollsichtung ist die Pflicht erfüllt.
        quittung, fertig = self.sichtung(frage, {"C-0301"}, root=kopie)
        mit = self.pruefe([{
            "id": "G2", "frage": frage, "quittung": quittung,
            "antwort": antwort + "\n\n" + self.zeile_sichtung(fertig)}],
            vault=kopie, argumente=["--json"])
        self.assertEqual(json.loads(mit.stdout)["zeilen"][0]["verstoesse"], [])
        # Ohne Kürzung ist dieselbe Frage keine Pflicht.
        frei = self.pruefe([{"id": "G3", "frage": frage, "antwort": antwort}],
                           argumente=["--json"])
        zeile = json.loads(frei.stdout)["zeilen"][0]
        self.assertFalse(zeile["pflicht"])
        self.assertEqual(zeile["verstoesse"], [])

    def test_typographic_dashes_are_hyphens(self):
        """Ein Modell, das U+2011 setzt, zitiert trotzdem."""
        result = self.pruefe([
            {"id": "D1", "frage": BEGRIFF, "erwartet": ["C-0305"],
             "antwort": "Laut Bestand gibt es vier Stufen (C\u20110305)."},
            {"id": "D2", "frage": BEGRIFF,
             "antwort": "Vier Stufen (C-0305), vergeben vom Kurator "
                        "(C\u20119998)."},
        ], argumente=["--json"])
        zeilen = {zeile["id"]: zeile
                  for zeile in json.loads(result.stdout)["zeilen"]}
        self.assertEqual(zeilen["D1"]["zitiert"], ["C-0305"])
        self.assertTrue(zeilen["D1"]["gefunden"])
        self.assertEqual(zeilen["D1"]["verstoesse"], [])
        self.assertIn("zitiert Claim-IDs, die es im Bestand nicht gibt: "
                      "C-9998", zeilen["D2"]["verstoesse"])

    def test_step_4c_is_checked_where_the_contract_makes_it_mandatory(self):
        """Seit v0.17.0 wird Schritt 4c nie still ausgelassen.

        Bleibt die Frage nach der Vollsichtung ungedeckt und sind Quellen
        aufgeführt, weist die Antwort aus, was extern gefunden oder nicht
        gelesen wurde, oder dass der Schritt unterblieb. Das Werkzeug rechnet
        die Abfrage mit --extern selbst nach, immer offline.
        """
        quittung, leer = self.sichtung(NEGATIV)
        kern = "Nicht im Bestand.\n" + self.zeile_sichtung(leer) + "\n"

        def zeile(antwort, frage=NEGATIV, eintraege=None, vorgabe=None,
                  **weiter):
            eintrag = {
                "id": "N1", "art": "negativ", "frage": frage,
                "quittung": quittung if eintraege is None else eintraege,
                "antwort": antwort}
            if vorgabe is not None:
                eintrag["vorgabe"] = vorgabe
            ergebnis = self.pruefe([eintrag], argumente=["--json"], **weiter)
            daten = json.loads(ergebnis.stdout)
            return daten["zeilen"][0], daten["zusammenfassung"]

        still, summe = zeile(kern)
        self.assertTrue(still["extern_pflicht"])
        self.assertEqual(summe["pflicht_extern"], 1)
        self.assertTrue(any(m.startswith("Schritt 4c fehlt")
                            for m in still["verstoesse"]), still)
        for name, antwort in {
                "eigene Zeile": kern + EXTERN,
                # Wie im Vertragsbeispiel: das Etikett mitten im Absatz.
                "im Satz": "Nicht im Bestand: Der Bestand nennt keinen "
                           "Urlaubsanspruch. " + EXTERN + ".\n"
                           + self.zeile_sichtung(leer),
                "Liste unter Etikett": kern + "**Extern nicht gelesen:**\n- "
                                       "X-0001: nicht gebunden\n- X-0002: "
                                       "SKILLSAFE_OFFLINE gesetzt\n\nHinweise: "
                                       "keine",
                "Überschrift ohne Doppelpunkt": kern + "### Extern nicht "
                                                "gelesen\n- X-0001 (nicht "
                                                "gebunden)\n- X-0002 (offline)",
                "Etikett, Leerzeile, Liste": kern + "Extern nicht gelesen:\n\n"
                                             "- X-0001 (nicht gebunden)\n"
                                             "- X-0002 (offline)",
        }.items():
            with self.subTest(form=name):
                sauber, _ = zeile(antwort)
                self.assertEqual(sauber["verstoesse"], [])
        halb, _ = zeile(kern + "Extern nicht gelesen: X-0001 (nicht gebunden) "
                        "— kein Negativbefund")
        self.assertTrue(any("fehlt für X-0002" in m
                            for m in halb["verstoesse"]), halb)
        # Unterbleibt der Schritt, nennt die Zeile jede aufgeführte Quelle.
        # Entfallen darf er nur auf Wunsch des Nutzers oder nach einer
        # Vorgabe der Umgebung; die hält das Protokoll fest.
        bitte = "Bitte schlag dafür nicht in externen Quellen nach."
        verzichtszeile = (kern + "Extern nicht gelesen: X-0001, X-0002 nicht "
                          "nachgeschlagen (auf deinen Wunsch) — kein "
                          "Negativbefund")
        verzicht, verzicht_summe = zeile(verzichtszeile, vorgabe=bitte)
        self.assertEqual(verzicht["verstoesse"], [])
        self.assertTrue(verzicht["extern_verzicht"])
        self.assertEqual(verzicht_summe["verzicht_extern"], 1)
        eigenmaechtig, _ = zeile(verzichtszeile)
        self.assertTrue(any(m.startswith("Verzicht auf Schritt 4c ohne Vorgabe")
                            for m in eigenmaechtig["verstoesse"]), eigenmaechtig)
        verteilt, _ = zeile(kern + "Extern nicht gelesen: X-0001 nicht "
                            "nachgeschlagen (auf Wunsch).\nExtern nicht gelesen: "
                            "X-0002 nicht nachgeschlagen (auf Wunsch).")
        self.assertTrue(any(m.startswith("Verzicht auf Schritt 4c ohne Vorgabe")
                            for m in verteilt["verstoesse"]), verteilt)
        # Eine Frage danach weist keine Quelle aus.
        nachfrage, _ = zeile(kern + "Extern nicht gelesen: X-0002 (offline) — "
                             "kein Negativbefund\nSoll ich X-0001 auf diesem "
                             "Host binden?")
        self.assertTrue(any("fehlt für X-0001" in m
                            for m in nachfrage["verstoesse"]), nachfrage)
        verzicht_halb, _ = zeile(kern + "Extern nicht gelesen: X-0001 nicht "
                                 "nachgeschlagen (Nutzerwunsch) — kein "
                                 "Negativbefund", vorgabe=bitte)
        self.assertTrue(any("X-0002 fehlt" in m
                            for m in verzicht_halb["verstoesse"]), verzicht_halb)
        # Ohne Vorgabe ist „nicht nachgeschlagen" für einen Teil der Quellen
        # der Wortlaut einer Zeile nach dem Aufruf: normaler Weg.
        nach_aufruf, _ = zeile(kern + "Extern nicht gelesen: X-0001 (nicht "
                               "gebunden). Extern nicht gelesen: X-0002 nicht "
                               "nachgeschlagen (SKILLSAFE_OFFLINE gesetzt) — "
                               "kein Negativbefund")
        self.assertEqual(nach_aufruf["verstoesse"], [])
        nach_aufruf_halb, _ = zeile(kern + "Extern nicht gelesen: X-0001 nicht "
                                    "nachgeschlagen (Nutzerwunsch) — kein "
                                    "Negativbefund")
        self.assertTrue(any("fehlt für X-0002" in m
                            for m in nach_aufruf_halb["verstoesse"]),
                        nach_aufruf_halb)
        # Eine Trefferzeile nennt nur, was die Abfrage liefert. Hier liest
        # sie nichts: X-0001 ist nicht gebunden, X-0002 hinter dem Schalter.
        erfunden = (kern + EXTERN + "\nExtern (nicht im Bestand): X-0001 "
                    "handbuch/miete.md, Satz 1\nExtern (nicht im Bestand): "
                    "X-0002 README.md, Satz 4")
        gebunden_bekannt, _ = zeile(erfunden, stand={
            "extern": {"gebunden": [], "offline": True}})
        self.assertTrue(any(
            "ohne Treffer der Abfrage" in m and "X-0001 handbuch/miete.md" in m
            and "X-0002 README.md" in m
            for m in gebunden_bekannt["verstoesse"]), gebunden_bekannt)
        # Ohne Angabe zur Bindung bleibt die lokale Quelle offen; die
        # Netzquelle nicht, denn der Lauf war offline.
        ohne_angabe, _ = zeile(erfunden)
        self.assertTrue(any(
            "ohne Treffer der Abfrage: X-0002 README.md" in m
            for m in ohne_angabe["verstoesse"]), ohne_angabe)
        self.assertTrue(any("X-0001 handbuch/miete.md" in h
                            for h in ohne_angabe["hinweise"]), ohne_angabe)
        # Eine Vorgabe ohne ausgewiesenen Verzicht ist ein Hinweis.
        trotzdem, _ = zeile(kern + EXTERN, vorgabe=bitte)
        self.assertEqual(trotzdem["verstoesse"], [])
        self.assertTrue(any("Vorgabe gegen das Nachschlagen" in h
                            for h in trotzdem["hinweise"]), trotzdem)
        # Ohne Offline-Angabe zum Lauf bleibt offen, was die Netzquelle
        # geliefert hätte: ein Hinweis, kein Verstoß.
        online, _ = zeile(kern + "Extern nicht gelesen: X-0001 (nicht gebunden) "
                          "— kein Negativbefund", offline=False)
        self.assertEqual(online["verstoesse"], [])
        self.assertTrue(any("Netzquelle nicht nachgeprüft (X-0002)" in h
                            for h in online["hinweise"]), online)
        # Die Angabe im Protokoll gilt vor der Umgebung des Werkzeugs.
        protokoll_offline, _ = zeile(
            kern + "Extern nicht gelesen: X-0001 (nicht gebunden) — kein "
            "Negativbefund", offline=False,
            stand={"extern": {"gebunden": [], "offline": True}})
        self.assertTrue(any("fehlt für X-0002" in m
                            for m in protokoll_offline["verstoesse"]),
                        protokoll_offline)
        # invalid_query liest nichts: Auch dann gehört die Zeile dazu.
        frage_kurz = "Was ist das?"
        kurz, kurz_fertig = self.sichtung(frage_kurz)
        unbrauchbar, _ = zeile("Nicht im Bestand.\n"
                               + self.zeile_sichtung(kurz_fertig),
                               frage=frage_kurz, eintraege=kurz)
        self.assertTrue(unbrauchbar["extern_pflicht"])
        self.assertTrue(any(m.startswith("Schritt 4c fehlt")
                            for m in unbrauchbar["verstoesse"]), unbrauchbar)

    def test_the_contract_examples_for_step_4c_read_as_written(self):
        """„Extern nicht gelesen" und „Teilweise gelesen": Die Beispiele im
        Vertrag schreiben die Angaben in den Fließtext, mitten in den Absatz.
        So liest sie das Werkzeug auch, Wort für Wort aus dem Vertrag."""
        tool = _werkzeug("antwort_check_bsp")
        vertrag = (SOURCE_SKILL / "references/antworten.md").read_text(
            encoding="utf-8")

        def beispiel(titel):
            absatz = " ".join(
                vertrag.split(f"**{titel}**", 1)[1].split("\n\n", 1)[0].split())
            return re.search(r"(?:Antwort: |kommen deshalb: )„(.+?)[\"“], dazu",
                             absatz).group(1)

        treffer, ungelesen = tool._extern_angaben(beispiel("Extern nicht gelesen"))
        self.assertEqual(treffer, [])
        self.assertEqual(len(ungelesen), 1, ungelesen)
        self.assertEqual(tool._kennungen(ungelesen[0]), {"X-0001", "X-0002"})
        treffer, ungelesen = tool._extern_angaben(beispiel("Teilweise gelesen"))
        self.assertEqual(len(treffer), 1, treffer)
        self.assertEqual(tool._kennungen(treffer[0]), {"X-0001"})
        self.assertTrue(tool._nennt_dokument(treffer[0],
                                             "handbuch/mietminderung.md"))
        self.assertEqual(len(ungelesen), 1, ungelesen)
        self.assertEqual(tool._kennungen(ungelesen[0]), {"X-0002"})
        # Formen, die die zweite Prüfung fand: Ein Dateiname behält seine
        # Unterstriche; eine lockere Liste ergibt je Punkt eine Angabe; eine
        # Etikettzeile mit Kennung gilt für die Punkte darunter; ein Etikett
        # hinter einer schließenden Klammer beginnt einen neuen Satz; eine
        # Frage setzt keine Angabe fort.
        treffer, _ = tool._extern_angaben(
            "Extern (nicht im Bestand): X-0001, handbuch/miet_recht.md, Satz 2")
        self.assertTrue(tool._nennt_dokument(treffer[0], "handbuch/miet_recht.md"))
        treffer, _ = tool._extern_angaben(
            "**Extern (nicht im Bestand):**\n\n- X-0001, a.md, Satz 3\n\n"
            "- X-0001, b.md, Satz 9\n\nHinweise: keine")
        self.assertEqual(treffer, ["X-0001, a.md, Satz 3", "X-0001, b.md, Satz 9"])
        treffer, _ = tool._extern_angaben(
            "Extern (nicht im Bestand): X-0001\n- a.md, Satz 3\n- b.md, Satz 9")
        self.assertEqual([tool._kennungen(t) for t in treffer],
                         [{"X-0001"}, {"X-0001"}])
        treffer, ungelesen = tool._extern_angaben(
            "Nicht im Bestand: „Darf er das?“ Extern (nicht im Bestand): X-0001, "
            "a.md (Satz 3, lokal gelesen.) Extern nicht gelesen: X-0002 (offline).")
        self.assertEqual((len(treffer), len(ungelesen)), (1, 1))
        _, ungelesen = tool._extern_angaben(
            "Extern nicht gelesen: X-0002 (offline) — kein Negativbefund\n"
            "Soll ich X-0001 auf diesem Host binden?")
        self.assertEqual(tool._kennungen(" ".join(ungelesen)), {"X-0002"})

    def test_step_4c_follows_the_contract_of_the_checked_vault(self):
        """Ob 4c Pflicht ist, sagt der Vertrag des Tresors, nicht VERSION."""
        tool = _werkzeug("antwort_check_4c")
        # Ändert sich die Formulierung, muss das Werkzeug mitwachsen.
        self.assertTrue(tool.vertrag_4c(SOURCE_SKILL))
        self.assertIsNone(tool.vertrag_4c_hinweis(SOURCE_SKILL))
        self.assertEqual(tool._version("0.17"), (0, 17, 0))
        # Die Fassung von v0.15.0 stellt den Schritt frei; ein Zeilenumbruch
        # in der Formel ändert nichts.
        for fassung, pflicht in (
                ("4c. **Externer Fallback.** Eine Option, keine Pflicht, und "
                 "nie von selbst:", False),
                ("4c. **Externer Fallback.** Der Schritt\n   ist **Pflicht**, "
                 "sobald beide", True)):
            with self.subTest(fassung=fassung[:40]):
                alt_vault = self.basis / f"fassung-{int(pflicht)}"
                (alt_vault / "references").mkdir(parents=True)
                (alt_vault / "references/antworten.md").write_text(
                    "# Antworten\n\n" + fassung + "\n", encoding="utf-8")
                self.assertIs(tool.vertrag_4c(alt_vault), pflicht)
                self.assertIsNone(tool.vertrag_4c_hinweis(alt_vault))
        ohne = self.basis / "ohne-4c"
        (ohne / "references").mkdir(parents=True)
        (ohne / "references/antworten.md").write_text(
            "# Antworten\n\nKein externer Schritt.\n", encoding="utf-8")
        self.assertFalse(tool.vertrag_4c(ohne))
        self.assertIn("nicht gefunden", tool.vertrag_4c_hinweis(ohne))
        frei = self.basis / "frei" / "wissenstresor"
        shutil.copytree(self.root, frei)
        antworten_md = frei / "references/antworten.md"
        text = antworten_md.read_text(encoding="utf-8")
        self.assertEqual(text.count("Der Schritt ist **Pflicht**"), 1)
        antworten_md.write_text(text.replace(
            "Der Schritt ist **Pflicht**", "Der Schritt ist eine Option"),
            encoding="utf-8")
        gepinnt = _cli(frei, "checksum")
        self.assertEqual(gepinnt.returncode, 0, gepinnt.stdout + gepinnt.stderr)
        self.assertFalse(tool.vertrag_4c(frei))
        quittung, leer = self.sichtung(NEGATIV, root=frei)
        ergebnis = self.pruefe([{
            "id": "N1", "art": "negativ", "frage": NEGATIV, "quittung": quittung,
            "antwort": "Nicht im Bestand.\n" + self.zeile_sichtung(leer)}],
            argumente=["--json"], vault=frei,
            stand={"version": "1.4.0"})
        daten = json.loads(ergebnis.stdout)
        self.assertFalse(daten["zeilen"][0]["extern_pflicht"])
        self.assertEqual(daten["zusammenfassung"]["verstoesse"], 0)
        # Die Version im Protokoll passt nicht zum Tresor: ohne Manifest ein
        # Hinweis, mit Manifest ein Abbruch.
        self.assertTrue(any("nennt den Stand v1.4.0" in h
                            for h in daten["hinweise"]), daten["hinweise"])
        manifest = daten["stand"]["manifest_sha256"]
        falsch = self.pruefe([{
            "id": "N1", "art": "negativ", "frage": NEGATIV, "quittung": quittung,
            "antwort": "Nicht im Bestand.\n" + self.zeile_sichtung(leer)}],
            vault=frei, stand={"version": "0.15.0",
                               "manifest_sha256": manifest})
        self.assertEqual(falsch.returncode, 2, falsch.stdout)
        self.assertIn("nennt den Stand v0.15.0", falsch.stdout)

    def gebundene_kopie(self, name):
        """Eine Kopie des Testtresors, X-0001 an beispiel-extern gebunden."""
        gebunden = self.basis / name / "wissenstresor"
        shutil.copytree(self.root, gebunden)
        bindung = _cli(gebunden, "extern", "bind", "X-0001",
                       str(REPOSITORY / "beispiel-extern"))
        self.assertEqual(bindung.returncode, 0, bindung.stdout + bindung.stderr)
        return gebunden

    def test_step_4c_with_a_bound_source_needs_the_external_hits(self):
        """Gebunden liest die Abfrage X-0001; ihre Treffer gehören in die Antwort."""
        gebunden = self.gebundene_kopie("gebunden")
        frage = "Welche Vektordatenbank empfiehlt der Bestand?"
        quittung, leer = self.sichtung(frage, root=gebunden)
        extern = _extern(gebunden, frage)
        self.assertEqual(extern["state"], "external_candidates_found", extern)
        self.assertGreaterEqual(len(extern["hits"]), 2, extern["hits"])
        kern = "Nicht im Bestand.\n" + self.zeile_sichtung(leer) + "\n"
        ungelesen = ("Extern nicht gelesen: X-0002 (SKILLSAFE_OFFLINE gesetzt) "
                     "— kein Negativbefund")
        zeilen = [f"Extern (nicht im Bestand): {stelle['source_id']} "
                  f"{stelle['document']}, Satz {stelle['sentence_index']}"
                  for stelle in extern["hits"]]

        def ergebnis(antwort, vault=gebunden, stand=None):
            lauf = self.pruefe([{
                "id": "N1", "art": "negativ", "frage": frage,
                "quittung": quittung, "antwort": antwort}],
                argumente=["--json"], vault=vault, stand=stand)
            return lauf

        def zeile(antwort, **weiter):
            return json.loads(ergebnis(antwort, **weiter).stdout)["zeilen"][0]

        alles = kern + "\n".join(zeilen) + "\n" + ungelesen
        self.assertEqual(zeile(alles)["verstoesse"], [])
        # Fehlt ein Treffer, nennt das Werkzeug ihn mit Quelle und Dokument.
        ohne_einen = zeile(kern + "\n".join(zeilen[1:]) + "\n" + ungelesen)
        self.assertTrue(any("Treffer ohne Zeile" in m
                            and extern["hits"][0]["document"] in m
                            for m in ohne_einen["verstoesse"]), ohne_einen)
        ohne_ungelesen = zeile(kern + "\n".join(zeilen))
        self.assertTrue(any("fehlt für X-0002" in m
                            for m in ohne_ungelesen["verstoesse"]), ohne_ungelesen)
        # „nicht nachgeschlagen" für eine Quelle neben Treffern ist kein
        # Verzicht auf den ganzen Schritt.
        teilweise = zeile(kern + "\n".join(zeilen) + "\nExtern nicht gelesen: "
                          "X-0002 nicht nachgeschlagen (SKILLSAFE_OFFLINE "
                          "gesetzt) — kein Negativbefund")
        self.assertEqual(teilweise["verstoesse"], [])
        # Bindung im Protokoll: gleich, dann geprüft; abweichend, dann Abbruch.
        lauf = {"extern": {"gebunden": ["X-0001"], "offline": True}}
        mit_angabe = zeile(alles, stand=lauf)
        self.assertEqual(mit_angabe["verstoesse"], [])
        # Eine Trefferzeile nennt nur, was die Abfrage liefert; ein Dateiname
        # im zitierten Treffersatz ist keine Fundstelle.
        erfunden = zeile(alles + "\nExtern (nicht im Bestand): X-0001 "
                         "handbuch/mietkaution.md, Satz 2", stand=lauf)
        self.assertTrue(any(
            "ohne Treffer der Abfrage: X-0001 handbuch/mietkaution.md" in m
            for m in erfunden["verstoesse"]), erfunden)
        zitiert = zeile(kern + zeilen[0] + ": „Mehr steht in anhang/weiteres.md.“\n"
                        + "\n".join(zeilen[1:]) + "\n" + ungelesen, stand=lauf)
        self.assertEqual(zitiert["verstoesse"], [])
        # Dokument vor der Kennung, eine Erläuterung mit einer Bestandsseite
        # und eine lockere Liste: alles sauber.
        umgestellt = "\n".join(
            f"Extern (nicht im Bestand): {stelle['document']} aus "
            f"{stelle['source_id']} (Satz {stelle['sentence_index']}). Auch "
            f"knowledge/demo-okf/okf.md sagt dazu nichts."
            for stelle in extern["hits"])
        self.assertEqual(zeile(kern + umgestellt + "\n" + ungelesen,
                               stand=lauf)["verstoesse"], [])
        locker = ("**Extern (nicht im Bestand):**\n\n"
                  + "\n\n".join("- " + z.split(": ", 1)[1] for z in zeilen)
                  + "\n\n" + ungelesen)
        self.assertEqual(zeile(kern + locker, stand=lauf)["verstoesse"], [])
        # Eine Angabe ohne geliefertes Dokument ist erfunden, auch ohne Pfad.
        ohne_pfad = zeile(alles + "\nExtern (nicht im Bestand): X-0001, "
                          "Abschnitt Kaution, Satzposition 2", stand=lauf)
        self.assertTrue(any("ohne Treffer der Abfrage: X-0001, Abschnitt Kaution"
                            in m for m in ohne_pfad["verstoesse"]), ohne_pfad)
        # Als ungelesen ausgewiesen, obwohl gelesen, und ein fremder Zustand:
        # Hinweise.
        vorlage = zeile(kern + "\n".join(zeilen) + "\nExtern nicht gelesen: "
                        "X-0001 (nicht gebunden), X-0002 (SKILLSAFE_OFFLINE "
                        "gesetzt), Zustand unreachable — kein Negativbefund",
                        stand=lauf)
        self.assertTrue(any("aber gelesen: X-0001" in h
                            for h in vorlage["hinweise"]), vorlage)
        self.assertTrue(any("Zustand unreachable genannt" in h
                            for h in vorlage["hinweise"]), vorlage)
        abweichend = ergebnis(alles, stand={"extern": {"gebunden": [],
                                                       "offline": True}})
        self.assertEqual(abweichend.returncode, 2, abweichend.stdout)
        self.assertIn("dieser Host bindet X-0001", abweichend.stdout)
        # Ohne Angabe im Protokoll: Nennt die Antwort Treffer aus einer
        # Quelle, die die Nachrechnung nicht lesen kann, ist das ein Hinweis.
        ungebunden = zeile(alles, vault=self.root)
        self.assertFalse(any("fehlt für X-0001" in m
                             for m in ungebunden["verstoesse"]), ungebunden)
        self.assertTrue(any("Bindung weicht vermutlich ab" in h
                            for h in ungebunden["hinweise"]), ungebunden)

    def test_step_4c_answer_forms_read_as_meant(self):
        """Antwortformen aus der dritten bis fünften Prüfung, je Bindung ein Lauf.

        Sauber: Hervorhebung, Anführungszeichen und Klammern am Satzende, eine
        Erläuterung als Listenpunkt, eine Rückfrage in einer Angabe, ein
        nacktes Etikett mit Absatz, ein Kopf mit Liste nach einer Leerzeile,
        „keine Treffer". Verstoß: ein erfundenes Dokument unter einem Kopf,
        in derselben Zeile, in einem anderen Verzeichnis oder mit längerem
        Namen; ein Verzicht ohne Vorgabe; eine Kennung nur in einer
        Rückfrage, auch umbrochen oder in Klammern. Hinweis: ein Zustand, den
        die Abfrage nicht meldet, und eine gelesene Quelle als ungelesen. Die
        erste Frage des Protokolls hat keinen suchbaren Begriff; die
        Bindungsprobe nimmt dann die nächste. Aus der fünften Prüfung:
        Dokumente in Anführungszeichen oder mit „./“, Einleitungssätze und
        Teilsätze mit Rückfrage, ein Nachsatz mit Quellkennung und
        „keine Treffer“ in mehreren Wortlauten sind sauber; eine Tresordatei
        oder ein endungsloser Pfad als Fundstelle, eine Seitenangabe und
        Inhalt neben „keine Treffer“ sind Verstöße, ebenso eine Rückfrage
        hinter dem Etikett, die als einzige eine Quelle nennt.
        """
        gebunden = self.gebundene_kopie("formen")
        mit = "Welche Vektordatenbank empfiehlt der Bestand?"
        ohne = "Wie hoch darf die Mietkaution höchstens sein?"
        leer = "Was ist das?"
        treffer = _extern(gebunden, mit)
        self.assertEqual(treffer["state"], "external_candidates_found", treffer)
        self.assertGreaterEqual(len(treffer["hits"]), 2, treffer["hits"])
        self.assertEqual(_extern(gebunden, ohne)["state"],
                         "no_external_candidates")
        self.assertEqual(_extern(gebunden, leer)["state"], "invalid_query")
        self.assertEqual(_extern(self.root, ohne)["state"], "unreachable")
        alle = [f"{stelle['source_id']}, {stelle['document']}, Satzposition "
                f"{stelle['sentence_index']}" for stelle in treffer["hits"]]
        erstes = treffer["hits"][0]["document"]
        # Die erste Zeile unter einem Etikett ohne Doppelpunkt beginnt klein:
        # Sie setzt das Etikett trotzdem nicht fort.
        klein_zuerst = sorted(treffer["hits"],
                              key=lambda stelle: stelle["document"][:1].isupper())
        self.assertTrue(klein_zuerst[0]["document"][:1].islower(), klein_zuerst)
        verzeichnis, _, name = erstes.rpartition("/")
        laenger = (verzeichnis + "/" if verzeichnis else "") + "keine-" + name
        ung = ("Extern nicht gelesen: X-0002 (SKILLSAFE_OFFLINE gesetzt) — "
               "kein Negativbefund")

        def sichtung(frage, root):
            quittung, fertig = self.sichtung(frage, root=root)
            return quittung, self.zeile_sichtung(fertig)

        q_mit, s_mit = sichtung(mit, gebunden)
        q_ohne, s_ohne = sichtung(ohne, gebunden)
        q_leer, s_leer = sichtung(leer, gebunden)
        kern = "Nicht im Bestand.\n\n" + s_mit + "\n"
        zeilen = "\n".join("Extern (nicht im Bestand): " + z for z in alle)
        liste = "\n".join("- " + z for z in alle)
        zeilen_text = kern + zeilen
        antworten = {
            # Zuerst die Frage ohne suchbaren Begriff (invalid_query).
            "L-ohne-begriff": (leer, "Nicht im Bestand. Die Frage nennt "
                               "keinen Gegenstand.\n\n" + s_leer + "\nExtern "
                               "nicht gelesen: X-0001, X-0002 — Zustand "
                               "invalid_query, die Frage enthält keinen "
                               "suchbaren Begriff — kein Negativbefund"),
            "T-erlaeuterung": (mit, kern + "**Extern (nicht im Bestand):**\n"
                               + liste + "\n- Das ist nur ein Zeiger, der über "
                               "ein Wort der Frage nahe liegt; zur Frage sagt "
                               "er nichts.\n\n" + ung),
            "T-unterpunkt": (mit, kern + "Extern (nicht im Bestand):\n"
                             + "\n".join(f"- {z}\n  - nur lexikalisch nah"
                                         for z in alle) + "\n" + ung),
            "T-rueckfrage": (mit, kern + "**Extern (nicht im Bestand):**\n- "
                             + alle[0] + " — beantwortet das die Frage?\n"
                             + "\n".join("- " + z for z in alle[1:])
                             + "\n\n" + ung),
            "T-kopf-leerzeile": (mit, kern + "**Extern (nicht im Bestand): "
                                 "X-0001**\n\n" + "\n".join(
                                     f"- {stelle['document']}, Satzposition "
                                     f"{stelle['sentence_index']}"
                                     for stelle in treffer["hits"])
                                 + "\n\n" + ung),
            "T-kopf-erfunden": (mit, kern + "Extern (nicht im Bestand): "
                                + alle[0] + "\n- weiterer Treffer: "
                                "handbuch/erfunden.md, Satzposition 2\n"
                                + "\n".join("Extern (nicht im Bestand): " + z
                                            for z in alle[1:])
                                + "\n" + ung),
            "T-eine-zeile": (mit, kern + zeilen + "; X-0001, "
                             "handbuch/erfunden.md, Satzposition 2\n" + ung),
            "T-verzeichnis": (mit, kern + zeilen.replace(
                erstes, "archiv/" + name, 1) + "\n" + ung),
            "T-laengerer-name": (mit, kern + zeilen + "\nExtern (nicht im "
                                 f"Bestand): X-0001, {laenger}, Satzposition "
                                 "2\n" + ung),
            "O-fett": (ohne, "Nicht im Bestand. Der Tresor enthält **keine "
                       "Aussage zur Mietkaution.** " + ung + "\n\n" + s_ohne),
            "O-kursiv": (ohne, "*Nicht im Bestand.* " + ung + "\n\n" + s_ohne),
            "O-fett-ganz": (ohne, "**Nicht im Bestand.** " + ung + "\n\n"
                            + s_ohne),
            "O-guillemets": (ohne, f"Nicht im Bestand: »{ohne}« " + ung
                             + "\n\n" + s_ohne),
            "O-anfuehrung": (ohne, f"Nicht im Bestand: „{ohne}“ " + ung
                             + "\n\n" + s_ohne),
            "O-keine-treffer": (ohne, "Nicht im Bestand.\n\n" + s_ohne
                                + "\nExtern (nicht im Bestand): keine Treffer "
                                "in X-0001 (bei dieser Abfrage lokal "
                                "gelesen)\n" + ung),
            "O-nichts": (ohne, "Nicht im Bestand.\n\n" + s_ohne + "\nExtern "
                         "(nicht im Bestand): nichts gefunden\n" + ung),
            "O-rueckfrage": (ohne, "Nicht im Bestand.\n\n" + s_ohne
                             + "\nExtern nicht gelesen:\n- X-0002: "
                             "SKILLSAFE_OFFLINE gesetzt — soll ich es abrufen, "
                             "sobald Netz da ist?\n- kein Negativbefund"),
            "O-etikett-absatz": (ohne, "Nicht im Bestand.\n\n" + s_ohne
                                 + "\n\n**Extern nicht gelesen:**\n\nX-0002 "
                                 "(SKILLSAFE_OFFLINE gesetzt) — kein "
                                 "Negativbefund"),
            "O-ueberschrift": (ohne, "Nicht im Bestand.\n\n" + s_ohne
                               + "\n\n### Extern nicht gelesen\n\nX-0002 "
                               "(SKILLSAFE_OFFLINE gesetzt) — kein "
                               "Negativbefund"),
            "O-zustand": (ohne, "Nicht im Bestand.\n\n" + s_ohne + "\nExtern "
                          "nicht gelesen: X-0002 (SKILLSAFE_OFFLINE gesetzt), "
                          "Zustand not_bound — kein Negativbefund"),
            "O-zustand-code": (ohne, "Nicht im Bestand.\n\n" + s_ohne
                               + "\nExtern nicht gelesen: X-0002 "
                               "(SKILLSAFE_OFFLINE gesetzt), Zustand "
                               "`budget_exceeded` — kein Negativbefund"),
            "O-verzicht-nachsatz": (ohne, "Nicht im Bestand.\n\n" + s_ohne
                                    + "\nExtern nicht gelesen:\n- X-0001\n- "
                                    "X-0002\nBeide nicht nachgeschlagen, weil "
                                    "die Frage klar außerhalb des Bestands "
                                    "liegt — kein Negativbefund."),
            # Auch kleingeschrieben gilt ein Nachsatz ohne Einrückung für
            # jeden Punkt der Liste.
            "O-verzicht-nachsatz-klein": (ohne, "Nicht im Bestand.\n\n"
                                          + s_ohne + "\nExtern nicht "
                                          "gelesen:\n- X-0001\n- X-0002\n"
                                          "beide nicht nachgeschlagen, weil "
                                          "die Frage klar außerhalb des "
                                          "Bestands liegt — kein "
                                          "Negativbefund."),
            "O-verzicht-zeile": (ohne, "Nicht im Bestand.\n\n" + s_ohne
                                 + "\nExtern nicht gelesen: X-0001, X-0002 "
                                 "nicht nachgeschlagen, weil die Frage klar "
                                 "außerhalb des Bestands liegt — kein "
                                 "Negativbefund."),
            "O-gelesen": (ohne, "Nicht im Bestand.\n\n" + s_ohne + "\n" + ung
                          + "; X-0001 wurde bei dieser Abfrage lokal gelesen, "
                          "ohne Treffer."),
            # Aus der vierten Prüfung: Eine Trefferangabe ohne geliefertes
            # Dokument ist erfunden, auch ohne .md-Pfad; nur ein
            # ausdrückliches „keine Treffer" behauptet nichts.
            "T-erfunden-kapitel": (mit, kern + zeilen + "\nExtern (nicht im "
                                   "Bestand): X-0001, Kapitel Kaution des "
                                   "Beispielhandbuchs: höchstens drei "
                                   "Monatsmieten\n" + ung),
            "T-erfunden-pdf": (mit, kern + zeilen + "\nExtern (nicht im "
                               "Bestand): X-0001, handbuch/mietkaution.pdf, "
                               "Absatz 2\n" + ung),
            "T-erfunden-ohne-endung": (mit, kern + zeilen + "\nExtern (nicht "
                                       "im Bestand): X-0001, "
                                       "handbuch/mietkaution, sentence_index "
                                       "4\n" + ung),
            "T-kennung-dahinter": (mit, kern + zeilen + "; außerdem "
                                   "handbuch/mietkaution.md (X-0002), "
                                   "Satzposition 2\n" + ung),
            "T-punkt-schraegstrich": (mit, kern + zeilen + "; X-0001, "
                                      "./handbuch/erfunden.md, Satzposition "
                                      "2\n" + ung),
            "T-unterstrich-erfunden": (mit, kern + zeilen + "; X-0001, "
                                       "_handbuch/erfunden.md_, Satzposition "
                                       "2\n" + ung),
            # Eine Liste nach einer Rückfrage gehört zur Frage.
            "T-rueckfrage-liste": (mit, kern + zeilen + "\nSoll ich zusätzlich "
                                   "diese Dokumente der Quelle prüfen lassen?"
                                   "\n- handbuch/anhang-a.md\n- "
                                   "handbuch/anhang-b.md\n" + ung),
            # Ein Etikett als Überschrift ohne Doppelpunkt; die Zeile danach
            # setzt es nicht fort, auch kleingeschrieben.
            "T-ueberschrift-ohne-doppelpunkt": (
                mit, kern + "### Extern (nicht im Bestand)\n" + "\n".join(
                    f"{stelle['document']} ({stelle['source_id']}), "
                    f"Satzposition {stelle['sentence_index']}"
                    for stelle in klein_zuerst) + "\n\n" + ung),
            "T-fett-ohne-doppelpunkt": (
                mit, kern + "**Extern (nicht im Bestand)**\n" + "\n".join(
                    f"{stelle['document']} ({stelle['source_id']}), "
                    f"Satzposition {stelle['sentence_index']}"
                    for stelle in klein_zuerst) + "\n\n" + ung),
            # Ein geliefertes Dokument in Hervorhebung, mit absolutem Pfad
            # oder unter der Kennung als Ordner ist genannt; ein Verweis auf
            # eine Datei des eigenen Tresors ist kein Treffer.
            "T-hervorhebung": (mit, kern + "\n".join(
                f"Extern (nicht im Bestand): X-0001, _{stelle['document']}_, "
                f"Satzposition {stelle['sentence_index']}"
                for stelle in treffer["hits"]) + "\n" + ung),
            "T-absolut": (mit, kern + "\n".join(
                f"Extern (nicht im Bestand): X-0001, "
                f"{REPOSITORY / 'beispiel-extern' / stelle['document']}, "
                f"Satzposition {stelle['sentence_index']}"
                for stelle in treffer["hits"]) + "\n" + ung),
            "T-quelle-als-ordner": (mit, kern + "\n".join(
                f"Extern (nicht im Bestand): X-0001/{stelle['document']}, "
                f"Satzposition {stelle['sentence_index']}"
                for stelle in treffer["hits"]) + "\n" + ung),
            "T-eigene-dateien": (mit, kern + "\n".join(
                f"Extern (nicht im Bestand): X-0001 (aufgeführt in "
                f"sources/EXTERN.md), {stelle['document']}, Satzposition "
                f"{stelle['sentence_index']} — nach Schritt 4c aus "
                f"references/antworten.md, kein Beleg"
                for stelle in treffer["hits"]) + "\n" + ung),
            "O-zustand-kursiv": (ohne, "Nicht im Bestand.\n\n" + s_ohne
                                 + "\nExtern nicht gelesen: X-0002 "
                                 "(SKILLSAFE_OFFLINE gesetzt), Zustand "
                                 "_unreachable_ — kein Negativbefund"),
            "O-keine-treffer-bestandsseite": (
                ohne, "Nicht im Bestand.\n\n" + s_ohne + "\nExtern (nicht im "
                "Bestand): keine Treffer in X-0001 (bei dieser Abfrage lokal "
                "gelesen; im Bestand steht nur "
                "knowledge/demo-extern/mietminderung.md)\n" + ung),
            # Eine Kennung im Klammerzusatz des Etiketts gehört zur Angabe.
            "O-klammer-kennung": (ohne, "Nicht im Bestand.\n\n" + s_ohne
                                  + "\nExtern nicht gelesen (X-0002, "
                                  "SKILLSAFE_OFFLINE gesetzt — kein "
                                  "Negativbefund)"),
            "O-klammer-kennung-liste": (ohne, "Nicht im Bestand.\n\n" + s_ohne
                                        + "\n**Extern nicht gelesen** "
                                        "(X-0002):\n- SKILLSAFE_OFFLINE "
                                        "gesetzt — kein Negativbefund"),
            "O-klammer-zustand": (ohne, "Nicht im Bestand.\n\n" + s_ohne
                                  + "\nExtern nicht gelesen (Zustand nur "
                                  "für X-0002): SKILLSAFE_OFFLINE gesetzt — "
                                  "kein Negativbefund"),
            # Aus der fünften Prüfung: Formen, die ein Agent so schreibt.
            "T-anfuehrungszeichen": (mit, kern + "\n".join(
                f"Extern (nicht im Bestand): X-0001, Dokument "
                f"„{stelle['document']}“, Satzposition {stelle['sentence_index']}"
                for stelle in treffer["hits"]) + "\n" + ung),
            "T-punkt-schraegstrich-geliefert": (mit, kern + "\n".join(
                f"Extern (nicht im Bestand): X-0001, ./{stelle['document']}, "
                f"Satzposition {stelle['sentence_index']}"
                for stelle in treffer["hits"]) + "\n" + ung),
            "T-einleitung-mit-rueckfrage": (
                mit, kern + "**Extern (nicht im Bestand):**\nIch habe drei "
                "Zeiger gefunden — soll ich sie genauer ansehen?\n" + liste
                + "\n\n" + ung),
            "T-einleitung-satz": (mit, kern + "**Extern (nicht im Bestand):**\n"
                                  "Ich habe drei Zeiger gefunden.\n" + liste
                                  + "\n\n" + ung),
            "T-bindestrich-rueckfrage": (mit, kern + "\n".join(
                f"Extern (nicht im Bestand): X-0001 - {stelle['document']}, "
                f"Satzposition {stelle['sentence_index']} - passt das?"
                for stelle in treffer["hits"]) + "\n" + ung),
            "T-teilsatz-rueckfrage": (mit, kern + "\n".join(
                f"Extern (nicht im Bestand): X-0001 — {stelle['document']}, "
                f"Satzposition {stelle['sentence_index']}, nur lexikalisch "
                f"nah: hilft das?" for stelle in treffer["hits"]) + "\n" + ung),
            "T-code-rueckfrage": (mit, kern + "**Extern (nicht im Bestand):**\n"
                                  + "\n".join(
                f"- `X-0001`, `{stelle['document']}`, Satzposition "
                f"{stelle['sentence_index']} — beantwortet das die Frage?"
                for stelle in treffer["hits"]) + "\n\n" + ung),
            "T-nachsatz-mit-quelle": (mit, kern + "Extern (nicht im Bestand):\n"
                                      + "\n".join(
                f"- {stelle['document']}, Satzposition {stelle['sentence_index']}"
                for stelle in treffer["hits"]) + "\nAlle aus X-0001, bei dieser "
                "Abfrage lokal gelesen.\n\n" + ung),
            "T-zitierte-frage": (mit, kern + "\n".join(
                f"Extern (nicht im Bestand): X-0001 – {stelle['document']}, "
                f"Satzposition {stelle['sentence_index']}, nur lexikalisch "
                f"nah an „{mit}“" for stelle in treffer["hits"]) + "\n" + ung),
            "T-zusatz-und-absatz": (
                mit, kern + "**Extern (nicht im Bestand)** (X-0001, bei dieser "
                "Abfrage lokal gelesen):\n\n" + "\n".join(
                    f"{stelle['document']}, Satzposition "
                    f"{stelle['sentence_index']} — nur lexikalisch nah."
                    for stelle in treffer["hits"]) + "\n\n" + ung),
            "T-erfunden-hinter-zitierter-frage": (
                mit, kern + zeilen + " – außerdem handbuch/erfunden.md, "
                "Satzposition 2: „Welche Vektordatenbank ist gemeint?“\n" + ung),
            "T-tresordatei-zugeschrieben": (mit, kern + zeilen + "; X-0001, "
                                            "INDEX.md, Satzposition 2\n" + ung),
            "T-endungslos-daneben": (mit, kern + zeilen + "; außerdem "
                                     "handbuch/eigenbedarf, Satzposition 2\n"
                                     + ung),
            "O-kein-zeiger": (ohne, "Nicht im Bestand.\n\n" + s_ohne
                              + "\nExtern (nicht im Bestand): kein Zeiger.\n"
                              + ung),
            "O-keine-passenden": (ohne, "Nicht im Bestand.\n\n" + s_ohne
                                  + "\nExtern (nicht im Bestand): keine "
                                  "passenden Treffer in X-0001\n" + ung),
            "O-treffer-keine": (ohne, "Nicht im Bestand.\n\n" + s_ohne
                                + "\nExtern (nicht im Bestand): X-0001 – "
                                "Treffer: keine\n" + ung),
            "O-kein-dokument-enthaelt": (ohne, "Nicht im Bestand.\n\n" + s_ohne
                                         + "\nExtern (nicht im Bestand): Kein "
                                         "Dokument von X-0001 enthält die "
                                         "Anfragebegriffe\n" + ung),
            "O-schraegstrich-und-abschnitt": (
                ohne, "Nicht im Bestand.\n\n" + s_ohne + "\nExtern (nicht im "
                "Bestand): keine Treffer zu Mietkaution/Kaution in X-0001 – das "
                "Beispielhandbuch hat keinen Abschnitt dazu\n" + ung),
            "O-nur-keine": (ohne, "Nicht im Bestand.\n\n" + s_ohne
                            + "\nExtern (nicht im Bestand): keine\n" + ung),
            "O-inhalt-sonst-keine": (ohne, "Nicht im Bestand.\n\n" + s_ohne
                                     + "\nExtern (nicht im Bestand): X-0001 – "
                                     "die Kaution beträgt höchstens drei "
                                     "Monatsmieten; sonst keine Treffer\n"
                                     + ung),
            "O-seite": (ohne, "Nicht im Bestand.\n\n" + s_ohne + "\nExtern "
                        "(nicht im Bestand): keine Treffer in X-0001; Seite 4 "
                        "des Beispielhandbuchs regelt nur die Minderung\n"
                        + ung),
            "O-ohne-fundstelle": (ohne, "Nicht im Bestand.\n\n" + s_ohne
                                  + "\nExtern (nicht im Bestand): X-0001 – das "
                                  "Beispielhandbuch begrenzt die Kaution auf "
                                  "höchstens drei Monatsmieten (ohne "
                                  "Fundstelle)\n" + ung),
            "O-seite-kurz": (ohne, "Nicht im Bestand.\n\n" + s_ohne
                             + "\nExtern (nicht im Bestand): keine Treffer in "
                             "X-0001, Seite 4\n" + ung),
            "O-kein-kapitel": (ohne, "Nicht im Bestand.\n\n" + s_ohne
                               + "\nExtern (nicht im Bestand): keine Treffer in "
                               "X-0001 – das Beispielhandbuch hat kein Kapitel "
                               "Mietrecht\n" + ung),
            "T-zitat-ohne-teilsatz": (mit, kern + "\n".join(
                f"Extern (nicht im Bestand): X-0001 {stelle['document']} "
                f"(Satzposition {stelle['sentence_index']}) nah an „{mit}“"
                for stelle in treffer["hits"]) + "\n" + ung),
            "T-strich-ohne-komma": (mit, kern + "\n".join(
                f"Extern (nicht im Bestand): X-0001 {stelle['document']} "
                f"Satzposition {stelle['sentence_index']} — passt das?"
                for stelle in treffer["hits"]) + "\n" + ung),
            # Aus der sechsten Prüfung: Ein Vorsatz mit Grund bleibt eine
            # Aussage, auch mit vorangestelltem Nebensatz; ein zitierter
            # Pfad ist eine Nennung; der Klammerzusatz des Etiketts zählt;
            # eine Klammerfrage macht eine Einleitung nicht zur Frage.
            "T-nebensatz-dann-frage": (mit, zeilen_text + "\nExtern nicht "
                                       "gelesen (kein Negativbefund): Da "
                                       "SKILLSAFE_OFFLINE gesetzt ist, ist "
                                       "X-0002 nicht abgerufen worden, soll ich "
                                       "es später erneut versuchen?"),
            "T-wie-gemeldet-frage": (mit, zeilen_text + "\nExtern nicht "
                                     "gelesen (kein Negativbefund): Wie "
                                     "gemeldet, ist X-0002 nicht abgerufen "
                                     "worden (SKILLSAFE_OFFLINE gesetzt), soll "
                                     "ich es später versuchen?"),
            "T-treffer-mit-nebensatz": (mit, kern + "\n".join(
                f"Extern (nicht im Bestand): Weil nur ein Wort der Frage passt, "
                f"hat X-0001 mit {stelle['document']} (Satzposition "
                f"{stelle['sentence_index']}) wohl nur einen Zeiger geliefert, "
                f"hilft dir das?" for stelle in treffer["hits"]) + "\n" + ung),
            "T-zitat-erfunden": (mit, kern + "\n".join(
                f"Extern (nicht im Bestand): X-0001, Dokument "
                f"„{stelle['document']}“, Satzposition "
                f"{stelle['sentence_index']}" for stelle in treffer["hits"])
                + " und Dokument „handbuch/erfunden.md“, Satzposition 2\n"
                + ung),
            "T-zusatz-nennt-dokument": (mit, kern + "\n".join(
                f"**Extern (nicht im Bestand)** (X-0001, {stelle['document']}, "
                f"Satzposition {stelle['sentence_index']}, bei dieser Abfrage "
                f"lokal gelesen)" for stelle in treffer["hits"]) + "\n" + ung),
            "T-zusatz-erfunden": (mit, kern + "Extern (nicht im Bestand) "
                                  "(X-0001, handbuch/erfunden.md):\n" + liste
                                  + "\n\n" + ung),
            "T-frage-nach-anderem-dokument": (
                mit, kern + zeilen + "\nSoll ich auch handbuch/mietminderung.md, "
                "das Kapitel zur Minderung, durchsehen?\n" + ung),
            "T-klammerfrage-in-einleitung": (
                mit, kern + "Extern (nicht im Bestand): X-0001, bei dieser "
                "Abfrage lokal gelesen\nAlle liegen nur lexikalisch nah (oder "
                "suchst du etwas anderes?):\n" + "\n".join(
                    f"- {stelle['document']}, Satzposition "
                    f"{stelle['sentence_index']}" for stelle in treffer["hits"])
                + "\n\n" + ung),
            "T-stichwort-schraegstrich": (mit, kern + "\n".join(
                f"Extern (nicht im Bestand): X-0001, {stelle['document']}, "
                f"Stichwort Mieter/Vermieter, Satzposition "
                f"{stelle['sentence_index']}" for stelle in treffer["hits"])
                + "\n" + ung),
            "T-register-in-klammer": (mit, kern + "\n".join(
                f"Extern (nicht im Bestand): X-0001 (sources/EXTERN.md: lokal "
                f"gebunden), {stelle['document']}, Satzposition "
                f"{stelle['sentence_index']}" for stelle in treffer["hits"])
                + "\n" + ung),
            "O-leer-in-saetzen": (ohne, "Nicht im Bestand.\n\n" + s_ohne
                                  + "\nExtern (nicht im Bestand): Keine Treffer. "
                                  "X-0001 wurde bei dieser Abfrage lokal "
                                  "gelesen. Die Abfrage lief offline.\n" + ung),
            "O-leer-ich-habe": (ohne, "Nicht im Bestand.\n\n" + s_ohne
                                + "\nExtern (nicht im Bestand): Ich habe X-0001 "
                                "bei dieser Abfrage lokal durchsucht – keine "
                                "Treffer\n" + ung),
            "O-grund-der-engine": (ohne, "Nicht im Bestand.\n\n" + s_ohne
                                   + "\nExtern (nicht im Bestand): Kein gelesenes "
                                   "Dokument enthält die Anfragebegriffe hoch, "
                                   "hoechstens, mietkaution (X-0001, 4 Dokumente "
                                   "lokal gelesen)\n" + ung),
            "O-paragraf-als-thema": (ohne, "Nicht im Bestand.\n\n" + s_ohne
                                     + "\nExtern (nicht im Bestand): keine "
                                     "Treffer zu § 551 BGB in X-0001 (bei dieser "
                                     "Abfrage lokal gelesen)\n" + ung),
            "O-ordner-der-quelle": (ohne, "Nicht im Bestand.\n\n" + s_ohne
                                    + "\nExtern (nicht im Bestand): keine "
                                    "Treffer in X-0001 (Ordner "
                                    "beispiel-extern/handbuch, lokal "
                                    "gelesen)\n" + ung),
            "O-paragraf-als-stelle": (ohne, "Nicht im Bestand.\n\n" + s_ohne
                                      + "\nExtern (nicht im Bestand): X-0001 "
                                      "regelt die Kaution in § 4; sonst keine "
                                      "Treffer\n" + ung),
            "O-abschnitt-ueber": (ohne, "Nicht im Bestand.\n\n" + s_ohne
                                  + "\nExtern (nicht im Bestand): X-0001 – "
                                  "keine Treffer, nur der Abschnitt über "
                                  "Mietminderung\n" + ung),
            "O-am-ehesten": (ohne, "Nicht im Bestand.\n\n" + s_ohne
                             + "\nExtern (nicht im Bestand): X-0001 – kein "
                             "direkter Treffer; am ehesten "
                             "handbuch/mietminderung\n" + ung),
            # Ein Verzicht unter einer Überschrift, mit Vorgabe.
            "O-verzicht-ueberschrift": (
                ohne, "Nicht im Bestand.\n\n" + s_ohne + "\n### Extern nicht "
                "gelesen\nnicht nachgeschlagen: X-0001, X-0002 (der Nutzer "
                "will ausdrücklich nicht extern nachschlagen lassen) — kein "
                "Negativbefund", "Bitte nichts extern nachschlagen, nur den "
                "Tresor."),
        }
        quittungen = {mit: q_mit, ohne: q_ohne, leer: q_leer}

        def urteile(eintraege, vault, stand, name):
            protokoll = []
            for kennung, eintrag in eintraege.items():
                frage, antwort = eintrag[:2]
                zeile = {"id": kennung, "art": "negativ", "frage": frage,
                         "quittung": quittungen[frage], "antwort": antwort}
                if len(eintrag) > 2:
                    zeile["vorgabe"] = eintrag[2]
                protokoll.append(zeile)
            lauf = self.pruefe(protokoll, stand=stand, argumente=["--json"],
                               vault=vault,
                               ort=self.basis / f"protokoll-formen-{name}.json")
            self.assertIn(lauf.returncode, (0, 1), lauf.stdout + lauf.stderr)
            return {zeile["id"]: zeile
                    for zeile in json.loads(lauf.stdout)["zeilen"]}

        ergebnis = urteile(antworten, gebunden,
                           {"extern": {"gebunden": ["X-0001"], "offline": True}},
                           "gebunden")
        verstoesse = {
            "T-kopf-erfunden": "ohne Treffer der Abfrage: X-0001 "
                               "handbuch/erfunden.md",
            "T-eine-zeile": "ohne Treffer der Abfrage: X-0001 "
                            "handbuch/erfunden.md",
            "T-verzeichnis": f"ohne Treffer der Abfrage: X-0001 archiv/{name}",
            "T-laengerer-name": f"ohne Treffer der Abfrage: X-0001 {laenger}",
            "O-verzicht-nachsatz": "Verzicht auf Schritt 4c ohne Vorgabe",
            "O-verzicht-nachsatz-klein": "Verzicht auf Schritt 4c ohne Vorgabe",
            "O-verzicht-zeile": "Verzicht auf Schritt 4c ohne Vorgabe",
            "T-erfunden-kapitel": "ohne Treffer der Abfrage: X-0001, Kapitel "
                                  "Kaution",
            "T-erfunden-pdf": "ohne Treffer der Abfrage: X-0001 "
                              "handbuch/mietkaution.pdf",
            "T-erfunden-ohne-endung": "ohne Treffer der Abfrage: X-0001 "
                                      "handbuch/mietkaution",
            "T-kennung-dahinter": "ohne Treffer der Abfrage: X-0002 "
                                  "handbuch/mietkaution.md",
            "T-punkt-schraegstrich": "ohne Treffer der Abfrage: X-0001 "
                                     "handbuch/erfunden.md",
            "T-unterstrich-erfunden": "ohne Treffer der Abfrage: X-0001 "
                                      "handbuch/erfunden.md",
            "T-erfunden-hinter-zitierter-frage": "ohne Treffer der Abfrage: "
                                                 "X-0001 handbuch/erfunden.md",
            "T-tresordatei-zugeschrieben": "ohne Treffer der Abfrage: X-0001 "
                                           "INDEX.md",
            "T-endungslos-daneben": "handbuch/eigenbedarf",
            "O-inhalt-sonst-keine": "ohne Treffer der Abfrage",
            "O-seite": "ohne Treffer der Abfrage",
            "O-ohne-fundstelle": "ohne Treffer der Abfrage",
            "O-seite-kurz": "ohne Treffer der Abfrage",
            "T-zitat-erfunden": "ohne Treffer der Abfrage: X-0001 "
                                "handbuch/erfunden.md",
            "T-zusatz-erfunden": "handbuch/erfunden.md",
            "O-paragraf-als-stelle": "ohne Treffer der Abfrage",
            "O-abschnitt-ueber": "ohne Treffer der Abfrage",
            "O-am-ehesten": "ohne Treffer der Abfrage",
        }
        hinweise = {
            "O-zustand": "Zustand not_bound genannt, die Abfrage meldet "
                         "no_external_candidates",
            "O-zustand-code": "Zustand budget_exceeded genannt",
            "O-zustand-kursiv": "Zustand unreachable genannt",
            "O-gelesen": "Als nicht gelesen ausgewiesen, aber gelesen: X-0001",
        }
        self.assertEqual(set(ergebnis), set(antworten))
        for kennung, zeile in ergebnis.items():
            erwartet = verstoesse.get(kennung)
            if erwartet:
                self.assertTrue(any(erwartet in m for m in zeile["verstoesse"]),
                                (kennung, zeile["verstoesse"]))
            else:
                self.assertEqual(zeile["verstoesse"], [], (kennung, zeile))
            hinweis = hinweise.get(kennung)
            if hinweis:
                self.assertTrue(any(hinweis in h for h in zeile["hinweise"]),
                                (kennung, zeile["hinweise"]))
            else:
                self.assertEqual(zeile["hinweise"], [], (kennung, zeile))
        # Im anderen Verzeichnis ist der Treffer selbst nicht genannt.
        self.assertTrue(any("Treffer ohne Zeile" in m and erstes in m
                            for m in ergebnis["T-verzeichnis"]["verstoesse"]))
        self.assertIs(ergebnis["O-verzicht-ueberschrift"]["extern_verzicht"],
                      True)

        # Ungebunden: X-0001 bleibt ungelesen, und eine Rückfrage weist das
        # nicht aus, ob einzeilig, umbrochen oder in Klammern.
        q_frei, s_frei = sichtung(ohne, self.root)
        quittungen[ohne] = q_frei
        kopf = ("Nicht im Bestand.\n\n" + s_frei + "\nExtern nicht gelesen: "
                "X-0002 (SKILLSAFE_OFFLINE gesetzt), Zustand unreachable — "
                "kein Negativbefund\n")
        frei = urteile({
            "F-einzeilig": (ohne, kopf + "Soll ich X-0001 auf diesem Host "
                            "binden lassen?"),
            "F-umbrochen": (ohne, kopf + "Soll ich X-0001 auf diesem Host\n"
                            "binden lassen?"),
            "F-klammern": (ohne, kopf + "(Soll ich X-0001 auf diesem Host "
                           "binden lassen?)"),
            "F-liste": (ohne, "Nicht im Bestand.\n\n" + s_frei + "\n**Extern "
                        "nicht gelesen** (Zustand unreachable, kein "
                        "Negativbefund):\n- X-0001: auf diesem Host nicht "
                        "gebunden — soll ich das nachholen lassen?\n- X-0002: "
                        "SKILLSAFE_OFFLINE gesetzt"),
            "F-zustand": (ohne, "Nicht im Bestand.\n\n" + s_frei + "\nExtern "
                          "nicht gelesen: X-0001 (nicht gebunden), X-0002 "
                          "(SKILLSAFE_OFFLINE gesetzt); Zustand not_bound — "
                          "kein Negativbefund"),
            # Aus der vierten Prüfung: weitere Rückfragen, die keine Angabe
            # sind, und ein Nachsatz, der nur eine Quelle meint.
            "F-rueckfrage-liste": (ohne, kopf + "Soll ich diese Quelle auf "
                                   "diesem Host binden lassen?\n- X-0001 "
                                   "(Beispielhandbuch des Repositoriums, "
                                   "lokaler Ordner)"),
            "F-befehl": (ohne, kopf + "`vault.py extern bind X-0001 <pfad>` — "
                         "soll ich das für dich vorbereiten?"),
            "F-klein": (ohne, kopf + "oder soll ich X-0001 auf diesem Host "
                        "binden lassen?"),
            "F-listenpunkt-frage": (ohne, "Nicht im Bestand.\n\n" + s_frei
                                    + "\nExtern nicht gelesen:\n- X-0002: "
                                    "SKILLSAFE_OFFLINE gesetzt\n- Soll ich "
                                    "X-0001 auf diesem Host binden lassen?"),
            "F-klammer-im-satz": (ohne, "Nicht im Bestand.\n\n" + s_frei
                                  + "\nExtern nicht gelesen: X-0002 – "
                                  "SKILLSAFE_OFFLINE ist gesetzt (soll ich "
                                  "X-0001 auf diesem Host binden lassen?) — "
                                  "kein Negativbefund"),
            "F-semikolon": (ohne, "Nicht im Bestand.\n\n" + s_frei
                            + "\nExtern nicht gelesen: X-0002 – "
                            "SKILLSAFE_OFFLINE ist gesetzt; soll ich X-0001 "
                            "auf diesem Host binden lassen?"),
            "F-nachsatz-eine-quelle": (ohne, "Nicht im Bestand.\n\n" + s_frei
                                       + "\nExtern nicht gelesen:\n- X-0001: "
                                       "auf diesem Host nicht gebunden\n- "
                                       "X-0002: SKILLSAFE_OFFLINE gesetzt\n"
                                       "Zustand unreachable; X-0002 wurde "
                                       "deshalb nicht nachgeschlagen — kein "
                                       "Negativbefund."),
            # Aus der fünften Prüfung: Eine Aussage vor der Rückfrage weist
            # aus, eine Rückfrage allein nicht, auch nicht hinter dem Etikett.
            "F-strich-aussage-frage": (ohne, "Nicht im Bestand.\n\n" + s_frei
                                       + "\nExtern nicht gelesen: X-0002 "
                                       "(SKILLSAFE_OFFLINE gesetzt) — X-0001 "
                                       "ist auf diesem Host nicht gebunden, "
                                       "soll ich es binden?"),
            "F-bindestrich-aussage": (ohne, "Nicht im Bestand.\n\n" + s_frei
                                      + "\nExtern nicht gelesen: X-0002 - "
                                      "SKILLSAFE_OFFLINE gesetzt - X-0001 nicht "
                                      "gebunden, soll ich binden?"),
            "F-einleitung-liste": (ohne, "Nicht im Bestand.\n\n" + s_frei
                                   + "\nExtern nicht gelesen:\nBeide Quellen "
                                   "blieben ungelesen — soll ich es später "
                                   "erneut versuchen?\n- X-0001: auf diesem "
                                   "Host nicht gebunden\n- X-0002: "
                                   "SKILLSAFE_OFFLINE gesetzt\nKein "
                                   "Negativbefund."),
            "F-code-liste": (ohne, "Nicht im Bestand.\n\n" + s_frei
                             + "\n**Extern nicht gelesen:**\n- `X-0001`: auf "
                             "diesem Host nicht gebunden\n- `X-0002`: "
                             "`SKILLSAFE_OFFLINE` gesetzt\n\nKein "
                             "Negativbefund."),
            "F-umbruch-hinter-etikett": (ohne, "Nicht im Bestand.\n\n"
                                         + s_frei + "\nExtern nicht gelesen: "
                                         "X-0002 (SKILLSAFE_OFFLINE gesetzt), "
                                         "Zustand unreachable — soll ich X-0001"
                                         "\nauf diesem Host binden lassen?"),
            "F-frage-hinter-etikett": (ohne, "Nicht im Bestand.\n\n" + s_frei
                                       + "\nExtern nicht gelesen: X-0002 "
                                       "(SKILLSAFE_OFFLINE gesetzt), Zustand "
                                       "unreachable — soll ich X-0001 auf "
                                       "diesem Host binden lassen?"),
            "F-klammer-umbrochen": (ohne, "Nicht im Bestand.\n\n" + s_frei
                                    + "\nExtern nicht gelesen: X-0002 "
                                    "(SKILLSAFE_OFFLINE gesetzt) (soll ich "
                                    "X-0001\nbinden lassen?)"),
            "F-frage-mit-oder": (ohne, "Nicht im Bestand.\n\n" + s_frei
                                 + "\nExtern nicht gelesen: X-0002 "
                                 "(SKILLSAFE_OFFLINE gesetzt) — soll ich X-0001 "
                                 "binden, oder lieber nicht?"),
            # Aus der sechsten Prüfung: Ein Vorsatz ohne Grund oder
            # Lesestatus gehört zur Frage, auch wenn das Verb nicht auf einer
            # Liste steht; einer mit Grund ist eine Aussage.
            "F-falls-du": (ohne, kopf + "Falls du X-0001 nutzen willst, soll ich "
                           "es binden?"),
            "F-bindest-oder": (ohne, kopf + "Bindest du X-0001 auf diesem Host, "
                               "oder soll ich das übernehmen?"),
            "F-komma-frage": (ohne, kopf + "X-0001 binden, passt das?"),
            "F-apposition": (ohne, kopf + "Soll ich X-0001, das "
                             "Beispielhandbuch, binden lassen?"),
            "F-frage-mit-grund-im-einschub": (ohne, kopf + "Soll ich X-0001, "
                                              "die auf diesem Host nicht "
                                              "gebunden ist, binden lassen?"),
            "F-etikett-falls": (ohne, "Nicht im Bestand.\n\n" + s_frei
                                + "\nExtern nicht gelesen: X-0002 "
                                "(SKILLSAFE_OFFLINE gesetzt)\nExtern nicht "
                                "gelesen: Falls du X-0001 nutzen willst, soll "
                                "ich es binden?"),
            "F-grund-dann-frage": (ohne, "Nicht im Bestand.\n\n" + s_frei
                                   + "\nExtern nicht gelesen: X-0002 "
                                   "(SKILLSAFE_OFFLINE gesetzt); da X-0001 auf "
                                   "diesem Host nicht gebunden ist, ist sie "
                                   "nicht gelesen worden, soll ich sie binden "
                                   "lassen? Kein Negativbefund."),
            "F-klammerfrage-einleitung": (ohne, "Nicht im Bestand.\n\n"
                                          + s_frei + "\nExtern nicht gelesen "
                                          "(kein Negativbefund):\nBeide Quellen "
                                          "blieben ungelesen (soll ich es "
                                          "erneut versuchen?):\n- X-0001: auf "
                                          "diesem Host nicht gebunden\n- X-0002: "
                                          "SKILLSAFE_OFFLINE gesetzt"),
        }, self.root, {"extern": {"gebunden": [], "offline": True}}, "frei")
        for kennung in ("F-einzeilig", "F-umbrochen", "F-klammern",
                        "F-rueckfrage-liste", "F-befehl", "F-klein",
                        "F-listenpunkt-frage", "F-klammer-im-satz",
                        "F-semikolon", "F-umbruch-hinter-etikett",
                        "F-frage-hinter-etikett", "F-klammer-umbrochen",
                        "F-frage-mit-oder", "F-falls-du", "F-bindest-oder",
                        "F-komma-frage", "F-apposition", "F-etikett-falls",
                        "F-frage-mit-grund-im-einschub"):
            self.assertTrue(any("fehlt für X-0001" in m
                                for m in frei[kennung]["verstoesse"]),
                            (kennung, frei[kennung]))
        self.assertEqual(frei["F-liste"]["verstoesse"], [], frei["F-liste"])
        self.assertEqual(frei["F-liste"]["hinweise"], [], frei["F-liste"])
        self.assertEqual(frei["F-zustand"]["verstoesse"], [], frei["F-zustand"])
        nachsatz = frei["F-nachsatz-eine-quelle"]
        self.assertEqual(nachsatz["verstoesse"], [], nachsatz)
        self.assertIs(nachsatz["extern_verzicht"], False)
        for kennung in ("F-strich-aussage-frage", "F-bindestrich-aussage",
                        "F-einleitung-liste", "F-code-liste",
                        "F-grund-dann-frage", "F-klammerfrage-einleitung"):
            self.assertEqual(frei[kennung]["verstoesse"], [],
                             (kennung, frei[kennung]))

        # Endet jede Frage des Protokolls extern in invalid_query, liest
        # keine etwas, und kein Urteil hängt an der Bindung: Das Werkzeug
        # prüft, statt abzubrechen.
        q_leer_frei, s_leer_frei = sichtung(leer, self.root)
        quittungen[leer] = q_leer_frei
        einleitung = ("Nicht im Bestand. Die Frage nennt keinen Gegenstand."
                      "\n\n" + s_leer_frei)
        nur_leer = urteile({
            "L-sauber": (leer, einleitung + "\nExtern nicht gelesen: X-0001, "
                         "X-0002 — Zustand invalid_query, die Frage enthält "
                         "keinen suchbaren Begriff — kein Negativbefund"),
            "L-ohne-4c": (leer, einleitung),
        }, self.root, {"extern": {"gebunden": [], "offline": True}}, "nur-leer")
        self.assertEqual(nur_leer["L-sauber"]["verstoesse"], [], nur_leer)
        self.assertTrue(any("Schritt 4c fehlt" in m
                            for m in nur_leer["L-ohne-4c"]["verstoesse"]),
                        nur_leer)
        self.assertTrue(any("Zustand not_bound genannt, die Abfrage meldet "
                            "unreachable" in h
                            for h in frei["F-zustand"]["hinweise"]),
                        frei["F-zustand"])

    def test_form_does_not_fool_the_tool(self):
        """Umbruch, Hervorhebung, Doppelpunkt: derselbe Verstoß, andere Form."""
        quittung, fertig = self.sichtung(NEGATIV)
        abdruck = fertig["sweep_fingerprint"]
        ohne_quittung = {
            "Formel umbrochen": (
                "Es gibt vier Stufen (C-0305). Wer sie vergibt, ist nicht im"
                "\nBestand.", "ohne vollständige Quittung"),
            "Formel hervorgehoben": (
                "Es gibt vier Stufen (C-0305). Der Rest ist **nicht** im "
                "_Bestand_.", "ohne vollständige Quittung"),
            "Formel mit geschütztem Leerzeichen": (
                "Nicht\u00a0im\u00a0Bestand.", "ohne vollständige Quittung"),
            "behauptete Sichtung": (
                "Es gibt vier Stufen (C-0305).\nSichtung: 28 von 28 Claims, "
                "Quittung 0123456789ab",
                "ohne eingereichte Quittung"),
        }
        for name, (antwort, meldung) in ohne_quittung.items():
            with self.subTest(fall=name):
                result = self.pruefe([{
                    "id": "A1", "frage": BEGRIFF, "antwort": antwort}])
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn(meldung, result.stdout)

        mit_quittung = {
            "Zahlen ohne das Wort Claims": (
                f"Nicht im Bestand.\nSichtung: 5 von 28, Quittung: {abdruck[:12]}",
                "nennt 5 von 28, die Quittung belegt 28 von 28 Claims"),
            "Kennung hinter Doppelpunkt": (
                "Nicht im Bestand.\nSichtung: 28 von 28 Claims, Quittung: "
                "ffffffffffff", "nicht zum Fingerabdruck"),
            "kurze fremde Kennung": (
                "Nicht im Bestand.\nSichtung: 28 von 28 Claims, Quittung dead",
                "nicht zum Fingerabdruck"),
            "kurze eigene Kennung": (
                f"Nicht im Bestand.\nSichtung: 28 von 28 Claims, Quittung "
                f"{abdruck[:5]}", "nur 5 Zeichen"),
            "keine Zahlen": (
                f"Nicht im Bestand.\nSichtung: vollständig, Quittung "
                f"{abdruck[:12]}", "nennt nicht, wie viele Claims"),
            "keine Kennung": (
                "Nicht im Bestand.\nSichtung: 28 von 28 Claims",
                "nennt keine Quittungskennung"),
            "zweite Angabe falsch": (
                f"Nicht im Bestand.\nSichtung: 28 von 28 Claims, Quittung "
                f"{abdruck[:12]}\nSichtung: 27 von 28 Claims, Quittung "
                f"{abdruck[:12]}", "nennt 27 von 28 Claims"),
            "fremde Kennung in Großbuchstaben": (
                "Nicht im Bestand.\nSichtung: 28 von 28 Claims, Quittung "
                "FFFFFFFFFFFF", "nicht zum Fingerabdruck"),
        }
        for name, (antwort, meldung) in mit_quittung.items():
            with self.subTest(fall=name):
                result = self.pruefe([{
                    "id": "N1", "art": "negativ", "frage": NEGATIV,
                    "quittung": quittung, "antwort": antwort}])
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn(meldung, result.stdout)

        # Dieselbe Angabe in erlaubter Form: im Satz, hervorgehoben, im Zitat.
        angabe = f"28 von 28 Claims, Quittung {abdruck[:12]}"
        for name, antwort in {
            "im Satz": f"Nicht im Bestand. Sichtung: {angabe}. Soll ich "
                       f"eine Quelle aufnehmen?",
            "fett": f"Nicht im Bestand.\n**Sichtung**: {angabe}",
            "fett mit Doppelpunkt": f"Nicht im Bestand.\n**Sichtung:** {angabe}",
            "im Zitat": f"> Nicht im Bestand.\n> Sichtung: {angabe}",
            "Kennung in Backticks": f"Nicht im Bestand.\nSichtung: 28 von 28 "
                                    f"Claims, Quittung `{abdruck[:12]}`",
            "Kennung in Großbuchstaben": f"Nicht im Bestand.\nSichtung: 28 von "
                                         f"28 Claims, Quittung "
                                         f"{abdruck[:12].upper()}",
        }.items():
            with self.subTest(form=name):
                result = self.pruefe([{
                    "id": "N1", "art": "negativ", "frage": NEGATIV,
                    "quittung": quittung, "antwort": antwort + "\n" + EXTERN}])
                self.assertEqual(
                    result.returncode, 0, result.stdout + result.stderr)

    def test_ranges_and_lowercase_ids_are_citations(self):
        """„C-0001 bis C-0005" zitiert C-0003, und „c-9998" ist erfunden."""
        bereich = self.pruefe([{
            "id": "R1", "frage": "Was ist OKF?", "erwartet": ["C-0003"],
            "antwort": "OKF v0.1 ist eine Spezifikation von Google (C-0001 "
                       "bis C-0005); maßgeblich ist v0.2 (C-0301).",
        }], argumente=["--json"])
        self.assertEqual(bereich.returncode, 0, bereich.stdout + bereich.stderr)
        zeile = json.loads(bereich.stdout)["zeilen"][0]
        self.assertEqual(
            zeile["zitiert"],
            ["C-0001", "C-0002", "C-0003", "C-0004", "C-0005", "C-0301"])
        self.assertTrue(zeile["gefunden"])
        erfunden = self.pruefe([{
            "id": "R2", "frage": BEGRIFF, "erwartet": ["C-0305"],
            "antwort": "Laut Bestand gibt es vier Stufen "
                       "(C-0305-C-9999, c-9998).",
        }])
        self.assertEqual(erfunden.returncode, 1, erfunden.stdout)
        self.assertIn("die es im Bestand nicht gibt: C-9998, C-9999",
                      erfunden.stdout)

    def test_the_protocol_cannot_smuggle_another_question(self):
        """sweep_args nennt den Zuschnitt, sonst nichts.

        Die Engine hängt jedes weitere Wort an die Frage an. Mit freien
        sweep_args prüfte das Werkzeug die Trefferstärke der einen Frage und
        die Quittung einer anderen.
        """
        lang = NEGATIV.rstrip("?") + " laut OKF?"
        quittung, fertig = self.sichtung(lang)
        erste, rest = lang.split(" ", 4)[:4], lang.split(" ", 4)[4]
        for name, argumente in {
            "Wörter der Frage": rest.split(),
            "fremder Schalter": ["--receipt", quittung[0]],
            "Schalter ohne Wert": ["--size"],
            "Wert ist ein Schalter": ["--domain", "--batch"],
        }.items():
            with self.subTest(fall=name):
                result = self.pruefe([{
                    "id": "S1", "art": "negativ", "frage": " ".join(erste),
                    "sweep_args": argumente, "quittung": quittung,
                    "antwort": "Nicht im Bestand.\n"
                               + self.zeile_sichtung(fertig)}])
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIn("nur den Zuschnitt der Sichtung", result.stdout)
        # Eine Frage, die die Engine nicht annimmt, wird nicht geprüft und
        # deshalb auch nicht durchgewinkt.
        umbruch = self.pruefe([{
            "id": "L1", "frage": "Wie hoch ist der Urlaubsanspruch\nin "
                                 "Teilzeit?",
            "antwort": "30 Tage, anteilig nach Arbeitstagen."}])
        self.assertEqual(umbruch.returncode, 2, umbruch.stdout)
        self.assertIn("Zeilenumbruch", umbruch.stdout)
        zu_lang = self.pruefe([{
            "id": "L2", "frage": "Wie hoch ist der Urlaubsanspruch? " * 40,
            "antwort": "30 Tage."}])
        self.assertEqual(zu_lang.returncode, 2, zu_lang.stdout)
        self.assertIn("nimmt die Frage nicht an (invalid_query)",
                      zu_lang.stdout)
        self.assertIn("Antwort L2", zu_lang.stdout)
        # Die Vorgabe gegen das Nachschlagen ist ihr Wortlaut, nichts sonst.
        for vorgabe in ("", "   ", True, ["kein Netz"]):
            with self.subTest(vorgabe=vorgabe):
                result = self.pruefe([{
                    "id": "V1", "frage": NEGATIV, "vorgabe": vorgabe,
                    "antwort": "Nicht im Bestand."}])
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIn("'vorgabe' ist der Wortlaut", result.stdout)

    def test_a_partial_scope_never_satisfies_the_mandatory_sweep(self):
        """Pflicht heißt: der ganze Bestand. Eine Domäne genügt nicht."""
        teil = json.loads(_cli(
            self.root, "sweep", UMSCHREIBUNG, "--domain", "demo-okf",
            "--size", "200", "--batch", "1").stdout)
        quittung = [f"1:{teil['seal']}=C-0002"]
        fertig = json.loads(_cli(
            self.root, "sweep", UMSCHREIBUNG, "--domain", "demo-okf",
            "--size", "200", "--receipt", *quittung).stdout)
        self.assertEqual(fertig["state"], "sweep_complete", fertig)
        self.assertFalse(fertig["abstention"]["allowed"])
        result = self.pruefe([{
            "id": "P1", "art": "positiv", "frage": UMSCHREIBUNG,
            "erwartet": ["C-0002"], "quittung": quittung,
            "sweep_args": ["--domain", "demo-okf", "--size", "200"],
            "antwort": "Der Dateipfad ist die Identität (C-0002).\n"
                       "Sichtung: Domäne demo-okf, 26 von 28 Claims, Quittung "
                       + fertig["sweep_fingerprint"][:12],
        }])
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("keine vollständige Quittung über den ganzen Bestand",
                      result.stdout)
        self.assertIn("gefunden", result.stdout)

    def test_several_batches_and_a_cited_neighbour_page(self):
        """Drei Stapel, und ein Zitat von der Nachfolgeseite ist kein Hinweis."""
        frage = "Woran wird ein einzelner Eintrag eindeutig erkannt?"
        quittung, fertig = self.sichtung(frage, {"C-0002"}, groesse=10)
        self.assertEqual(len(quittung), 3)
        result = self.pruefe([{
            "id": "P1", "art": "positiv", "frage": frage,
            "erwartet": ["C-0002"], "quittung": quittung,
            "sweep_args": ["--size", "10"],
            "antwort": "Am Dateipfad (C-0002); maßgeblich ist v0.2 (C-0301).\n"
                       + self.zeile_sichtung(fertig),
        }], argumente=["--json"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        zeile = json.loads(result.stdout)["zeilen"][0]
        self.assertEqual(zeile["stapel"], 3)
        self.assertEqual(zeile["hinweise"], [])
        # Ohne die Größe im Protokoll passen die Siegel nicht.
        ohne = self.pruefe([{
            "id": "P1", "frage": frage, "quittung": quittung,
            "antwort": "Am Dateipfad (C-0002).\n" + self.zeile_sichtung(fertig),
        }])
        self.assertEqual(ohne.returncode, 1, ohne.stdout)

    def test_protocol_is_bound_to_its_state_and_stays_out_of_the_skill(self):
        antworten = self.saubere_antworten()
        fremd = self.pruefe(antworten, stand={
            "version": "0.0.1", "manifest_sha256": "0" * 64,
            "commit": "abc1234"})
        self.assertEqual(fremd.returncode, 2, fremd.stdout)
        self.assertIn("gebunden", fremd.stdout)
        self.assertIn("abc1234", fremd.stdout)
        self.assertNotIn("Verstoß", fremd.stdout)

        drinnen = self.pruefe(antworten, ort=self.root / "notes/protokoll.json")
        (self.root / "notes/protokoll.json").unlink()
        self.assertEqual(drinnen.returncode, 2, drinnen.stdout)
        self.assertIn("liegt im Skill-Ordner", drinnen.stdout)

        kaputt = self.basis / "kaputt.json"
        gut = {"frage": BEGRIFF, "antwort": "Vier Stufen (C-0305)."}
        for inhalt in ('{"schema": "anderes/v1", "antworten": []}',
                       json.dumps({"schema": SCHEMA, "antworten": [
                           {"frage": "x", "antwort": ""}]}),
                       "kein json",
                       # Felder vom falschen Typ sind ein unbrauchbares
                       # Protokoll, kein Absturz.
                       json.dumps({"schema": SCHEMA, "antworten": [
                           dict(gut, id=["A"])]}),
                       json.dumps({"schema": SCHEMA, "antworten": [
                           dict(gut, id=None)]}),
                       json.dumps({"schema": SCHEMA, "antworten": [
                           dict(gut, id=1), dict(gut, id="1")]}),
                       json.dumps({"schema": SCHEMA, "antworten": [gut],
                                   "stand": {"manifest_sha256": 123}}),
                       json.dumps({"schema": SCHEMA, "antworten": [gut],
                                   "stand": {"manifest_sha256": "0" * 64,
                                             "commit": 5}}),
                       json.dumps({"schema": SCHEMA, "antworten": [
                           dict(gut, frage="Was ist\u0000 OKF?")]}),
                       # Eine Negativfrage erwartet keinen Claim: Beides
                       # zugleich wäre ein Widerspruch im Protokoll.
                       json.dumps({"schema": SCHEMA, "antworten": [
                           dict(gut, art="negativ", erwartet=["C-0305"])]})):
            kaputt.write_text(inhalt, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-B", str(TOOL), "--vault", str(self.root),
                 "--antworten", str(kaputt)],
                cwd=REPOSITORY, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, check=False, timeout=60)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_relative_vault_path_and_locked_vault(self):
        antworten = self.saubere_antworten()[:1]
        relativ = self.pruefe(
            antworten, vault=self.root.name, cwd=self.basis,
            argumente=["--kurz"])
        self.assertEqual(relativ.returncode, 0, relativ.stdout + relativ.stderr)

        with tempfile.TemporaryDirectory(prefix="skillsafe-antwort-") as temp:
            gesperrt = Path(temp) / "wissenstresor"
            shutil.copytree(self.root, gesperrt)
            seite = gesperrt / "knowledge/demo-okf/fakten.md"
            seite.write_text(
                seite.read_text(encoding="utf-8") + "\nOhne Release.\n",
                encoding="utf-8")
            result = self.pruefe(antworten, vault=gesperrt)
            self.assertEqual(result.returncode, 2, result.stdout)
            self.assertIn("nicht bereit (invalid_vault)", result.stdout)
            self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_stored_protocols_are_readable_bound_and_consistent(self):
        """tests/e2e/ hält die Messläufe fest, auf die sich die Doku beruft.

        Nachrechnen lassen sie sich nur gegen ihren gebundenen Stand; hier
        zählt, dass sie lesbar sind, ihren Stand nennen und dass ihr
        'ergebnis' zu den Antworten passt, die in derselben Datei stehen.
        """
        tool = _werkzeug("antwort_check")
        dateien = sorted((REPOSITORY / "tests/e2e").glob("runde-*.json"))
        self.assertGreaterEqual(len(dateien), 3)
        runden = [json.loads(datei.read_text(encoding="utf-8"))["runde"]
                  for datei in dateien]
        self.assertEqual(runden, list(range(1, len(dateien) + 1)))
        for datei in dateien:
            with self.subTest(datei=datei.name):
                antworten, stand = tool.lade_protokoll(datei, self.root)
                self.assertRegex(stand["manifest_sha256"], r"^[0-9a-f]{64}$")
                self.assertRegex(stand["commit"], r"^[0-9a-f]{7,40}$")
                roh = json.loads(datei.read_text(encoding="utf-8"))
                ergebnis = roh["ergebnis"]
                self.assertEqual(ergebnis["antworten"], len(antworten))
                self.assertEqual(ergebnis["positiv"], sum(
                    1 for eintrag in antworten if eintrag["erwartet"]))
                self.assertEqual(ergebnis["negativ"], sum(
                    1 for eintrag in antworten if eintrag.get("art") == "negativ"))
                self.assertEqual(ergebnis["quittungen"], sum(
                    1 for eintrag in antworten if eintrag["quittung"]))
                self.assertEqual(ergebnis["verstoesse"], 0)
                self.assertEqual(ergebnis["ohne_verstoss"], len(antworten))
                # Was sich ohne den alten Stand nachzählen lässt, wird
                # nachgezählt: 'ergebnis' ist sonst nur eine Behauptung, an
                # die README und Landingpage gebunden sind.
                gefunden = 0
                for eintrag in antworten:
                    gewaehlt = set()
                    for teil in eintrag["quittung"]:
                        self.assertRegex(teil, tool.QUITTUNG_RE)
                        urteil = teil.split("=", 1)[1]
                        if urteil != "-":
                            gewaehlt.update(urteil.split(","))
                    zitiert = set(tool._zitierte_claims(eintrag["antwort"], ()))
                    if set(eintrag["erwartet"]) & (zitiert | gewaehlt):
                        gefunden += 1
                    if eintrag["quittung"]:
                        self.assertTrue(
                            tool._sichtungsangaben(eintrag["antwort"]),
                            eintrag["id"])
                self.assertEqual(ergebnis["positiv_gefunden"], gefunden)
                # Abgelehnt ist „Nicht im Bestand", bei vorgegebenem Umfang
                # auch „in diesem Umfang nicht gefunden" (antworten.md, 4b).
                abgelehnt = sum(
                    1 for eintrag in antworten
                    if eintrag.get("art") == "negativ"
                    and (tool._sagt_nicht_im_bestand(eintrag["antwort"])
                         or (eintrag.get("umfang_vorgegeben")
                             and tool._sagt_im_umfang_nicht(
                                 eintrag["antwort"]))))
                # Dazu die Antworten auf eine Frage nach einer Kennung, die es
                # nicht gibt: ohne Formel und ohne Quittung, aber mit der
                # Kennung im Wortlaut (antworten.md, Schritt 2b).
                kennungsfaelle = 0
                for eintrag in antworten:
                    kennungen = re.findall(
                        r"(?i)(?<![A-Za-z0-9])[CSB]-\d{4}(?!\d)",
                        eintrag["frage"])
                    if (eintrag.get("art") == "negativ" and kennungen
                            and not eintrag["quittung"]
                            and not tool._sagt_nicht_im_bestand(
                                eintrag["antwort"])
                            and all(k.upper() in eintrag["antwort"].upper()
                                    for k in kennungen)):
                        kennungsfaelle += 1
                self.assertEqual(
                    ergebnis["negativ_korrekt"], abgelehnt + kennungsfaelle)
                self.assertEqual(
                    ergebnis["quittungen_gueltig"], ergebnis["quittungen"])
                self.assertLessEqual(
                    ergebnis["vom_ranking_verfehlt"], ergebnis["positiv"])
                self.assertEqual(
                    ergebnis["davon_gefunden"], ergebnis["vom_ranking_verfehlt"])
                self.assertLessEqual(
                    ergebnis["pflicht_vollsichtung"], len(antworten))
                # Ein Verzicht auf Schritt 4c braucht die Vorgabe im Protokoll
                # und die Formel in der Antwort; mehr kann er nicht sein, als
                # der Schritt fällig war.
                verzichte = 0
                for eintrag in antworten:
                    treffer, ungelesen = tool._extern_angaben(eintrag["antwort"])
                    if eintrag.get("vorgabe") and not treffer and any(
                            "nicht nachgeschlagen" in " ".join(b.split()).casefold()
                            for b in ungelesen):
                        verzichte += 1
                self.assertEqual(ergebnis.get("verzicht_extern", 0), verzichte)
                self.assertLessEqual(verzichte, ergebnis.get("pflicht_extern", 0))
                # Gegen den heutigen Stand verweigert das Werkzeug die Prüfung,
                # statt lauter ungültige Quittungen zu melden.
                result = subprocess.run(
                    [sys.executable, "-B", str(TOOL), "--vault", str(self.root),
                     "--antworten", str(datei), "--kurz"],
                    cwd=REPOSITORY, text=True, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, check=False, timeout=120)
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIn("gebunden", result.stdout)

    def test_tool_leaves_the_vault_untouched(self):
        vorher = _cli(self.root, "checksum", "--verify")
        self.pruefe(self.saubere_antworten())
        nachher = _cli(self.root, "checksum", "--verify")
        self.assertEqual(vorher.returncode, 0, vorher.stdout)
        self.assertEqual(nachher.stdout, vorher.stdout)
        self.assertFalse(list(self.root.rglob("__pycache__")))


if __name__ == "__main__":
    unittest.main()
