# Umsetzungsplan: OKF v0.2 in SkillSafe

Stand: 2026-07-28. Grundlage ist die vollständige `SPEC.md` aus
`GoogleCloudPlatform/knowledge-catalog` (Ordner `okf/`, v0.2 seit
2026-07-24, Apache-2.0) sowie eine Zeile-für-Zeile-Prüfung des eigenen
Bestands. Jede Zahl unten stammt aus einer ausgeführten Ausgabe, nicht aus
einer Schätzung. Die harten Kopplungen wurden in einer Kopie des Repos
nachgebaut und gegen die echte Testsuite gemessen.

Leitregel dieses Plans: **der Tresor bleibt ein Skill-basierter
Wissensspeicher.** Kein Server, keine Datenbank, keine Embeddings, kein
ausführbarer Fremdcode im Artefakt. Alles, was v0.2 anbietet, wird entweder
als Wissen aufgenommen, als optionales flaches Feld gelernt, beim Export
abgebildet, oder ausdrücklich und begründet abgelehnt. Nichts bleibt
unbehandelt.

---

## 1. Ist-Stand, gemessen

```
Profil oksv-lite/1.1 — 4 Seiten, 16 Claims, 3 Quellen, 3 Kanten
Begriffswelten: 1, Begriffe: 4, Medienrepräsentationen: 0
Status: aktiv=4
VERSION 0.6.1 · 28 manifestierte Dateien · 30 Paketeinträge · 43 Tests grün
doctor: 0 Fehler, 0 Warnungen, 0 Hinweise
```

Testverteilung: 32 in `test_vault_security.py`, 9 in
`test_vault_retrieval.py`, 2 in `test_packaged_vault.py`.

`dist/` ist per `.gitignore:18` ausgeschlossen und nie committet. Der
SHA-256 in `README.md:25-27` ist damit ein Reproduktionsversprechen, kein
Verweis auf ein eingechecktes Artefakt.

Diese Plandatei liegt im Repo-Root und damit außerhalb von `ROOT`
(`ROOT = wissenstresor/`). Der Manifest-Baumlauf sieht sie nie. Sie darf
niemals nach `wissenstresor/` wandern, sonst wird `doctor` rot.

---

## 2. Die Konsistenz-Grundregel

Der wichtigste operative Befund, gemessen und nicht vermutet:

> **`pytest` ist nach jeder Änderung unter `wissenstresor/` erst nach
> `checksum` oder `release` grün.**

`tests/test_packaged_vault.py` ruft `doctor`, und `doctor` wird bei jeder
neuen oder geänderten manifestierten Datei rot. Messung: eine einzige
angehängte Kommentarzeile in `vault.py` ergibt `2 failed, 41 passed` mit
`package: FEHLER — doctor fehlgeschlagen: 🔴 GEÄNDERT scripts/vault.py`.
Nach `python3 scripts/vault.py checksum` in derselben Kopie wieder
`43 passed`.

Daraus folgt die feste Schrittfolge für **jede** Änderung im Skill-Ordner:

```
1. ändern
2. python3 scripts/vault.py validate      (inhaltliches Gate)
3. python3 scripts/vault.py release <stufe>   ODER   checksum
4. python3 -m pytest tests -q             (jetzt erst aussagekräftig)
5. python3 scripts/vault.py doctor
6. python3 tools/build_skill_package.py   (aus dem Repo-Root)
7. Zahlen in README.md und index.html aus der echten Ausgabe nachziehen
8. committen: Inhalt + VERSION + MANIFEST.sha256 + INDEX.md + graph.json + log.md gemeinsam
```

Zwei Folgerungen, die in der naiven Reihenfolge falsch wären:

* Tests vor dem Release laufen zu lassen ist nicht „sicherer", es ist
  irreführend. Zwei Tests sind dann garantiert rot, ohne dass etwas
  kaputt ist.
* Manifestierte Dokumentation nach dem Release anzufassen macht
  `checksum --verify` sofort rot. `KONZEPT.md`, `SKILL.md`,
  `schema/profil.md`, `references/*.md` und `notes/dead-ends.md` liegen
  **im** Manifest (Zeilen 2, 5, 12, 13, 20). Sie gehören vor Schritt 3,
  nicht danach. `README.md`, `index.html` und diese Plandatei liegen
  außerhalb und dürfen danach.

Im Fenster zwischen Änderung und Release ist der Tresor bewusst
fail-closed. Gemessen direkt nach den Dateiänderungen von R2: `query`
liefert `state: invalid_vault` mit `["NEU knowledge/demo-okf/okf-v02.md",
"NEU sources/raw/S-0004__okf-spec-v02.md", "GEÄNDERT
knowledge/demo-okf/okf.md"]`, und `doctor` meldet 3 Fehler (INDEX-Drift,
Graph-Drift, Manifestabweichung), also rot mit Exit 1. Das ist richtig so.
In diesem Fenster nicht abfragen und nicht paketieren.

Ein fehlgeschlagener `release` hinterlässt keinen Rückstand: der
`finally`-Block gibt den Lock frei (`vault.py:2855-2861`). Liegen bleibt
`.vault-release.lock` ausschließlich bei `RollbackIncompleteError`
(`2848-2849`).

---

## 3. Reihenfolge

```
R1  0.6.1 → 0.6.2   patch   Parser fail-closed, Paket-Allowlist        ERLEDIGT
R2  0.6.2 → 0.7.0   minor   Bestand lernt v0.2 + gesamte Doku          ERLEDIGT
R3  0.7.0 → 0.8.0   minor   geprueft_von / geprueft_am, Profil oksv-lite/1.2 ERLEDIGT
R4  0.8.0 → 0.9.0   minor   export --okf
R5  später          minor   gueltig_bis + --asof, nur bei Anlass
```

R1 bis R2 sind ein zusammenhängendes Arbeitspaket. R3 und R4 sind
eigenständig und können beliebig lange warten, ohne dass der Bestand
falsch wird. R5 braucht einen echten Anlass.

R1 vor R2, weil die Parser-Härtung den Bestand nicht anfasst und geprüft
ist, dass sie nichts rot macht: alle vier Wissensseiten und alle drei
Pointer-Records haben ausschließlich `key: wert`- und `  - `-Zeilen im
Frontmatter. Wer die Härtung nach R2 legt, prüft sie gegen einen
Bestand, der sich gerade geändert hat.

---

## 4. R1 · Parser fail-closed und Paket-Allowlist (patch, 0.6.2) — ERLEDIGT

Umgesetzt am 2026-07-28. Ergebnis: `validate` und `doctor` grün, 48 Tests
bestanden (vorher 43), 28 manifestierte Dateien, 30 Paketeinträge,
Paket-SHA-256
`ac7c877baab9534f1d92ff6080c5c500f2ff0a98a406b441a7e0fc1d4189c15f`.
`query "Was ist OKF?"` liefert unverändert `candidates_found` mit C-0001 als
erster Evidenz.

Abweichung vom Entwurf: `.py` steht **nicht** pauschal in der Allowlist.
Erlaubt ist genau ein Script, `scripts/vault.py`, über die Konstante
`ENGINE_SCRIPT`. Ein zweites Script wie `references/attesters/revenue.py`
wird abgewiesen, obwohl es dieselbe Endung trägt. Das ist die eigentliche
AD-09-Fläche, und die pauschale Endungsfreigabe hätte sie offen gelassen.


### 4.1 Der Bug

`parse_frontmatter` (`vault.py:522-574`) kennt Skalar, Inline-Liste und
Bindestrich-Liste. Bei Blockform-Nesting schweigt er und zerstört die
Struktur:

| Eingabe | heutiges Ergebnis |
|---|---|
| `generated: { by: x, at: y }` | Skalar-String `"{ by: x, at: y }"` |
| `generated:` + `  by: x` + `  at: y` | `generated=[]`, **`by` und `at` werden Top-Level-Schlüssel** |
| `sources:` + `  - id: a` + `    resource: b` | `sources=['id: a']`, `resource` wird Top-Level |

Fall zwei ist stille Strukturkorruption. Aufgefangen wird sie heute nur
zufällig durch die Unbekannte-Felder-Prüfung (`vault.py:1149-1153`). Fällt
diese Prüfung je weg oder heißt ein Streuschlüssel wie ein erlaubtes Feld,
ist der Fehler unsichtbar.

### 4.2 Änderungen

* `vault.py:522-574`: jede eingerückte Zeile, die nicht mit `  - `
  beginnt, erzeugt einen Fehler „Einrückung außerhalb der
  Profil-Untermenge". Vorbild ist `parse_types:638-639`, das genau das
  schon tut.
* `tests/test_vault_security.py`: die drei Fälle aus der Tabelle als
  Negativtests.
* `schema/profil.md`: den Satz „Kein Nesting" um den Hinweis ergänzen,
  dass Nesting jetzt fail-closed abgelehnt und nicht mehr toleriert wird.
