#!/usr/bin/env python3
"""Abnahme für tools/antwort_check.py.

Das Werkzeug wertet aus, ob ein Agent dem Antworten-Vertrag gefolgt ist. Es
darf dabei nichts glauben, was der Agent über sich selbst sagt: Geprüft wird
hier deshalb vor allem, dass es Verstöße findet, die ein Protokoll verschweigt.
"""

import importlib.util
import json
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

    def sichtung(self, frage, auswahl=(), groesse=None):
        """Eine echte Vollsichtung fahren: Quittungseinträge und Ergebnis."""
        extra = ["--size", str(groesse)] if groesse else []
        plan = json.loads(_cli(self.root, "sweep", frage, *extra).stdout)
        eintraege = []
        for stapel in plan["batches"]:
            ausgabe = json.loads(_cli(
                self.root, "sweep", frage, *extra,
                "--batch", str(stapel["batch"])).stdout)
            ids = [claim["claim_id"] for seite in ausgabe["pages"]
                   for claim in seite["claims"]]
            gewaehlt = [cid for cid in ids if cid in auswahl]
            eintraege.append(
                f"{stapel['batch']}:{ausgabe['seal']}="
                + (",".join(gewaehlt) if gewaehlt else "-"))
        fertig = json.loads(_cli(
            self.root, "sweep", frage, *extra, "--receipt", *eintraege).stdout)
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
        }
        for name, (gefragt, antwort, meldung) in faelle.items():
            with self.subTest(fall=name):
                result = self.pruefe([{
                    "id": "K1", "art": "negativ", "frage": gefragt,
                    "antwort": antwort}])
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn(meldung, result.stdout)

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
                "nennt 5 von 28 Claims"),
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
                        self.assertRegex(
                            eintrag["antwort"], tool.SICHTUNG_RE, eintrag["id"])
                self.assertEqual(ergebnis["positiv_gefunden"], gefunden)
                abgelehnt = sum(
                    1 for eintrag in antworten
                    if eintrag.get("art") == "negativ"
                    and tool._sagt_nicht_im_bestand(eintrag["antwort"]))
                self.assertEqual(ergebnis["negativ_korrekt"], abgelehnt)
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
