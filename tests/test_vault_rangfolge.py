#!/usr/bin/env python3
"""Abnahme für tools/rangfolge_check.py und den Schnappschuss der Rangfolge.

Die Trefferquote zeigt nicht, wenn ein Gewicht, eine Schwelle oder ein Zähler
verrutscht: Ein Review hat das mit Dutzenden Einzelfehlern vorgeführt, die
alle grün blieben. Der Schnappschuss unter tests/gold/ hält deshalb für jede
Goldfrage und eine Handvoll fester Abfragen fest, was ``query`` ausgibt. Hier
wird geprüft, dass der eingecheckte Skill genau das ausgibt, und dass das
Werkzeug eine Abweichung tatsächlich meldet.
"""

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
SOURCE_SKILL = REPOSITORY / "wissenstresor"
TOOL = REPOSITORY / "tools/rangfolge_check.py"
GOLD = REPOSITORY / "tests/gold/recall-demo.json"
STAND = REPOSITORY / "tests/gold/rangfolge-demo.json"


def _cli(root, *args):
    return subprocess.run(
        [sys.executable, "-B", str(root / "scripts/vault.py"), *args],
        cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False, timeout=60,
    )


class RangfolgeTests(unittest.TestCase):
    """Vergleicht den eingecheckten Skill, wie test_packaged_vault."""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "skillsafe_rangfolge_check", TOOL)
        cls.tool = importlib.util.module_from_spec(spec)
        vorher = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        try:
            spec.loader.exec_module(cls.tool)
        finally:
            sys.dont_write_bytecode = vorher
        cls.fragen, cls.negativ = cls.tool.lade_gold(GOLD)
        cls.abfragen = cls.tool.abfragen_liste(cls.fragen, cls.negativ)
        cls.alt = cls.tool.lade_stand(STAND, SOURCE_SKILL)

    def werkzeug(self, *argumente, cwd=REPOSITORY):
        return subprocess.run(
            [sys.executable, "-B", str(TOOL), *argumente],
            cwd=cwd, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False, timeout=180,
        )

    def zeile(self, frage, limit=8, welt=None):
        for eintrag in self.alt["abfragen"]:
            if (eintrag["frage"], eintrag["limit"], eintrag["welt"]) == (
                    frage, limit, welt):
                return eintrag
        self.fail(f"Nicht im Schnappschuss: {frage!r} (Limit {limit})")

    def test_ranking_gives_out_what_was_recorded(self):
        """Das eine Netz: jede Punktzahl, jede Stärke, jeder Zähler."""
        neu = self.tool.aufnehmen(SOURCE_SKILL, [
            (eintrag["frage"], eintrag["limit"], eintrag["welt"])
            for eintrag in self.alt["abfragen"]])
        abweichungen = self.tool.vergleiche(self.alt, neu, self.abfragen)
        self.assertEqual(
            abweichungen, [],
            "Die Ausgabe von query weicht vom festgehaltenen Stand ab. "
            "Versehen beheben; eine Entscheidung am Ranking bekommt eine "
            "neue Profilnummer und 'tools/rangfolge_check.py --schreiben'.",
        )

    def test_snapshot_covers_the_gold_and_every_strength(self):
        self.assertEqual(self.alt["schema"], "skillsafe.rangfolge/v1")
        festgehalten = {
            (eintrag["frage"], eintrag["limit"], eintrag["welt"])
            for eintrag in self.alt["abfragen"]}
        self.assertEqual(len(festgehalten), len(self.alt["abfragen"]))
        for frage in self.fragen:
            for limit in self.tool.LIMITS:
                self.assertIn((frage, limit, None), festgehalten)
        for frage in self.negativ:
            self.assertIn((frage, self.tool.LIMIT_NEGATIV, None), festgehalten)
        staerken = Counter(e["staerke"] for e in self.alt["abfragen"])
        for staerke in ("strong", "partial", "weak", "none"):
            self.assertGreaterEqual(staerken[staerke], 10, staerken)
        # Knappes Limit: dort entscheidet die Nachrück-Regel, wer bleibt.
        self.assertGreaterEqual(
            sum(1 for e in self.alt["abfragen"] if e["limit"] == 1), 80)

    def test_strength_thresholds_are_written_down(self):
        """Die Tabelle aus profil.md, an Grenzfällen ohne Anker.

        100 % ist 'strong'; ab zwei getroffenen Begriffen und 60 % ist es
        'partial'; darunter 'weak' mit Pflicht-Vollsichtung. Die Abdeckung
        wird abgerundet.
        """
        basis = "Kernoperationen Chunking "
        faelle = {
            basis + "Urlaubsanspruch Zahnarzt": ("weak", 50),
            basis + "Vermieter Urlaubsanspruch Zahnarzt": ("partial", 60),
            basis + "Vermieter Urlaubsanspruch": ("partial", 75),
            basis + "Vermieter": ("strong", 100),
            basis + ("Vermieter Dateipfad Urlaubsanspruch Zahnarzt "
                     "Fahrradhelm"): ("weak", 57),
            basis + "Paragraphen": ("partial", 66),
        }
        for frage, (staerke, abdeckung) in faelle.items():
            with self.subTest(frage=frage):
                eintrag = self.zeile(frage)
                self.assertEqual(
                    (eintrag["staerke"], eintrag["abdeckung"]),
                    (staerke, abdeckung))
        # Dieselben Grenzen über den Prozess, mit dem Feld, an dem der
        # Antworten-Workflow die Pflicht festmacht.
        for frage, pflicht in ((basis + "Urlaubsanspruch Zahnarzt", True),
                               (basis + "Vermieter Urlaubsanspruch Zahnarzt",
                                False)):
            with self.subTest(frage=frage):
                ausgabe = json.loads(_cli(SOURCE_SKILL, "query", frage).stdout)
                self.assertIs(
                    ausgabe["fallback"]["exhaustive_review_required"], pflicht)
                self.assertEqual(
                    ausgabe["coverage"]["query_terms"]["unmatched"],
                    ["urlaubsanspruch", "zahnarzt"])

    def test_recorded_scores_follow_the_published_weights(self):
        """Lesbare Stichproben neben den Prüfwerten: je ein Gewicht.

        Exakter Treffer im Claim 20, Graph-Nachbar 5, Kompositumteil 12, als
        geerbter Kontext 6; ein direkt getroffener Begriff hebt die Claims
        seiner Seite um 100, sein Definitions-Claim liegt 40 darüber.
        """
        eintrag = self.zeile(
            "Kernoperationen Chunking Urlaubsanspruch Zahnarzt")
        self.assertEqual(eintrag["evidenz"][:3],
                         ["C-0102:20", "C-0291:20", "C-0001:5"])
        miete = self.zeile("Kann ich bei nassen Wänden die Miete kürzen?")
        self.assertEqual(miete["evidenz"], ["C-0401:12", "C-0402:6"])
        self.assertEqual((miete["staerke"], miete["abdeckung"]), ("weak", 0))
        ausgabe = json.loads(_cli(
            SOURCE_SKILL, "query", "Welche Vertrauensstufen gibt es?").stdout)
        self.assertEqual(ausgabe["concepts"]["matched"][0]["id"], "B-0006")
        # Je Claim der Begriffsseite 170: 100 für den direkten Begriff und
        # je 35 für zwei verwandte. Dazu der geerbte Wortteil-Treffer (6)
        # oder der eigene (12); der Definitions-Claim liegt 40 darüber.
        self.assertEqual(
            [(b["claim_id"], b["score"]) for b in ausgabe["evidence"]],
            [("C-0305", 216), ("C-0310", 182), ("C-0301", 176),
             ("C-0302", 176), ("C-0303", 176), ("C-0304", 176),
             ("C-0306", 176), ("C-0307", 176)])
        self.assertIn("concept-definition:B-0006",
                      ausgabe["evidence"][0]["reasons"])

    def test_a_changed_weight_is_noticed(self):
        """Positivkontrolle: ein verstelltes Gewicht macht das Werkzeug rot."""
        with tempfile.TemporaryDirectory(prefix="skillsafe-rang-") as temp:
            vault = Path(temp) / "wissenstresor"
            shutil.copytree(SOURCE_SKILL, vault)
            engine = vault / "scripts/vault.py"
            text = engine.read_text(encoding="utf-8")
            alt = 'CLAIM_GEWICHTE = {"token": 20, "stem": 16, "compound": 12}'
            self.assertEqual(text.count(alt), 1)
            engine.write_text(text.replace(
                alt, 'CLAIM_GEWICHTE = {"token": 20, "stem": 18, "compound": 12}'),
                encoding="utf-8")
            gesperrt = self.werkzeug("--vault", str(vault))
            self.assertEqual(gesperrt.returncode, 2, gesperrt.stdout)
            self.assertIn("nicht bereit (invalid_vault)", gesperrt.stdout)
            self.assertEqual(_cli(vault, "checksum").returncode, 0)

            rot = self.werkzeug("--vault", str(vault))
            self.assertEqual(rot.returncode, 1, rot.stdout + rot.stderr)
            self.assertIn("Abweichung(en) vom festgehaltenen Stand", rot.stdout)
            self.assertIn("evidenz festgehalten", rot.stdout)
            self.assertIn("Das Profil heißt weiter", rot.stdout)
            self.assertIn("Profilnummer heben", rot.stdout)
            self.assertFalse(list(vault.rglob("__pycache__")))

            # --schreiben hält den neuen Stand fest, außerhalb des Skills.
            neu = Path(temp) / "stand.json"
            geschrieben = self.werkzeug(
                "--vault", str(vault), "--stand", str(neu), "--schreiben")
            self.assertEqual(geschrieben.returncode, 0, geschrieben.stdout)
            gruen = self.werkzeug("--vault", str(vault), "--stand", str(neu))
            self.assertEqual(gruen.returncode, 0, gruen.stdout + gruen.stderr)
            drinnen = self.werkzeug(
                "--vault", str(vault), "--stand", str(vault / "notes/s.json"),
                "--schreiben")
            self.assertEqual(drinnen.returncode, 2, drinnen.stdout)
            self.assertIn("liegt im Skill-Ordner", drinnen.stdout)
            self.assertFalse((vault / "notes/s.json").exists())

    def test_a_fallback_only_change_needs_no_new_profile(self):
        """Weicht nur der Block fallback ab, ist die Rangfolge dieselbe."""
        basis = json.loads(STAND.read_text(encoding="utf-8"))
        for eintrag in basis["abfragen"]:
            if eintrag["frage"] == "Was ist OKF?" and eintrag["limit"] == 8:
                eintrag["bloecke"]["fallback"] = "0" * 10
        with tempfile.TemporaryDirectory(prefix="skillsafe-rang-") as temp:
            datei = Path(temp) / "stand.json"
            datei.write_text(json.dumps(basis, ensure_ascii=False),
                             encoding="utf-8")
            result = self.werkzeug("--stand", str(datei))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("Nur der Block fallback weicht ab", result.stdout)
        self.assertIn("keine neue Profilnummer", result.stdout)
        self.assertNotIn("Profilnummer heben", result.stdout)

    def test_every_recorded_field_is_compared(self):
        """Ein verfälschter Schnappschuss fällt auf, Feld für Feld."""
        basis = json.loads(STAND.read_text(encoding="utf-8"))
        ziel = "Was ist OKF?"

        def verfaelscht(aendern):
            daten = json.loads(json.dumps(basis))
            aendern(daten, next(
                e for e in daten["abfragen"]
                if (e["frage"], e["limit"], e["welt"]) == (ziel, 8, None)))
            return daten

        def evidenz(daten, eintrag):
            eintrag["evidenz"][0], eintrag["evidenz"][1] = (
                eintrag["evidenz"][1], eintrag["evidenz"][0])

        faelle = {
            "staerke": (lambda d, e: e.update(staerke="weak"),
                        "staerke festgehalten 'weak'"),
            "zustand": (lambda d, e: e.update(state="no_candidates"),
                        "state festgehalten 'no_candidates'"),
            "abdeckung": (lambda d, e: e.update(abdeckung=1),
                          "abdeckung festgehalten 1"),
            "evidenz": (evidenz, "evidenz festgehalten"),
            "block": (lambda d, e: e["bloecke"].update(coverage="0" * 10),
                      "Block coverage weicht ab"),
            "seiten": (lambda d, e: e["bloecke"].update(pages="0" * 10),
                       "Block pages weicht ab"),
            # Jeder Block hat seinen Prüfwert, auch die beiden, die keine
            # Rangfolge tragen: concepts (vertreten, erweitert) und fallback
            # (wann die Vollsichtung Pflicht ist, und warum).
            "begriffe": (lambda d, e: e["bloecke"].update(concepts="0" * 10),
                         "Block concepts weicht ab"),
            "rueckfall": (lambda d, e: e["bloecke"].update(fallback="0" * 10),
                          "Block fallback weicht ab"),
            "belege": (lambda d, e: e["bloecke"].update(evidence="0" * 10),
                       "Block evidence weicht ab"),
            "profil": (lambda d, e: d.update(retrieval="hybrid-local/v2"),
                       "retrieval: festgehalten 'hybrid-local/v2'"),
            "fehlende Frage": (
                lambda d, e: d["abfragen"].remove(e),
                "fehlt im Schnappschuss: 'Was ist OKF?' (Limit 8"),
            "fremde Frage": (
                lambda d, e: d["abfragen"].append(dict(e, frage="Fremd?")),
                "weder im Gold noch unter den festen Abfragen: 'Fremd?'"),
        }
        with tempfile.TemporaryDirectory(prefix="skillsafe-rang-") as temp:
            for name, (aendern, meldung) in faelle.items():
                with self.subTest(fall=name):
                    datei = Path(temp) / "stand.json"
                    datei.write_text(json.dumps(
                        verfaelscht(aendern), ensure_ascii=False),
                        encoding="utf-8")
                    result = self.werkzeug("--stand", str(datei))
                    self.assertEqual(result.returncode, 1, result.stdout)
                    self.assertIn(meldung, result.stdout)
            kaputt = Path(temp) / "kaputt.json"
            eintrag = next(e for e in basis["abfragen"]
                           if (e["frage"], e["limit"]) == (ziel, 8))

            def mit(**felder):
                # Mit dem echten Kopf: So prüft jeder Fall seinen eigenen
                # Fehler und nicht nur das fehlende Kopffeld.
                return json.dumps(dict(
                    basis, abfragen=[dict(eintrag, **felder)]))

            ohne_bloecke = dict(eintrag)
            del ohne_bloecke["bloecke"]
            ohne_fallback = dict(eintrag["bloecke"])
            del ohne_fallback["fallback"]
            for inhalt in ("kein json", '{"schema": "anderes/v1"}',
                           json.dumps({"schema": "skillsafe.rangfolge/v1",
                                       "abfragen": [{"frage": "x"}]}),
                           mit(bloecke=["x"]), mit(bloecke="abc"),
                           mit(bloecke={"coverage": 5}), mit(evidenz="C-0001:5"),
                           mit(evidenz=[5]), mit(limit=True), mit(limit="8"),
                           mit(abdeckung="50"), mit(state=["x"]),
                           json.dumps({"schema": "skillsafe.rangfolge/v1",
                                       "abfragen": [ohne_bloecke]}),
                           json.dumps({"schema": "skillsafe.rangfolge/v1",
                                       "abfragen": ["x"]}),
                           mit(bloecke={}), mit(bloecke=ohne_fallback),
                           mit(frage=""), json.dumps(dict(basis, claims=True)),
                           json.dumps({k: v for k, v in basis.items()
                                       if k != "wortform"}),
                           mit(bloecke=dict(eintrag["bloecke"], zusatz="abc")),
                           json.dumps(dict(basis, retrieval=None)),
                           json.dumps(dict(basis, claims="28")),
                           "[" * 100000):
                with self.subTest(stand=inhalt[:60]):
                    kaputt.write_text(inhalt, encoding="utf-8")
                    result = self.werkzeug("--stand", str(kaputt))
                    self.assertEqual(result.returncode, 2, result.stdout)
                    self.assertNotIn("Traceback", result.stdout + result.stderr)
            # Ebenso ein kaputtes Gold: Ein Text statt einer Liste zerfiele
            # sonst in einzelne Zeichen, jedes eine Frage.
            gold = json.loads(GOLD.read_text(encoding="utf-8"))
            kaputt_gold = Path(temp) / "gold.json"
            for name, inhalt in {
                    "negativ als Text": dict(gold, negativ="Wie?"),
                    "negativ mit Zahl": dict(gold, negativ=[1]),
                    "fragen als Text": dict(gold, fragen="Was?"),
                    "Frage leer": dict(gold, fragen=[{"frage": " "}]),
                    "Frage als Zahl": dict(gold, fragen=[{"frage": 3}]),
                    "Gold als Liste": [1, 2],
                    "ohne Fragen": dict(gold, fragen=[]),
                    "fremdes Schema": dict(gold, schema="irgendwas/v9"),
                    "zu tief": None}.items():
                with self.subTest(gold=name):
                    kaputt_gold.write_text(
                        "[" * 100000 if inhalt is None else json.dumps(inhalt),
                        encoding="utf-8")
                    result = self.werkzeug("--gold", str(kaputt_gold))
                    self.assertEqual(result.returncode, 2, result.stdout)
                    self.assertIn("kein lesbares Gold", result.stdout)
                    self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_mixed_deviations_ask_for_a_new_profile(self):
        """Weicht neben fallback auch Evidenz ab, ist es kein reiner Fall.

        Und eine Frage, die die Engine gar nicht annähme, gehört in keinen
        Schnappschuss: Sie hielte ein Ranking fest, das nie jemand bekommt.
        """
        basis = json.loads(STAND.read_text(encoding="utf-8"))
        for eintrag in basis["abfragen"]:
            if eintrag["frage"] == "Was ist OKF?" and eintrag["limit"] == 8:
                eintrag["bloecke"]["fallback"] = "0" * 10
            if (eintrag["frage"] == "Welche Vertrauensstufen gibt es?"
                    and eintrag["limit"] == 8):
                eintrag["evidenz"] = list(reversed(eintrag["evidenz"]))
        with tempfile.TemporaryDirectory(prefix="skillsafe-rang-") as temp:
            datei = Path(temp) / "stand.json"
            datei.write_text(json.dumps(basis, ensure_ascii=False),
                             encoding="utf-8")
            result = self.werkzeug("--stand", str(datei))
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("Profilnummer heben", result.stdout)
            self.assertNotIn("Nur der Block fallback weicht ab", result.stdout)

            gold = json.loads(GOLD.read_text(encoding="utf-8"))
            gold["negativ"] = list(gold["negativ"]) + ["Was ist\nOKF?"]
            mit_umbruch = Path(temp) / "gold.json"
            mit_umbruch.write_text(json.dumps(gold, ensure_ascii=False),
                                   encoding="utf-8")
            ziel = Path(temp) / "neu.json"
            result = self.werkzeug("--gold", str(mit_umbruch), "--stand",
                                   str(ziel), "--schreiben")
            self.assertEqual(result.returncode, 2, result.stdout)
            self.assertIn("nimmt die Frage", result.stdout)
            self.assertFalse(ziel.exists())
            # Ebenso zu lang, mit DEL, oder nicht als UTF-8 schreibbar; ein
            # vorhandener Schnappschuss bleibt dabei unangetastet.
            vorhanden = Path(temp) / "vorhanden.json"
            vorhanden.write_text(STAND.read_text(encoding="utf-8"),
                                 encoding="utf-8")
            for name, frage in (("zu lang", "x" * 1001),
                                ("DEL", "Was ist\x7fOKF?"),
                                ("Surrogat", "Was ist OKF\udcff?")):
                with self.subTest(frage=name):
                    gold = json.loads(GOLD.read_text(encoding="utf-8"))
                    gold["negativ"] = list(gold["negativ"]) + [frage]
                    mit_umbruch.write_text(json.dumps(gold), encoding="utf-8")
                    result = self.werkzeug("--gold", str(mit_umbruch),
                                           "--stand", str(vorhanden),
                                           "--schreiben")
                    self.assertEqual(result.returncode, 2,
                                     result.stdout + result.stderr)
                    self.assertNotIn("Traceback", result.stdout + result.stderr)
                    self.assertEqual(vorhanden.read_text(encoding="utf-8"),
                                     STAND.read_text(encoding="utf-8"))
            # Ein Ziel, das sich nicht schreiben lässt: Exit 2.
            result = self.werkzeug("--stand", str(Path(temp) / "fehlt" / "neu.json"),
                                   "--schreiben")
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_tool_leaves_the_vault_untouched(self):
        vorher = _cli(SOURCE_SKILL, "checksum", "--verify")
        gruen = self.werkzeug()
        self.assertEqual(gruen.returncode, 0, gruen.stdout + gruen.stderr)
        self.assertIn("gibt aus, was festgehalten ist", gruen.stdout)
        nachher = _cli(SOURCE_SKILL, "checksum", "--verify")
        self.assertEqual(vorher.returncode, 0, vorher.stdout)
        self.assertEqual(nachher.stdout, vorher.stdout)
        self.assertFalse(list(SOURCE_SKILL.rglob("__pycache__")))


if __name__ == "__main__":
    unittest.main()
