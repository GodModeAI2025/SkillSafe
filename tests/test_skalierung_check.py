"""Die Skalierungsmessung als fester Test (tools/skalierung_check.py).

Das Gold misst gegen 28 Claims. Bis hybrid-local/v4 hieß eine Frage in einem
großen Bestand 'strong', sobald jedes ihrer Wörter irgendwo getroffen war,
auch verteilt über Ablenkerseiten: Mit 200 Seiten Nahtext (Saat 1) hieß so
eine Goldfrage 'strong', während ihr Claim fehlte. Der Vertrag fing sie nur
ab, weil die Liste ausgelassener Seiten gekürzt war. Seit v5 verlangt
'strong', dass die losen Wörter auf einer gezeigten Seite zusammenkommen und
kein gleich guter Träger eines losen Worts nur am Limit gescheitert ist. Der
Test baut diesen Bestand und hält beides auf null: stille Verfehlungen und
'strong' ohne Claim.
"""

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]


def _werkzeug(name):
    spec = importlib.util.spec_from_file_location(
        f"test_{name}", REPOSITORY / "tools" / f"{name}.py")
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def _summe(wurzel):
    """Prüfsumme über Seiten und ROUTER einer gebauten Kopie."""
    summe = hashlib.sha256()
    for pfad in sorted((wurzel / "knowledge").rglob("*.md")):
        summe.update(str(pfad.relative_to(wurzel)).encode("utf-8"))
        summe.update(pfad.read_bytes())
    summe.update((wurzel / "ROUTER.md").read_bytes())
    return summe.hexdigest()


class SkalierungTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.sk = _werkzeug("skalierung_check")
        cls.rc = cls.sk.RC
        cls._temp = tempfile.TemporaryDirectory(prefix="skillsafe-skalierung-")
        cls.vault = Path(cls._temp.name) / "nah-200" / "wissenstresor"
        try:
            cls.claims, cls.abbildung = cls.sk.bauen(cls.vault, 200, "nah", 1)
        except BaseException:
            cls._temp.cleanup()
            raise

    @classmethod
    def tearDownClass(cls):
        cls._temp.cleanup()

    def test_corpus_is_frozen_and_holds_no_gold_question(self):
        saetze, titel = self.sk.korpus_lesen()
        self.assertGreater(len(saetze), 1000)
        self.assertGreater(len(titel), 50)
        self.assertEqual(len(saetze), len(set(saetze)))
        # Der Korpus kommt aus einem festen Stand: neu erzeugt aus derselben
        # Doku käme dasselbe heraus, aus der heutigen Doku nicht zwingend.
        kopf = self.sk.KORPUS.read_text(encoding="utf-8").split("\n", 3)
        self.assertIn("6d32ae3", kopf[1])
        for name in self.sk.KORPUS_DATEIEN:
            self.assertTrue((REPOSITORY / name).is_file(), name)

    def test_distractors_leak_no_gold_question_and_carry_no_signature(self):
        gold = json.loads(self.sk.STANDARD_GOLD.read_text(encoding="utf-8"))
        fragen = [e["frage"] for e in gold["fragen"]] + list(gold["negativ"])
        self.assertEqual(self.rc.leck_suche(self.vault, fragen), [])
        ergebnis = subprocess.run(
            [sys.executable, "-B", "scripts/vault.py", "validate"],
            cwd=str(self.vault), text=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False, timeout=600)
        self.assertEqual(ergebnis.returncode, 0, ergebnis.stdout + ergebnis.stderr)
        self.assertRegex(ergebnis.stdout, r"0 Fehler, 0 Warnungen")
        self.assertNotIn("Instruktionssignatur", ergebnis.stdout)
        seiten = sorted((self.vault / "knowledge" / "demo-okf").glob("abl-*.md"))
        self.assertEqual(len(seiten), 200)
        ids = [cid for seite in seiten for cid in re.findall(
            r"^- \*\*(C-\d{4})\*\*", seite.read_text(encoding="utf-8"),
            flags=re.MULTILINE)]
        self.assertEqual(len(ids), self.claims)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(1000 <= int(cid[2:]) <= 9999 for cid in ids))
        self.assertEqual(self.abbildung, {})

    def test_same_seed_same_vault_other_seed_other_vault(self):
        with tempfile.TemporaryDirectory(prefix="skillsafe-skalierung-") as temp:
            eins = Path(temp) / "a" / "wissenstresor"
            zwei = Path(temp) / "b" / "wissenstresor"
            drei = Path(temp) / "c" / "wissenstresor"
            self.sk.bauen(eins, 20, "nah", 7)
            self.sk.bauen(zwei, 20, "nah", 7)
            self.sk.bauen(drei, 20, "nah", 8)
            self.assertEqual(_summe(eins), _summe(zwei))
            self.assertNotEqual(_summe(eins), _summe(drei))

    def test_new_order_moves_the_demo_claims_and_keeps_their_ranking(self):
        """Reihenfolge 'neu': Die Demo-Claims rücken ans obere Ende des
        Kennungsraums, das Gold wandert mit. Unter sich behalten sie ihre
        Reihenfolge, ohne Ablenker antwortet die Engine also gleich."""
        gold = json.loads(self.sk.STANDARD_GOLD.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(prefix="skillsafe-skalierung-") as temp:
            alt = Path(temp) / "alt" / "wissenstresor"
            neu = Path(temp) / "neu" / "wissenstresor"
            mit = Path(temp) / "mit" / "wissenstresor"
            self.assertEqual(self.sk.bauen(alt, 0, "nah", 1), (0, {}))
            claims, abbildung = self.sk.bauen(neu, 0, "nah", 1, reihenfolge="neu")
            self.assertEqual(claims, 0)
            self.assertEqual(len(abbildung), 28)
            self.assertEqual(list(abbildung), sorted(abbildung))
            self.assertEqual(list(abbildung.values()),
                             [f"C-{n:04d}" for n in range(9972, 10000)])
            for eintrag in gold["fragen"]:
                self.assertTrue(set(eintrag["erwartet"]) <= set(abbildung),
                                eintrag["frage"])
            text = "".join(seite.read_text(encoding="utf-8")
                           for seite in sorted((neu / "knowledge").rglob("*.md")))
            text += (neu / "schema" / "begriffswelten.json").read_text(encoding="utf-8")
            self.assertFalse(set(re.findall(r"\bC-\d{4}\b", text)) & set(abbildung))

            def antworten(vault, name):
                engine = self.sk._laden(name, vault / "scripts" / "vault.py")
                stand, fehler = engine._load_released_query_snapshot("x")
                self.assertIsNone(fehler)
                aus = []
                for frage in [e["frage"] for e in gold["fragen"]] + gold["negativ"]:
                    r = engine.build_query_result(dict(stand, query=frage),
                                                  world=None, limit=8)
                    aus.append((frage, r["state"], r["coverage"]["match_strength"],
                                r["coverage"]["term_coverage_percent"],
                                r["coverage"]["query_terms"],
                                [b["claim_id"] for b in r["evidence"]],
                                [s["path"] for s in r["pages"]]))
                return aus

            erwartet = [(f, s, st, ab, qt, [abbildung[c] for c in ids], seiten)
                        for f, s, st, ab, qt, ids, seiten in antworten(alt, "test_alt")]
            self.assertEqual(antworten(neu, "test_neu"), erwartet)
            # Mit Ablenkern bleiben deren Kennungen unter dem Demo-Block.
            claims, abbildung = self.sk.bauen(mit, 5, "nah", 1, reihenfolge="neu")
            ids = [int(nummer) for seite in (mit / "knowledge" / "demo-okf").glob("abl-*.md")
                   for nummer in re.findall(r"^- \*\*C-(\d{4})\*\*",
                                         seite.read_text(encoding="utf-8"),
                                         flags=re.MULTILINE)]
            self.assertEqual(len(ids), claims)
            self.assertTrue(ids and max(ids) < 9972 and min(ids) == 1000)

    def test_no_silent_miss_in_a_grown_vault(self):
        ergebnis = self.sk.messen(self.vault)
        self.assertEqual(ergebnis["fragen"], 84)
        self.assertEqual(ergebnis["claims"], 28 + self.claims)
        self.assertEqual(ergebnis["still"], 0, ergebnis["still_fragen"])
        self.assertEqual(ergebnis["strong_ohne_claim"], 0,
                         ergebnis["strong_ohne_claim_fragen"])
        # Gefunden wird weniger als im Demo-Bestand, und das sagt das
        # Ergebnis: Mindestens neun von zehn Verfehlungen verlangen die
        # Vollsichtung (weak, none oder gekürzte Liste ausgelassener Seiten),
        # die übrigen sind 'partial' mit benanntem Grund.
        self.assertGreater(ergebnis["treffer"], 0)
        verfehlt = ergebnis["pflicht"] + ergebnis["hinweis"]
        self.assertEqual(verfehlt + ergebnis["treffer"], 84)
        self.assertGreaterEqual(10 * ergebnis["pflicht"], 9 * verfehlt)


if __name__ == "__main__":
    unittest.main()