* `tools/build_skill_package.py`: Suffix-Allowlist. Die naive Liste
  bricht den Bau sofort, deshalb genau:
  `.md`, `.py`, `.json`, `.yaml`, `.sha256`, dazu die **acht**
  Suffixe aus `MEDIA_TYPES` (`vault.py:105-113`: `.png .jpg .jpeg .gif
  .webp .tif .tiff .pdf`), dazu die **zwei** endungslosen Dateien
  `LICENSE` **und** `VERSION`. `.svg` bleibt ausdrücklich draußen
  (`ACTIVE_MEDIA_SUFFIXES`, `vault.py:115`). Alles andere bricht den Bau
  fail-closed ab.
  Gemessene Inventur der 30 Paketdateien: 23× `.md`, 2× `.json`, 1×
  `.yaml`, 1× `.py`, 1× `.sha256`, `LICENSE`, `VERSION`. Wer `VERSION`
  vergisst, verwirft eine Pflichtdatei.
* Spiegelbildlich eine `validate`-Prüfung, die ausführbare oder unbekannte
  Dateitypen im Baum meldet, analog zu den Symlink-Prüfungen
  (`vault.py:1361-1366`).
* Je ein Negativtest in `test_vault_security.py` und
  `test_packaged_vault.py`.

### 4.3 Ablauf

```bash
cd wissenstresor
# 1. vault.py und schema/profil.md ändern, Tests ergänzen
python3 scripts/vault.py validate
python3 scripts/vault.py log note "Parser haertet Blockform-Nesting fail-closed; Paketbau mit Suffix-Allowlist"
python3 scripts/vault.py release patch          # 0.6.2
python3 -m pytest tests -q                      # jetzt erst aussagekräftig
python3 scripts/vault.py doctor
cd .. && python3 tools/build_skill_package.py
```

Danach `README.md:25-27` nachziehen. Die Testzahl steigt um die neuen
Negativtests, also nicht mehr 43. Zahl aus der letzten `pytest`-Zeile
übernehmen, Dateizahl aus `checksum --verify`, Paketeinträge aus der
`files:`-Zeile des Builders, Paket-SHA aus der Builder-Ausgabe.

---

## 5. R2 · Der Bestand lernt v0.2 (minor, 0.7.0) — ERLEDIGT

Umgesetzt am 2026-07-28. Die in der Simulation vorhergesagten Zielwerte sind
exakt eingetreten: **5 Seiten, 26 Claims, 4 Quellen, 4 Kanten, 9 Begriffe,
30 manifestierte Dateien, 32 Paketeinträge, Status aktiv=4 / veraltet=1.**
`validate`, `doctor` und `checksum --verify` grün, 48 Tests bestanden,
Paket-SHA-256
`47d1b5da3db7afa417e38e8a2576fd31d849c93a287a7b00385562dfe63726bf`.
Drei Läufe von `query "Was ist OKF?"` sind byteidentisch.

Alle zehn Zwangsbedingungen haben getragen. Zwei Beobachtungen aus der
Umsetzung:

* Der Supersessions-Effekt ist stärker als in der Simulation, weil
  `okf-v02.md` bewusst nur B-0001 aus der alten Begriffsmenge führt und
  damit `concept_base` 100 statt 190 erreicht. `query "Was ist OKF?"` liefert
  C-0001 mit 210 vor C-0301 mit 120, jeder Treffer der alten Seite mit
  Signal `page_status:veraltet`. Bei `query "LLM-Wiki-Muster"` steht C-0004
  der überholten Seite mit 330 vor C-0101 der eigentlich einschlägigen Seite
  mit 240. Beides ist in `references/antworten.md` als Regel hinterlegt.
* Die Fixture-Kollision (Z3) wurde durch Umstellung der Test-ID auf `B-0900`
  gelöst, mit Kommentar im Test. Damit ist die Fehlerklasse abgeräumt und
  nicht nur um fünf IDs verschoben.

Zusätzlich zum Plan korrigiert: `index.html` zeigte im `doctor`-Block eine
`validate`-Zeile, die der echte `doctor` nie ausgibt, weil er
`cmd_validate(still=True)` aufruft. Der Block ist jetzt in zwei Kommandos
mit je echter Ausgabe geteilt, und der einleitende Satz sagt, dass auch
Evidenz-Einträge gekürzt sind.

### 5.1 Zehn Zwangsbedingungen

Diese Liste ist der Kern des Plans. Jede Position wurde gemessen. Wer eine
verletzt, bekommt entweder einen roten Test oder eine stille Unwahrheit.

**Z1 · `definition_claim` erzwingt die `concepts`-Zeile der neuen Seite.**
`vault.py:1461-1473` prüft für jeden Begriff, ob sein `definition_claim`
auf einer Seite liegt, die den Begriff in `concepts` führt. Liegen
C-0301..C-0310 auf `okf-v02.md` und definieren B-0005..B-0009, dann **muss**
`okf-v02.md` alle fünf neuen IDs führen. Gemessen ohne sie: fünf rote
Fehler der Form „Definition C-0303 liegt auf einer Seite, die B-0005 nicht
in concepts führt", `validate` RC=1, damit auch `release` und `query`
blockiert. Die `concepts`-Zeile ist also keine freie Wahl.

**Z2 · Keine `broader: [B-0001]` bei den neuen Begriffen.**
Bei `query OKF` ist `direct=[B-0001]`, `expanded={B-0002:55 (broader),
B-0003:35 (related)}`. `okf.md` erreicht damit `concept_base` 190 und
C-0001 kommt auf 290. Sortiert wird nach `(-score, claim_id, page)`
(`vault.py:2061`). Trägt einer der neuen Begriffe `broader: [B-0001]`,
entsteht über die Umkehrung eine `narrower`-Kante mit Gewicht 55,
`okf-v02.md` steigt auf 345 und C-0301 wird `evidence[0]`. Gemessen:
`tests/test_vault_retrieval.py:154` und `tests/test_packaged_vault.py:128`
fallen. Bei Gleichstand 290 zu 290 gewinnt C-0001 über den
`claim_id`-Tiebreak, das hält. Also: `broader: []` bei allen fünf neuen
Begriffen, und `B-0001.broader` / `B-0001.related` nicht erweitern.

**Z3 · Die Test-Fixture belegt B-0005 selbst.**
`tests/test_vault_retrieval.py:223-238`
(`test_cross_world_alias_is_explicitly_ambiguous`) legt eine zweite Welt
BW-0002 an und darin einen Begriff mit fest verdrahteter `"id": "B-0005"`
(Zeile 232), Alias `OKF`, `definition_claim` C-0101, und hängt B-0005
zusätzlich in die `concepts` von `llm-wiki-muster.md` (Zeile 247).
Gemessen bei belegtem B-0005: `schema/begriffswelten.json.concepts[10].id:
Begriff-ID B-0005 ist doppelt`, danach `release: ABBRUCH`, danach
AssertionError. Ergebnis `1 failed, 42 passed`.

Lösung: die **Fixture** auf eine bewusst reservierte hohe ID umstellen,
`B-0900`, an beiden Stellen (232 und 247). Das räumt die Fehlerklasse
dauerhaft ab, statt sie um fünf IDs zu verschieben. Ein Kommentar im Test
hält fest, warum die ID hoch liegt.

**Z4 · Fünf Tabu-Tokens.**
`tests/test_vault_retrieval.py:179-195` stellt die Paraphrasenfrage
„Welche Adresse fungiert als dauerhafter Schlüssel einer Wissenseinheit?"
und erwartet `no_candidates` plus `exhaustive_review_required`. Die Sonde
lebt davon, dass keines ihrer Tokens im Bestand vorkommt. Wirksam sind
`adresse`, `fungiert`, `dauerhafter`, `schluessel`, `wissenseinheit`.

Gemessen kippt die Sonde an einem einzigen Claim, der das Wort Schlüssel
enthält (`C-0301 okf-v02.md 20 [token:schluessel]`), und ebenso an einem
**Begriffslabel**: mit `B-0008.preferred = "Wissenseinheit"` liefert die
Frage `candidates_found`, `concepts.matched=["B-0008"]`, `evidence[0] =
C-0302` mit Score 120.

Das Verbot gilt deshalb für: alle zehn Claim-Texte, Titel und `tags` von
`okf-v02.md`, **und** `preferred` wie `aliases` aller fünf neuen Begriffe.
Praktische Folge für die Formulierung: §4.1 heißt auf Deutsch nicht
„Pflichtschlüssel", sondern „Pflichtfeld" oder „Pflichtangabe". Für die
OKF-Identität „Dateipfad" und „Identität" verwenden, nicht „Adresse".

