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
# Die veröffentlichte Messung, Limit 8: Fragen, direkt gefunden, Pflicht,
# Hinweis, still, Seite gelesen. README und Landingpage nennen dieselben
# Zahlen (tools/check_docs.py). Ändert sie eine Entscheidung am Ranking,
# ändern sich Profilnummer, diese Zeilen und der Schnappschuss der Rangfolge
# gemeinsam; ein Versehen fällt hier auf.
MESSUNG = {
    "entwicklung": (28, 19, 9, 0, 0, 22),
    "kontrolle": (56, 18, 37, 1, 0, 38),
}
# Negativfragen: Anzahl, davon Pflicht-Vollsichtung, davon 'strong'.
MESSUNG_NEGATIV = (27, 16, 1)
DOCS_TOOL = REPOSITORY / "tools/check_docs.py"


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

    def add_concept(self, concept_id, preferred, aliases, definition_claim,
                    world="BW-0001"):
        """Einen Begriff in die Begriffswelten der eigenen Kopie eintragen."""
        pfad = self.root / "schema/begriffswelten.json"
        daten = json.loads(pfad.read_text(encoding="utf-8"))
        daten["concepts"].append({
            "id": concept_id, "world": world, "preferred": preferred,
            "aliases": list(aliases), "broader": [], "related": [],
            "definition_claim": definition_claim,
        })
        pfad.write_text(
            json.dumps(daten, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")

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

        Genau dieser Fehler steckte bis extern-zweistufig/v1 in
        RETRIEVAL_STOPWORDS ('für' stand dort, geprüft wurde gegen 'fuer');
        seit v2 wird die alte Liste normalisiert. Die neue darf ihn nie haben.
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

    def test_indexed_variants_equal_the_full_scan(self):
        """Die Verzeichnisse für Stamm, Kopf und Schwanz sind nur schneller.

        Bis v0.13.0 prüfte jede Abfrage je Fragebegriff das ganze Vokabular;
        200 Begriffe gegen 70.000 Tokens brauchten rund zehn Sekunden. Die
        Verzeichnis-Fassung muss dieselben Mengen liefern wie der Vollscan,
        der hier als Referenz noch einmal ausgeschrieben steht.
        """
        engine = self.engine

        def vollscan(begriffe, vokabular):
            staemme = {token: engine._wortstamm(token) for token in vokabular}
            ergebnis = {}
            for begriff in begriffe:
                stamm = engine._wortstamm(begriff)
                formen = {begriff, stamm}
                gleiche, teile = set(), set()
                for token, token_stamm in staemme.items():
                    if token == begriff:
                        continue
                    if token_stamm == stamm:
                        gleiche.add(token)
                        continue
                    token_formen = {token, token_stamm}
                    if (engine._kompositum_teil(formen, token_formen)
                            or engine._kompositum_teil(token_formen, formen)):
                        teile.add(token)
                ergebnis[begriff] = (gleiche, teile)
            return ergebnis

        snapshot, fehler = engine._load_released_query_snapshot("x")
        self.assertIsNone(fehler)
        vokabular = set()
        for page in snapshot["pages"].values():
            vokabular |= set(engine._inhaltstokens(page["fm"].get("title", "")))
            for claim in page["claims"]:
                vokabular |= set(engine._inhaltstokens(
                    f"{claim['text']} {claim['fundstelle']}"))
        silben = ["miet", "minder", "ung", "schimmel", "befall", "nach",
                  "weis", "wissen", "tresor", "stufe", "en", "er", "e", "s",
                  "ae", "ue", "neu", "foerd", "ford", "seite", "sicher"]
        kunst = {a + b + c for a in silben for b in silben
                 for c in ("", "en", "ung")}
        begriffe = sorted(vokabular)[::3] + sorted(kunst)[::7] + [
            "miete", "waende", "wand", "it", "ab", "himmel", "nachweis"]
        for menge in (vokabular, kunst, vokabular | kunst):
            erwartet = vollscan(begriffe, menge)
            self.assertEqual(
                engine._wortform_varianten(begriffe, [menge]), erwartet)
        mit_teil = sum(1 for _, teile in erwartet.values() if teile)
        mit_stamm = sum(1 for gleiche, _ in erwartet.values() if gleiche)
        self.assertGreater(mit_teil, 50)
        self.assertGreater(mit_stamm, 50)

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
        # Die Ausgabe widerspricht sich nicht: Was unter concepts.partial als
        # Wortteil steht, ist auch in der Begriffsliste ein Teiltreffer und
        # kein unbekanntes Wort. Zur Abdeckung zählt es trotzdem nicht.
        begriffe = payload["coverage"]["query_terms"]
        self.assertEqual(begriffe["partial"], ["herkunft"])
        self.assertNotIn("herkunft", begriffe["unmatched"])
        self.assertNotIn("herkunft", begriffe["matched"])
        self.assertEqual(payload["coverage"]["term_coverage_percent"], 0)

    def test_pages_name_their_typed_edges_in_both_directions(self):
        """Wer okf.md liest, sieht dort nicht, dass okf-v02.md sie ersetzt.

        Die Kante steht im Frontmatter der neuen Fassung. Die Seitenangabe
        nennt sie deshalb an beiden Enden, und zwar als Verweis: Sie hebt
        keinen Rang und macht die Nachbarin nicht zur Evidenz.
        """
        _, payload = self.query("Was ist OKF?")
        seiten = {page["path"]: page for page in payload["pages"]}
        alt = seiten["knowledge/demo-okf/okf.md"]
        neu = seiten["knowledge/demo-okf/okf-v02.md"]
        kante_alt = {"type": "ersetzt", "page": "knowledge/demo-okf/okf-v02.md"}
        kante_neu = {"type": "ersetzt", "page": "knowledge/demo-okf/okf.md"}
        self.assertIn(kante_alt, alt["relations"]["incoming"])
        self.assertIn(kante_neu, neu["relations"]["outgoing"])
        self.assertNotIn(kante_alt, alt["relations"]["outgoing"])
        for page in payload["pages"]:
            with self.subTest(page=page["path"]):
                self.assertEqual(
                    set(page["relations"]), {"outgoing", "incoming"})
                for richtung in ("outgoing", "incoming"):
                    kanten = page["relations"][richtung]
                    self.assertEqual(kanten, sorted(
                        kanten, key=lambda k: (k["type"], k["page"])))
                    for kante in kanten:
                        self.assertEqual(set(kante), {"type", "page"})
        # Jede ausgehende Kante steht am Ziel als eingehende, wortgleich mit
        # dem Frontmatter auf der Platte.
        text = (self.root / "knowledge/demo-okf/okf-v02.md").read_text(
            encoding="utf-8")
        self.assertIn("ersetzt -> demo-okf/okf.md", text)

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

    def test_who_moves_up_and_who_gives_way(self):
        """Drei Teile der Nachrück-Regel, die sich einzeln verstellen ließen.

        Für einen Begriff rückt sein Definitions-Claim nach, nicht irgendein
        Claim, der sein Wort trägt. Weichen muss der rangniedrigste reine
        Kontext-Kandidat, aber nie der letzte gezeigte Claim seiner Seite.
        Und ein Wort, das eine vertretene Benennung trägt, holt keinen
        weiteren Träger herein.
        """
        _, paar = self.query("Wissensgraph und Trust-Tier")
        belege = {b["claim_id"]: b["reasons"] for b in paar["evidence"]}
        self.assertIn("concept-definition:B-0003", belege["C-0002"])
        self.assertIn("concept-definition:B-0006", belege["C-0305"])
        self.assertEqual(
            [b["claim_id"] for b in paar["evidence"]],
            ["C-0305", "C-0301", "C-0302", "C-0303", "C-0304", "C-0306",
             "C-0307", "C-0002"])

        # fakten.md steht mit genau einem Claim in der Auswahl. Für "10"
        # rückt C-0202 nach; weichen muss ein Kontext-Claim einer Seite, die
        # danach noch vertreten ist, nicht C-0290.
        _, zehn = self.query("Wissenstresor 10", "--limit", "10")
        self.assertEqual(
            [b["claim_id"] for b in zehn["evidence"]],
            ["C-0005", "C-0001", "C-0002", "C-0003", "C-0004", "C-0104",
             "C-0101", "C-0102", "C-0290", "C-0202"])
        self.assertIn("knowledge/demo-okf/fakten.md",
                      [seite["path"] for seite in zehn["pages"]])
        self.assertEqual(zehn["coverage"]["query_terms"]["unmatched"], [])

        # Eine Benennung "Vermieter" auf fakten.md; das Wort selbst steht nur
        # in C-0402 auf einer anderen Seite.
        self.use_private_vault()
        self.add_concept("B-0100", "Vermieter", [], "C-0290")
        fakten = self.root / "knowledge/demo-okf/fakten.md"
        kopf = fakten.read_text(encoding="utf-8")
        self.assertEqual(kopf.count("\nconcepts: [B-0002]\n"), 1)
        fakten.write_text(kopf.replace(
            "\nconcepts: [B-0002]\n",
            "\nconcepts: [B-0002, B-0100]\n"), encoding="utf-8")
        self.release()
        _, benannt = self.query("Vermieter", "--limit", "2")
        self.assertEqual(
            [b["claim_id"] for b in benannt["evidence"]], ["C-0290", "C-0291"])
        self.assertTrue(benannt["concepts"]["matched"][0]["represented"])
        self.assertEqual(
            benannt["coverage"]["query_terms"]["matched"], ["vermieter"])
        # Der wörtliche Träger ist gekürzt, und das steht da.
        self.assertEqual(
            [seite["best_claim"]
             for seite in benannt["coverage"]["omitted_pages"]], ["C-0402"])

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
        # Die Zähler im Wortlaut. Vertauscht oder verrutscht sagten sie dem
        # Modell das Gegenteil: 'direct' sind gekürzte Claims mit eigenem
        # Treffer, 'context' solche, die nur über ihre Seite Kandidat waren.
        self.assertEqual(zahlen, {
            "total": 28, "returned": 1,
            "omitted_direct": 7, "omitted_context": 20})
        self.assertEqual(voll["coverage"]["candidates"], {
            "total": 28, "returned": 20,
            "omitted_direct": 0, "omitted_context": 8})
        # Genannt werden nur Seiten, die einen gekürzten eigenen Treffer
        # tragen und nicht ohnehin unter 'pages' stehen, die beste zuerst.
        self.assertEqual(knapp["coverage"]["omitted_pages"], [
            {"path": "knowledge/demo-okf/okf-v02.md", "claims": 4,
             "best_claim": "C-0301", "best_score": 160},
            {"path": "knowledge/demo-extern/mietminderung.md", "claims": 1,
             "best_claim": "C-0401", "best_score": 20},
        ])
        self.assertFalse(knapp["coverage"]["omitted_pages_truncated"])
        self.assertEqual(voll["coverage"]["omitted_pages"], [])
        # Der Aufwand der Vollsichtung steht auch dann da, wenn es
        # Kandidaten gibt.
        self.assertEqual(knapp["fallback"]["sweep"], {
            "claims": 28, "batch_size": 40, "batches": 1})
        # Mehrere unverstandene Wörter stehen alle da, nicht nur das erste.
        _, mehrere = self.query("Wann erscheint OKF v1.0?")
        self.assertEqual(mehrere["coverage"]["query_terms"], {
            "content": ["0", "erscheint", "okf", "v1"], "matched": ["okf"],
            "partial": [], "unmatched": ["0", "erscheint", "v1"]})
        self.assertEqual(mehrere["coverage"]["candidates"], {
            "total": 26, "returned": 8,
            "omitted_direct": 1, "omitted_context": 17})
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

    def test_an_unknown_id_stays_an_unmatched_word(self):
        """Eine vertippte ID verschwand bis v2 spurlos aus der Frage.

        Übrig blieb ein Allerweltswort, das irgendwo traf, und das Ergebnis
        hieß 'strong': jedes Wort wiedererkannt.
        """
        faelle = [("Was steht in C-9999?", "9999", ["C-9999"]),
                  ("Was steht laut S-9999?", "9999", ["S-9999"]),
                  ("Was steht zu B-9999?", "9999", ["B-9999"])]
        for frage, rest, unbekannt in faelle:
            with self.subTest(frage=frage):
                _, payload = self.query(frage)
                begriffe = payload["coverage"]["query_terms"]
                self.assertIn(rest, begriffe["content"])
                self.assertIn(rest, begriffe["unmatched"])
                # Ob es eine Kennung gibt, entscheidet das Script: Das steht
                # im Wortlaut da, nicht nur als ungetroffene Ziffernfolge.
                self.assertEqual(
                    payload["coverage"]["unknown_ids"], unbekannt)
                self.assertNotEqual(
                    payload["coverage"]["match_strength"], "strong")
                # Die Frage gilt allein der Kennung: Das weiß das Script,
                # und eine Vollsichtung fände nichts anderes.
                self.assertFalse(
                    payload["fallback"]["exhaustive_review_required"])
                self.assertIs(payload["fallback"]["unknown_ids_only"], True)
                self.assertEqual(
                    payload["fallback"]["reason"], "unknown_ids_only")
        # Einleitende Wörter ändern daran nichts, gleich ob sie zufällig in
        # einem Claim vorkommen: Die Liste steht in KENNUNG_RAHMENWOERTER.
        # Ein benennendes Substantiv zählt unmittelbar vor der Kennung.
        for frage in ("Was sagt C-9999?", "Worum geht es in S-0099?",
                      "Erkläre C-9999", "Was ist C-9999?",
                      "Was steht in C-9998 und C-9999?",
                      "Was steht in der Quelle S-0099?",
                      "Was steht in den Kennungen C-9998 und C-9999?",
                      "Was steht in den Einträgen C-9998 und C-9999?",
                      "Worum handelt es sich bei C-9999?",
                      "Bitte erkläre C-9999",
                      # "laut" vor der Kennung, auch über einen Artikel;
                      # "bitte" am Ende; Satzzeichen und Auszeichnung.
                      "Was gilt laut der Quelle S-0099?",
                      "Was steht in C-9999, bitte?",
                      "Was steht in `C-9999`?", "Was steht in „C-9999“?",
                      "Welche der Kennungen C-9998 und C-9999 gibt es?",
                      "Was steht in den Begriffen B-9998 und B-9999?"):
            with self.subTest(frage=frage):
                _, payload = self.query(frage)
                self.assertIs(payload["fallback"]["unknown_ids_only"], True)
                self.assertFalse(
                    payload["fallback"]["exhaustive_review_required"])
        # Gilt die Frage auch einer Sache, oder stehen die Ziffern selbst im
        # Bestand, bleibt die Vollsichtung Pflicht. Sachwort ist jedes Wort
        # außerhalb der Liste: auch ein Homograph, den das Ranking als
        # Funktionswort überliest ("Waren", "Soll und Haben"), und ein
        # Substantiv, das die gefragte Sache ist ("eine Aussage laut S-0099").
        for frage in ("Was sagt S-0099 zur Mietminderung bei Schimmel?",
                      "S-0007", "Mietminderung C-9999", "Miete C-9999",
                      "Waren C-9999", "Was sagt S-0099 zu Soll und Haben?",
                      "Was ist eine Aussage laut S-0099?",
                      "Was ist ein Claim laut S-0099?",
                      "Was ist ein Eintrag (C-9999)?",
                      "Was ist der Inhalt von C-9999?", "What is C-9999?",
                      # Ein Homograph der Liste als Substantiv, eine
                      # angehängte zweite Frage, ein großes Wort mittendrin.
                      "Regeln C-9999",
                      "Welche Regeln gibt es und was steht in C-9999?",
                      "Was bedeutet das genau, und was steht in C-9999?",
                      "Was ist ein Laut und was ist C-9999?",
                      "Was steht in C-9999? Und was in C-9998?",
                      # Kleingeschrieben: hinter einem Artikel steht ein
                      # Substantiv (dritte Prüfrunde).
                      "was ist ein laut in c-9999", "was sagt c-9999 zum aus",
                      "welche bitte enthält c-9999",
                      "was steht in c-9999 zum ist",
                      "was sagt c-9999 über das stehen",
                      "welcher laut steht in c-9999",
                      "C-9999 was ist ein laut", "welche lauten nennt c-9999",
                      # "laut" nur vor einer Kennung, nie am Anfang; Verben,
                      # die auch Substantive sind, stehen nicht in der Liste.
                      "Laut C-9999", "Lauten C-9999", "Stehen C-9999",
                      "Laut in C-9999?", "„Laut“ – was ist das in C-9999?",
                      "Erkläre bitte C-9999",
                      # Ein Zeichen ist ein Sachwort.
                      "Was bedeutet ∀ laut C-9999?", "Was bedeutet § in C-9999?",
                      "Was ist % in C-9999?", "Was gilt für € laut C-9999?",
                      "Was bedeutet \U0001F525 in C-9999?",
                      # Je eine Regel allein: das große Wort mittendrin, das
                      # Bindewort, das eine zweite Frage anhängt.
                      "Was sagt C-9999 über Wie?",
                      "Was steht in C-9999 und worum geht es?"):
            with self.subTest(frage=frage):
                _, payload = self.query(frage)
                self.assertTrue(payload["coverage"]["unknown_ids"])
                self.assertIs(payload["fallback"]["unknown_ids_only"], False)
                self.assertNotEqual(
                    payload["fallback"]["reason"], "unknown_ids_only")
                if payload["coverage"]["match_strength"] in ("weak", "none"):
                    self.assertTrue(
                        payload["fallback"]["exhaustive_review_required"])
        # Geprüft wird am ganzen Bestand, nicht an der Ausgabe: Die Ziffern
        # von S-0007 stehen in der Fundstelle A-0007 von C-0402, und die
        # schneidet ein knappes Limit ab.
        for limit in ("1", "8"):
            with self.subTest(limit=limit):
                _, knapp = self.query("Was steht in S-0007?", "--limit", limit)
                self.assertIs(knapp["fallback"]["unknown_ids_only"], False)
        # Vollbreit-Ziffern: kein Absturz und keine Kennung. Als Kennung
        # zählt nur die Schreibung mit ASCII-Ziffern; stünde "C-０００１" unter
        # unknown_ids, hieße das "gibt es nicht", obwohl es C-0001 gibt.
        for frage in ("Was steht in C-\uff19\uff19\uff19\uff19?",
                      "Was steht in C-\uff10\uff10\uff10\uff11?",
                      "Was regelt C-\uff10\uff10\uff10\uff11 zu Markdown?"):
            with self.subTest(frage=frage):
                result, breit = self.query(frage)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(breit["coverage"]["unknown_ids"], [])
                self.assertIs(breit["fallback"]["unknown_ids_only"], False)
        # Neben einer vorhandenen Kennung oder einem getroffenen Begriff ist
        # es kein Kennungsfall; was die Stärke verlangt, gilt wie sonst.
        for frage in ("C-0401 C-9999", "OKF C-9999"):
            with self.subTest(frage=frage):
                _, payload = self.query(frage)
                self.assertEqual(payload["coverage"]["unknown_ids"], ["C-9999"])
                self.assertIs(payload["fallback"]["unknown_ids_only"], False)
                self.assertNotEqual(
                    payload["fallback"]["reason"], "unknown_ids_only")
        _, ohne_frage = self.query("C-9999")
        self.assertEqual(ohne_frage["state"], "no_candidates")
        self.assertEqual(ohne_frage["fallback"]["reason"], "unknown_ids_only")
        self.assertIs(ohne_frage["fallback"]["unknown_ids_only"], True)
        self.assertFalse(ohne_frage["fallback"]["exhaustive_review_required"])
        # Eine Frage ohne jede Kennung ist nie der Kennungsfall.
        _, ohne_kennung = self.query("Was steht in?")
        self.assertIs(ohne_kennung["fallback"]["unknown_ids_only"], False)
        # Eine vorhandene ID bleibt, was sie war: ein Anker, kein Wort.
        _, bekannt = self.query("Was steht in C-0001?")
        self.assertEqual(
            bekannt["coverage"]["query_terms"]["content"], ["steht"])
        self.assertEqual(bekannt["coverage"]["unknown_ids"], [])
        # Bekannte und unbekannte Kennung in einer Frage: Die bekannte ist
        # ein Anker, die unbekannte steht trotzdem da und verhindert 'strong'.
        _, beide = self.query("Was steht in c-9999 und in C-0001?")
        self.assertEqual(beide["coverage"]["unknown_ids"], ["C-9999"])
        self.assertEqual(beide["coverage"]["match_strength"], "partial")
        self.assertIn("9999", beide["coverage"]["query_terms"]["unmatched"])
        self.assertEqual(beide["evidence"][0]["claim_id"], "C-0001")
        _, fehler = self.query("C-9999", "--world", "BW-9999")
        self.assertEqual(fehler["state"], "invalid_query")
        self.assertEqual(fehler["coverage"]["unknown_ids"], [])
        self.assertEqual(bekannt["evidence"][0]["claim_id"], "C-0001")
        # Eine B-ID der gewählten Welt bleibt ebenfalls ein Anker.
        _, welt = self.query("B-0001", "--world", "BW-0001")
        self.assertEqual(welt["coverage"]["query_terms"]["content"], [])
        # Ziffern als Wortteil eines Claims ("Formblatt C9991", "Anlage
        # C-9992a", "die 9993er Fassung") stehen im Bestand: kein Erlass.
        self.use_private_vault()
        seite = self.root / "knowledge/demo-okf/okf.md"
        text = seite.read_text(encoding="utf-8")
        claim = re.search(r"^- \*\*C-0001\*\* .*$", text, flags=re.M).group(0)
        seite.write_text(text.replace(
            claim, claim + " (vgl. Formblatt C9991, Anlage C-9992a, die "
                           "9993er Fassung)").replace(
            "tags: [okf, format,", "tags: [okf, formblatt-9994, format,").replace(
            "title: Open Knowledge Format (OKF)",
            "title: Open Knowledge Format (OKF) 9997"), encoding="utf-8")
        self.release()
        # Auch im Tag und im Seitentitel stehen Ziffern im Bestand.
        for ziffern in ("9991", "9992", "9993", "9994", "9997"):
            with self.subTest(wortteil=ziffern):
                _, teil = self.query(f"Was steht in C-{ziffern}?")
                self.assertEqual(teil["coverage"]["unknown_ids"],
                                 [f"C-{ziffern}"])
                self.assertIs(teil["fallback"]["unknown_ids_only"], False)
        _, frei = self.query("Was steht in C-9996?")
        self.assertIs(frei["fallback"]["unknown_ids_only"], True)
        # Eine B-ID aus einer anderen Welt steht unter unknown_ids, aber es
        # gibt sie: Der Satz "gibt es im Bestand nicht" wäre falsch.
        self.install_second_world()
        _, fremd = self.query("Was bedeutet B-0900?", "--world", "BW-0001")
        self.assertEqual(fremd["coverage"]["unknown_ids"], ["B-0900"])
        self.assertIs(fremd["fallback"]["unknown_ids_only"], False)
        _, eigen = self.query("Was bedeutet B-0900?")
        self.assertEqual(eigen["coverage"]["unknown_ids"], [])

    def test_second_concept_is_never_dropped_behind_a_strong_label(self):
        """Zwei kuratierte Begriffe in einer Frage.

        Bis v2 füllte die Seite des einen das Limit mit Kontext-Claims, die
        Seite des anderen fehlte samt Definitions-Claim, und weil eine
        getroffene Benennung pauschal als verstanden galt, hieß das Ergebnis
        'strong' mit 100 Prozent. Gefunden hat das der Review, nicht das Gold:
        Dort erreichen nur zwei von 84 Fragen überhaupt 'strong'.
        """
        _, payload = self.query("Ontologie und Provenienz")
        belege = [item["claim_id"] for item in payload["evidence"]]
        seiten = [page["path"] for page in payload["pages"]]
        self.assertIn("C-0201", belege)   # Definition von B-0004
        self.assertIn("C-0302", belege)   # Definition von B-0007
        self.assertIn("knowledge/demo-okf/ontologie-strategie.md", seiten)
        self.assertIn("knowledge/demo-okf/okf-v02.md", seiten)
        self.assertEqual(payload["coverage"]["match_strength"], "strong")

        # Als Reihe über alle Paare von Vorzugsbenennungen: 'strong' gibt es
        # nur, wenn jeder getroffene Begriff in der Ausgabe vertreten ist.
        engine = load_engine(self.root)
        snapshot, fehler = engine._load_released_query_snapshot("x")
        self.assertIsNone(fehler)
        begriffe = snapshot["concepts"]
        geprueft = 0
        for eins in sorted(begriffe):
            for zwei in sorted(begriffe):
                if eins == zwei:
                    continue
                frage = (f"{begriffe[eins]['preferred']} und "
                         f"{begriffe[zwei]['preferred']}")
                paar, _ = engine._load_released_query_snapshot(frage)
                ergebnis = engine.build_query_result(paar)
                if ergebnis["coverage"]["match_strength"] != "strong":
                    continue
                geprueft += 1
                gezeigt = {item["claim_id"] for item in ergebnis["evidence"]}
                seiten = {page["path"] for page in ergebnis["pages"]}
                for treffer in ergebnis["concepts"]["matched"]:
                    cid = treffer["id"]
                    vertreten = (
                        begriffe[cid].get("definition_claim") in gezeigt
                        or any(cid in snapshot["pages"][pfad]["fm"].get(
                            "concepts", []) for pfad in seiten))
                    self.assertTrue(vertreten, (frage, cid))
        self.assertGreater(geprueft, 20)

    def test_strong_needs_every_named_concept_and_every_id(self):
        """'strong' heißt: nichts an der Frage blieb unverstanden.

        Zwei Wege blieben nach hybrid-local/v3 offen, beide über Dinge, die
        kein Inhaltswort beisteuern. Ein Begriff, der per ID genannt ist
        (oder dessen Benennung nur aus Funktionswörtern besteht), fehlte in
        der Ausgabe, und das Ergebnis hieß trotzdem 'strong'. Und die Ziffern
        einer Kennung, die es nicht gibt, standen zufällig irgendwo im
        Bestand.
        """
        # B-0004 ist genannt, aber die acht Plätze füllt die Seite der Quelle.
        _, payload = self.query("S-0004 OKF B-0004")
        begriffe = {b["id"]: b for b in payload["concepts"]["matched"]}
        self.assertEqual(begriffe["B-0004"]["match"], "id")
        self.assertFalse(begriffe["B-0004"]["represented"])
        self.assertTrue(begriffe["B-0001"]["represented"])
        self.assertEqual(payload["coverage"]["term_coverage_percent"], 100)
        self.assertEqual(payload["coverage"]["match_strength"], "partial")
        # Seine Seite steht dann unter den gekürzten, damit sie gelesen wird.
        self.assertIn(
            "knowledge/demo-okf/ontologie-strategie.md",
            [seite["path"] for seite in payload["coverage"]["omitted_pages"]])
        _, knapp = self.query("C-0401 B-0004", "--limit", "1")
        self.assertEqual(
            [b["claim_id"] for b in knapp["evidence"]], ["C-0401"])
        self.assertEqual(knapp["coverage"]["match_strength"], "partial")
        self.assertFalse(knapp["concepts"]["matched"][0]["represented"])
        # Ist der Begriff vertreten, bleibt es bei 'strong'.
        _, allein = self.query("B-0004")
        self.assertTrue(allein["concepts"]["matched"][0]["represented"])
        self.assertEqual(allein["coverage"]["match_strength"], "strong")
        self.assertEqual(allein["coverage"]["omitted_pages"], [])

        # Eine Benennung ohne Inhaltswort, in einem eigenen Bestand. Mit
        # acht Plätzen rückt ihr Definitions-Claim nach; mit einem Platz kann
        # nichts weichen, und der Begriff bleibt unvertreten.
        self.use_private_vault()
        self.add_concept("B-0100", "Soll und Haben", [], "C-0291")
        fakten = self.root / "knowledge/demo-okf/fakten.md"
        kopf = fakten.read_text(encoding="utf-8")
        self.assertEqual(kopf.count("\nconcepts: [B-0002]\n"), 1)
        fakten.write_text(kopf.replace(
            "\nconcepts: [B-0002]\n",
            "\nconcepts: [B-0002, B-0100]\n"), encoding="utf-8")
        self.release()
        _, voll = self.query("OKF Soll und Haben")
        self.assertEqual(
            {b["id"]: b["represented"] for b in voll["concepts"]["matched"]},
            {"B-0001": True, "B-0100": True})
        self.assertIn("C-0291", [b["claim_id"] for b in voll["evidence"]])
        self.assertEqual(voll["coverage"]["match_strength"], "strong")
        _, einer = self.query("OKF Soll und Haben", "--limit", "1")
        self.assertEqual(
            {b["id"]: b["represented"] for b in einer["concepts"]["matched"]},
            {"B-0001": True, "B-0100": False})
        self.assertEqual(einer["coverage"]["query_terms"]["content"], ["okf"])
        self.assertEqual(einer["coverage"]["term_coverage_percent"], 100)
        self.assertEqual(einer["coverage"]["match_strength"], "partial")
        self.assertIn(
            "knowledge/demo-okf/fakten.md",
            [seite["path"] for seite in einer["coverage"]["omitted_pages"]])

        # Eine Kennung, die es nicht gibt, deren Ziffern aber irgendwo stehen.
        seite = fakten
        text = seite.read_text(encoding="utf-8")
        self.assertIn("POLE stammt aus", text)
        seite.write_text(text.replace(
            "POLE stammt aus", "POLE stammt seit 2026 aus"), encoding="utf-8")
        self.release()
        _, datum = self.query("S-2026")
        self.assertEqual(datum["coverage"]["unknown_ids"], ["S-2026"])
        self.assertEqual(
            datum["coverage"]["query_terms"]["matched"], ["2026"])
        self.assertEqual(datum["coverage"]["term_coverage_percent"], 100)
        self.assertEqual(datum["coverage"]["match_strength"], "weak")
        self.assertTrue(datum["fallback"]["exhaustive_review_required"])
        _, beide = self.query("Was sagt S-2026 zu OKF?")
        self.assertEqual(beide["coverage"]["unknown_ids"], ["S-2026"])
        self.assertEqual(beide["coverage"]["match_strength"], "partial")

    def test_the_definition_page_survives_a_shortened_page_list(self):
        """Die Liste der gekürzten Seiten hat eine Obergrenze.

        Der Vertrag schickt den Agenten zur Definitionsseite eines
        unvertretenen Begriffs. Fiel sie der Obergrenze zum Opfer, stand der
        Begriff unvertreten da, und niemand sagte, wo er definiert ist.
        """
        engine = load_engine(self.root)
        frage = "S-0004 OKF B-0004"
        snapshot, fehler = engine._load_released_query_snapshot(frage)
        self.assertIsNone(fehler)
        voll = engine.build_query_result(snapshot)
        self.assertEqual(
            [seite["path"] for seite in voll["coverage"]["omitted_pages"]],
            ["knowledge/demo-okf/okf.md",
             "knowledge/demo-okf/ontologie-strategie.md"])
        vorher = engine.MAX_OMITTED_PAGES
        engine.MAX_OMITTED_PAGES = 1
        try:
            knapp = engine.build_query_result(snapshot)
        finally:
            engine.MAX_OMITTED_PAGES = vorher
        # Die Seite mit dem höheren Rang weicht, die Definitionsseite bleibt.
        self.assertEqual(
            [seite["path"] for seite in knapp["coverage"]["omitted_pages"]],
            ["knowledge/demo-okf/ontologie-strategie.md"])
        self.assertTrue(knapp["coverage"]["omitted_pages_truncated"])
        self.assertFalse(
            {b["id"]: b for b in knapp["concepts"]["matched"]}
            ["B-0004"]["represented"])

        # Die Auswahl selbst: Vorrangseiten verdrängen nur Seiten ohne
        # Vorrang, nie einander, und die Reihenfolge bleibt der Rang.
        def seiten(*namen):
            return [{"path": name} for name in namen]

        def wahl(namen, vorrang, grenze):
            return [eintrag["path"] for eintrag in engine._sichtbare_seiten(
                seiten(*namen), set(vorrang), grenze)]

        self.assertEqual(wahl("xaB", "aB", 2), ["a", "B"])
        self.assertEqual(wahl("axB", "aB", 2), ["a", "B"])
        self.assertEqual(wahl("xyz", "", 2), ["x", "y"])
        self.assertEqual(wahl("xaBc", "aBc", 2), ["a", "B"])
        self.assertEqual(wahl("xy", "y", 5), ["x", "y"])
        self.assertEqual(wahl("", "a", 3), [])

    def test_a_phrase_made_of_a_function_word_is_no_anchor(self):
        """"IT" ist als Abkürzung ein Inhaltswort der Frage, im Bestand aber
        nur das englische "it" einer Fundstelle ("How it works")."""
        _, payload = self.query("IT")
        self.assertEqual(
            payload["coverage"]["query_terms"],
            {"content": ["it"], "matched": [], "partial": [],
             "unmatched": ["it"]})
        self.assertIn("exact:claim", payload["evidence"][0]["reasons"])
        self.assertEqual(payload["coverage"]["match_strength"], "weak")
        self.assertTrue(payload["fallback"]["exhaustive_review_required"])
        # Eine Wortfolge mit getroffenem Inhaltswort bleibt ein Anker.
        _, phrase = self.query("unverzüglich anzuzeigen und zu beheben")
        self.assertEqual(
            phrase["coverage"]["query_terms"]["unmatched"], ["beheben"])
        _, anker = self.query("dem Vermieter nach dem Beispielhandbuch")
        self.assertIn("exact:claim", anker["evidence"][0]["reasons"])
        self.assertEqual(anker["evidence"][0]["claim_id"], "C-0402")
        self.assertEqual(anker["coverage"]["match_strength"], "strong")

    def test_a_function_word_never_names_a_concept(self):
        """'sich' ist nicht 'Sicherung', 'seit' nicht 'Seite'.

        Über die Wortform traf bis v2 jedes Füllwort eine Benennung mit
        gleichem Stamm. Das gab einen Anker, hob die Stärke auf 'partial'
        oder 'strong' und schaltete die Pflicht-Vollsichtung ab: derselbe
        Fehler wie beim Hilfsverb 'darf', nur über die Begriffswelt.
        """
        engine = load_engine(self.root)

        def treffer(benennung, frage):
            begriffe = {"B-0001": {
                "id": "B-0001", "world": "BW-0001", "preferred": benennung,
                "aliases": [], "broader": [], "related": []}}
            _, _, _, arten = engine._match_concepts(
                engine._retrieval_norm(frage), begriffe,
                inhalt=set(engine._inhaltstokens(frage)))
            return arten

        fehltreffer = [
            ("Sicherung", "Wie wirkt sich Schimmel auf die Miete aus?"),
            ("Seite", "Was gilt seit v0.2?"),
            ("Änderung", "Was machen die anderen?"),
            ("Fall", "Was tun, falls es regnet?"),
            ("Weg", "Wegen Regen geschlossen?"),
            ("Wille", "Was will er?"),
            ("Stand der Technik", "Stand und Technik"),
        ]
        for benennung, frage in fehltreffer:
            with self.subTest(benennung=benennung, frage=frage):
                self.assertEqual(treffer(benennung, frage), {})
        # Was ein Inhaltswort trägt, trifft weiterhin: exakt und als Wortform.
        self.assertEqual(
            treffer("Sicherung", "Wie mache ich eine Sicherung?"),
            {"B-0001": "exact"})
        self.assertEqual(
            treffer("Sicherung", "Welche Sicherungen gibt es?"),
            {"B-0001": "wortform"})
        self.assertEqual(
            treffer("Stand der Technik", "Was sind die Stände der Technik?"),
            {"B-0001": "wortform"})
        # Ein Homograph bleibt als Benennung exakt auffindbar, mehr nicht.
        self.assertEqual(
            treffer("Macht", "Was macht er?"), {"B-0001": "exact"})

        # Dasselbe durch die ganze Abfrage: ein Begriff 'Sicherung' im
        # Bestand darf eine Frage mit 'sich' nicht an sich ziehen.
        self.use_private_vault()
        pfad = self.root / "schema/begriffswelten.json"
        daten = json.loads(pfad.read_text(encoding="utf-8"))
        daten["concepts"].append({
            "id": "B-0901", "world": "BW-0001", "preferred": "Sicherung",
            "aliases": [], "broader": [], "related": [],
            "definition_claim": "C-0101",
        })
        pfad.write_text(
            json.dumps(daten, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        seite = self.root / "knowledge/demo-okf/llm-wiki-muster.md"
        seite.write_text(
            seite.read_text(encoding="utf-8").replace(
                "concepts: [B-0002]", "concepts: [B-0002, B-0901]"),
            encoding="utf-8")
        self.release()
        _, payload = self.query("Wie wirkt sich Schimmel auf die Miete aus?")
        self.assertEqual(payload["concepts"]["matched"], [])
        self.assertTrue(payload["fallback"]["exhaustive_review_required"])
        _, direkt = self.query("Wie funktioniert die Sicherung?")
        self.assertEqual(
            [item["id"] for item in direkt["concepts"]["matched"]], ["B-0901"])

    def test_own_hit_outranks_a_grazed_label(self):
        """Ein Claim mit dem Fragewort steht vor der Seite, deren Benennung
        das Wort nur als Wortteil streift. Bis v2 war es umgekehrt (30 gegen
        20 Punkte), und der Claim mit dem Wort fiel aus dem Limit."""
        _, payload = self.query("Wissen verdichten")
        belege = {item["claim_id"]: item for item in payload["evidence"]}
        self.assertIn("C-0301", belege)
        self.assertIn("token:wissen", belege["C-0301"]["reasons"])
        eigene = [item["score"] for item in payload["evidence"]
                  if item["reasons"] != ["concept-page:partial"]]
        gestreift = [item["score"] for item in payload["evidence"]
                     if item["reasons"] == ["concept-page:partial"]]
        self.assertTrue(gestreift)
        self.assertGreater(min(eigene), max(gestreift))
        self.assertEqual(payload["coverage"]["omitted_pages"], [])

    def test_a_question_without_content_words_is_never_strong(self):
        """'nicht' und 'und' stehen wörtlich in vielen Claims.

        Als ganze Frage ist das kein Anker: Verstanden wurde nichts.
        """
        for frage in ("nicht", "und", "Was ist das?"):
            with self.subTest(frage=frage):
                _, payload = self.query(frage)
                self.assertEqual(
                    payload["coverage"]["query_terms"]["content"], [])
                self.assertIn(
                    payload["coverage"]["match_strength"], {"weak", "none"})
                self.assertTrue(
                    payload["fallback"]["exhaustive_review_required"])

    def test_an_acronym_is_never_a_function_word(self):
        """'die IT' ist nicht das englische 'it'."""
        engine = load_engine(self.root)
        tokens = engine._inhaltstokens
        self.assertEqual(
            tokens("Welche Aufgaben hat die IT?"), ("aufgaben", "it"))
        self.assertEqual(tokens("IT"), ("it",))
        self.assertEqual(
            tokens("Die IT übernimmt den Betrieb."),
            ("it", "uebernimmt", "betrieb"))
        # Wer alles groß schreibt, meint keine Abkürzungen.
        self.assertEqual(tokens("WAS IST DIE IT"), ())
        # Das englische Pronomen bleibt ein Funktionswort.
        self.assertEqual(tokens("Is it valid?"), ("valid",))
        # Englische Einträge, die ein deutsches Hauptwort verschluckten.
        self.assertEqual(
            tokens("Not, All, Most und Same"),
            ("not", "all", "most", "same"))
        _, payload = self.query("Welche Aufgaben hat die IT?")
        self.assertEqual(
            payload["coverage"]["query_terms"]["content"], ["aufgaben", "it"])
        self.assertNotEqual(payload["coverage"]["match_strength"], "strong")

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

    def test_legacy_page_list_is_capped_and_says_so(self):
        """fallback.page_paths war die Arbeitsliste des alten Rückfalls.

        Die Vollsichtung hat ihn ersetzt; die Liste bleibt als Feld, wächst
        aber nicht mehr mit dem Bestand in jede Ausgabe hinein.
        """
        _, payload = self.query("Was ist OKF?")
        rueckfall = payload["fallback"]
        self.assertEqual(rueckfall["page_paths_total"], 6)
        self.assertEqual(len(rueckfall["page_paths"]), 6)
        engine = load_engine(self.root)
        self.assertEqual(engine.MAX_FALLBACK_SEITEN, 50)
        snapshot, _ = engine._load_released_query_snapshot("Was ist OKF?")
        vorlage = snapshot["pages"]["knowledge/demo-okf/fakten.md"]
        for nummer in range(80):
            snapshot["pages"][f"knowledge/gross/seite-{nummer:03}.md"] = {
                "fm": dict(vorlage["fm"], concepts=[], tags=[]),
                "claims": [], "relationen": [],
            }
        gross = engine.build_query_result(snapshot)["fallback"]
        self.assertEqual(gross["page_paths_total"], 86)
        self.assertEqual(len(gross["page_paths"]), 50)
        self.assertEqual(gross["page_paths"], sorted(gross["page_paths"]))

    def test_signal_fields_exist_in_every_state(self):
        self.use_private_vault()
        erwartet = {"match_strength", "term_coverage_percent", "query_terms",
                    "candidates", "omitted_pages", "wortform"}
        _, leer = self.query("   ")
        self.assertEqual(leer["state"], "invalid_query")
        self.assertTrue(erwartet <= set(leer["coverage"]))
        # Ein Fehlerzustand ist kein "kein Kandidat": Die Stärke ist nicht
        # bewertet, und die Pflicht-Vollsichtung ist kein Thema.
        self.assertIsNone(leer["coverage"]["match_strength"])
        self.assertFalse(leer["fallback"]["exhaustive_review_required"])
        self.assertEqual(leer["concepts"]["partial"], [])

        page = self.root / "knowledge/demo-okf/okf.md"
        page.write_text(page.read_text(encoding="utf-8") + "\nDrift\n",
                        encoding="utf-8")
        _, kaputt = self.query("OKF")
        self.assertEqual(kaputt["state"], "invalid_vault")
        self.assertTrue(erwartet <= set(kaputt["coverage"]))
        self.assertIsNone(kaputt["coverage"]["match_strength"])
        self.assertIsNone(kaputt["fallback"]["sweep"])

    def test_word_form_ranking_is_deterministic(self):
        erster = self.run_cli(
            "query", "Wie werden Bestätigungen und Vertrauensstufen geprüft?")
        self.assertEqual(erster.returncode, 0, erster.stdout + erster.stderr)
        self.assertEqual(
            json.loads(erster.stdout)["retrieval"], "hybrid-local/v4")
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
        # Der gewählte Claim liegt auf einer überholten Seite, und nach einer
        # Vollsichtung gibt es keinen Graph-Hop, der die Nachfolgerin
        # hereinholte. Die Quittung nennt sie deshalb an der Seite.
        self.assertIn(
            {"type": "ersetzt", "page": "knowledge/demo-okf/okf-v02.md"},
            fertig["pages"][0]["relations"]["incoming"],
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
        inhalt = page.read_text(encoding="utf-8")
        self.assertIn("Sammelbecken dieser Domäne für belegte", inhalt)
        page.write_text(inhalt.replace(
            "Sammelbecken dieser Domäne für belegte",
            "Sammelbecken dieser Domäne für die belegten"), encoding="utf-8")
        self.release()
        _, neuer_stand = self.sweep(self.FRAGE, "--receipt", quittung)
        self.assertEqual(neuer_stand["state"], "invalid_receipt")

    def test_seal_tells_apart_what_the_ranking_may_blur(self):
        """Das Ranking darf 'Maßen' und 'Massen' gleich lesen, das Siegel nicht.

        Sonst gälte die Quittung einer Frage für eine andere, die sich nur in
        einem Operator, einem Vorzeichen oder in ß gegen ss unterscheidet, und
        die Engine bescheinigte eine Sichtung, die es zu dieser Frage nie gab.
        """
        paare = [
            ("Gilt ein Konzept mit stale_after < heute als veraltet?",
             "Gilt ein Konzept mit stale_after >= heute als veraltet?"),
            ("Darf ein Agent Parameter in Maßen ändern?",
             "Darf ein Agent Parameter in Massen ändern?"),
            ("Was sagt der Bestand zu C++?", "Was sagt der Bestand zu C#?"),
            ("Gilt das bei -5 Grad?", "Gilt das bei 5 Grad?"),
            ("Was kostet das: 5 €?", "Was kostet das: 5 %?"),
            ("?", "!"),
            # Bis v0.14.0 fielen Satzzeichen an jedem Wortrand weg. Diese
            # Paare teilten sich deshalb ein Siegel, und die Quittung der
            # einen Frage galt für ihr Gegenteil.
            ("Gilt die Regel bei a != b?", "Gilt die Regel bei a = b?"),
            ("Gilt das bei !aktiv?", "Gilt das bei aktiv?"),
            ("Welcher Faktor gilt: .5?", "Welcher Faktor gilt: 5?"),
            ("Was ergibt 5!?", "Was ergibt 5?"),
            ("Was bedeutet ? in einem Pfad?", "Was bedeutet ! in einem Pfad?"),
            ("Was liefert f()?", "Was liefert f?"),
            ("Wie breit sind 5'?", 'Wie breit sind 5"?'),
            ("Was ist a := b?", "Was ist a = b?"),
            ("Was gilt bei x<5?", "Was gilt bei x 5?"),
            ("Was ist OKF?", "Was ist OKF!"),
            # Auch ein Komma oder ein Punkt bleibt stehen: Das Siegel rät
            # nicht, welches Satzzeichen nichts bedeutet.
            ("Was ist OKF, und wozu?", "Was ist OKF und wozu?"),
            ("Gilt Version 1.5?", "Gilt Version 15?"),
        ]
        for eine, andere in paare:
            with self.subTest(frage=eine):
                _, erste = self.sweep(eine, "--batch", "1")
                _, zweite = self.sweep(andere, "--batch", "1")
                self.assertEqual(erste["state"], "batch", erste)
                self.assertNotEqual(erste["seal"], zweite["seal"])
                _, erschlichen = self.sweep(
                    andere, "--receipt", f"1:{erste['seal']}=-")
                self.assertEqual(erschlichen["state"], "invalid_receipt")
                self.assertFalse(erschlichen["abstention"]["allowed"])
        # Was zwischen zwei Aufrufen derselben Frage schwankt, ohne etwas zu
        # bedeuten, bleibt gleich: Groß-/Kleinschreibung, Leerraum, die Art
        # der Anführungszeichen und Striche, das Fragezeichen am Ende.
        gruppen = [
            ["Was ist OKF?", "was ist okf", "  Was   ist OKF ?  ",
             "WAS IST OKF??"],
            ['Was bedeutet "Trust-Tier" genau?',
             "Was bedeutet „Trust-Tier“ genau?",
             "was bedeutet »Trust‑Tier« genau"],
            ["Wie geht's weiter – und wozu?", "Wie geht’s weiter - und wozu"],
        ]
        alle = set()
        for gleich in gruppen:
            with self.subTest(frage=gleich[0]):
                siegel = {self.sweep(frage, "--batch", "1")[1]["seal"]
                          for frage in gleich}
                self.assertEqual(len(siegel), 1, siegel)
                alle |= siegel
        self.assertEqual(len(alle), len(gruppen))

    def test_repeated_receipt_switches_are_collected(self):
        """Je Stapel ein eigenes --receipt, wie beim Einsammeln von Subagenten."""
        _, gelesen = self.stapel(self.FRAGE, "--size", "10")
        einzeln = []
        for nummer, (siegel, _) in sorted(gelesen.items()):
            einzeln += ["--receipt", f"{nummer}:{siegel}=-"]
        result, fertig = self.sweep(self.FRAGE, "--size", "10", *einzeln)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(fertig["state"], "sweep_complete")
        self.assertEqual(fertig["coverage"]["batches_confirmed"], 3)
        self.assertTrue(fertig["abstention"]["allowed"])

        # Bis v0.13.0 zählte nur der letzte Schalter. War er allein
        # vollständig, verschwand ein früheres Urteil spurlos: hier ein
        # positives zu C-0002, und die Engine erlaubte die Abstention.
        mit_c2 = [nummer for nummer, (_, ids) in gelesen.items()
                  if "C-0002" in ids][0]
        widerspruch = ["--receipt", f"{mit_c2}:{gelesen[mit_c2][0]}=C-0002"]
        widerspruch += ["--receipt"] + [
            f"{nummer}:{siegel}=-"
            for nummer, (siegel, _) in sorted(gelesen.items())]
        result, doppelt = self.sweep(self.FRAGE, "--size", "10", *widerspruch)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertEqual(doppelt["state"], "invalid_receipt")
        self.assertIn("doppelt quittiert", " ".join(doppelt["errors"]))
        self.assertFalse(doppelt["abstention"]["allowed"])
        self.assertEqual(doppelt["selected"], [])

        # Die Frage hinter --receipt würde als Quittungseintrag verschluckt.
        # Das endet als JSON-Zustand mit Hinweis, nicht als Usage-Text.
        result, payload = self.sweep("--size", "10", *einzeln, self.FRAGE)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(payload["state"], "invalid_query")
        self.assertIn("Die Frage fehlt", payload["errors"][0])
        self.assertFalse(payload["abstention"]["allowed"])
        result, payload = self.sweep()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(payload["state"], "invalid_query")

    def test_every_state_carries_the_fail_closed_fields(self):
        """Niemand soll auf einen fehlenden Schlüssel prüfen müssen."""
        faelle = [
            ((), "plan"),
            (("--batch", "1"), "batch"),
            (("--receipt",), "sweep_incomplete"),
            (("--receipt", "1:0000000000000000=-"), "invalid_receipt"),
            (("--domain", "gibt-es-nicht"), "invalid_query"),
            (("--size", "4", "--receipt", "1:0000000000000000=-"),
             "invalid_query"),
        ]
        for argumente, zustand in faelle:
            with self.subTest(zustand=zustand, argumente=argumente):
                _, payload = self.sweep(self.FRAGE, *argumente)
                self.assertEqual(payload["state"], zustand, payload)
                self.assertEqual(payload["evidence"], [])
                self.assertEqual(payload["selected"], [])
                self.assertIs(payload["abstention"]["allowed"], False)
                self.assertTrue(payload["abstention"]["reason"])
        self.use_private_vault()
        page = self.root / "knowledge/demo-okf/fakten.md"
        page.write_text(
            page.read_text(encoding="utf-8") + "\nNachtrag ohne Release.\n",
            encoding="utf-8")
        for argumente in ((), ("--batch", "1"), ("--receipt",)):
            with self.subTest(zustand="invalid_vault", argumente=argumente):
                result, payload = self.sweep(self.FRAGE, *argumente)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(payload["state"], "invalid_vault")
                self.assertEqual(payload["evidence"], [])
                self.assertEqual(payload["selected"], [])
                self.assertIs(payload["abstention"]["allowed"], False)

    def test_no_page_lives_outside_the_manifest(self):
        """knowledge/__pycache__/ nähme das Manifest aus: Wissen ohne Schutz."""
        self.use_private_vault()
        schatten = self.root / "knowledge/__pycache__"
        schatten.mkdir()
        quelle = self.root / "knowledge/demo-okf/fakten.md"
        (schatten / "schatten.md").write_text(
            quelle.read_text(encoding="utf-8")
            .replace("domain: demo-okf", "domain: __pycache__")
            .replace("C-0290", "C-8001").replace("C-0291", "C-8002"),
            encoding="utf-8")
        result = self.run_cli("validate")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("den das Manifest ausnimmt", result.stdout)
        self.assertNotEqual(self.run_cli("release", "patch").returncode, 0)

    def test_side_fields_say_what_was_swept(self):
        """Plan, Stapel, Zähler und Fingerabdruck: was profil.md zusagt."""
        plan, gelesen = self.stapel(self.FRAGE, "--size", "10")
        for eintrag in plan["batches"]:
            ids = gelesen[eintrag["batch"]][1]
            self.assertEqual(
                (eintrag["first_claim"], eintrag["last_claim"],
                 eintrag["claims"]),
                (ids[0], ids[-1], len(ids)))
        _, stapel = self.sweep(self.FRAGE, "--size", "10", "--batch", "1")
        self.assertEqual(
            (stapel["batches_total"], stapel["batch_size"], stapel["batch"]),
            (3, 10, 1))
        for seite in stapel["pages"]:
            # Was das Modell zum Urteilen braucht, steht am Stapel selbst.
            self.assertRegex(seite["stand"], r"^\d{4}-\d{2}-\d{2}$")
            self.assertTrue(seite["tags"])
            self.assertTrue(seite["title"])
            self.assertIn(seite["status"], {"aktiv", "veraltet"})
            self.assertTrue(seite["domain"])

        # Unvollständig: gezählt wird, was quittiert ist, nicht der Umfang.
        gut = [f"{n}:{siegel}=-" for n, (siegel, _) in sorted(gelesen.items())]
        _, teil = self.sweep(self.FRAGE, "--size", "10", "--receipt", *gut[:2])
        self.assertEqual(teil["coverage"]["batches_confirmed"], 2)
        self.assertEqual(teil["coverage"]["batches_total"], 3)
        self.assertEqual(
            teil["coverage"]["claims_swept"],
            len(gelesen[1][1]) + len(gelesen[2][1]))
        self.assertLess(teil["coverage"]["claims_swept"], 28)
        self.assertEqual(teil["coverage"]["claims_total"], 28)
        self.assertEqual(teil["coverage"]["semantic_coverage"], "not_assessed")

        # Der Fingerabdruck steht in der Antwort als Beleg der Sichtung. Er
        # bindet deshalb alles, worin sich zwei Sichtungen unterscheiden
        # können: Auswahl, Frage, Stapelgröße und Umfang.
        _, leer = self.sweep(self.FRAGE, "--size", "10", "--receipt", *gut)
        mit = [f"{n}:{siegel}=" + ("C-0002" if "C-0002" in ids else "-")
               for n, (siegel, ids) in sorted(gelesen.items())]
        _, gewaehlt = self.sweep(self.FRAGE, "--size", "10", "--receipt", *mit)
        abdruecke = [leer["sweep_fingerprint"], gewaehlt["sweep_fingerprint"]]
        for argumente in (("Was ist OKF?", "--size", "10"),
                          (self.FRAGE, "--size", "7"),
                          (self.FRAGE, "--size", "10", "--domain", "demo-okf")):
            _, andere = self.stapel(*argumente)
            quittung = [f"{n}:{s}=-" for n, (s, _) in sorted(andere.items())]
            _, fertig = self.sweep(*argumente, "--receipt", *quittung)
            self.assertEqual(fertig["state"], "sweep_complete", fertig)
            abdruecke.append(fertig["sweep_fingerprint"])
        for abdruck in abdruecke:
            self.assertRegex(abdruck, r"^[0-9a-f]{64}$")
        self.assertEqual(len(set(abdruecke)), 5)

    def test_scope_is_counted_and_filters_unite(self):
        """'complete' zählt Claims, und --domain und --page vereinigen."""
        beide = ("--domain", "demo-okf", "--domain", "demo-extern")
        plan, gelesen = self.stapel(self.FRAGE, *beide)
        self.assertTrue(plan["scope"]["complete"])
        self.assertEqual(plan["scope"]["claims_in_scope"], 28)
        quittung = [f"{n}:{s}=-" for n, (s, _) in sorted(gelesen.items())]
        _, fertig = self.sweep(self.FRAGE, *beide, "--receipt", *quittung)
        self.assertEqual(fertig["state"], "sweep_complete", fertig)
        # Zwei Filter, die zusammen alles treffen, sind der ganze Bestand.
        self.assertTrue(fertig["coverage"]["scope_complete"])
        self.assertTrue(fertig["abstention"]["allowed"])

        gemischt = ("--domain", "demo-extern",
                    "--page", "knowledge/demo-okf/fakten.md")
        plan, gelesen = self.stapel(self.FRAGE, *gemischt)
        self.assertEqual(plan["scope"]["pages_in_scope"], 2)
        self.assertEqual(plan["scope"]["claims_in_scope"], 4)
        self.assertFalse(plan["scope"]["complete"])
        self.assertEqual(
            sorted(cid for _, ids in gelesen.values() for cid in ids),
            ["C-0290", "C-0291", "C-0401", "C-0402"])

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

    def test_receipt_names_the_successor_even_outside_the_scope(self):
        """Der Umfang begrenzt, was gelesen wird, nicht was der Graph weiß."""
        umfang = ("--page", "knowledge/demo-okf/okf.md")
        _, gelesen = self.stapel(self.FRAGE, *umfang)
        quittung = [
            f"{nummer}:{siegel}=" + ("C-0002" if "C-0002" in ids else "-")
            for nummer, (siegel, ids) in sorted(gelesen.items())
        ]
        _, fertig = self.sweep(self.FRAGE, *umfang, "--receipt", *quittung)
        self.assertEqual(fertig["state"], "sweep_complete", fertig)
        self.assertFalse(fertig["abstention"]["allowed"])
        # okf-v02.md liegt außerhalb des Umfangs und wurde nicht vorgelegt.
        self.assertEqual(fertig["coverage"]["claims_swept"], 5)
        self.assertIn(
            {"type": "ersetzt", "page": "knowledge/demo-okf/okf-v02.md"},
            fertig["pages"][0]["relations"]["incoming"],
        )

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
                self.assertEqual(payload["evidence"], [])
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
        cls.sichtung = cls.tool.sichtung_pruefen(
            SOURCE_SKILL, cls.fragen[0]["frage"])
        # Wie das Werkzeug selbst misst: mit der Zuordnung Claim zu Seite,
        # damit auch der Seitentreffer gezählt ist.
        cls.zeilen, cls.negativ_zeilen = cls.tool.messe(
            SOURCE_SKILL, cls.fragen, cls.negativ, 8,
            cls.sichtung["seite_von"])

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
            # 100 %. Der Wächter findet sie; in welchen Schreibungen, zeigt
            # test_leak_guard_reads_like_the_engine.
            frage = self.fragen[0]["frage"]
            (vault / "notes" / "dead-ends.md").write_text(
                f"Notiz: {frage}\n", encoding="utf-8")
            lecks = self.tool.leck_suche(vault, alle)
            self.assertEqual(lecks, [(frage, "notes/dead-ends.md")])

    def test_measurement_is_the_published_one(self):
        """Die Zahlen der Tabelle, nicht nur ihre Untergrenzen."""
        for gruppe, erwartet in sorted(MESSUNG.items()):
            with self.subTest(gruppe=gruppe):
                zahl = self.tool.zusammenfassung(
                    [z for z in self.zeilen if z["gruppe"] == gruppe])
                self.assertEqual(
                    (zahl["gesamt"], zahl["treffer"], zahl["pflicht"],
                     zahl["hinweis"], zahl["still"], zahl["seite"]),
                    erwartet)
        self.assertEqual(
            (len(self.negativ_zeilen),
             sum(1 for z in self.negativ_zeilen if z["pflicht"]),
             sum(1 for z in self.negativ_zeilen if z["staerke"] == "strong")),
            MESSUNG_NEGATIV)
        # Ein Treffer ist der Claim unter den Kandidaten, nicht bloß seine
        # Seite: Diese Frage zeigt die Seite, nicht den Claim.
        zeile = next(z for z in self.zeilen if z["frage"].startswith(
            "Ab wann ist ein Eintrag abgelaufen"))
        self.assertTrue(zeile["seite_gefunden"])
        self.assertIsNone(zeile["rang"])
        self.assertNotEqual(zeile["ausgang"], "treffer")
        # Negativfragen werden wirklich abgefragt: Die eine, die 'strong'
        # aussieht, nennt einen kuratierten Begriff.
        stark = [z["frage"] for z in self.negativ_zeilen
                 if z["staerke"] == "strong"]
        self.assertEqual(stark, ["Wie groß ist das Open Knowledge Format?"])
        probe = self.tool.lauf(SOURCE_SKILL, "query", stark[0])
        self.assertEqual(probe["coverage"]["match_strength"], "strong")
        self.assertFalse(probe["fallback"]["exhaustive_review_required"])

    def test_the_silent_miss_gate_can_fire(self):
        """Positivkontrolle für das eine harte Gate.

        Am Demo-Gold erreichen nur zwei Fragen 'strong', und beide treffen:
        Das Gate schlug dort noch nie an. Hier bekommt eine 'strong'-Frage
        absichtlich den falschen Claim.
        """
        falsch = [{"frage": "Welche Vertrauensstufen gibt es?",
                   "erwartet": ["C-0402"], "gruppe": "probe"}]
        zeilen, _ = self.tool.messe(SOURCE_SKILL, falsch, [])
        self.assertEqual(zeilen[0]["staerke"], "strong")
        self.assertEqual(zeilen[0]["ausgang"], "still")
        verletzt = self.tool.gates(zeilen, self.sichtung, [], 0, None)
        self.assertEqual(len(verletzt), 1, verletzt)
        self.assertIn("1 stille Verfehlung", verletzt[0])
        with tempfile.TemporaryDirectory(prefix="skillsafe-gold-") as temp:
            gold = Path(temp) / "gold.json"
            gold.write_text(json.dumps({
                "schema": "skillsafe.recall-gold/v1", "fragen": falsch,
            }, ensure_ascii=False), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-B", str(RECALL_TOOL), "--gold", str(gold)],
                cwd=REPOSITORY, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, check=False, timeout=120,
            )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("VERFEHLT, STILL", result.stdout)
        self.assertIn("1 stille Verfehlung", result.stdout)
        self.assertNotIn("🟢", result.stdout)

    def test_each_gate_fires_on_its_own(self):
        """Jedes Gate einzeln, mit Eingaben, die nur dieses eine verletzen."""
        def zeile(ausgang, erwartet="C-0001"):
            return {"frage": "x", "erwartet": [erwartet], "gruppe": "g",
                    "ausgang": ausgang, "rang": None, "seite_gefunden": False,
                    "staerke": "weak", "abdeckung": 0, "ungetroffen": []}

        sauber = {"claims_total": 2, "geliefert": ["C-0001", "C-0002"],
                  "seite_von": {}, "stapel": 1, "vollstaendig": True}
        treffer = [zeile("treffer"), zeile("treffer"), zeile("pflicht")]
        self.assertEqual(self.tool.gates(treffer, sauber, [], 0, None), [])
        # Abgerundet: zwei von drei sind 66 %, nicht 67.
        self.assertEqual(
            self.tool.zusammenfassung(treffer)["recall_prozent"], 66)
        self.assertEqual(self.tool.gates(treffer, sauber, [], 66, None), [])
        faelle = {
            "Untergrenze": (
                (treffer, sauber, [], 67, None), "unter der Untergrenze 67 %"),
            "Hinweis": (
                ([zeile("treffer"), zeile("hinweis")], sauber, [], 0, 0),
                "1 Verfehlungen nur mit Hinweis, erlaubt sind 0"),
            "still": (
                ([zeile("still")], sauber, [], 0, None),
                "1 stille Verfehlung"),
            "doppelt vorgelegt": (
                (treffer, dict(sauber, geliefert=["C-0001", "C-0002",
                                                  "C-0002"]), [], 0, None),
                "nicht jeden Claim genau einmal"),
            "nicht alles vorgelegt": (
                (treffer, dict(sauber, claims_total=3), [], 0, None),
                "nicht jeden Claim genau einmal"),
            "erwarteter Claim fehlt": (
                ([zeile("treffer", "C-0009")], sauber, [], 0, None),
                "legt C-0009 nicht vor"),
            "Leck": (
                (treffer, sauber, [("x", "notes/a.md")], 0, None),
                "1 Goldfrage(n) stehen im Skill-Ordner"),
        }
        for name, (argumente, meldung) in faelle.items():
            with self.subTest(gate=name):
                verletzt = self.tool.gates(*argumente)
                self.assertEqual(len(verletzt), 1, verletzt)
                self.assertIn(meldung, verletzt[0])
        # Ohne --max-hinweis ist eine Verfehlung mit Hinweis kein Gate.
        self.assertEqual(self.tool.gates(
            [zeile("treffer"), zeile("hinweis")], sauber, [], 0, None), [])

    def test_sweep_check_counts_against_the_plan_not_the_delivery(self):
        """Fehlt ein Claim in den Stapeln, darf die Soll-Zahl nicht mitfallen.

        Die Soll-Zahl kommt aus dem Plan der Engine. Nähme das Werkzeug
        stattdessen die Länge dessen, was es bekam, wäre der Wächter blind.
        """
        echt = self.tool.lauf

        def ein_claim_fehlt(vault, *argv):
            ausgabe = echt(vault, *argv)
            if "--batch" in argv:
                ausgabe["pages"][0]["claims"] = ausgabe["pages"][0]["claims"][1:]
            return ausgabe

        self.tool.lauf = ein_claim_fehlt
        try:
            sichtung = self.tool.sichtung_pruefen(SOURCE_SKILL, "Was ist OKF?")
        finally:
            self.tool.lauf = echt
        self.assertEqual(sichtung["claims_total"], 28)
        self.assertEqual(len(sichtung["geliefert"]), 27)
        verletzt = self.tool.gates([], sichtung, [], 0, None)
        self.assertEqual(len(verletzt), 1, verletzt)
        self.assertIn("nicht jeden Claim genau einmal", verletzt[0])

    def test_gold_rejects_one_question_in_two_spellings(self):
        def gold(fragen, negativ=()):
            return {"schema": "skillsafe.recall-gold/v1",
                    "fragen": [{"frage": f, "erwartet": ["C-0305"]}
                               for f in fragen],
                    "negativ": list(negativ)}

        faelle = {
            "wörtlich doppelt": gold(["Was ist OKF?", "Was ist OKF?"]),
            "andere Schreibung": gold(
                ["Welche Vertrauensstufen gibt es?",
                 "welche  vertrauensstufen gibt es"]),
            "Umschrift": gold(["Wie groß ist das?", "Wie gross ist das"]),
            "positiv und negativ": gold(
                ["Was ist OKF?"], ["was ist okf"]),
            "negativ doppelt": gold(
                ["Was ist OKF?"], ["Gibt es Hunde?", "Gibt es Hunde ?"]),
        }
        with tempfile.TemporaryDirectory(prefix="skillsafe-gold-") as temp:
            datei = Path(temp) / "gold.json"
            for name, inhalt in faelle.items():
                with self.subTest(fall=name):
                    datei.write_text(
                        json.dumps(inhalt, ensure_ascii=False),
                        encoding="utf-8")
                    with self.assertRaises(self.tool.GoldFehler) as fehler:
                        self.tool.lade_gold(datei, SOURCE_SKILL)
                    self.assertIn("doppelt", str(fehler.exception))
            datei.write_text(json.dumps(gold(
                ["Was ist OKF?", "Was ist OKF v0.2?"], ["Gibt es Hunde?"]),
                ensure_ascii=False), encoding="utf-8")
            fragen, negativ = self.tool.lade_gold(datei, SOURCE_SKILL)
            self.assertEqual((len(fragen), len(negativ)), (2, 1))

    def test_leak_guard_reads_like_the_engine(self):
        """Eine Goldfrage als Alias sähe aus wie ein Alias.

        Ohne Fragezeichen, in Umschrift, in anderer Großschreibung: genau
        so, wie die Engine eine Benennung trifft. Der Wächter liest deshalb
        mit derselben Normalisierung, in jeder Datei des Skill-Ordners.
        """
        engine = load_engine(SOURCE_SKILL)
        for probe in ("Wie groß ist „OKF“?", "Füße & Öl — ÄRGER", "A\u0308pfel",
                      "ｖｏｌｌｂｒｅｉｔ", "C-0001 / §5.1", "  viel   Raum\n"):
            self.assertEqual(
                self.tool._norm(probe), engine._retrieval_norm(probe), probe)
        # Die Wortform ebenso: jedes Wort des Skill-Ordners und des Golds,
        # dazu Grenzfälle der Endungsregeln.
        woerter = {"prozess", "status", "pruefungen", "waende", "maengel",
                   "s2026", "abcs", "ung", "lesung", "ab", "einer", "ritus"}
        for pfad in SOURCE_SKILL.rglob("*"):
            if pfad.is_file():
                woerter.update(self.tool._norm(
                    self.tool._lesbarer_text(pfad)).split())
        for eintrag in self.fragen:
            woerter.update(self.tool._norm(eintrag["frage"]).split())
        self.assertGreater(len(woerter), 1000)
        abweichend = sorted(wort for wort in woerter if self.tool._wortstamm(
            wort) != engine._wortstamm(wort))
        self.assertEqual(abweichend, [])
        for eintrag in self.fragen:
            self.assertEqual(self.tool._stammform(eintrag["frage"]),
                             engine._stamm_norm(eintrag["frage"]))

        frage = next(e["frage"] for e in self.fragen if "ä" in e["frage"]
                     or "ö" in e["frage"] or "ü" in e["frage"])
        self.assertTrue(frage.endswith("?"))
        nackt = frage.rstrip("?")
        umschrift = (nackt.replace("ä", "ae").replace("ö", "oe")
                     .replace("ü", "ue").replace("ß", "ss"))
        # Dieselbe Frage in anderer Beugung trifft die Engine über die
        # Wortform-Stufe; als Alias brächte sie die Frage auf 'strong'.
        self.assertIn("Einträge ", nackt)
        gebeugt = nackt.replace("Einträge ", "Einträgen ")
        self.assertNotEqual(gebeugt, nackt)
        self.assertEqual(engine._stamm_norm(gebeugt), engine._stamm_norm(nackt))
        alle = [eintrag["frage"] for eintrag in self.fragen]
        nfd = __import__("unicodedata").normalize("NFD", frage)
        varianten = {
            "ohne Fragezeichen": ("notes/a.md", f"Alias: {nackt}\n"),
            "gebeugt": ("notes/a.md", f"Alias: {gebeugt}\n"),
            "gebeugt als Alias": (
                "schema/zusatz.json",
                json.dumps({"aliases": [gebeugt]}, ensure_ascii=True)),
            "Umschrift": ("notes/a.md", f"- {umschrift}\n"),
            "Großschreibung": ("notes/a.md", nackt.upper() + "\n"),
            "Umbruch im Zitat": (
                "notes/a.md",
                "> " + nackt.replace(" ", "\n> ", 3) + "\n"),
            "Hervorhebung": (
                "notes/a.md", nackt.replace(" ", " *", 1).replace(
                    " ", "* ", 2) + "\n"),
            "zerlegte Umlaute": ("notes/a.md", nfd + "\n"),
            "Endung groß": ("notes/FRAGEN.MD", frage + "\n"),
            "ohne Endung": ("notes/FRAGEN", frage + "\n"),
            "Textdatei": ("notes/fragen.txt", frage + "\n"),
            "JSON mit Escape": (
                "schema/extra.json",
                json.dumps({"aliases": [nackt]}, ensure_ascii=True)),
            # Ein Schlüssel ist auch eine Zeichenkette, und die Endung zählt
            # unabhängig von der Schreibung: Mit Escape stünde die Frage
            # sonst nirgends im Klartext.
            "JSON-Schlüssel": (
                "schema/extra.json",
                json.dumps({nackt: "x"}, ensure_ascii=True)),
            "JSON, Endung groß": (
                "schema/EXTRA.JSON",
                json.dumps({"aliases": [nackt]}, ensure_ascii=True)),
        }
        with tempfile.TemporaryDirectory(prefix="skillsafe-gold-") as temp:
            for name, (ort, inhalt) in varianten.items():
                with self.subTest(variante=name):
                    vault = Path(temp) / name.replace(" ", "-") / "wt"
                    shutil.copytree(SOURCE_SKILL, vault)
                    (vault / ort).write_text(inhalt, encoding="utf-8")
                    self.assertEqual(
                        self.tool.leck_suche(vault, alle), [(frage, ort)])
            # Kein Fehlalarm: ein Teil der Frage ist nicht die Frage, und
            # eine Binärdatei wird nicht als Text gelesen.
            vault = Path(temp) / "sauber" / "wt"
            shutil.copytree(SOURCE_SKILL, vault)
            (vault / "notes/a.md").write_text(
                " ".join(nackt.split()[:-1]) + "\n", encoding="utf-8")
            (vault / "notes/bild.bin").write_bytes(
                b"\x00\x01" + frage.encode("utf-8"))
            self.assertEqual(self.tool.leck_suche(vault, alle), [])

            # Wo ein Leck wirkt: in der echten Begriffsdatei, auch ohne das
            # erste Wort der Frage (die Engine trifft eine Benennung als
            # Wortfolge in der Frage), und in einer Seite tief unter
            # knowledge/, auch hinter einem NUL-Byte oder viel Füllstoff.
            def mit_alias(name, alias):
                ziel = Path(temp) / name / "wt"
                shutil.copytree(SOURCE_SKILL, ziel)
                pfad = ziel / "schema/begriffswelten.json"
                daten = json.loads(pfad.read_text(encoding="utf-8"))
                daten["concepts"][0]["aliases"].append(alias)
                pfad.write_text(json.dumps(daten, ensure_ascii=False, indent=2),
                                encoding="utf-8")
                return ziel

            ohne_erstes = " ".join(nackt.split()[1:])
            for name, alias in (("alias-ganz", nackt),
                                ("alias-ohne-erstes", ohne_erstes)):
                with self.subTest(alias=name):
                    self.assertEqual(
                        self.tool.leck_suche(mit_alias(name, alias), alle),
                        [(frage, "schema/begriffswelten.json")])
            # Ein Begriff aus zwei Wörtern der Frage ist kein Leck.
            kurz = mit_alias("alias-kurz", " ".join(nackt.split()[-2:]))
            self.assertEqual(self.tool.leck_suche(kurz, alle), [])
            # Die Schwelle: ab vier Wörtern, oder ab drei, wenn sie drei
            # Viertel der Frage decken; verglichen an Wortgrenzen.
            schwelle = [
                ("drei-von-vier", "heißt das Wissensformat",
                 "Wie heißt das Wissensformat?", True),
                ("drei-von-fünf", "das offene Wissensformat",
                 "Wie heißt das offene Wissensformat?", False),
                ("vier-woerter", "heißt das offene Wissensformat",
                 "Sag mir, wie heißt das offene Wissensformat genau?", True),
                ("wortteil", "heißt das Wissensform",
                 "Wie heißt das Wissensformat?", False),
            ]
            for name, alias, frage_probe, leck in schwelle:
                with self.subTest(schwelle=name):
                    gefunden = self.tool.leck_suche(
                        mit_alias(f"schwelle-{name}", alias), [frage_probe])
                    self.assertEqual(
                        gefunden,
                        [(frage_probe, "schema/begriffswelten.json")]
                        if leck else [])
            # Textordner zählen relativ zum Tresor: Liegt der Tresor selbst
            # unter einem Ordner "schema", bleibt eine Binärdatei binär; eine
            # Datei unter knowledge/ liest der Wächter ganz.
            binaer = b"\x00\x01" + frage.encode("utf-8")
            unter_schema = Path(temp) / "schema" / "wt"
            shutil.copytree(SOURCE_SKILL, unter_schema)
            (unter_schema / "notes/bild.bin").write_bytes(binaer)
            self.assertEqual(self.tool.leck_suche(unter_schema, alle), [])
            (unter_schema / "knowledge/anhang.dat").write_bytes(binaer)
            self.assertEqual(self.tool.leck_suche(unter_schema, alle),
                             [(frage, "knowledge/anhang.dat")])
            seite = "knowledge/demo-okf/okf-v02.md"
            for name in ("Seite", "NUL", "Füllstoff"):
                with self.subTest(seite=name):
                    ziel = Path(temp) / f"seite-{name}" / "wt"
                    shutil.copytree(SOURCE_SKILL, ziel)
                    pfad = ziel / seite
                    text = pfad.read_text(encoding="utf-8") + f"\n{nackt}\n"
                    if name == "NUL":
                        text = text.replace("---\n", "---\n# Notiz \x00\n", 1)
                    if name == "Füllstoff":
                        text += "x " * (3 * 1024 * 1024)
                    pfad.write_text(text, encoding="utf-8")
                    self.assertEqual(self.tool.leck_suche(ziel, alle),
                                     [(frage, seite)])

    def test_doc_check_reads_tables_and_sums_like_a_reader(self):
        """Was gerendert gleich aussieht oder gleich gemeint ist, zählt gleich.

        Eine zweite, falsche Zeile fällt in jeder Schreibweise auf; eine
        richtige Angabe in anderer, legitimer Schreibweise ist kein Fehler;
        und nichts endet in einem Traceback.
        """
        spec = importlib.util.spec_from_file_location(
            "skillsafe_check_docs_leser", DOCS_TOOL)
        docs = importlib.util.module_from_spec(spec)
        vorher = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        try:
            spec.loader.exec_module(docs)
        finally:
            sys.dont_write_bytecode = vorher

        class Stand(dict):
            def __missing__(self, schluessel):
                return None

        stand = Stand({
            f"recall_{gruppe}": werte[:5] for gruppe, werte in MESSUNG.items()})
        stand.update(docs.e2e_eintraege(docs.e2e_stand()))
        readme, landing = docs.README, docs.LANDING
        text = readme.read_text(encoding="utf-8")
        html = landing.read_text(encoding="utf-8")
        dritte_md = "| Ende zu Ende, Runde 3 | v0.14.0 | 12 | 7 | 7 | 5 | 5 | 5 | 5 | **0** |"
        dritte_html = ("<tr><td>Runde 3</td><td>12</td><td>7</td><td>5</td>"
                       "<td>5</td><td>0</td></tr>")
        self.assertEqual(text.count(dritte_md), 1)
        self.assertEqual(html.count(dritte_html), 1)
        falsch_md = "| Ende zu Ende, Runde 3 | v0.14.0 | 12 | 7 | 6 | 5 | 4 | 5 | 4 | **1** |"

        def meldungen(readme_text, landing_text, protokoll=stand):
            with tempfile.TemporaryDirectory(prefix="skillsafe-docs-") as temp:
                try:
                    docs.README = Path(temp) / "README.md"
                    docs.LANDING = Path(temp) / "index.html"
                    docs.README.write_text(readme_text, encoding="utf-8")
                    docs.LANDING.write_text(landing_text, encoding="utf-8")
                    return [m for m in docs.pruefe(protokoll)
                            if "Messwerte" in m or "Ende-zu-Ende" in m]
                finally:
                    docs.README, docs.LANDING = readme, landing

        self.assertEqual(meldungen(text, html), [])
        zweite = {
            "Runde 03": (text.replace(dritte_md, dritte_md + "\n" + falsch_md
                                      .replace("Runde 3", "Runde 03")), html),
            "Vollbreite": (text.replace(dritte_md, dritte_md + "\n" + falsch_md
                                        .replace("Runde 3", "Runde \uff13")),
                           html),
            "Markdown mit Tag": (text.replace(
                dritte_md, dritte_md + "\n" + falsch_md.replace(
                    "Ende zu Ende, Runde 3", "<b>Ende zu Ende, Runde 3</b>")),
                html),
            "ohne Strich am Rand": (text.replace(
                dritte_md, dritte_md + "\n" + falsch_md.strip("|").strip()),
                html),
            "Landing mit Entity": (text, html.replace(
                dritte_html, dritte_html + dritte_html.replace(
                    "<td>Runde 3</td>", "<td>Runde&nbsp;3</td>").replace(
                    "<td>0</td></tr>", "<td>1</td></tr>"))),
            "Landing Runde 03": (text, html.replace(
                dritte_html, dritte_html + dritte_html.replace(
                    "Runde 3", "Runde 03").replace(
                    "<td>0</td></tr>", "<td>1</td></tr>"))),
            "Landing ohne </td>": (text, html.replace(
                dritte_html, dritte_html + "<tr><td>Runde 3<td>12<td>7<td>5"
                "<td>5<td>1</tr>")),
            "Landing fett": (text, html.replace(
                dritte_html, dritte_html + dritte_html.replace(
                    "<td>Runde 3</td>", "<td><b>Runde 3</b></td>").replace(
                    "<td>0</td></tr>", "<td>1</td></tr>"))),
            "README Link": (text.replace(dritte_md, dritte_md + "\n" + falsch_md
                .replace("Ende zu Ende, Runde 3",
                         "[Ende zu Ende, Runde 3](tests/e2e/runde-3.json)")),
                html),
            "README HTML-Tabelle": (text.replace(
                dritte_md, dritte_md + "\n\n<table><tr><td>Ende zu Ende, Runde 3"
                "</td><td>v0.14.0</td><td>12</td><td>7</td><td>6</td><td>5</td>"
                "<td>4</td><td>5</td><td>4</td><td>1</td></tr></table>\n"), html),
            "README zweite Tabelle ohne Rand": (text.replace(
                dritte_md, dritte_md + "\n\nLauf | Stand | a | b | c | d | e | f"
                " | g | h\n---|---|---|---|---|---|---|---|---|---\n"
                + falsch_md.strip("|").strip() + "\n"), html),
            "README falsche Zeile als Kopf": (text.replace(
                dritte_md, dritte_md + "\n\n" + falsch_md.strip("|").strip()
                + "\n---|---|---|---|---|---|---|---|---|---\n"), html),
            "README im Zitat": (text.replace(
                dritte_md, dritte_md + "\n\n> " + falsch_md + "\n"), html),
            "README Fußnote": (text.replace(dritte_md, dritte_md + "\n" + falsch_md
                .replace("Runde 3", "Runde 3 ¹")), html),
            "README Entity": (text.replace(dritte_md, dritte_md + "\n" + falsch_md
                .replace("Runde 3", "Runde&nbsp;3")), html),
            "README vollbreites Komma": (text.replace(
                dritte_md, dritte_md + "\n" + falsch_md.replace(
                    "Ende zu Ende, Runde 3", "Ende zu Ende\uff0cRunde 3")), html),
            "README Code danach": (text.replace(
                dritte_md, dritte_md + "\n\n```Runde``` heißt hier ein Lauf.\n\n"
                + falsch_md.replace("| Ende", "| Ende", 1) + "\n\n```Ende``` der "
                "Nachträge.\n"), html),
            "README Vierer-Zaun": (text.replace(
                dritte_md, dritte_md + "\n\n````md\n```bash\n````\n\n"
                + falsch_md + "\n"), html),
            "README Tilde-Zaun": (text.replace(
                dritte_md, dritte_md + "\n\n~~~md\n```\n~~~\n\n" + falsch_md
                + "\n"), html),
            "README kurze Trennstriche": (text.replace(
                dritte_md, dritte_md + "\n\nLauf|Stand|a|b|c|d|e|f|g|h\n"
                "-|-|-|-|-|-|-|-|-|-\n" + falsch_md.strip("|").strip()
                + "\n"), html),
            "README Kommentar im Codespan": (text.replace(
                dritte_md, dritte_md + "\n\nKommentare beginnen mit `<!--`.\n\n"
                + falsch_md + "\n\nund enden mit `-->`.\n"), html),
            "Landing Fußnote": (text, html.replace(
                dritte_html, dritte_html + dritte_html.replace(
                    "<td>Runde 3</td>", "<td>Runde 3 &dagger;</td>").replace(
                    "<td>0</td></tr>", "<td>1</td></tr>"))),
            "Landing Umbruch": (text, html.replace(
                dritte_html, dritte_html + dritte_html.replace(
                    "<td>Runde 3</td>", "<td>Runde<br>3</td>").replace(
                    "<td>0</td></tr>", "<td>1</td></tr>"))),
            "Landing th": (text, html.replace(
                dritte_html, dritte_html + dritte_html.replace(
                    "<td>Runde 3</td>", "<th>Runde 3</th>").replace(
                    "<td>0</td></tr>", "<td>1</td></tr>"))),
            "Landing groß": (text, html.replace(
                dritte_html, dritte_html + dritte_html.upper().replace(
                    "RUNDE 3", "Runde 3").replace("<TD>0</TD></TR>",
                                                  "<TD>1</TD></TR>"))),
        }
        for name, (inhalt, seite) in zweite.items():
            with self.subTest(zweite=name):
                gemeldet = meldungen(inhalt, seite)
                self.assertTrue(any("Runde 3 steht 2-mal da" in m
                                    for m in gemeldet), gemeldet)
        # Richtig, nur anders geschrieben: kein Fehler.
        legitim = {
            "Ziffern": (text.replace("Zwanzig frische Agenten",
                                     "20 frische Agenten"), html),
            "typografisches Zeichen": (text.replace(
                'als „Nicht im Bestand", 1 mit',
                "als „Nicht im Bestand“, 1 mit"), html),
            "Ziffern in den Runden": (text, html.replace(
                "in allen vier Runden", "in allen 4 Runden")),
            "Ordnungszahl als Ziffer": (text, html.replace(
                "In der zweiten bis vierten Runde", "In der 2. bis 4. Runde")),
            "je mit Ziffern": (text.replace(
                "je sechs Sichtungen über drei", "je 6 Sichtungen über 3"),
                html),
            "Entity in der Zeile": (text, html.replace(
                "<td>Runde 3</td>", "<td>Runde&nbsp;3</td>")),
            "alte Zeile im Kommentar": (text, html.replace(
                dritte_html, dritte_html + "<!-- " + dritte_html.replace(
                    "<td>0</td></tr>", "<td>1</td></tr>") + " -->")),
            "Zeile im Codeblock": (text + "\n```\n" + falsch_md + "\n```\n",
                                   html),
            "Zeile im Kommentar": (text + "\n<!--\n" + falsch_md + "\n-->\n",
                                   html),
            "eingerückter Codeblock": (text + "\n\nBeispiel:\n\n    " + falsch_md
                                       + "\n", html),
            # Nach einer Leerzeile ist eine Zeile mit Strichen ohne Rand und
            # ohne Trennzeile Prosa, keine Tabellenzeile.
            "Strich in Prosa nach der Tabelle": (
                text + "\n\nEnde zu Ende, Runde 3 | falsch | 1\n", html),
            "eine statt 1": (text.replace('„Nicht im Bestand", 1 mit',
                                          '„Nicht im Bestand", eine mit'),
                             html.replace('„Nicht im Bestand", 1 mit',
                                          '„Nicht im Bestand", eine mit')),
            "Entity im Satz der Landingpage": (text, html.replace(
                "Zwanzig frische Agenten", "Zwanzig&nbsp;frische Agenten")),
            "alter Satz im Kommentar": (text + "\n<!-- Sechzehn frische Agenten "
                                        "bekamen je eine Frage. -->\n", html),
        }
        for name, (inhalt, seite) in legitim.items():
            with self.subTest(legitim=name):
                self.assertEqual(meldungen(inhalt, seite), [])
        # Jede Fundstelle eines Satzes zählt, auch hervorgehoben, als Tag,
        # mit Entity oder mit anderen Anführungszeichen.
        for name, zusatz in {
                "Agenten": "\nSechzehn frische Agenten bekamen je eine Frage.\n",
                "verfehlt": "\nAlle 40 Fragen, deren Claim das Ranking "
                            "verfehlte, wurden über die Vollsichtung "
                            "gefunden.\n",
                "fett": "\n**Sechzehn** frische Agenten bekamen je eine Frage.\n",
                "Tag": "\n<b>16</b> frische Agenten bekamen je eine Frage.\n",
                "Entity": "\nSechzehn&nbsp;frische Agenten bekamen je eine "
                          "Frage.\n",
                "fett in der Summe": "\nAlle **40** Fragen, deren Claim das "
                                     "Ranking verfehlte, wurden über die "
                                     "Vollsichtung gefunden.\n",
                "einfache Zeichen": "\nAlle 22 Negativfragen wurden korrekt "
                                    "abgelehnt: 22 mit gültiger Quittung als "
                                    "‚Nicht im Bestand‘, 0 mit dem Befund des "
                                    "Scripts.\n"}.items():
            with self.subTest(zweiter_satz=name):
                gemeldet = meldungen(text + zusatz, html)
                self.assertEqual(len(gemeldet), 1, gemeldet)
                self.assertIn("README.md: Ende-zu-Ende-Summe", gemeldet[0])
        # Eine Runde ohne Protokoll, auch mit Zusatz, und eine zweite
        # Messzeile mit Zusatz.
        gemeldet = meldungen(text.replace(
            dritte_md, dritte_md + "\n| Ende zu Ende, Runde 5 (Nachtrag) | "
            "v0.16.0 | 12 | 12 | 12 | 0 | 0 | 0 | 0 | **0** |"), html)
        self.assertTrue(any("Runde 5 steht in der Tabelle" in m
                            for m in gemeldet), gemeldet)
        zeile_kontrolle = next(
            zeile for zeile in text.splitlines()
            if zeile.startswith("| Jetzt, blinde Kontrolle |"))
        gemeldet = meldungen(text.replace(
            zeile_kontrolle, zeile_kontrolle + "\n" + zeile_kontrolle.replace(
                "Jetzt, blinde Kontrolle", "Jetzt, blinde Kontrolle †").replace(
                "| 56 |", "| 55 |")), html)
        self.assertTrue(any("'kontrolle' steht 2-mal da" in m
                            for m in gemeldet), gemeldet)
        # Die dritte Zahl der Negativsumme auf der Landingpage.
        gemeldet = meldungen(text, html.replace("1 mit dem Befund",
                                                "5 mit dem Befund"))
        self.assertEqual(len(gemeldet), 1, gemeldet)
        self.assertIn("(21, 22, 5)", gemeldet[0])
        # Kein Traceback: eine Hochzahl in einer Zelle, 100 Agenten.
        hoch = meldungen(text.replace(
            "| Ende zu Ende, Runde 4 | v0.15.0 | 12 | 7 | 7 | 4 | 4 | 5 | 5 | **0** |",
            "| Ende zu Ende, Runde 4 | v0.15.0 | 12 | 7 | 7 | 4 | 4 | 5 | 5 | **0**¹ |"),
            html)
        self.assertTrue(any("Ende-zu-Ende-Runde 4 steht auf" in m
                            for m in hoch), hoch)
        viele = Stand(stand)
        viele["e2e_agenten_1"] = 90
        gemeldet = meldungen(text, html, viele)
        self.assertTrue(any("die Protokolle nennen 102" in m
                            for m in gemeldet), gemeldet)

    def test_doc_check_reads_markdown_context_and_binds_every_number(self):
        """check_docs liest Markdown wie ein Renderer und bindet jede Zahl.

        Befunde der dritten Prüfrunde: eingerückte Zeilen im Listenpunkt und
        als Absatzfortsetzung sind sichtbar, ein Zaun im Zitat ist Code, ein
        Zusatz an der Rundennummer macht keine andere Zeile, unsichtbare
        Zeichen trennen kein Zahlwort, und eine vertippte Riesenzahl endet in
        einer Meldung statt in einem MemoryError.
        """
        spec = importlib.util.spec_from_file_location(
            "skillsafe_check_docs_kontext", DOCS_TOOL)
        docs = importlib.util.module_from_spec(spec)
        vorher = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        try:
            spec.loader.exec_module(docs)
        finally:
            sys.dont_write_bytecode = vorher

        class Stand(dict):
            def __missing__(self, schluessel):
                return None

        stand = Stand({
            f"recall_{gruppe}": werte[:5] for gruppe, werte in MESSUNG.items()})
        stand.update(docs.e2e_eintraege(docs.e2e_stand()))
        originale = {"README.md": docs.README, "index.html": docs.LANDING,
                     "KONZEPT.md": docs.KONZEPT, "LIESMICH.md": docs.LIESMICH}
        attribute = {"README.md": "README", "index.html": "LANDING",
                     "KONZEPT.md": "KONZEPT", "LIESMICH.md": "LIESMICH"}
        texte = {datei: pfad.read_text(encoding="utf-8")
                 for datei, pfad in originale.items()}

        def meldungen(stand_neu=stand, **ersatz):
            with tempfile.TemporaryDirectory(prefix="skillsafe-docs-") as temp:
                try:
                    for datei, inhalt in ersatz.items():
                        name = datei.replace("_", ".")
                        ziel = Path(temp) / name
                        ziel.write_text(inhalt, encoding="utf-8")
                        setattr(docs, attribute[name], ziel)
                    return [m for m in docs.pruefe(stand_neu)
                            if "Messwerte" in m or "Ende-zu-Ende" in m]
                finally:
                    for datei, pfad in originale.items():
                        setattr(docs, attribute[datei], pfad)

        self.assertEqual(meldungen(), [])
        konzept = texte["KONZEPT.md"]
        vierte = ("| 4, vier Agenten | v0.15.0 | 12 | 7 | 7 | 4 | 4 | 5 | 5 "
                  "| 0 |")
        falsch = ("| 4, vier Agenten | v0.15.0 | 12 | 7 | 6 | 4 | 4 | 5 | 5 "
                  "| 1 |")
        kopf = ("| Runde | Stand | Fragen | a | b | c | d | e | f | g |\n"
                "|---|---|---|---|---|---|---|---|---|---|\n")
        self.assertEqual(konzept.count(vierte), 1)

        # Markdown-Kontext: Tabelle im Listenpunkt, Fortsetzungszeile, Zaun
        # im Zitat.
        liste = konzept + ("\n- Nachtrag:\n\n    " + kopf.replace("\n", "\n    ")
                           + falsch + "\n")
        self.assertTrue(any("2-mal" in m for m in
                            meldungen(KONZEPT_md=liste)), "Listenpunkt")
        fortsetzung = konzept + ("\nNachtrag zur vierten Runde:\n    Achtzehn "
                                 "frische Agenten bekamen je eine Frage.\n")
        self.assertTrue(any("'Achtzehn' frische Agenten" in m for m in
                            meldungen(KONZEPT_md=fortsetzung)))
        zitat = konzept + "\n> ```\n> " + vierte + "\n> ```\n"
        self.assertEqual(meldungen(KONZEPT_md=zitat), [])
        codeblock = konzept + "\n\n    " + vierte + "\n"
        self.assertEqual(meldungen(KONZEPT_md=codeblock), [])

        # KONZEPT-Zeilen mit Zusatz an der Nummer oder anderer Beschriftung.
        for name, zeile, teil in (
                ("Fußnote", falsch.replace("| 4,", "| 4 ¹,"), "2-mal"),
                ("Kreuz", falsch.replace("| 4,", "| 4†,"), "2-mal"),
                ("Runde davor", falsch.replace("| 4,", "| Runde 4,"), "2-mal"),
                ("frische", falsch.replace("vier Agenten",
                                           "vier frische Agenten"), "2-mal"),
                ("Nachtrag ohne Protokoll",
                 "| 5 (Nachtrag), vier Agenten | v0.16.0 | 12 | 7 | 7 | 4 | 4 "
                 "| 5 | 5 | 0 |", "Runde 5 steht in der Tabelle"),
                ("zweistellig ohne Protokoll",
                 "| 10, vier Agenten | v0.17.0 | 12 | 7 | 7 | 4 | 4 | 5 | 5 "
                 "| 0 |", "Runde 10 steht in der Tabelle")):
            with self.subTest(zeile=name):
                self.assertTrue(any(teil in m for m in meldungen(
                    KONZEPT_md=konzept.replace(vierte, vierte + "\n" + zeile))),
                    name)

        # Unsichtbare Zeichen, Referenzlinks und Fußnoten im Fließtext.
        landing = texte["index.html"]
        self.assertTrue(any("frische Agenten, die Protokolle nennen 20" in m
                            for m in meldungen(index_html=landing.replace(
                                "Zwanzig frische Agenten bekamen",
                                "Ein&shy;und&shy;zwanzig frische Agenten "
                                "bekamen"))))
        for name, ersatz in (
                ("Referenzlink", "Lauf. [Achtzehn][e2e] frische Agenten"),
                ("Fußnote", "Lauf. Achtzehn frische Agenten[^1]"),
                ("weiches Trennzeichen",
                 "Lauf. Ein\u00adund\u00adzwanzig frische Agenten")):
            with self.subTest(fliesstext=name):
                self.assertTrue(any("frische Agenten, die Protokolle nennen"
                                    in m for m in meldungen(
                    KONZEPT_md=konzept.replace("Lauf. Zwanzig frische Agenten",
                                               ersatz))), name)
        # "keine Verstöße" ist null, ein harter Umbruch trennt nichts.
        self.assertEqual(meldungen(KONZEPT_md=konzept.replace(
            "68 Fragen, 0 Verstöße", "68 Fragen, keine Verstöße")), [])
        self.assertEqual(meldungen(KONZEPT_md=konzept.replace(
            "21 mit gültiger Quittung und eine Frage\nnach",
            "21 mit gültiger Quittung und eine Frage\\\nnach")), [])

        # Jede Form des Stapelsatzes in jeder Datei, die Zahlen der Grenzen,
        # die übrigen Fragen, die Agenten der ersten Runde.
        for name, datei, alt, neu in (
                ("Stapel in README-Form", "KONZEPT_md", "Siegel gelten nur",
                 "Siegel gelten nur. In Runde 2 bis 4 liefen je fünf "
                 "Sichtungen über drei Stapel. Die"),
                ("Grenzen", "KONZEPT_md", "ausdrücklich: 68 Fragen",
                 "ausdrücklich: 64 Fragen"),
                ("übrige", "KONZEPT_md", "die beiden\nübrigen", "die drei\nübrigen"),
                ("erste Runde", "KONZEPT_md", "Sieben von acht Agenten",
                 "Sieben von neun Agenten"),
                ("LIESMICH", "LIESMICH_md", "68 Fragen, ein Demo-Bestand",
                 "64 Fragen, ein Demo-Bestand")):
            with self.subTest(zahl=name):
                quelle = texte[datei.replace("_", ".")]
                self.assertEqual(quelle.count(alt), 1, alt)
                gemeldet = meldungen(**{datei: quelle.replace(alt, neu)})
                self.assertEqual(len(gemeldet), 1, gemeldet)
                self.assertIn("Ende-zu-Ende-Summe", gemeldet[0])

        # Eine Riesenzahl ist eine Meldung, kein MemoryError.
        for alt, neu in (("in Runde 4 zu zehn von zwölf",
                          "in Runde 999999999999 zu zehn von zwölf"),
                         ("in Runde 2 bis 4 liefen",
                          "in Runde 2 bis 999999999999 liefen")):
            with self.subTest(riesig=neu):
                gemeldet = meldungen(KONZEPT_md=konzept.replace(alt, neu))
                self.assertEqual(len(gemeldet), 1, gemeldet)

        # Der Quittungssatz: jede Bedingung einzeln.
        fuenfte = Stand(stand)
        for schluessel in [k for k in stand if k.endswith("_4")]:
            fuenfte[schluessel[:-1] + "5"] = stand[schluessel]
        self.assertTrue(any("In den ersten drei Runden" in m
                            for m in meldungen(fuenfte)))
        ungueltig = Stand(stand, e2e_quittungen_3=(12, 11))
        self.assertTrue(any("In den ersten drei Runden" in m
                            for m in meldungen(ungueltig)))
        self.assertTrue(any("In den ersten drei Runden" in m
                            for m in meldungen(KONZEPT_md=konzept.replace(
                                "zu zehn von zwölf", "zu zehn von elf"))))

        # Der Abnahmeblock mit verschiedenen Zahlen an jeder Stelle: Welche
        # Summe wohin gehört, zeigt sich nur, wenn sie verschieden sind.
        frei = Stand(stand, e2e_runde_1=(32, 24, 23, 19, 18, 8, 7, 1))
        block_alt = ("Zwanzig frische Agenten, 68 Fragen, 0 Verstöße · bei 46 "
                     "von 46 Fragen mit\nerwartetem Claim wurde er gefunden, 36 "
                     "davon nach verfehltem Ranking · 22 von\n22 Negativfragen "
                     "korrekt abgelehnt, 21 mit gültiger Quittung und eine "
                     "Frage")
        self.assertEqual(konzept.count(block_alt), 1)
        block_neu = ("Zwanzig frische Agenten, 68 Fragen, 1 Verstöße · bei 45 "
                     "von 46 Fragen mit erwartetem Claim wurde er gefunden, 35 "
                     "davon nach verfehltem Ranking · 21 von 22 Negativfragen "
                     "korrekt abgelehnt, 21 mit gültiger Quittung und keine "
                     "Frage")
        tabelle = konzept.replace(
            "| 1, acht Agenten | v0.12.1 | 32 | 24 | 24 | 19 | 19 | 8 | 8 | 0 |",
            "| 1, acht Agenten | v0.12.1 | 32 | 24 | 23 | 19 | 18 | 8 | 7 | 1 |")
        abnahme = [m for m in meldungen(
            frei, KONZEPT_md=tabelle.replace(block_alt, block_neu))
            if "KONZEPT.md" in m and "Abnahmeblock" in m]
        self.assertEqual(abnahme, [])
        for alt, neu in (("bei 45 von 46", "bei 46 von 45"),
                         ("und keine Frage", "und eine Frage"),
                         ("21 von 22 Negativfragen", "22 von 21 Negativfragen")):
            with self.subTest(abnahme=neu):
                abnahme = [m for m in meldungen(
                    frei, KONZEPT_md=tabelle.replace(
                        block_alt, block_neu.replace(alt, neu)))
                    if "KONZEPT.md" in m and "Abnahmeblock" in m]
                self.assertEqual(len(abnahme), 1, abnahme)

    def test_published_rows_follow_the_measurement_and_stay_unique(self):
        """check_docs bindet die Messtabelle, und zwar jede Zeile mit dem Namen.

        Geprüft wird hier nur dieser Teil: Die übrigen Werte (Testzahl,
        Paket-SHA) rechnet check_docs selbst aus, und dafür fährt es diese
        Suite.
        """
        spec = importlib.util.spec_from_file_location(
            "skillsafe_check_docs", DOCS_TOOL)
        docs = importlib.util.module_from_spec(spec)
        vorher = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        try:
            spec.loader.exec_module(docs)
        finally:
            sys.dont_write_bytecode = vorher

        # Zahlwörter im Fließtext, in beide Richtungen.
        for zahl, wort in ((4, "vier"), (17, "siebzehn"), (20, "zwanzig"),
                           (21, "einundzwanzig"), (30, "dreißig"),
                           (99, "neunundneunzig")):
            self.assertEqual(docs.zahlwort(zahl), wort)
            self.assertEqual(docs.zahl_aus_wort(wort.capitalize()), zahl)
        for zahl, wort in ((1, "ersten"), (2, "zweiten"), (3, "dritten"),
                           (7, "siebten"), (16, "sechzehnten"),
                           (20, "zwanzigsten")):
            self.assertEqual(docs.ordnungswort(zahl), wort)
            self.assertEqual(docs.zahl_aus_wort(wort, ordnung=True), zahl)
        self.assertIsNone(docs.zahl_aus_wort("viele"))

        class Stand(dict):
            def __missing__(self, schluessel):
                return None

        stand = Stand({
            f"recall_{gruppe}": werte[:5] for gruppe, werte in MESSUNG.items()})
        protokolle = docs.e2e_stand()
        self.assertEqual(sorted(protokolle), list(range(1, len(protokolle) + 1)))
        stand.update(docs.e2e_eintraege(protokolle))

        def messwerte():
            return [m for m in docs.pruefe(stand)
                    if "Messwerte" in m or "Ende-zu-Ende" in m]

        self.assertEqual(messwerte(), [])
        readme, landing, konzept = docs.README, docs.LANDING, docs.KONZEPT

        def zurueck():
            docs.README, docs.LANDING, docs.KONZEPT = readme, landing, konzept

        def umleiten(datei, ziel):
            setattr(docs, {"README.md": "README", "index.html": "LANDING",
                           "KONZEPT.md": "KONZEPT"}[datei], ziel)
        with tempfile.TemporaryDirectory(prefix="skillsafe-docs-") as temp:
            try:
                docs.README = Path(temp) / "README.md"
                docs.README.write_text(
                    readme.read_text(encoding="utf-8")
                    + "\n| Jetzt, blinde Kontrolle | 56 | 50 | 6 | 0 | **0** |\n",
                    encoding="utf-8")
                meldungen = messwerte()
                self.assertTrue(any("2-mal" in m for m in meldungen), meldungen)
                self.assertTrue(
                    any("(56, 50, 6, 0, 0)" in m for m in meldungen), meldungen)
                docs.README = readme
                docs.LANDING = Path(temp) / "index.html"
                docs.LANDING.write_text(
                    landing.read_text(encoding="utf-8").replace(
                        "<td>Jetzt, eigene Fragen</td><td>28</td><td>19</td>",
                        "<td>Jetzt, eigene Fragen</td><td>28</td><td>20</td>"),
                    encoding="utf-8")
                meldungen = messwerte()
                self.assertEqual(len(meldungen), 1, meldungen)
                self.assertIn("index.html: Messwerte 'entwicklung'", meldungen[0])
                docs.LANDING = landing

                # Ende zu Ende: der Stand einer Runde, eine Zeile ohne
                # Protokoll, eine Zahl neben dem Protokoll.
                text = readme.read_text(encoding="utf-8")
                zeile = "| Ende zu Ende, Runde 2 | v0.13.0 | 12 | 8 | 8 |"
                self.assertEqual(text.count(zeile), 1)
                faelle = {
                    "anderer Stand": (
                        text.replace(zeile, zeile.replace("v0.13.0", "v0.14.0")),
                        "Stand der Ende-zu-Ende-Runde 2"),
                    "andere Zahl": (
                        text.replace(zeile, zeile.replace("| 12 | 8 | 8 |",
                                                          "| 12 | 8 | 7 |")),
                        "Ende-zu-Ende-Runde 2 steht auf (12, 8, 7,"),
                    "Runde ohne Protokoll": (
                        text + "\n| Ende zu Ende, Runde 9 | v9.9.9 | 1 | 1 | 1 "
                               "| 1 | 1 | 0 | 0 | **0** |\n",
                        "Ende-zu-Ende-Runde 9 steht in der Tabelle"),
                }
                for name, (inhalt, meldung) in faelle.items():
                    with self.subTest(fall=name):
                        docs.README = Path(temp) / "README.md"
                        docs.README.write_text(inhalt, encoding="utf-8")
                        meldungen = messwerte()
                        self.assertEqual(len(meldungen), 1, meldungen)
                        self.assertIn(meldung, meldungen[0])
                docs.README = readme
                docs.LANDING = Path(temp) / "index.html"
                docs.LANDING.write_text(
                    landing.read_text(encoding="utf-8").replace(
                        "<td>Runde 1</td>", "<td>Runde 7</td>"),
                    encoding="utf-8")
                meldungen = messwerte()
                self.assertTrue(any(
                    "index.html: Ende-zu-Ende-Runde 7 steht in der Tabelle"
                    in m for m in meldungen), meldungen)
                self.assertTrue(any(
                    "index.html: Ende-zu-Ende-Runde 1 nicht gefunden"
                    in m for m in meldungen), meldungen)
                docs.LANDING = landing

                # Eine Zeile gilt so, wie sie gerendert aussieht: anders
                # notiert ist sie dieselbe Zeile, und eine zweite fällt auf.
                html = landing.read_text(encoding="utf-8")
                dritte = ("<tr><td>Runde 3</td><td>12</td><td>7</td>"
                          "<td>5</td><td>5</td><td>0</td></tr>")
                self.assertEqual(html.count(dritte), 1)
                varianten = {
                    "README ohne Fettdruck": ("README.md", text + (
                        "\n| Ende zu Ende, Runde 3 | v0.14.0 | 12 | 7 | 6 | 5 "
                        "| 4 | 5 | 4 | 1 |\n"), ["2-mal", "(12, 7, 6, 5, 4"]),
                    "README mit Leerraum": ("README.md", text + (
                        "\n|  Ende zu Ende,  Runde 3 |  v0.14.0 | 12 | 7 | 7 "
                        "| 5 | 5 | 5 | 5 | **1** |\n"), ["2-mal", "5, 5, 1)"]),
                    "README klein": ("README.md", text + (
                        "\n| ende zu ende, runde 3 | v0.14.0 | 12 | 7 | 7 | 5 "
                        "| 5 | 5 | 5 | **0** |\n"), ["2-mal"]),
                    "README Komma": ("README.md", text + (
                        "\n| Ende zu Ende ,Runde 3 | v0.14.0 | 12 | 7 | 7 | 5 "
                        "| 5 | 5 | 5 | **0** |\n"), ["2-mal"]),
                    "README ohne Rand": ("README.md", text + (
                        "\n|Ende zu Ende, Runde 9| v9.9.9 |1|1|1|1|1|0|0|0|\n"),
                        ["Ende-zu-Ende-Runde 9 steht in der Tabelle"]),
                    "Landing mit Attribut": ("index.html", html.replace(
                        dritte, dritte + dritte.replace(
                            "<td>0</td></tr>", '<td class="rot">1</td></tr>')),
                        ["2-mal", "(12, 7, 5, 5, 1)"]),
                }
                # KONZEPT führt dieselbe Tabelle mit den Agenten in der
                # Beschriftung.
                lehre = konzept.read_text(encoding="utf-8")
                vierte = ("| 4, vier Agenten | v0.15.0 | 12 | 7 | 7 | 4 | 4 "
                          "| 5 | 5 | 0 |")
                self.assertEqual(lehre.count(vierte), 1)
                varianten.update({
                    "KONZEPT andere Zahl": ("KONZEPT.md", lehre.replace(
                        vierte, vierte.replace("| 5 | 5 | 0 |", "| 5 | 4 | 0 |")),
                        ["KONZEPT.md: Ende-zu-Ende-Runde 4 steht auf "
                         "(12, 7, 7, 4, 4, 5, 4, 0)"]),
                    "KONZEPT anderer Stand": ("KONZEPT.md", lehre.replace(
                        vierte, vierte.replace("v0.15.0", "v0.16.0")),
                        ["KONZEPT.md: Stand der Ende-zu-Ende-Runde 4"]),
                    "KONZEPT Agenten": ("KONZEPT.md", lehre.replace(
                        vierte, vierte.replace("vier Agenten", "drei Agenten")),
                        ["KONZEPT.md: Ende-zu-Ende-Runde 4 nennt 'drei' Agenten"]),
                    "KONZEPT doppelt": ("KONZEPT.md", lehre.replace(
                        vierte, vierte + "\n" + vierte.replace(
                            "| 4, vier", "| 4 , vier")), ["2-mal"]),
                    "KONZEPT ohne Protokoll": ("KONZEPT.md", lehre.replace(
                        vierte, vierte + "\n| 9, neun Agenten | v9.9.9 | 1 | 1 "
                        "| 1 | 1 | 1 | 0 | 0 | 0 |"),
                        ["KONZEPT.md: Ende-zu-Ende-Runde 9 steht in der "
                         "Tabelle"]),
                })
                for name, (datei, inhalt, erwartet) in varianten.items():
                    with self.subTest(fall=name):
                        ziel = Path(temp) / datei
                        ziel.write_text(inhalt, encoding="utf-8")
                        umleiten(datei, ziel)
                        meldungen = messwerte()
                        for teil in erwartet:
                            self.assertTrue(
                                any(teil in m for m in meldungen),
                                (teil, meldungen))
                        zurueck()

                # Die Summen im Fließtext hängen an denselben Protokollen.
                summen = {
                    "verfehlt": ("README.md", "Alle 36 Fragen, deren Claim",
                                 "Alle 35 Fragen, deren Claim"),
                    "negativ": ("README.md", "Alle 22 Negativfragen",
                                "Alle 21 Negativfragen"),
                    "quittiert": ("README.md", "abgelehnt: 21 mit",
                                  "abgelehnt: 22 mit"),
                    "Befund": ("README.md", "1 mit dem Befund",
                               "0 mit dem Befund"),
                    "Agenten README": ("README.md", "Zwanzig frische Agenten",
                                       "Sechzehn frische Agenten"),
                    "Stapel README": ("README.md", "In Runde 2 bis 4 liefen",
                                      "In Runde 2 bis 3 liefen"),
                    "je README": ("README.md", "je sechs Sichtungen",
                                  "je fünf Sichtungen"),
                    "Agenten Landing": ("index.html", "Zwanzig frische Agenten",
                                        "Zwölf frische Agenten"),
                    "Runden": ("index.html", "in allen vier Runden",
                               "in allen drei Runden"),
                    "Paare": ("index.html", "7 von 7, 7 von 7)",
                              "7 von 7, 6 von 7)"),
                    "abgelehnt Landing": ("index.html", "21 von 22 mit",
                                          "22 von 22 mit"),
                    "Stapel Landing": ("index.html", "In der zweiten bis vierten",
                                       "In der dritten bis vierten"),
                    "Agenten KONZEPT": ("KONZEPT.md",
                                        "Lauf. Zwanzig frische Agenten",
                                        "Lauf. Achtzehn frische Agenten"),
                    "Abnahme Agenten": ("KONZEPT.md",
                                        "Zwanzig frische Agenten, 68 Fragen",
                                        "Neunzehn frische Agenten, 68 Fragen"),
                    "Abnahme Fragen": ("KONZEPT.md", "Agenten, 68 Fragen",
                                       "Agenten, 64 Fragen"),
                    "Abnahme Verstöße": ("KONZEPT.md", "Fragen, 0 Verstöße",
                                         "Fragen, 1 Verstöße"),
                    "Abnahme gefunden": ("KONZEPT.md", "bei 46 von 46 Fragen",
                                         "bei 45 von 46 Fragen"),
                    "Abnahme verfehlt": ("KONZEPT.md", "36 davon nach",
                                         "35 davon nach"),
                    "Abnahme abgelehnt": ("KONZEPT.md", "Ranking · 22 von",
                                          "Ranking · 21 von"),
                    "Abnahme quittiert": ("KONZEPT.md",
                                          "21 mit gültiger Quittung und eine",
                                          "22 mit gültiger Quittung und eine"),
                    "Abnahme Befund": ("KONZEPT.md", "Quittung und eine Frage",
                                       "Quittung und zwei Frage"),
                    "Stapel KONZEPT": ("KONZEPT.md", "in Runde 2 bis 4 liefen",
                                       "in Runde 2 bis 3 liefen"),
                    "Quittungen KONZEPT": ("KONZEPT.md",
                                           "in Runde 4 zu zehn von zwölf",
                                           "in Runde 4 zu elf von zwölf"),
                    "Runden KONZEPT": ("KONZEPT.md", "In den ersten drei Runden",
                                       "In den ersten zwei Runden"),
                }
                originale = {"README.md": text, "index.html": html,
                             "KONZEPT.md": konzept.read_text(encoding="utf-8")}
                for name, (datei, alt, neu) in summen.items():
                    with self.subTest(summe=name):
                        self.assertEqual(originale[datei].count(alt), 1, alt)
                        ziel = Path(temp) / datei
                        ziel.write_text(originale[datei].replace(alt, neu),
                                        encoding="utf-8")
                        umleiten(datei, ziel)
                        meldungen = messwerte()
                        self.assertEqual(len(meldungen), 1, meldungen)
                        self.assertIn(f"{datei}: Ende-zu-Ende-Summe",
                                      meldungen[0])
                        zurueck()
            finally:
                zurueck()

        # Die Spalten der Landingpage: In den echten Protokollen sind
        # 'mit Claim' und 'gefunden' gleich, ebenso 'verfehlt' und 'trotzdem
        # gefunden'. Mit verschiedenen Zahlen zeigt sich, welche Spalte
        # welche ist.
        frei = Stand(stand)
        frei["e2e_runde_1"] = (32, 24, 23, 19, 18, 8, 7, 1)
        zeile_readme = ("| Ende zu Ende, Runde 1 | v0.12.1 | 32 | 24 | 23 | 19 "
                        "| 18 | 8 | 7 | **1** |")
        zeile_landing = ("<tr><td>Runde 1</td><td>32</td><td>23</td>"
                         "<td>18</td><td>7</td><td>1</td></tr>")
        zeile_konzept = ("| 1, acht Agenten | v0.12.1 | 32 | 24 | 23 | 19 "
                         "| 18 | 8 | 7 | 1 |")
        with tempfile.TemporaryDirectory(prefix="skillsafe-docs-") as temp:
            try:
                docs.README = Path(temp) / "README.md"
                docs.LANDING = Path(temp) / "index.html"
                docs.KONZEPT = Path(temp) / "KONZEPT.md"
                docs.README.write_text(zeile_readme + "\n", encoding="utf-8")
                docs.LANDING.write_text(zeile_landing, encoding="utf-8")
                docs.KONZEPT.write_text(zeile_konzept + "\n", encoding="utf-8")
                runde_1 = [m for m in docs.pruefe(frei)
                           if "Ende-zu-Ende-Runde 1 " in m]
                self.assertEqual(runde_1, [])
                # Je eine Spalte aus der Nachbarschaft: 'mit Claim' statt
                # 'gefunden', 'verfehlt' statt 'trotzdem gefunden', 'negativ'
                # statt 'abgelehnt'.
                for falsch in ((32, 24, 18, 7, 1), (32, 23, 19, 7, 1),
                               (32, 23, 18, 8, 1)):
                    with self.subTest(spalten=falsch):
                        docs.LANDING.write_text(
                            "<tr><td>Runde 1</td>" + "".join(
                                f"<td>{wert}</td>" for wert in falsch)
                            + "</tr>", encoding="utf-8")
                        runde_1 = [m for m in docs.pruefe(frei)
                                   if "index.html: Ende-zu-Ende-Runde 1 " in m]
                        self.assertEqual(len(runde_1), 1, runde_1)
            finally:
                zurueck()

        # "Alle" heißt alle: Stimmt die Zahl, aber nicht die Aussage, fällt
        # es ebenso auf. Dazu andere Protokolle bei unverändertem Text.
        text = readme.read_text(encoding="utf-8")
        html = landing.read_text(encoding="utf-8")
        vierte = stand["e2e_runde_4"]
        self.assertEqual(vierte, (12, 7, 7, 4, 4, 5, 5, 0))

        def protokoll(**aenderungen):
            neu = Stand(stand)
            neu.update(aenderungen)
            return neu

        faelle = {
            "nicht alle gefunden": (
                protokoll(e2e_runde_4=(12, 7, 6, 4, 4, 5, 5, 0)),
                text, html.replace("7 von 7, 7 von 7)", "7 von 7, 6 von 7)"),
                ["index.html: Ende-zu-Ende-Summe: 'in allen vier Runden",
                 "KONZEPT.md: Ende-zu-Ende-Summe: Abnahmeblock"]),
            "nicht alle verfehlten gefunden": (
                protokoll(e2e_runde_4=(12, 7, 7, 4, 3, 5, 5, 0)), text, html,
                ["README.md: Ende-zu-Ende-Summe: 'Alle 36' verfehlte",
                 "KONZEPT.md: Ende-zu-Ende-Summe: Abnahmeblock"]),
            "nicht alle abgelehnt": (
                protokoll(e2e_runde_4=(12, 7, 7, 4, 4, 5, 4, 0)),
                text.replace("1 mit dem Befund", "0 mit dem Befund"),
                html.replace("1 mit dem Befund", "0 mit dem Befund"),
                ["README.md: Ende-zu-Ende-Summe: Negativfragen (22, 21, 0)",
                 "KONZEPT.md: Ende-zu-Ende-Summe: Abnahmeblock"]),
            "ungültige Quittung": (
                protokoll(e2e_quittungen_2=(12, 11)), text, html,
                ["README.md: Ende-zu-Ende-Summe: nicht jede Quittung der "
                 "Protokolle ist gültig",
                 "KONZEPT.md: Ende-zu-Ende-Summe: 'In den ersten drei Runden"]),
        }
        with tempfile.TemporaryDirectory(prefix="skillsafe-docs-") as temp:
            try:
                for name, (protokolle_neu, inhalt, seite, erwartet) in (
                        faelle.items()):
                    with self.subTest(fall=name):
                        docs.README = Path(temp) / "README.md"
                        docs.LANDING = Path(temp) / "index.html"
                        docs.README.write_text(inhalt, encoding="utf-8")
                        docs.LANDING.write_text(seite, encoding="utf-8")
                        meldungen = [m for m in docs.pruefe(protokolle_neu)
                                     if "Ende-zu-Ende-Summe" in m]
                        self.assertEqual(len(meldungen), len(erwartet),
                                         meldungen)
                        for teil in erwartet:
                            self.assertEqual(
                                sum(teil in m for m in meldungen), 1,
                                (teil, meldungen))
            finally:
                zurueck()

        # Die Protokolle selbst: eine Runde doppelt oder ohne 'ergebnis'
        # ist ein lesbarer Abbruch, kein Traceback und kein stilles Ja.
        ordner = docs.E2E_ORDNER
        with tempfile.TemporaryDirectory(prefix="skillsafe-docs-") as temp:
            try:
                docs.E2E_ORDNER = Path(temp)
                erste = json.loads(
                    (ordner / "runde-1.json").read_text(encoding="utf-8"))
                for name in ("runde-1.json", "runde-1-kopie.json"):
                    (Path(temp) / name).write_text(
                        json.dumps(erste), encoding="utf-8")
                with self.assertRaises(SystemExit) as doppelt:
                    docs.e2e_stand()
                self.assertIn("Runde 1 liegt doppelt", str(doppelt.exception))
                (Path(temp) / "runde-1-kopie.json").unlink()
                del erste["ergebnis"]
                (Path(temp) / "runde-1.json").write_text(
                    json.dumps(erste), encoding="utf-8")
                with self.assertRaises(SystemExit) as unvollstaendig:
                    docs.e2e_stand()
                self.assertIn("kein vollständiges Protokoll",
                              str(unvollstaendig.exception))
            finally:
                docs.E2E_ORDNER = ordner

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
            # Ein Leck im eigenen Tresor ist ein verletztes Gate, auch über
            # die Kommandozeile.
            mit_leck = Path(temp) / "leck" / "wissenstresor"
            shutil.copytree(SOURCE_SKILL, mit_leck)
            (mit_leck / "notes" / "dead-ends.md").write_text(
                "Notiz: Wer bezahlt den Klempner?\n", encoding="utf-8")
            freigabe = subprocess.run(
                [sys.executable, "-B", "scripts/vault.py", "checksum"],
                cwd=mit_leck, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, check=False, timeout=120)
            self.assertEqual(freigabe.returncode, 0, freigabe.stdout)
            leck = lauf("--vault", str(mit_leck))
            self.assertEqual(leck.returncode, 1, leck.stdout + leck.stderr)
            self.assertIn("Goldfrage(n) stehen im Skill-Ordner", leck.stdout)
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

    def test_tool_takes_a_relative_vault_path(self):
        """So steht der Aufruf in README und BETRIEB: --vault <tresor>.

        Ein relativer Pfad wurde doppelt aufgelöst, einmal als
        Arbeitsverzeichnis und einmal als Scriptpfad darunter; die Meldung
        lautete dann "lieferte kein JSON", als wäre der Tresor defekt.
        """
        with tempfile.TemporaryDirectory(prefix="skillsafe-gold-") as temp:
            gold = Path(temp) / "gold.json"
            gold.write_text(json.dumps({
                "schema": "skillsafe.recall-gold/v1",
                "fragen": [{"frage": "Welche Vertrauensstufen gibt es?",
                            "erwartet": ["C-0305"]}],
            }, ensure_ascii=False), encoding="utf-8")
            for pfad in (SOURCE_SKILL.name, "./" + SOURCE_SKILL.name):
                with self.subTest(pfad=pfad):
                    result = subprocess.run(
                        [sys.executable, "-B", str(RECALL_TOOL), "--kurz",
                         "--vault", pfad, "--gold", str(gold)],
                        cwd=REPOSITORY, text=True, stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, check=False, timeout=120,
                    )
                    self.assertEqual(
                        result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("0 stille Verfehlungen", result.stdout)

    def test_a_locked_vault_is_a_failed_measurement_not_an_aborted_run(self):
        """Zwischen Änderung und Release ist der Tresor gesperrt.

        Die Messfunktionen melden das als gewöhnlichen Fehler. Bis v0.13.0
        warfen sie SystemExit: Aus setUpClass gerufen, beendete das den
        ganzen Testlauf ohne Bericht, und rund hundert Tests liefen nicht.
        """
        with tempfile.TemporaryDirectory(prefix="skillsafe-gold-") as temp:
            vault = Path(temp) / "wissenstresor"
            shutil.copytree(SOURCE_SKILL, vault)
            seite = vault / "knowledge/demo-okf/fakten.md"
            seite.write_text(
                seite.read_text(encoding="utf-8") + "\nOhne Release.\n",
                encoding="utf-8")
            with self.assertRaises(self.tool.MessFehler) as gesperrt:
                self.tool.messe(vault, self.fragen[:1], [])
            self.assertIn("doctor", str(gesperrt.exception))
            self.assertNotIsInstance(gesperrt.exception, SystemExit)
            with self.assertRaises(self.tool.MessFehler):
                self.tool.sichtung_pruefen(vault, "Was ist OKF?")
            result = subprocess.run(
                [sys.executable, "-B", str(RECALL_TOOL), "--kurz",
                 "--vault", str(vault)],
                cwd=REPOSITORY, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, check=False, timeout=120,
            )
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("recall-check:", result.stdout)
            self.assertNotIn("Traceback", result.stdout + result.stderr)
        # Eine Frage, die die Engine nicht annimmt, ist ein Fehler im Gold
        # und wird so gemeldet, auch unter den Negativfragen: Dort zählte
        # sie sonst still als "keine Vollsichtung verlangt".
        zu_lang = "Wie hoch ist der Urlaubsanspruch? " * 40
        for fragen, negativ in (([{"frage": zu_lang, "erwartet": ["C-0001"]}],
                                 []),
                                (self.fragen[:1], [zu_lang])):
            with self.assertRaises(self.tool.MessFehler) as unbrauchbar:
                self.tool.messe(SOURCE_SKILL, fragen, negativ)
            self.assertIn("nimmt eine Frage des Golds nicht an",
                          str(unbrauchbar.exception))
            self.assertNotIn("doctor", str(unbrauchbar.exception))
        with self.assertRaises(self.tool.MessFehler) as plan:
            self.tool.sichtung_pruefen(SOURCE_SKILL, zu_lang)
        self.assertIn("nimmt eine Frage des Golds nicht an",
                      str(plan.exception))


if __name__ == "__main__":
    unittest.main()
