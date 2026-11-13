#!/usr/bin/env python3
"""Abnahme für tools/antwort_check.py.

Das Werkzeug wertet aus, ob ein Agent dem Antworten-Vertrag gefolgt ist. Es
darf dabei nichts glauben, was der Agent über sich selbst sagt: Geprüft wird
hier deshalb vor allem, dass es Verstöße findet, die ein Protokoll verschweigt.
"""

import importlib.util
import json
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


def _cli(root, *args):
    return subprocess.run(
        [sys.executable, "-B", str(root / "scripts/vault.py"), *args],
        cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False, timeout=60,
    )


def tool_urteil(zeile):
    """Das Urteil, wie das Werkzeug es druckt (geladen ohne Bytecode)."""
    spec = importlib.util.spec_from_file_location("antwort_check_urteil", TOOL)
    modul = importlib.util.module_from_spec(spec)
    vorher = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(modul)
    finally:
        sys.dont_write_bytecode = vorher
    return modul.urteil(zeile)


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
               vault=None, cwd=None):
        ziel = ort or (self.basis / f"protokoll-{self.id().split('.')[-1]}.json")
        daten = {"schema": SCHEMA, "antworten": antworten}
        if stand is not None:
            daten["stand"] = stand
        ziel.write_text(json.dumps(daten, ensure_ascii=False), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, "-B", str(TOOL), "--vault",
             str(vault or self.root), "--antworten", str(ziel), *argumente],
            cwd=cwd or REPOSITORY, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False, timeout=180,
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
                        "zum Urlaubsanspruch.\n" + self.zeile_sichtung(leer)},
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
        spec = importlib.util.spec_from_file_location("antwort_check", TOOL)
        tool = importlib.util.module_from_spec(spec)
        vorher = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        try:
            spec.loader.exec_module(tool)
        finally:
            sys.dont_write_bytecode = vorher

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
                        + self.zeile_sichtung(fertig_frage)},
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
                        "S-0004."},
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
                    "quittung": quittung, "antwort": antwort}])
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
        spec = importlib.util.spec_from_file_location("antwort_check", TOOL)
        tool = importlib.util.module_from_spec(spec)
        vorher = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        try:
            spec.loader.exec_module(tool)
        finally:
            sys.dont_write_bytecode = vorher
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
                abgelehnt = sum(
                    1 for eintrag in antworten
                    if eintrag.get("art") == "negativ"
                    and tool._sagt_nicht_im_bestand(eintrag["antwort"]))
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