**Z5 · Der ROUTER-Eintrag ist test-blockierend, nicht kosmetisch.**
`doctor` erzeugt für jede nicht gelistete Seite zwei Warnungen
(`vault.py:2929-2933`), weil `ersetzt -> demo-okf/okf.md` eine ausgehende
und keine eingehende Relation ist. Die Ampel wird gelb, der Rückgabewert
bleibt 0, der Paketbau läuft durch. Aber
`tests/test_packaged_vault.py:32` prüft wörtlich
`assertIn("🟢 doctor:", …)`. Gemessen: ohne Router-Eintrag `3 failed, 40
passed`, mit Eintrag `2 failed, 41 passed` und `doctor` grün.

**Z6 · Zwei Zeilen in `okf.md` müssen byteidentisch bleiben.**
Zeile 11 `concepts: [B-0001, B-0002, B-0003]` ist Fixture-Anker in
`tests/test_vault_retrieval.py:320-323` und `:501-507`. Zeile 13
`  - formalisiert -> demo-okf/llm-wiki-muster.md` ist Anker in
`tests/test_vault_security.py:128-131` und `:138-142`, und `replace_text`
hat ein `assertIn` auf den Suchtext (`:60-65`), scheitert also laut.
Gemessen bei geänderter `concepts`-Zeile: **beide** Tests fallen, auch der
Rekursionslimit-Test, weil die 1100-Begriffe-Fixture `definition_claim
C-0001` behält und über Z1 dann 1096 Fehler entstehen.

R2 ändert an `okf.md` deshalb nur `status`, `version`, `stand`, den
Abschnitt „Kontext und Grenzen" sowie die Profilnennungen aus Z10. Die
neue `ersetzt`-Kante gehört ausschließlich auf `okf-v02.md`.

**Z7 · Die Registerzeile für S-0004 wird angehängt, nicht eingefügt.**
`tests/test_vault_security.py:119-124` ersetzt die **erste** Fundstelle von
`Nur Verweis/Paraphrase, kein Volltext` durch `TODO` und erwartet dann
„Rechte müssen". Heute ist das die S-0001-Zeile. S-0004 kommt als vierte
Datenzeile hinter S-0003.

Zum Rechtetext: `vault.py:1378-1380` vergleicht das **ganze** Feld nach
`strip().upper()` gegen die Verbotsmenge, nicht als Teilstring.
`Apache-2.0, Volltext erlaubt` läuft gemessen grün durch. Nur ein Feld,
das exakt `OFFEN`, `UNKLAR`, `TODO`, `UNGEKLÄRT` und so weiter ist, fällt
durch.

**Z8 · `cmd_source` mit dem nackten Dateinamen aufrufen.**
`vault.py:2694` bildet die Ablage als `sources/raw/{sid}__{p.name}`.
Gemessen: eine bereits `S-0004__okf-spec-v02.md` benannte Datei ergibt
`sources/raw/S-0004__S-0004__okf-spec-v02.md`. Also erst unter
`okf-spec-v02.md` registrieren, dann verschieben und umbenennen.

**Z9 · Die `SKILL.md`-Description hat 119 Zeichen Luft.**
`tools/build_skill_package.py:130` erlaubt 1 bis 1024 Zeichen, aktuell
sind 905 belegt. Jede Erweiterung der Trigger-Liste zeichenweise
gegenrechnen und den Paketbau probeweise laufen lassen, bevor releast
wird.

**Z10 · Die Profilnennung steckt in einem Claim-Text.**
`oksv-lite/1.1` steht an neun Stellen: `vault.py:3`, `vault.py:59`,
`schema/profil.md:1`, `schema/types.yaml:1`, `KONZEPT.md:1`,
`SKILL.md:3`, `index.html:236`, `knowledge/demo-okf/okf.md:26`
(Kurzfassung) und `knowledge/demo-okf/okf.md:33` (**Text von C-0005**).
`graph/graph.json:96` ist generiert.

