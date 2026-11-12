#!/usr/bin/env python3
"""Abnahme für Wortform-Abgleich, Trefferstärke, Vollsichtung und Recall-Gate.

Der Leitgedanke dieser Datei: Eine Suche, die etwas nicht findet, ist kein
Fehler. Ein Ergebnis, das das nicht zugibt, ist einer.
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
RECALL_TOOL = REPOSITORY / "tools/recall_check.py"
GOLD = REPOSITORY / "tests/gold/recall-demo.json"

# Untergrenzen statt Punktwerte, wie beim externen Routing: die Zahl darf
# nicht still absacken. Gemessen am 12.11.2026 mit hybrid-local/v2: 67 % in
# der Gruppe 'entwicklung', 32 % in der Gruppe 'kontrolle'. Die zweite Zahl
# ist die ehrlichere. Ihre Fragen schrieb ein Agent, der nur die Claims
# kannte, und sie meiden deren Wortlaut mit Absicht.
MIN_RECALL = {"entwicklung": 60, "kontrolle": 25}


def _cli(root, *args):
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-B", str(root / "scripts/vault.py"), *args],
        cwd=root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=60,
    )


class VaultCase(unittest.TestCase):
    """Eine freigegebene Wegwerf-Kopie des Tresors je Testklasse.

    Die meisten Tests hier lesen nur. Für sie wäre eine eigene Kopie samt
    Release je Test reine Laufzeit, und die Suite fährt in der Prüfkette
    zweimal. Wer den Bestand verändert, holt sich mit ``use_private_vault``
    eine eigene Kopie; ``self.root`` zeigt danach nur für diesen einen Test
    dorthin.

    Die Kopie wird einmal released statt nur gepinnt: Damit hängt kein Test
    davon ab, ob das Manifest im Arbeitsbaum gerade zum Stand passt.
    """

    @classmethod
    def setUpClass(cls):
        cls._tempdir = tempfile.TemporaryDirectory(prefix="skillsafe-recall-")
        cls.root = Path(cls._tempdir.name) / "wissenstresor"
        shutil.copytree(SOURCE_SKILL, cls.root)
        result = _cli(cls.root, "release", "patch")
        if result.returncode != 0:
            raise AssertionError(result.stdout + result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls._tempdir.cleanup()

    def use_private_vault(self):
        temp = tempfile.TemporaryDirectory(prefix="skillsafe-recall-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "wissenstresor"
        shutil.copytree(SOURCE_SKILL, self.root)
        self.release()

    def run_cli(self, *args):
        return _cli(self.root, *args)

    def json_cli(self, *args):
        result = self.run_cli(*args)
        try:
            return result, json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            self.fail(f"Kein einzelnes JSON-Dokument: {exc}\n{result.stdout}")

    def query(self, *args):
        return self.json_cli("query", *args)

    def sweep(self, *args):
        return self.json_cli("sweep", *args)

    def release(self):
        result = self.run_cli("release", "patch")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def claim_ids_on_disk(self):
        ids = []
        for page in sorted((self.root / "knowledge").rglob("*.md")):
            ids.extend(re.findall(
                r"^- \*\*(C-\d{4})\*\*", page.read_text(encoding="utf-8"),
                flags=re.MULTILINE,
            ))
        return ids


def load_engine(root):
    """Die Engine als Modul laden — aus der Wegwerf-Kopie, nie aus dem
    Repository: der Import darf im ausgelieferten Skill-Ordner kein
    __pycache__ hinterlassen."""
    spec = importlib.util.spec_from_file_location(
        "vault_recall_test", root / "scripts/vault.py"
    )
    module = importlib.util.module_from_spec(spec)
    vorher = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = vorher
    return module


class WortformTests(VaultCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.engine = load_engine(cls.root)

    def stamm(self, wort):
        return " ".join(
            self.engine._wortstamm(token)
            for token in self.engine._retrieval_norm(wort).split()
        )

    def test_function_words_are_stored_in_normalized_spelling(self):
        """Ein Funktionswort in Umlautschreibung träfe nie ein Token.

        Genau dieser Fehler steckt in RETRIEVAL_STOPWORDS ('für' steht dort,
        geprüft wird aber gegen 'fuer'). Die neue Liste darf ihn nicht erben.
        """
        for wort in sorted(self.engine.FUNKTIONSWOERTER):
            self.assertEqual(wort, self.engine._retrieval_norm(wort), wort)
        self.assertEqual(
            self.engine._inhaltstokens("Quelle für Daten"), ("quelle", "daten")
        )

    def test_one_word_family_shares_one_stem(self):
        familien = [
            ("Wände", "Wand"), ("Mängel", "Mangel"), ("Verträge", "Vertrag"),
            ("Verträgen", "Vertrag"), ("Häuser", "Haus"),
            ("Vertrauensstufen", "Vertrauensstufe"), ("Quellen", "Quelle"),
            ("Bundles", "Bundle"), ("Claims", "Claim"), ("Dateien", "Datei"),
            ("Typen", "Typ"), ("Feldern", "Feld"), ("Prozesse", "Prozess"),
            ("Prüfungen", "prüfen"), ("Minderung", "mindern"),
            ("Berechnungen", "berechnen"), ("Bestätigungen", "bestätigen"),
            ("Änderung", "ändern"),
            # Transliterierte und Umlautschreibung derselben Benennung.
            ("Glaubwürdigkeitssignale", "Glaubwuerdigkeitssignal"),
            ("attestierte Berechnungen", "Attestierte Berechnung"),
        ]
        for links, rechts in familien:
            with self.subTest(links=links, rechts=rechts):
                self.assertEqual(self.stamm(links), self.stamm(rechts))

    def test_stems_do_not_eat_the_word(self):
        self.assertEqual(self.stamm("Prozess"), "prozess")
        self.assertEqual(self.stamm("Status"), "status")
        self.assertEqual(self.stamm("Haus"), "haus")
        self.assertEqual(self.stamm("OKF"), "okf")
        self.assertEqual(self.stamm("v0"), "v0")
        self.assertEqual(self.stamm("2026"), "2026")
        # '-er' braucht vier Zeichen Stamm, sonst wird aus 'andere' ein 'and'.
        self.assertEqual(self.stamm("andere"), "ander")
        self.assertNotEqual(self.stamm("Recht"), self.stamm("rechnen"))

    def test_documented_limits_stay_limits(self):
        """Was wortform/v1 bewusst nicht leistet, steht hier fest.

        Wer eine dieser Zeilen kippt, hat die Regeln erweitert und muss
        Profilnummer, Messung und Doku mitziehen.
        """
        for links, rechts in [("bestätigt", "bestätigen"), ("gilt", "gelten"),
                              ("geprüft", "prüfen"),
                              ("Sicherheit", "sichern")]:
            with self.subTest(links=links, rechts=rechts):
                self.assertNotEqual(self.stamm(links), self.stamm(rechts))

    def test_compound_parts_match_only_at_word_boundaries(self):
        kompositum = self.engine._kompositum
        self.assertTrue(kompositum("miete", "mietminderung"))
        self.assertTrue(kompositum("mietminderung", "miete"))
        self.assertTrue(kompositum("nachweis", "herkunftsnachweis"))
        self.assertTrue(kompositum("herkunft", "herkunftsnachweis"))
        self.assertTrue(kompositum("stufen", "vertrauensstufe"))
        # Der Rest an der Nahtstelle ist zu kurz, um ein Wortteil zu sein.
        self.assertFalse(kompositum("himmel", "schimmel"))
        self.assertFalse(kompositum("recht", "gerecht"))
        self.assertFalse(kompositum("text", "kontext"))
        self.assertFalse(kompositum("form", "format"))
        # Kurze Wörter sind nie Kompositumteil.
        self.assertFalse(kompositum("art", "startet"))
        self.assertFalse(kompositum("tag", "vertrag"))
        # In der Wortmitte wird nie gesucht.
        self.assertFalse(kompositum("wuerdigkeit", "glaubwuerdigkeitssignal"))


class QuerySignalTests(VaultCase):
    def test_function_words_never_fake_an_answer(self):
        """Der gemessene Ausgangsbefund, als Regressionstest.

        Unter hybrid-local/v1 traf 'darf' einen Claim über Agenten-Parameter,
        das Ergebnis hieß 'candidates_found' mit acht Kandidaten, und die
        Vollprüfung war abgeschaltet. Der Claim zum Schimmel fehlte.
        """
        result, payload = self.query(
            "Darf ich bei feuchten Wänden weniger Miete zahlen?")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        coverage = payload["coverage"]
        self.assertEqual(coverage["match_strength"], "weak")
        self.assertTrue(payload["fallback"]["exhaustive_review_required"])
        self.assertEqual(payload["fallback"]["reason"], "weak_candidates_only")
        self.assertEqual(
            coverage["query_terms"]["content"],
            ["feuchten", "miete", "waenden", "zahlen"],
        )
        self.assertEqual(coverage["query_terms"]["matched"], [])
        self.assertEqual(coverage["query_terms"]["partial"], ["miete"])
        gruende = {
            item["claim_id"]: item["reasons"] for item in payload["evidence"]
        }
        self.assertIn("compound:miete", gruende["C-0401"])
        self.assertNotIn("C-0308", gruende)
        for reasons in gruende.values():
            self.assertFalse(
                [reason for reason in reasons if "darf" in reason], reasons)

    def test_inflected_alias_reaches_its_concept_and_definition_first(self):
        result, payload = self.query("Welche Vertrauensstufen gibt es?")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        begriff = payload["concepts"]["matched"][0]
        self.assertEqual(begriff["id"], "B-0006")
        self.assertEqual(begriff["match"], "wortform")
        self.assertEqual(begriff["matched_labels"], ["Vertrauensstufe"])
        self.assertEqual(payload["coverage"]["match_strength"], "strong")
        self.assertFalse(payload["fallback"]["exhaustive_review_required"])
        erster = payload["evidence"][0]
        self.assertEqual(erster["claim_id"], "C-0305")
        self.assertIn("concept-definition:B-0006", erster["reasons"])

        # Die exakte Benennung bleibt 'exact' und verändert sich nicht.
        _, exakt = self.query("Trust-Tier")
        self.assertEqual(exakt["concepts"]["matched"][0]["match"], "exact")

    def test_compound_part_of_a_label_is_a_hint_not_a_concept(self):
        _, payload = self.query(
            "Wo wird die Herkunft einer Information eingetragen?")
        self.assertEqual(payload["concepts"]["matched"], [])
        teilweise = {item["id"]: item for item in payload["concepts"]["partial"]}
        self.assertEqual(teilweise["B-0007"]["terms"], ["herkunft"])
        # Ein Fingerzeig ist kein Anker: die Frage bleibt unverstanden.
        self.assertEqual(payload["coverage"]["match_strength"], "weak")
        self.assertTrue(payload["fallback"]["exhaustive_review_required"])
        self.assertIn(
            "C-0302", [item["claim_id"] for item in payload["evidence"]])

    def install_second_world(self):
        """Welt 2 mit dem Alias 'Verträge', Welt 1 bekommt 'Vertrag'."""
        self.use_private_vault()
        concepts_path = self.root / "schema/begriffswelten.json"
        data = json.loads(concepts_path.read_text(encoding="utf-8"))
        data["worlds"].append({
            "id": "BW-0002",
            "name": "Zweite Fachsprache",
            "description": "Fixture für Wortformen über Weltgrenzen.",
        })
        for concept in data["concepts"]:
            if concept["id"] == "B-0004":
                concept["aliases"].append("Vertrag")
        data["concepts"].append({
            "id": "B-0900",
            "world": "BW-0002",
            "preferred": "Zweitabrede",
            "aliases": ["Verträge"],
            "broader": [],
            "related": [],
            "definition_claim": "C-0101",
        })
        concepts_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        page = self.root / "knowledge/demo-okf/llm-wiki-muster.md"
        page.write_text(
            page.read_text(encoding="utf-8").replace(
                "concepts: [B-0002]", "concepts: [B-0002, B-0900]"
            ),
            encoding="utf-8",
        )
        self.release()

    def test_exact_label_wins_and_word_forms_stay_ambiguous_across_worlds(self):
        self.install_second_world()
        # Exakt benannt: nur der exakt benannte Begriff, wie in v1. Die
        # Wortform derselben Phrase zieht keine zweite Welt herein.
        result, payload = self.query("Verträge")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            [item["id"] for item in payload["concepts"]["matched"]], ["B-0900"])
        _, payload = self.query("Vertrag")
        self.assertEqual(
            [item["id"] for item in payload["concepts"]["matched"]], ["B-0004"])

        # Dritte Form, in keiner Welt exakt: beide treffen nur über die
        # Wortform. Still mischen wäre genau das, was 'ambiguous' verhindert.
        mehrdeutig, payload = self.query("Verträgen")
        self.assertEqual(mehrdeutig.returncode, 2)
        self.assertEqual(payload["state"], "ambiguous")
        self.assertEqual(payload["evidence"], [])
        self.assertIn("B-0004", payload["errors"][0])
        self.assertIn("B-0900", payload["errors"][0])

        eindeutig, payload = self.query("Verträgen", "--world", "BW-0001")
        self.assertEqual(eindeutig.returncode, 0, eindeutig.stdout)
        self.assertEqual(
            [(item["id"], item["match"])
             for item in payload["concepts"]["matched"]],
            [("B-0004", "wortform")],
        )

    def test_second_topic_is_not_crowded_out_by_the_first(self):
        """Kontext weicht, Treffer nie.

        Ein Begriffstreffer hebt jeden Claim seiner Seite um 100 Punkte, ein
        wörtlicher Treffer woanders bringt 20. Ohne Ausgleich füllte 'OKF'
        allein jedes Limit, und die Mietminderung fehlte selbst bei 20.
        """
        for limit in ("8", "20"):
            with self.subTest(limit=limit):
                _, payload = self.query("Mietminderung OKF", "--limit", limit)
                ids = [item["claim_id"] for item in payload["evidence"]]
                self.assertEqual(ids[0], "C-0001")
                self.assertIn("C-0401", ids)
                self.assertEqual(
                    payload["coverage"]["query_terms"]["unmatched"], [])
                self.assertEqual(payload["coverage"]["match_strength"], "strong")
                self.assertIn(
                    "knowledge/demo-extern/mietminderung.md",
                    [page["path"] for page in payload["pages"]],
                )
                # Die Ausgabe bleibt nach Rang sortiert.
                scores = [item["score"] for item in payload["evidence"]]
                self.assertEqual(scores, sorted(scores, reverse=True))

    def test_a_filler_word_never_evicts_a_real_hit(self):
        """Der Befund der Kontrollmessung, als Regressionstest.

        Die Frage nennt 'OKF' und daneben Allerweltswörter, die je ein
        unbeteiligter Claim zufällig trägt. In der ersten Fassung der
        Nachrück-Regel verdrängten deren Träger den Definitions-Claim C-0301
        von Rang 6. Nachrücken darf nur, wer reinen Kontext ersetzt.
        """
        _, payload = self.query(
            "Welche Angabe muss in jedem Dokument mindestens stehen, "
            "damit es nach OKF 0.2 zulässig ist?")
        ids = [item["claim_id"] for item in payload["evidence"]]
        self.assertIn("C-0301", ids)
        direkt_vorher = {"C-0001", "C-0004", "C-0005", "C-0301"}
        self.assertTrue(direkt_vorher <= set(ids), ids)
        _, weit = self.query(
            "Welche Angabe muss in jedem Dokument mindestens stehen, "
            "damit es nach OKF 0.2 zulässig ist?", "--limit", "20")
        rang_weit = [item["claim_id"] for item in weit["evidence"]]
        # Wer bei Limit 8 einen eigenen Treffer hat und unter den ersten acht
        # der ungekürzten Rangfolge steht, bleibt.
        eigene = [
            item["claim_id"] for item in weit["evidence"][:8]
            if any(reason.split(":")[0] in {"token", "stem", "compound",
                                            "concept-definition", "id"}
                   for reason in item["reasons"])
        ]
        self.assertTrue(set(eigene) <= set(ids), (eigene, ids, rang_weit))

    def test_truncation_is_never_silent(self):
        _, voll = self.query("Mietminderung OKF", "--limit", "20")
        # Bei Limit 2 tragen beide Plätze einen eigenen Treffer zu 'OKF'.
        # Kein Kontext, der weichen könnte: also rückt nichts nach, und die
        # Kürzung wird stattdessen gemeldet.
        _, zwei = self.query("Mietminderung OKF", "--limit", "2")
        self.assertEqual(
            [item["claim_id"] for item in zwei["evidence"]],
            ["C-0001", "C-0004"],
        )
        self.assertEqual(
            zwei["coverage"]["query_terms"]["unmatched"], ["mietminderung"])
        _, knapp = self.query("Mietminderung OKF", "--limit", "1")
        zahlen = knapp["coverage"]["candidates"]
        self.assertEqual(zahlen["returned"], 1)
        self.assertEqual(zahlen["total"], voll["coverage"]["candidates"]["total"])
        self.assertEqual(
            zahlen["total"],
            zahlen["returned"] + zahlen["omitted_direct"]
            + zahlen["omitted_context"],
        )
        self.assertGreater(zahlen["omitted_direct"], 0)
        # Ein Platz, zwei Themen: die Seite, die dem Limit zum Opfer fiel,
        # wird beim Namen genannt.
        gezeigt = {page["path"] for page in knapp["pages"]}
        verdeckt = {page["path"] for page in knapp["coverage"]["omitted_pages"]}
        self.assertEqual(gezeigt, {"knowledge/demo-okf/okf.md"})
        self.assertIn("knowledge/demo-extern/mietminderung.md", verdeckt)
        self.assertFalse(gezeigt & verdeckt)
        for eintrag in knapp["coverage"]["omitted_pages"]:
            self.assertGreaterEqual(eintrag["claims"], 1)
            self.assertRegex(eintrag["best_claim"], r"^C-\d{4}$")
        # Ein Begriff, den nur ein gekürzter Kandidat trägt, gilt als
        # ungetroffen: das Modell hat ihn nicht gesehen.
        self.assertEqual(
            knapp["coverage"]["query_terms"]["unmatched"], ["mietminderung"])
        self.assertEqual(knapp["coverage"]["match_strength"], "partial")
        self.assertEqual(voll["coverage"]["query_terms"]["unmatched"], [])

    def test_ids_are_anchors_not_unmatched_words(self):
        _, payload = self.query("C-0001")
        self.assertEqual(payload["coverage"]["query_terms"]["content"], [])
        self.assertEqual(payload["coverage"]["match_strength"], "strong")
        self.assertEqual(payload["evidence"][0]["claim_id"], "C-0001")

    def test_nothing_found_stays_nothing_found(self):
        _, payload = self.query("Urlaubsanspruch")
        self.assertEqual(payload["state"], "no_candidates")
        self.assertEqual(payload["coverage"]["match_strength"], "none")
        self.assertEqual(payload["fallback"]["reason"], "no_retrieval_candidates")
        self.assertEqual(
            payload["fallback"]["sweep"],
            {"claims": 28, "batch_size": 40, "batches": 1},
        )
        # 'himmel' findet auch lokal keinen 'schimmel'.
        _, payload = self.query("himmel")
        self.assertEqual(payload["state"], "no_candidates")

    def test_signal_fields_exist_in_every_state(self):
        self.use_private_vault()
        erwartet = {"match_strength", "term_coverage_percent", "query_terms",
                    "candidates", "omitted_pages", "wortform"}
        _, leer = self.query("   ")
        self.assertEqual(leer["state"], "invalid_query")
        self.assertTrue(erwartet <= set(leer["coverage"]))
        self.assertEqual(leer["coverage"]["match_strength"], "none")
        self.assertEqual(leer["concepts"]["partial"], [])

        page = self.root / "knowledge/demo-okf/okf.md"
        page.write_text(page.read_text(encoding="utf-8") + "\nDrift\n",
                        encoding="utf-8")
        _, kaputt = self.query("OKF")
        self.assertEqual(kaputt["state"], "invalid_vault")
        self.assertTrue(erwartet <= set(kaputt["coverage"]))
        self.assertIsNone(kaputt["fallback"]["sweep"])

    def test_word_form_ranking_is_deterministic(self):
        erster = self.run_cli(
            "query", "Wie werden Bestätigungen und Vertrauensstufen geprüft?")
        self.assertEqual(erster.returncode, 0, erster.stdout + erster.stderr)
        self.assertEqual(
            json.loads(erster.stdout)["retrieval"], "hybrid-local/v2")
        for _ in range(5):
            wieder = self.run_cli(
                "query", "Wie werden Bestätigungen und Vertrauensstufen geprüft?")
            self.assertEqual(wieder.stdout, erster.stdout)


class SweepTests(VaultCase):
    FRAGE = "Welche Adresse fungiert als dauerhafter Schlüssel einer Wissenseinheit?"

    def stapel(self, frage, *args):
        """Alle Stapel einer Sichtung holen: {nummer: (siegel, [claim ids])}."""
        _, plan = self.sweep(frage, *args)
        self.assertEqual(plan["state"], "plan", plan)
        gelesen = {}
        for eintrag in plan["batches"]:
            result, stapel = self.sweep(
                frage, *args, "--batch", str(eintrag["batch"]))
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertEqual(stapel["state"], "batch")
            ids = [claim["claim_id"]
                   for seite in stapel["pages"] for claim in seite["claims"]]
            self.assertEqual(len(ids), eintrag["claims"])
            gelesen[eintrag["batch"]] = (stapel["seal"], ids)
        return plan, gelesen

    def test_every_claim_is_presented_exactly_once_at_any_batch_size(self):
        erwartet = sorted(self.claim_ids_on_disk())
        self.assertEqual(len(erwartet), 28)
        for groesse in ("5", "7", "40", "200"):
            with self.subTest(groesse=groesse):
                plan, gelesen = self.stapel(self.FRAGE, "--size", groesse)
                alle = [cid for _, ids in gelesen.values() for cid in ids]
                self.assertEqual(sorted(alle), erwartet)
                self.assertEqual(len(alle), len(set(alle)))
                self.assertTrue(plan["scope"]["complete"])
                self.assertEqual(plan["scope"]["claims_in_scope"], 28)
                # Der Plan verrät kein Siegel; das steht nur am Stapel.
                self.assertNotIn("seal", json.dumps(plan))

    def test_sweep_finds_the_paraphrase_the_ranking_cannot(self):
        """Die Sonde aus test_vault_retrieval, zu Ende geführt.

        Das Ranking gibt die Umschreibung als 'weak' aus und liefert C-0002
        nicht. Die Vollsichtung legt C-0002 vor, die Quittung macht ihn zur
        Evidenz — und erst sie erlaubt überhaupt ein 'Nicht im Bestand'.
        """
        _, antwort = self.query(self.FRAGE)
        self.assertTrue(antwort["fallback"]["exhaustive_review_required"])
        self.assertNotIn(
            "C-0002", [item["claim_id"] for item in antwort["evidence"]])

        plan, gelesen = self.stapel(self.FRAGE, "--size", "10")
        self.assertEqual(plan["batches_total"], 3)
        quittung = [
            f"{nummer}:{siegel}=" + ("C-0002" if "C-0002" in ids else "-")
            for nummer, (siegel, ids) in sorted(gelesen.items())
        ]
        self.assertEqual(sum("C-0002" in eintrag for eintrag in quittung), 1)
        result, fertig = self.sweep(
            self.FRAGE, "--size", "10", "--receipt", *quittung)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(fertig["state"], "sweep_complete")
        self.assertEqual(fertig["selected"], ["C-0002"])
        self.assertEqual(fertig["coverage"]["claims_swept"], 28)
        self.assertEqual(fertig["coverage"]["batches_confirmed"], 3)
        self.assertEqual(fertig["coverage"]["semantic_coverage"], "swept")
        self.assertTrue(fertig["abstention"]["allowed"])
        beleg = fertig["evidence"][0]
        self.assertEqual(beleg["claim_id"], "C-0002")
        self.assertEqual(beleg["role"], "sweep_selected")
        self.assertEqual(beleg["source"]["id"], "S-0001")
        self.assertIn("page_status:veraltet", beleg["signals"])
        self.assertEqual(
            [page["path"] for page in fertig["pages"]],
            ["knowledge/demo-okf/okf.md"],
        )
        # Dieselbe Quittung, derselbe Stand: derselbe Fingerabdruck.
        wieder = self.run_cli(
            "sweep", self.FRAGE, "--size", "10", "--receipt", *quittung)
        self.assertEqual(wieder.stdout, result.stdout)

    def test_receipt_fails_closed(self):
        _, gelesen = self.stapel(self.FRAGE, "--size", "10")
        gut = [f"{n}:{siegel}=-" for n, (siegel, _) in sorted(gelesen.items())]
        siegel_1, ids_1 = gelesen[1]
        fremd = next(cid for cid in gelesen[2][1] if cid not in ids_1)
        faelle = {
            "fehlender Stapel": (gut[:2], "sweep_incomplete"),
            "leere Quittung": ([], "sweep_incomplete"),
            "falsches Siegel": (
                ["1:0000000000000000=-"] + gut[1:], "invalid_receipt"),
            "doppelter Stapel": (gut + [gut[0]], "invalid_receipt"),
            "unbekannter Stapel": (
                gut + [f"9:{siegel_1}=-"], "invalid_receipt"),
            "Claim aus anderem Stapel": (
                [f"1:{siegel_1}={fremd}"] + gut[1:], "invalid_receipt"),
            "kaputte Form": (gut[:2] + ["3=C-0001"], "invalid_receipt"),
        }
        for name, (quittung, zustand) in faelle.items():
            with self.subTest(fall=name):
                result, payload = self.sweep(
                    self.FRAGE, "--size", "10", "--receipt", *quittung)
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertEqual(payload["state"], zustand)
                self.assertEqual(payload["evidence"], [])
                self.assertEqual(payload["selected"], [])
                self.assertFalse(payload["abstention"]["allowed"])
                self.assertIsNone(payload["sweep_fingerprint"])
        _, unvollstaendig = self.sweep(
            self.FRAGE, "--size", "10", "--receipt", *gut[:2])
        self.assertEqual(unvollstaendig["missing_batches"], [3])

    def test_seal_binds_question_batch_size_and_release(self):
        self.use_private_vault()
        _, gelesen = self.stapel(self.FRAGE)
        siegel = gelesen[1][0]
        quittung = f"1:{siegel}=-"
        _, gut = self.sweep(self.FRAGE, "--receipt", quittung)
        self.assertEqual(gut["state"], "sweep_complete")

        # Gleiche Frage in anderer Schreibung: dasselbe Siegel.
        _, schreibung = self.sweep(
            "welche  ADRESSE fungiert als dauerhafter Schlüssel einer "
            "Wissenseinheit", "--receipt", quittung)
        self.assertEqual(schreibung["state"], "sweep_complete")

        _, andere_frage = self.sweep("Was ist OKF?", "--receipt", quittung)
        self.assertEqual(andere_frage["state"], "invalid_receipt")
        _, andere_groesse = self.sweep(
            self.FRAGE, "--size", "200", "--receipt", quittung)
        self.assertEqual(andere_groesse["state"], "invalid_receipt")

        # Ein neuer Release ist ein neuer Stand: alte Quittungen verfallen.
        page = self.root / "knowledge/demo-okf/fakten.md"
        page.write_text(
            page.read_text(encoding="utf-8").replace(
                "Sammelbecken für belegte", "Sammelbecken für die belegten"),
            encoding="utf-8",
        )
        self.release()
        _, neuer_stand = self.sweep(self.FRAGE, "--receipt", quittung)
        self.assertEqual(neuer_stand["state"], "invalid_receipt")

    def test_partial_scope_never_licenses_not_in_vault(self):
        plan, gelesen = self.stapel(self.FRAGE, "--domain", "demo-extern")
        self.assertFalse(plan["scope"]["complete"])
        self.assertEqual(plan["scope"]["claims_in_scope"], 2)
        self.assertEqual(plan["scope"]["claims_total"], 28)
        quittung = [f"{n}:{s}=-" for n, (s, _) in sorted(gelesen.items())]
        result, fertig = self.sweep(
            self.FRAGE, "--domain", "demo-extern", "--receipt", *quittung)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(fertig["state"], "sweep_complete")
        self.assertFalse(fertig["coverage"]["scope_complete"])
        self.assertFalse(fertig["abstention"]["allowed"])
        self.assertIn("in diesem Umfang", fertig["abstention"]["reason"])

        # Dieselbe Quittung gilt nicht für den ganzen Bestand.
        _, erschlichen = self.sweep(self.FRAGE, "--receipt", *quittung)
        self.assertNotEqual(erschlichen["state"], "sweep_complete")

        _, seite = self.sweep(
            self.FRAGE, "--page", "knowledge/demo-okf/fakten.md")
        self.assertEqual(seite["scope"]["claims_in_scope"], 2)

    def test_invalid_arguments_are_no_negative_finding(self):
        faelle = [
            ("--domain", "gibt-es-nicht"),
            ("--page", "knowledge/demo-okf/gibt-es-nicht.md"),
            ("--size", "4"),
            ("--size", "201"),
            ("--batch", "2"),
            ("--batch", "0"),
        ]
        for argumente in faelle:
            with self.subTest(argumente=argumente):
                result, payload = self.sweep(self.FRAGE, *argumente)
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertEqual(payload["state"], "invalid_query")
                self.assertTrue(payload["errors"])
                self.assertNotIn("evidence", payload)
        result, payload = self.sweep(
            self.FRAGE, "--batch", "1", "--receipt", "1:0000000000000000=-")
        self.assertEqual(payload["state"], "invalid_query")

    def test_sweep_honours_the_manifest_gate(self):
        self.use_private_vault()
        page = self.root / "knowledge/demo-okf/okf.md"
        page.write_text(page.read_text(encoding="utf-8") + "\nDrift\n",
                        encoding="utf-8")
        for argumente in ([], ["--batch", "1"], ["--receipt"]):
            with self.subTest(argumente=argumente):
                result, payload = self.sweep(self.FRAGE, *argumente)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertEqual(payload["state"], "invalid_vault")
                self.assertEqual(payload["schema"], "skillsafe.sweep/v1")
                self.assertNotIn("pages", payload)
                self.assertNotIn("C-0001", result.stdout)

    def test_stats_reports_what_a_sweep_costs(self):
        result = self.run_cli("stats")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            "Vollsichtung: 28 Claims, Stapel: 1, Stapelgröße: 40", result.stdout)


class RecallGateTests(unittest.TestCase):
    """Misst den tatsächlich eingecheckten Skill, wie test_packaged_vault."""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "skillsafe_recall_check", RECALL_TOOL)
        cls.tool = importlib.util.module_from_spec(spec)
        vorher = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        try:
            spec.loader.exec_module(cls.tool)
        finally:
            sys.dont_write_bytecode = vorher
        cls.fragen, cls.negativ = cls.tool.lade_gold(GOLD, SOURCE_SKILL)
        cls.zeilen, cls.negativ_zeilen = cls.tool.messe(
            SOURCE_SKILL, cls.fragen, cls.negativ)
        cls.sichtung = cls.tool.sichtung_pruefen(
            SOURCE_SKILL, cls.fragen[0]["frage"])

    def test_no_miss_is_silent(self):
        """Das eine harte Gate. Güte darf schwanken, Ehrlichkeit nicht."""
        still = [zeile for zeile in self.zeilen if zeile["ausgang"] == "still"]
        self.assertEqual(
            still, [],
            "Der Claim fehlt, aber das Ergebnis behauptet 'strong'. "
            "Entweder fehlt ein Alias, oder die Trefferstärke lügt.",
        )

    def test_recall_stays_above_the_floor(self):
        gruppen = {zeile["gruppe"] for zeile in self.zeilen}
        self.assertEqual(gruppen, set(MIN_RECALL))
        for gruppe, untergrenze in sorted(MIN_RECALL.items()):
            with self.subTest(gruppe=gruppe):
                zahl = self.tool.zusammenfassung(
                    [z for z in self.zeilen if z["gruppe"] == gruppe])
                self.assertGreaterEqual(
                    zahl["recall_prozent"], untergrenze,
                    f"Trefferquote der Gruppe {gruppe!r} auf "
                    f"{zahl['recall_prozent']} % gefallen",
                )

    def test_every_expected_claim_is_reachable_by_sweep(self):
        """Was das Ranking verfehlt, muss die Vollsichtung vorlegen."""
        geliefert = self.sichtung["geliefert"]
        self.assertEqual(len(geliefert), len(set(geliefert)))
        self.assertEqual(len(geliefert), self.sichtung["claims_total"])
        for zeile in self.zeilen:
            for claim_id in zeile["erwartet"]:
                self.assertIn(claim_id, geliefert, zeile["frage"])

    def test_negative_questions_never_get_a_free_pass(self):
        """Kein Feld der Abfrage erlaubt ein 'Nicht im Bestand'.

        Die Erlaubnis steht ausschließlich in der Quittung einer
        vollständigen Sichtung. Geprüft wird am Vertrag, nicht an einer
        Trefferzahl: eine Negativfrage darf 'strong' aussehen, wenn sie einen
        bekannten Begriff nennt, und braucht die Sichtung trotzdem.
        """
        self.assertGreaterEqual(len(self.negativ_zeilen), 10)
        probe = self.tool.lauf(SOURCE_SKILL, "query", self.negativ[0])
        self.assertNotIn("abstention", probe)
        self.assertEqual(probe["coverage"]["semantic_coverage"], "not_assessed")

    def test_gold_never_lives_in_or_leaks_into_the_skill(self):
        alle = [eintrag["frage"] for eintrag in self.fragen] + list(self.negativ)
        self.assertEqual(self.tool.leck_suche(SOURCE_SKILL, alle), [])
        with tempfile.TemporaryDirectory(prefix="skillsafe-gold-") as temp:
            vault = Path(temp) / "wissenstresor"
            shutil.copytree(SOURCE_SKILL, vault)
            drinnen = vault / "notes" / "gold.json"
            shutil.copy(GOLD, drinnen)
            with self.assertRaises(self.tool.GoldFehler):
                self.tool.lade_gold(drinnen, vault)
            drinnen.unlink()
            # Eine Goldfrage als Alias einzutragen wäre der bequeme Weg zu
            # 100 %. Der Wächter findet sie.
            frage = self.fragen[0]["frage"]
            (vault / "notes" / "dead-ends.md").write_text(
                f"Notiz: {frage}\n", encoding="utf-8")
            lecks = self.tool.leck_suche(vault, alle)
            self.assertEqual(lecks, [(frage, "notes/dead-ends.md")])

    def test_tool_exit_code_follows_the_gates(self):
        """Das Werkzeug als Prozess, mit einem kleinen eigenen Gold.

        Bewusst nicht der ganze Fragensatz: der läuft oben schon einmal. Hier
        zählt nur, dass Exit-Code und Meldung den Gates folgen.
        """
        with tempfile.TemporaryDirectory(prefix="skillsafe-gold-") as temp:
            gold = Path(temp) / "gold.json"
            gold.write_text(json.dumps({
                "schema": "skillsafe.recall-gold/v1",
                "fragen": [
                    {"frage": "Welche Stufen des Vertrauens kennt Trust-Tier?",
                     "erwartet": ["C-0305"]},
                    {"frage": "Wer bezahlt den Klempner?",
                     "erwartet": ["C-0402"]},
                ],
                "negativ": [],
            }, ensure_ascii=False), encoding="utf-8")
            argv = [sys.executable, "-B", str(RECALL_TOOL), "--kurz",
                    "--gold", str(gold)]

            def lauf(*extra):
                return subprocess.run(
                    argv + list(extra), cwd=REPOSITORY, text=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    check=False, timeout=120,
                )

            gruen = lauf()
            self.assertEqual(gruen.returncode, 0, gruen.stdout + gruen.stderr)
            self.assertIn("0 stille Verfehlungen", gruen.stdout)
            self.assertIn("verfehlt, Vollsichtung Pflicht    1", gruen.stdout)
            rot = lauf("--min-recall", "100")
            self.assertEqual(rot.returncode, 1, rot.stdout + rot.stderr)
            self.assertIn("unter der Untergrenze", rot.stdout)

            # Ein Claim, den es im Bestand nicht gibt, ist kein Messwert,
            # sondern ein kaputtes Gold: die Vollsichtung legt ihn nie vor.
            gold.write_text(json.dumps({
                "schema": "skillsafe.recall-gold/v1",
                "fragen": [{"frage": "Gibt es das?", "erwartet": ["C-9999"]}],
            }), encoding="utf-8")
            kaputt = lauf()
            self.assertEqual(kaputt.returncode, 1, kaputt.stdout + kaputt.stderr)
            self.assertIn("C-9999", kaputt.stdout)


if __name__ == "__main__":
    unittest.main()