Der Profilsprung kommt erst in R3, aber die Vorarbeit gehört nach R2:
`okf.md:26` und `:33` in R2 versionsneutral formulieren („ein strengeres
Profil oberhalb von OKF, hier oksv-lite"), solange die Seite ohnehin
angefasst wird. Danach zieht R3 den Profilsprung ohne Claim-Eingriff. Wer
das versäumt, muss in R3 einen Claim-Text ändern, um eine
Versionsnummer nachzuziehen.

### 5.2 Quelle S-0004 aufnehmen

Nächste freie ID ist S-0004 (`cmd_source` rechnet max+1,
`vault.py:2683-2685`).

Lizenz ist geprüft: Apache-2.0, sowohl `LICENSE.md` im Repo-Root als auch
`okf/LICENSE.md`. Volltext ist damit zulässig, mit Attribution. Volltext
ist hier der bessere Weg als ein Pointer-Record, weil alle Claims
Paragraphen-Fundstellen tragen und die Nummerierung nur innerhalb der
Version stabil ist.

Wichtig: die Datei selbst enthält **keine** Rechte- oder Herkunftsangabe.
Ein `grep` über `SPEC.md` nach `apache|licen[sc]e|copyright|github` liefert
null Zeilen. Der Attributionskopf muss also von Hand ergänzt werden, und
zwar **vor** dem Hashen, danach ist die Datei unveränderlich.

Attributionskopf, vier Zeilen: Titel, Herkunfts-URL, Commit oder
Abrufdatum, Lizenz. Dazu die Konvention, die C-Fundstellen auflösbar
macht:

```
Fundstellen-Konvention: Paragraphennummern (§) der Spezifikation v0.2
```

```bash
cd wissenstresor
cp <spec> sources/quarantine/okf-spec-v02.md
# Attributionskopf einfügen, Rechte und Trust klären, Injection-Sichtung
python3 scripts/vault.py source sources/quarantine/okf-spec-v02.md   # nackter Name, siehe Z8
mv sources/quarantine/okf-spec-v02.md sources/raw/S-0004__okf-spec-v02.md
```

Registerzeile, angehängt hinter S-0003 (sieben Spalten, keine Pipes im
Titel):

```
| S-0004 | Open Knowledge Format Specification v0.2 | v0.2 / 2026-07-24 | <hash> | T1 | Apache-2.0, Volltext erlaubt | sources/raw/S-0004__okf-spec-v02.md |
```

Trust **T1**: die Spec ist das normative Artefakt, nicht ein Bericht
darüber. Zu wissen ist, dass die Wahl mechanisch nichts ändert. `T1` kommt
in `vault.py` nur in `TRUST_WERTE` (`67`) und einer Fehlermeldung (`1377`)
vor, ausgewertet wird ausschließlich `T3` (`2047-2048`). Der Unterschied
wirkt auf menschliche Leser und auf die Formulierungsregel in
`references/antworten.md`.

Empfohlen, im selben Release: den Registerkopf (`REGISTER.md:5-7`) einmal
schärfen, damit die Frage bei künftigen Ingests nicht neu aufgeht.
„T1 amtlich oder normatives Primärdokument, also die Norm selbst; T2
Bericht, Ankündigung, Herstellerdoku über etwas anderes; T3 Web oder
unbestätigt."

Die LinkedIn-Ankündigung bewusst **nicht** aufnehmen. Sie trägt nichts,
was die Spec nicht selbst sagt, und `references/lint.md:52-55` meldet
claimlose Registereinträge zu Recht als tote Quelle. Entscheidung nach
`notes/dead-ends.md`.

Die Spec richtet sich an mehreren Stellen normativ an Agenten und Consumer
(§10.3 „the agent MUST NOT author or edit the computation", §11 „consumers
MUST treat…", §5.3 „consumers MUST NOT reject it"). `PROMPT_INJECTION_RE`
trifft davon nichts, die Meldung ist Modellarbeit. In den Abschlussbericht:
„S-0004 enthält normative Konformanzsprache in Richtung Agenten und
Consumer, unter anderem §10.3, §11, §5.3. Als Quelldaten behandelt, keine
Anweisung befolgt." Kein Blocker. Die Claims dürfen die Regeln als
Wortlaut wiedergeben, dann sind sie Aussage über die Spec und nicht
Anweisung an den Skill.

### 5.3 Neue Seite, nicht Edit

Beide Lesarten der Neue-Seite-vs-Edit-Heuristik sind vertretbar, deshalb
entscheidet der Supersessions-Fall: §13 sagt selbst „v0.2 supersedes OKF
v0.1", und `references/befuellen.md:86-88` schreibt dafür `status:
veraltet` plus `ersetzt`-Kante vor. Ein Edit würde das unmöglich machen,
eine Seite kann sich nicht selbst ersetzen. Die Kompressionsregel spricht
nicht dagegen, sie zielt auf Seiten, die dasselbe Quelldokument spiegeln,
nicht auf zwei Versionsstände mit getrennten Quellen.

`knowledge/demo-okf/okf-v02.md`, Typ `konzept` (passt auf
`types.yaml:19-24`, also kein Type-Onboarding, Schritt 3 von
`befuellen.md` entfällt begründet):

```yaml
type: konzept
title: Open Knowledge Format v0.2
domain: demo-okf
status: aktiv
confidence: hoch
version: 1.0.0
stand: 2026-07-28
sources: [S-0004]
tags: [okf, okf-v02, provenienz, vertrauen, lebenszyklus, spezifikation]
concepts: [B-0001, B-0005, B-0006, B-0007, B-0008, B-0009]
relations:
  - ersetzt -> demo-okf/okf.md
```

`concepts` enthält B-0005..B-0009 zwingend (Z1) und B-0001, damit das
Umhängen des `definition_claim` möglich ist. Keine weiteren B-IDs, damit
`concept_base` bei 190 bleibt (Z2).

Nur `ersetzt`, nicht zusätzlich `basiert_auf`. Zwei Kanten desselben
Ursprungs zum selben Ziel validieren zwar, machen den Graph aber
unlesbar. Keine `formalisiert`-Kante auf `llm-wiki-muster.md`, die wäre
durch keinen Claim von S-0004 gedeckt. Keine `widerspricht`-Kante, die
beiden Bruchstellen aus §13.1 berühren keinen bestehenden Claim.

An `knowledge/demo-okf/okf.md`:

| Zeile | alt | neu |
|---|---|---|
| 5 | `status: aktiv` | `status: veraltet` |
| 7 | `version: 1.1.0` | `version: 1.2.0` |
| 8 | `stand: 2026-07-26` | `stand: 2026-07-28` |
| 26 | „…(hier: oksv-lite/1.1)." | versionsneutral, siehe Z10 |
| 33 | C-0005-Text mit `oksv-lite/1.1` | versionsneutral, siehe Z10 |
| 35-38 | „Kontext und Grenzen" | Satz auf die Nachfolgeseite ergänzen |

Zeile 11 und 13 bleiben byteidentisch (Z6).

### 5.4 Claims C-0301 bis C-0310

Der Block C-03xx ist frei und folgt der Konvention „ein Block pro Seite".
Zehn Claims liegen unter der Split-Schwelle 20 (`vault.py:75`), also kein
`doctor`-Hinweis. `Beobachtung` scheidet aus, das ist nur für registrierte
Bild- und PDF-Quellen zulässig (`vault.py:1270-1273`).

Inhaltlich abgedeckt werden: Bundle-Struktur und Konformanz (§3, §4,
§4.1, §11), `sources` samt Credibility-Signalen und `usage_window` (§5.1),
die bewusste Ablehnung eines gespeicherten Scores (§5.1), `generated` und
`verified` samt Actor-Konvention (§5.2, §7), die drei Trust-Tiers (§5.3),
`status` und `stale_after` (§5.4, §5.5), der Typ `Attested Computation`
samt `runtime`/`parameters`/`computation`/`executor`/`attester` (§10.1,
§10.2), die Parameter-Only-Regel und die Trennung von Verifikation und
Attestierung (§10.3, §10.6), Versionierung und die zwei Bruchstellen
(§12, §13, §13.1), und als `Auslegung` die Kollision mit oksv-lite (§5,
§13.2).

Korrigierte Fundstellen: C-0301 „§3, §4, §4.1 und §11" (UTF-8 steht im
§4-Vorspann, `SPEC.md:155`), C-0309 „§12, §13 und §13.1" (der
Supersessions-Satz steht in `SPEC.md:795`, also im §13-Vorspann).

Bei der Formulierung Z4 beachten. Der volle Entwurfsblock liegt im
Analyse-Journal und muss vor der Übernahme gegen die fünf Tabu-Tokens
geprüft werden. Konkret betroffen sind C-0301 und C-0302, wo „Pflichtfeld"
statt „Pflichtschlüssel" stehen muss.

C-0310 ist der wichtige Claim: er hält die Kollision von `sources` und
`status` als `Auslegung` im Bestand fest, damit jede künftige Aussage über
OKF-Kompatibilität die Zielversion nennen muss.

### 5.5 Was am Bestand ausdrücklich NICHT migriert wird

**C-0001 bis C-0005 bleiben alle wahr.** Einzeln gegen v0.2 geprüft:

* C-0001, C-0003, C-0004 tragen ihren Versionsbezug im Text und werden von
  §3, §3.1 und §4 inhaltlich bestätigt.
* C-0002 (Dateipfad als Identität, Links als Graph) nennt keine Version
  und wird von §2 („Concept ID", `SPEC.md:79-80`) und §6.1 wörtlich
  bestätigt.
* C-0005 („weil die Spezifikation bewusst minimal ist, braucht ein
  evidenzgebundener Tresor ein strengeres Profil") bleibt gültig. Die
  naheliegende Annahme, v0.2 sei nicht mehr minimal, hält der Spec nicht
  stand: `SPEC.md:44-46` sagt zweimal „minimally opinionated", `281` sagt
  „All are optional", `188` hält `type` als einziges Pflichtfeld fest.
  Prämisse und Schluss tragen unverändert.

Angefasst wird an C-0005 also nur die Profilnennung (Z10), nicht die
Aussage.

**Begriffsumhängung.** `definition_claim` von B-0001 zeigt auf C-0001,
und C-0001 spricht ausdrücklich von v0.1. Für die Discovery ist ein
versionsneutraler Claim besser. Das Umhängen auf C-0301 ist reine
Registry-Metadatenpflege, hat aber eine Vorbedingung: `okf-v02.md` muss
B-0001 in `concepts` führen (`vault.py:1465-1471`). Das ist im Frontmatter
oben eingeplant. Das `definition_claim` von B-0002 bleibt bei C-0005.

Dies ist die einzige echte gegenseitige Blockade im ganzen Plan: die
Umhängung braucht einen Claim, der erst mit der neuen Seite existiert.
Reihenfolge innerhalb von R2: erst Seite und Claims, dann Registry.

### 5.6 Neue Begriffe B-0005 bis B-0009

In der bestehenden Welt BW-0001. Jeder Eintrag mit explizitem
`"world": "BW-0001"`, `broader: []` (Z2), Labels frei von den fünf
Tabu-Tokens (Z4), und Aliase nur als echte Synonyme, keine Werte des
Begriffs.

| ID | preferred | aliases | related | definition_claim |
|---|---|---|---|---|
| B-0005 | Attested Computation | Attestierte Berechnung, sanktionierte Berechnung, Attestierung | B-0001, B-0006 | C-0307 |
| B-0006 | Trust-Tier | Vertrauensstufe | B-0007, B-0009 | C-0305 |
| B-0007 | Provenienz | Provenance, Herkunftsnachweis | B-0001, B-0008 | C-0302 |
| B-0008 | Credibility Signal | Glaubwuerdigkeitssignal, Quellensignal | B-0006 | C-0303 |
| B-0009 | Staleness | Veraltungsdatum | B-0006 | C-0306 |

Nicht als Aliase: `unverified`, `machine-confirmed`, `human-reviewed`
(Werte, keine Bezeichnungen), `stale_after` (Feldname, keine
Bezeichnung), `Trust Tier` bei B-0006 (Dublette zum `preferred`),
`Wissenseinheit` bei B-0008 (Tabu-Token, gemessen bricht es die
`no_candidates`-Sonde).

`broader: [B-0007]` bei B-0008 wäre fachlich richtig, ist aber unkritisch,
weil B-0007 nicht B-0001 ist. Die Z2-Sperre gilt nur für Kanten zu
B-0001.

### 5.7 Router

Neue Seite hinter `okf.md` einsortieren:

```
- knowledge/demo-okf/okf-v02.md
```

Schlagworte an die bestehende Zeile anhängen: `okf v0.2, okf v02, okf 0.2,
attested computation, attestierte berechnung, attestierung, attester,
executor, receipt, trust tier, trust-tier, vertrauensstufe, provenance,
provenienz, credibility signal, stale_after, staleness, usage_count,
usage_window, actor-konvention, human-reviewed, machine-confirmed,
supersession, veraltete fassung`.

Bewusst **nicht**: `status`, `draft`, `stable`, `deprecated`, `runtime`,
`generated`, `verified`, `sources`. `cmd_route` vergleicht normalisierte
Schlagworte als Teilstring der Frage (`vault.py:2703-2722`), generische
Einzelwörter würden zu Dauerfehltreffern.

`INDEX.md` nicht anfassen, `release` erzeugt sie neu.

### 5.8 Doku, vollständige Liste

Alles unter `wissenstresor/` ist manifestiert und gehört **vor** den
`release`. Alles außerhalb danach.

**Vor dem Release, im Skill-Ordner:**

* `schema/profil.md:3-6`: die Kompatibilitätsaussage schärfen. Vorschlag:

  > Dieses Profil schreibt Seiten, die als OKF-Konzeptdokumente lesbar
  > sind: jede Seite unter `knowledge/` trägt parsebares YAML-Frontmatter
  > mit nicht leerem `type` und erfüllt damit die Bedingungen 1 und 2 aus
  > §11 der OKF-Spezifikation, in v0.1 wie in v0.2. Alles Weitere ist ein
  > eigener Vertrag. `sources`, `status` und `confidence` tragen hier
  > andere Werte als die gleichnamigen v0.2-Felder, und `vault.py` lehnt
  > fremde Felder sowie unbekannte Typen fail-closed ab. SkillSafe ist
  > damit ein strenger OKF-Produzent für den eigenen Bestand und kein
  > allgemeiner OKF-Consumer: fremde Bundles laufen ohne Konvertierung
  > nicht.

* `schema/profil.md`: Satz, dass die OKF-Bundle-Wurzel
  `wissenstresor/knowledge/` ist und nicht der Skill-Ordner. Damit liegen
  `INDEX.md` und `log.md` außerhalb des Bundles, und §8 wie §9 greifen gar
  nicht (`SPEC.md:740-741` bindet reservierte Dateinamen nur „when
  present" im Bundle). Ohne diese Klarstellung reißen 17 nicht reservierte
  `.md`-Dateien §11, auf case-sensitiven Dateisystemen 18.
* `schema/profil.md`: Satz, dass unser `references/` nicht das
  `references/` aus §6.3 ist.
* `schema/profil.md`: Auflösung der `verified`-Doppelbedeutung zwischen
  Frontmatter-Abschnitt und Medienabschnitt.
* `KONZEPT.md:1`: bleibt in R2 bei `oksv-lite/1.1`, Profilsprung erst R3.
* `KONZEPT.md:5`: „Google-OKF-Muster" um die Zielversion ergänzen.
* `KONZEPT.md:83-84`: „bewusst strenger als OKF v0.1" → „strenger als OKF
  (v0.1 wie v0.2, §11)". Die Toleranzpflicht gegenüber unbekannten Typen
  gilt in v0.2 unverändert (`SPEC.md:756`).
* `KONZEPT.md:285-288`: die Herkunftsnotiz präzisieren, dass die Namen
  `index.md`/`log.md` übernommen wurden, die Strukturen aus §8/§9 aber
  bewusst abweichen und außerhalb der Bundle-Wurzel liegen.
* `KONZEPT.md:304`, `:307`, `:309-310`: Abnahmezahlen und Abnahmedatum
  nachziehen. Achtung, diese drei Stellen fehlten in der ersten Planfassung.
* `KONZEPT.md`: neuer Abschnitt „Verhältnis zu OKF v0.2" mit der
  Wertetabelle (`aktiv`/`veraltet`/`in-pruefung` zu
  `stable`/`deprecated`/`draft`), der Begründung, warum die typisierte
  `ersetzt`-Kante über dem Statuswort steht, und der Feststellung, dass die
  Claim-Grammatik die Fußnotenattribution aus §5.1 abdeckt und um die
  Evidenzart erweitert.
* `KONZEPT.md`: neues **AD-09 „Keine ausführbaren Verweise im Tresor"**
  (Inhalt siehe Abschnitt 9).
* `KONZEPT.md`: Notiz, dass `schema/begriffswelten.json` kuratierter
  Inhalt innerhalb von `schema/` ist. Sonst widerspricht die Zonentabelle
  (`KONZEPT.md:23`, ganz `schema/` ist Engine) der Einstufung von R2 als
  `minor`. `references/befuellen.md:95-100` zählt die Begriffspflege
  ausdrücklich zum Ingest-Workflow, das ist die tragfähige Begründung.
* `KONZEPT.md` „Bewusste Grenzen": ein Punkt, dass SkillSafe sanktionierte
  Berechnungen höchstens dokumentiert, nie ausführt oder attestiert.
* `SKILL.md:3` (description): Zielversion aufnehmen. **Z9 beachten**, nur
  119 Zeichen Luft. Im Zweifel ein bestehendes Triggerwort kürzen.
* `SKILL.md` Regel 5: das Verbot fremder Ausführung ausdrücklich
  aufnehmen. Heute ist die Regel nur positiv formuliert („macht
  `scripts/vault.py`"), das Verbot trägt nur implizit.
* `references/antworten.md:61`: das Beispiel nennt `okf.md` mit „Stand
  2026-07-04". Diese Zahl passt zu keiner Lesart, `REGISTER.md:11` nennt
  für S-0001 den Stand 2026-06-12 und die Seite trägt 2026-07-26. Nach R2
  ist `okf.md` zusätzlich `veraltet` und damit kein gutes Musterbeispiel.
  Auf `okf-v02.md` mit S-0004 umstellen.
* `references/antworten.md`: eine Zeile, die `confidence`, Register-Trust
  und die spätere abgeleitete Stufe gegeneinander abgrenzt.
* `notes/dead-ends.md`: `## [2026-07-28] OKF-v0.2-Typ „Attested
  Computation" mit executor/attester — verworfen`, mit Querverweis auf
  AD-09 und Hinweis auf die geprüfte deskriptive Variante. Dazu der
  LinkedIn-Eintrag. Dazu eine Präzisierung des vorhandenen Eintrags zur
  bi-temporalen Gültigkeit (`valid_from`/`valid_until`), damit er nicht
  später als Widerspruch zu `gueltig_bis` aus R5 gelesen wird.

**Nach dem Release, außerhalb des Skill-Ordners:**

`README.md`

| Zeile | Änderung |
|---|---|
| 21-23 | Version auf v0.7.0, Supersessions-Kette erwähnen |
| 25-27 | Testzahl, manifestierte Dateien (30), Paketeinträge (32), Paket-SHA aus echter Ausgabe |
| 75 | „Treibstoff: OKF-Seiten mit Claims" → „Wissensseiten im OKF-Muster (Profil oksv-lite/1.1)" |
| 94 | bleibt; darunter ein zweites Beispiel `query "OKF v0.2"` |
| 150-154 | 5 Seiten, 26 Claims, 4 Quellen, Spezifikation in der Aufzählung |

`index.html`

| Zeile | Änderung |
|---|---|
| 241 | „Was v0.6.1 kann" → v0.7.0 |
| 247 | Stempel: 5 Seiten · 26 Claims · v0.7.0 |
| 345 | behauptet „echte Ausgabe"; die folgenden Blöcke müssen es dann auch sein |
| 350 | die `validate`-Zeile stammt aus keinem echten `doctor`-Lauf, `cmd_doctor` ruft `cmd_validate(still=True)` (`vault.py:2887`). Entweder streichen oder als `validate`-Ausgabe kennzeichnen |
| 352 | 28 → 30 Dateien |
| 354 | 5 Seiten / 26 Claims / 4 Quellen |
| 355-363 | Query-Block durch den Supersessions-Fall ersetzen, siehe unten |
| 371-376 | `knowledge/demo-okf/okf-v02.md` in die Fallback-Liste, sortiert nach `okf.md` |
| 398 | wie README Zeile 75 |
| 414 | „drei Quellen mit 16 Claims" → vier Quellen mit 26 Claims |
| 420-423 | S-0004 mit T1 in die Quellentabelle |
| 433 | Footer auf v0.7.0 |

Zeile 297 braucht keine Korrektur, dort steht „nach dem
Google-OKF-Muster" und kein Kompatibilitätsversprechen. Eine Präzisierung
auf das Profil wäre trotzdem sinnvoll.

Zum Query-Block: der Supersessions-Fall ist der beste Demo, den die Seite
haben kann. Das Ranking wertet `veraltet` nicht ab, es hängt nur das
Signal `page_status:veraltet` an (`vault.py:2043-2044`), und die
Evidenz-Sortierung ist `(-score, claim_id, page)` (`2061`). Bei
Punktgleichstand steht C-0001 also weiter vor C-0301. Darunter ein
erklärender Satz, sonst wirkt der veraltete Treffer wie ein Fehler:

> Das Ranking versteckt die alte Fassung nicht, es markiert sie. Welche
> Fassung gilt, entscheidet der Antwort-Workflow anhand der
> `ersetzt`-Kante, und er benennt beide.

Eine kurze Sektion zu OKF v0.2 und zur bewussten Nicht-Übernahme von
`Attested Computation` wäre ein Argument für den Tresor, nicht gegen ihn.
Optional.

### 5.9 Ein Verhaltenseffekt, der dokumentiert werden muss

Nach der Supersession liefert `query "LLM-Wiki-Muster"` gemessen als erste
Evidenz C-0004 aus der **veralteten** `okf.md` mit Score 330, vor C-0101
der eigentlich einschlägigen Seite mit 240. Die veraltete Seite kommt
nicht über den Graph-Hop herein, sondern über die Begriffserweiterung:
`page_reasons` von `okf.md` sind `concept:B-0002:direct`,
`concept:B-0001:expanded:55`, `concept:B-0003:expanded:35`, `exact:claim`
und Tokens. Der Graph-Hop wiegt nur 10 im `page_score`.

Das ist gewolltes Verhalten nach AD-01, aber es muss in
`references/antworten.md` stehen, damit das Modell es nicht für einen
Fehler hält und die veraltete Fassung nicht kommentarlos ausgibt.

### 5.10 Ablauf R2

```bash
cd wissenstresor
#  1. Quelle: Attributionskopf, source, mv, Registerzeile anhängen (Z7, Z8)
#  2. Fixture-ID im Test von B-0005 auf B-0900 umstellen (Z3, zwei Stellen)
#  3. okf-v02.md anlegen (Z1, Z2, Z4)
#  4. okf.md: status/version/stand/Kontext + Profilnennungen versionsneutral (Z6, Z10)
#  5. begriffswelten.json: B-0005..B-0009 anhängen, definition_claim von B-0001 auf C-0301
#  6. ROUTER.md: Seite + Schlagworte (Z5)
#  7. Doku im Skill-Ordner: profil.md, KONZEPT.md, SKILL.md (Z9), antworten.md, dead-ends.md
python3 scripts/vault.py validate
python3 scripts/vault.py log ingest "S-0004 OKF-Spezifikation v0.2: Seite demo-okf/okf-v02.md mit C-0301..C-0310, B-0005..B-0009, okf.md auf veraltet mit ersetzt-Relation"
python3 scripts/vault.py release minor          # 0.7.0
python3 -m pytest tests -q                      # erst jetzt aussagekräftig
python3 scripts/vault.py doctor                 # muss 🟢 sein, sonst Z5 prüfen
python3 scripts/vault.py checksum --verify
cd .. && python3 tools/build_skill_package.py
#  8. README.md und index.html mit den echten Zahlen nachziehen
```

Zwischen `validate` und `log` nichts Inhaltliches mehr ändern.

Aufwand: M bis L, vor allem wegen der zehn Claim-Formulierungen und der
Doku-Breite.

---

## 6. R3 · `geprueft_von` und `geprueft_am` (minor, 0.8.0, Profil oksv-lite/1.2) — ERLEDIGT

Umgesetzt am 2026-07-28. 52 Tests bestanden, `validate`, `doctor` und
`checksum --verify` grün, drei Query-Läufe byteidentisch, Paket-SHA-256
`99745997113aa2c5a15db90282be8cfbda83cdc692d748dad8096eca5b8cddb4`.

Vier Entscheidungen, die während der Umsetzung fielen:

* **Der `doctor`-Hinweis ist bedingt.** Er feuert nur, wenn mindestens eine
  Seite `geprueft_von` führt. Sonst hätte ein Tresor, der das Feld gar nicht
  nutzt, auf jeder Seite mit `confidence: hoch` einen Hinweis, und das ist
  Rauschen statt Signal. Gemessen: ohne Nutzung 0 Hinweise, mit Nutzung genau
  ein Hinweis, Ampel in beiden Fällen grün.
* **`geprueft_am` vor `stand` ist eine Warnung, kein Fehler.** Eine Prüfung
  darf älter sein als die letzte inhaltliche Änderung. Sie deckt den Inhalt
  dann nur nicht mehr, und genau das soll sichtbar werden statt den Release
  zu blockieren.
* **Die Injection-Prüfung auf dem Aktor ist erreichbar, aber knapp.** Der
  Zeichenvorrat von `ACTOR_RE` lässt keine Leerzeichen zu und verhindert
  natürlichsprachige Anweisungen von sich aus. Für `mensch:ignore all
  previous instructions` greift die spezifischere Meldung, weil die
  Injection-Prüfung vor der Grammatikprüfung liegt. Ein Testfall war zuerst
  falsch gedacht: `ignore-all-previous-instructions` mit Bindestrichen ist
  eine gültige Aktor-ID, und das ist richtig so.
* **Kein `generated`-Aktor.** `geprueft_von` ist §5.2 `verified`. Wer
  geschrieben hat, bleibt bewusst offen: es wäre eine zweite Angabe ohne
  zweiten Nutzen, und für den Export ist ein leeres `generated` ehrlicher als
  ein erfundener Aktor.

Die Aktorkonvention gegen Personenbezug steht als Abschnitt 9 in
`references/mehrere-tresore.md`: Rollenkennung statt Klarname, weil der
Bestand die Historie behält und das ZIP den Ort wechselt. Der Validator prüft
nur die Grammatik, die Konvention durchzusetzen bleibt Kuratierungsarbeit.


Zwei optionale flache Frontmatter-Felder. Aus ihnen wird die Trust-Stufe
nach §5.3 **abgeleitet**: kein Feld gleich unverified, nicht-menschlicher
Aktor gleich machine-confirmed, `mensch:<id>` gleich human-reviewed. Die
Stufe wird nie gespeichert und **nie im Score verwendet**.

Diese Änderung wurde in einer Kopie vollständig umgesetzt und gemessen:
`validate` bleibt im Leerzustand grün, acht Negativfälle liefern je genau
einen Fehler, `doctor` bleibt mit einem ℹ️-Hinweis grün, die Query liefert
identische Scores und Rangfolge, drei Läufe sind byteidentisch, und alle
bestehenden Tests laufen durch. Das Risiko ist damit klein und bekannt.

### 6.1 Der Fallstrick

Ein neu in `OPTIONAL_FIELDS` aufgenommenes **skalares** Feld erhält heute
überhaupt keine Typprüfung. Die Listen-Schleife deckt nur `LIST_FIELDS`
ab, die Text-Schleife nur `set(REQUIRED_FIELDS) - LIST_FIELDS`
(`vault.py:1157-1162`). Gemessen: `geprueft_von:` ohne Wert wird zur
leeren Liste und läuft grün durch, eine Inline-Liste
`['mensch:mz','agent:boese/1']` ebenfalls. Und `ACTOR_RE.fullmatch` auf
einer Liste würde einen unbehandelten `TypeError` werfen, weil die Aufrufer
von `lade_seiten` nur `OSError` und `UnicodeError` fangen
(`vault.py:1451-1458`).

Also braucht R3 zwingend: je eine `isinstance(..., str)`-Wache vor der
Regex-Prüfung, und eine vierte Prüfschleife für optionale Skalare.

### 6.2 Änderungen

1. `ACTOR_RE` neben die übrigen Muster (`vault.py:88-95`), streng, mit
   Längenbegrenzung, drei Formen: `mensch:<id>`, `agent:<name>/<version>`,
   `prozess:<id>`. Strenger als §7 ist zulässig, §7 fixiert das Präfix,
   nicht den Zeichenvorrat.
2. `OPTIONAL_FIELDS` (`vault.py:62`) um beide Felder erweitern.
3. Neuer Helfer `_iso_date`, der `DATE_RE` mit
   `datetime.date.fromisoformat` kombiniert, und ihn auch auf `stand`
   anwenden. Heute prüft der Validator nur das Format, nicht die
   Kalendervalidität. Alle vorhandenen `stand`-Werte sind gültig, also kein
   Breaking Change.
4. Prüfblock **nach `vault.py:1179`**, nicht nach 1178. Zeile 1178 ist das
   `if not VERSION_RE.match(...)`, 1179 das zugehörige `fehler.append`.
   Dazwischen einzufügen zerreißt den Block.
5. Paar-Regel: die beiden Felder treten gemeinsam auf oder gar nicht.
   Eines allein ist ein Validierungsfehler.
6. Jeder Aktorwert zusätzlich durch `_plain_text` und
   `PROMPT_INJECTION_RE`.
7. Envelope additiv: abgeleitete Stufe in `page_results` und in
   `evidence[]`, ein `signals`-Eintrag nur beim untersten Tier (analog zu
   `source_trust:T3`, `vault.py:2047-2048`). `QUERY_SCHEMA` bleibt bei
   `v1`, weil nur Schlüssel hinzukommen. Der `retrieval_fingerprint`
   bleibt unangetastet, die Felder sind zeitunabhängig.
8. `doctor`: ein ℹ️-Hinweis bei `confidence: hoch` und unverified. Als
   Hinweis, nicht als Warnung, sonst kippt die Ampel und
   `test_packaged_vault.py:32` fällt.
9. Profilsprung auf `oksv-lite/1.2` an acht Zeilen in sieben Dateien
   (Z10). Wenn R2 die Vorarbeit gemacht hat, ist `okf.md` nicht mehr
   dabei.

### 6.3 Drei Vertrauensmaße auseinanderhalten

Nach R3 hat der Tresor drei Maße plus einen Sonderfall:

| Maß | Ort | Frage |
|---|---|---|
| `confidence` | Seiten-Frontmatter | Wie belastbar ist die Aussage? |
| Trust T1/T2/T3 | `sources/REGISTER.md` | Wie nah ist die Quelle am Original? |
| abgeleitete Stufe | aus `geprueft_von` | Hat ein Mensch das gegengeprüft? |
| `verified` (Boolean) | `sources/derived/*__media.json` | Wurde diese Bildextraktion sichtgeprüft? |

Die Abgrenzung gehört in `schema/profil.md` (beide betroffenen
Abschnitte), in `references/antworten.md` (Envelope-Regeln) und als ein
Satz nach `KONZEPT.md`. Ohne diese Abgrenzung liest sich jede
Kombination wie ein Widerspruch. Eine hoch-konfidente Seite kann
unverifiziert sein und umgekehrt, genau die Trennung, die §5.2 zwischen
`generated` und `verified` schon zieht.

### 6.4 Personenbezug

`mensch:<name>` in einem Artefakt, das als ZIP verteilt und in fremde
Skill-Ordner entpackt wird, ist ein neues Datenschutzthema. Empfehlung:
Rollenkennungen statt Klarnamen (`mensch:kuratorin`,
`mensch:fachbereich-hr`). Festgeschrieben in
`references/mehrere-tresore.md`, weil dort schon die Grenze zwischen
Tresor-Instanzen steht.

### 6.5 Bestand

Die fünf Demo-Seiten bekommen die Felder **nicht**. Für Seiten, die
niemand gegengeprüft hat, ist der leere Zustand die ehrliche Antwort, und
§5.3 liest ihn korrekt als unverified. Ein nachträglich erfundener Aktor
wäre genau die Art Angabe, die der Tresor sonst verbietet.

### 6.6 Release-Stufe

`minor`, nicht `major`. Beide Felder sind optional, kein bestehender
Bestand wird ungültig, kein Vertrag bricht. Die eigene Regel in
`references/befuellen.md:116` nennt „major bei Profil- oder
Strukturänderungen" und trifft damit formal zu, ist aber zu grob: sie
unterscheidet nicht zwischen additiven und brechenden Profiländerungen.
Diese Präzisierung gehört in `befuellen.md:116` mit dazu, sonst ist die
Einstufung angreifbar.

---

## 7. R4 · `export --okf` (minor, 0.9.0)

Neues Unterkommando `export --okf --out <pfad>`. `validate`-Gate davor
(Muster: `cmd_index`, `vault.py:1552-1569`), kein Schreibzugriff innerhalb
von `ROOT`, kein Zeitstempel in der Ausgabe, kein Release-Ziel. Damit
bleiben die Rollback-Tests unberührt und der interne Datenvertrag
unangetastet.

Was der Export erzeugt:

1. Jede Seite aus `knowledge/` als v0.2-Konzept.
2. `status` hart übersetzt: `aktiv` → `stable`, `veraltet` →
   `deprecated`, `in-pruefung` → `draft`. Verlustfreie 1:1-Abbildung, der
   einzige Punkt exakter semantischer Deckung.
3. `sources` aus dem Register aufgefaltet: S-ID → `id`, Titel → `title`,
   Stand/Version → `last_modified` sofern gegen `DATE_RE` passend.
4. Jede Claim-Zeile um `[^S-nnnn]`, am Dokumentende der Fußnotenblock. Das
   Label **muss** die S-ID sein, §5.1 sagt „a markdown footnote whose
   label is a `sources[].id`" und „the join key into `sources`". Die C-ID
   kann in den Fußnotentext.
5. `relations` als Body-Sektion mit bundle-relativen Links, also **mit**
   führendem Slash. Ohne Slash löst ein Consumer sie relativ zur
   Konzeptdatei auf und sie zeigen ins Leere.
6. `verified` aus `geprueft_von`/`geprueft_am`: Skalarpaar zu
   Ein-Element-Liste (`SPEC.md:391-396` erlaubt die Bare-Mapping-Form),
   Kalendertag zu ISO-8601-Datetime (`SPEC.md:386`). Die deutsche
   Aktorgrammatik braucht dieselbe Übersetzungstabelle wie `status`:
   `mensch:` → `human:`, `prozess:` → `process:`, `agent:x/y` → `x/y`.
   Die Rückrichtung ist bei Großbuchstaben in IDs bewusst nicht umkehrbar.
7. `confidence`, `version`, `domain`, `concepts` und die Trust-Stufe als
   producer-eigene Zusatzschlüssel, §4.1 deckt das ausdrücklich. Trust
   unter einem Namen, der nicht nach v0.2 aussieht, etwa `oksv_trust: T2`.
8. `index.md` pro Verzeichnis nach §8, an der Wurzel mit
   `okf_version: "0.2"` (nach §12 ein MAY, also freiwillig).

Vier Dinge kann der Export **nicht** liefern, und das muss dokumentiert
werden statt geschönt:

* **`generated.by`.** `geprueft_von` ist §5.2 `verified`, nicht
  `generated`. Wer geschrieben hat, weiß der Tresor auch nach R3 nicht.
  Konsequenz: `generated` bleibt leer. Das ist ehrlicher als ein
  erfundener Aktor.
* **`sources[].author`.** Das siebenspaltige Register hat keine
  Urheberspalte. Nachrüstbar als achte Spalte, das berührt aber
  `parse_register` (`vault.py:868-869`), `schema/profil.md:162-163`, den
  Registerkopf und die Beispielzeile in `cmd_source` (`vault.py:2694`).
  Eigene Entscheidung, nicht Teil von R4.
* **Ein folgbares `sources[].resource`.** Der Registerpfad
  `sources/raw/S-0001__…md` ist ohne führenden Slash ein relativer Pfad
  und würde vom Konzept aus ins Leere zeigen. Der Export muss ihn zu einem
  bundle-relativen Pfad mit Slash machen und `sources/raw/` mit ins
  Zielverzeichnis kopieren, oder das Feld bewusst leer lassen. Erste
  Variante ist besser, kostet aber Kopierlogik.
* **`usage_count` und `usage_window`.** Ein lokaler Tresor ohne Telemetrie
  hat diese Zahlen nicht. Bewusst leer.

Umfang: geschätzt 250 bis 350 Zeilen plus zwei Tests (zweimaliger Export
byteidentisch; Ausgabe erfüllt §11 Bedingung 1 bis 3). Dazu ein Workflow
`references/export-okf.md` und ein README-Abschnitt.

Vorher zu klären, weil es die Doktrin berührt: welcher Tresor darf
exportiert werden und wohin. Der Export schreibt bewusst außerhalb von
`ROOT` und steht damit quer zur AD-06-Linie „die Grenze ist der
Installationsort". Das braucht eine Regel in
`references/mehrere-tresore.md`, keinen Flag.

---

## 8. R5 · `gueltig_bis` und `--asof` (später, nur bei Anlass)

Nicht weil es falsch wäre, sondern weil ein optionales Feld, das niemand
setzt, den Vertrag verlängert und nichts leistet. Ein Demo-Bestand über
OKF hat kein natürliches Verfallsdatum. Der Zeitpunkt ist der erste
Tresor mit Inhalten, die eines haben.

Wenn er kommt, gilt zwingend:

* `--asof JJJJ-MM-TT` als Eingabe, nie ein impliziter Vergleich gegen
  „heute". Ohne Stichtag kein Urteil, das Feld erscheint roh und das
  Urteilsfeld bleibt `not_assessed`, genau das Idiom, das der Envelope für
  `semantic_coverage` schon nutzt (`vault.py:1663`).
* `asof` **muss** in `fingerprint_data` (`vault.py:2101-2109`). Sonst
  liefern zwei verschiedene Stichtage denselben Fingerprint bei
  unterschiedlichem Inhalt, und der Fingerprint hört auf, die Ausgabe zu
  charakterisieren.
* `validate` prüft nur das Format, nie die Fälligkeit. Sonst macht ein
  Kalendertag ein grünes Release rot, ohne dass sich eine Datei geändert
  hat.
* `doctor` meldet Fälligkeit als ℹ️-Hinweis, nicht als Warnung.
* `INDEX.md` und `graph.json` dürfen das Datum wörtlich aufnehmen, aber
  niemals ein Urteil daraus. Regel in den Kommentarkopf beider Builder.
* Drei Tests: zwei `--asof`-Werte ergeben identische Scores und
  Rangfolge, aber unterschiedliche Staleness-Felder **und** unterschiedliche
  Fingerprints; `query` ohne `--asof` ist byteidentisch auch bei
  gefälschtem Systemdatum; eine überfällige Seite lässt `release` grün
  durchlaufen und erzeugt genau einen ℹ️-Hinweis.

Der Eintrag zur bi-temporalen Gültigkeit in `notes/dead-ends.md` muss
spätestens hier präzisiert werden, damit er nicht als Widerspruch gelesen
wird. R2 legt die Präzisierung schon an.

---

## 9. AD-09 · Keine ausführbaren Verweise im Tresor

Der v0.2-Typ `Attested Computation` (§10) wird in seiner normativen
Fassung nicht übernommen. Sieben Gründe, jeder einzeln tragfähig:

1. **Zonenbruch.** `executor.resource` und `attester.resource`
   etablieren ausführbare Verweise aus der Content-Zone heraus. Code
   kennt der Tresor bisher nur in der Engine-Zone, die sich ausschließlich
   durch bewusste Motor-Releases ändert (`KONZEPT.md:21-26`). Kein
   Buchstabe einer eisernen Regel verbietet das heute, Regel 5 ist nur
   positiv formuliert. Genau deshalb braucht es AD-09 als eigene
   Entscheidung.
2. **Eskalation der Injection-Fläche.** `PROMPT_INJECTION_RE` wird heute
   auf Claim-Text und Fundstelle angewandt, auf Frontmatter überhaupt
   nicht. Sobald Content einen Ausführungspfad benennen darf, eskaliert
   indirekte Prompt Injection von „falsche Antwort" zu „Codeausführung".
   Der Weg läuft über kuratierten Content, und Kuratierung ist
   probabilistisch.
3. **Pfadhärtung.** Zwei der drei §6.2-Formen fallen hart durch: absolute
   URLs und bundle-relative Pfade mit führendem `/` an
   `_safe_relative_path` (`vault.py:390-392`), `..` an `393-394`. Nur ein
   relativer Pfad unterhalb `ROOT` wäre vereinbar.
4. **Nesting.** §10.2 braucht verschachteltes Frontmatter, das der
   Ein-Parser-Entwurf ausschließt. Der Verzicht ist eine Sicherheits- und
   keine Bequemlichkeitsentscheidung. Sollte eine v0.2-Familie später doch
   Nesting brauchen, ist die doktrinkonforme Ablage eine strikte
   JSON-Registry unter `sources/derived/` nach dem Muster von
   `skillsafe.media/v1`, nicht eine Aufweichung des Parsers.
5. **Auslieferungsfläche.** Der Paketbau würde Attester-Code
   stillschweigend nach `~/.claude/skills` ausliefern. Die Allowlist aus
   R1 macht das mechanisch unmöglich.
6. **Kein Vertrauensanker.** Das Manifest ist selbstbezeugt. Der Tresor
   kann Integrität von Code nur relativ zu sich selbst behaupten, nicht
   gegenüber einem Empfänger. Ausführbare Artefakte gehören in den
   Ausbaupfad mit getrennten Vertrauenszonen, der in `SKILL.md:142-148`
   und `KONZEPT.md:255-257` schon benannt ist.
7. **Asymmetrie.** Der normative Aufwand fällt vollständig im Tresor an,
   der Ertrag (Receipt, Verdict) entsteht laut §10.5 und §10.6
   ausdrücklich außerhalb des Bundles und erreicht ihn nie. Receipt-Format
   und Attester-ABI sind in §12 selbst noch deferred, es gäbe nicht einmal
   ein stabiles Ziel.

Nebenbefund: der Typname `Attested Computation` scheitert am
Typnamen-Regex in `parse_types`. Nicht am Leerzeichen, die Ebenen werden
an der Einrückung unterschieden, sondern am Zeichenvorrat. Falls der Typ je
gewollt ist, wäre `attestierte_berechnung` intern plus Export-Mapping der
spec-konforme Weg, §4.1 sagt ausdrücklich, dass Typwerte nicht zentral
registriert sind.

**Geprüfte Restmenge, die in AD-09 stehen bleibt:** ein rein deskriptiver
Berechnungstyp ohne `executor`, ohne `attester`, ohne Pfad auf Code, der
eine sanktionierte Berechnung nur dokumentiert. Er ginge über das reguläre
Type-Onboarding, mit `besonderheiten`, das festhält, dass die Seite nie
eine Ausführung auslöst, und `pflicht_extra`, das Sanktionierungsgeber und
Stand als Claim verlangt. Das steht in AD-09, damit sichtbar bleibt, dass
die schlanke Variante geprüft und nicht übersehen wurde.

Zusätzlicher Negativtest in `test_vault_security.py`: eine Seite mit
`type: Attested Computation` oder mit einem `executor`-Feld muss
fail-closed abgewiesen werden.

---

## 10. Vollständigkeitsmatrix

Kein v0.2-Element bleibt unbehandelt.

| Element | Spec | Behandlung |
|---|---|---|
| `type` | §4.1 | haben wir strenger: Registry-Zwang, `vault.py:1164-1166` |
| `title`, `tags` | §4.1 | haben wir, Pflichtfelder |
| `description` | §4.1 | fehlt. Bewusst nicht aufgenommen; der Name ist in `begriffswelten.json` schon belegt (`vault.py:710`, `721`). Export zieht bei Bedarf den ersten Satz der Kurzfassung |
| `resource` | §4.1 | fehlt, folgerichtig: unsere vier Typen beschreiben keine Assets mit URI. Frage ins Type-Onboarding aufnehmen |
| `sources` (Maps) | §5.1 | nicht nativ. Register ist die Wahrheit, Abbildung in R4 |
| `sources[].author` | §5.1 | Lücke. Achte Registerspalte nötig, eigene Entscheidung |
| `usage_count`, `usage_window` | §5.1 | bewusst ignoriert: lokaler Tresor ohne Telemetrie |
| kein gespeicherter Score | §5.1 | Übereinstimmung. Unser Trust ist eine Quellenklasse, kein Score. Als Claim aufgenommen (C-0303) |
| `generated.at` | §5.2 | haben wir als `stand`, Export bildet ab |
| `generated.by` | §5.2 | Lücke, bleibt offen. R3 liefert `verified`, nicht `generated` |
| `verified` | §5.2 | gelernt in R3 als `geprueft_von`/`geprueft_am` |
| Trust-Tiers | §5.3 | gelernt in R3, abgeleitet und nie gespeichert |
| `status` | §5.4 | haben wir mit eigenen Werten, 1:1-Abbildung in R4 |
| `stale_after` | §5.5 | gelernt in R5 als `gueltig_bis`, mit `--asof` |
| Links | §6.1 | bewusste Verletzung: `vault.py:1332-1333` lehnt tote Links ab, §6.1 verlangt Toleranz. Dokumentiert in R2 |
| Pfadformen | §6.2 | bewusst enger: nur relative Pfade unterhalb `ROOT` |
| `references/` | §6.3 | Namensüberschneidung, in R2 dokumentiert |
| Actor-Konvention | §7 | gelernt in R3, deutsche Präfixe plus Übersetzungstabelle im Export |
| `index.md` | §8 | außerhalb der Bundle-Wurzel, greift nicht. Export erzeugt §8-konforme Fassung |
| `log.md` | §9 | außerhalb der Bundle-Wurzel, greift nicht. Grep-barer Präfix bleibt |
| `Attested Computation` | §10 | dokumentiert abgelehnt, AD-09. Als Wissen aufgenommen (C-0307, C-0308) |
| Conformance | §11 | Produzentenrolle erfüllt, Consumer-MUST-NOTs bewusst verletzt. Dokumentiert in R2 |
| `okf_version` | §12 | freiwillig (MAY). Nur im Export |
| `timestamp` → `generated.at` | §13.1 | betrifft uns nicht, wir hatten nie `timestamp` |
| `# Citations` → `sources` | §13.1 | betrifft uns nicht, wir hatten nie `# Citations` |

Zwei bewusste Verletzungen bleiben: die §6.1-Toleranzpflicht bei toten
Links und die Consumer-MUST-NOTs aus §11. Beide sind Ausdruck der
Fail-closed-Doktrin und gehören ausgeschrieben, nicht behoben.

---

## 11. Offene Entscheidungen

1. **Trust-Stufe S-0004:** T1 oder T2. Empfehlung T1, mechanisch ohne
   Unterschied.
2. **`definition_claim` von B-0001** auf C-0301 umhängen oder bei C-0001
   lassen. Empfehlung umhängen, C-0001 spricht ausdrücklich von v0.1.
3. **Achte Registerspalte „Urheber"** für `sources[].author`. Berührt
   `parse_register`, `profil.md`, Registerkopf und `cmd_source`. Nur
   sinnvoll, wenn R4 kommt.
4. **Aktor-Konvention und Personenbezug:** Klarname, Kürzel oder
   Rollenkennung. Muss vor R3 entschieden werden.
5. **Exportziel-Regel für AD-06:** welcher Tresor darf wohin exportieren.
   Muss vor R4 entschieden werden.

---

## 12. Was schiefgeht, wenn man den Plan verlässt

* Wer `pytest` vor `checksum` laufen lässt, sieht zwei rote Tests und
  sucht an der falschen Stelle.
* Wer manifestierte Doku nach dem Release anfasst, macht
  `checksum --verify` rot und `query` fail-closed.
* Wer `broader: [B-0001]` bei einem neuen Begriff setzt, kippt das erste
  Evidenzstück und zwei Tests.
* Wer die Fixture-ID `B-0005` stehen lässt, bekommt einen Abbruch im
  `release` des Tests, nicht im eigenen Bestand, und sucht dort zuerst.
* Wer „Schlüssel" oder „Wissenseinheit" in einen Claim oder ein
  Begriffslabel schreibt, macht die `no_candidates`-Sonde stumpf. Sie ist
  der Test, der das Kernversprechen des Tresors absichert.
* Wer die Profilnennung in C-0005 nicht in R2 versionsneutral macht,
  muss in R3 einen Claim-Text ändern, um eine Versionsnummer nachzuziehen.
* Wer Zahlen in README oder `index.html` vor dem Release schreibt,
  schreibt sie falsch.
