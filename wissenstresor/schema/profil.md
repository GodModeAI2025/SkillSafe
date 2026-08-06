# Profil oksv-lite/1.3 — Datenvertrag des Wissenstresors

Dieses Profil schreibt Seiten, die als OKF-Konzeptdokumente lesbar sind: jede
Seite unter `knowledge/` trägt parsebares YAML-Frontmatter mit nicht leerem
`type` und erfüllt damit die Bedingungen 1 und 2 aus §11 der
OKF-Spezifikation, in v0.1 wie in v0.2. Alles Weitere ist ein eigener
Vertrag; es liegt in flachem Frontmatter, in Claims oder in separaten
JSON-Registries. `scripts/vault.py validate` erzwingt ihn fail-closed;
unbekannte Felder und JSON-Schlüssel sind Fehler.

Die Kompatibilität ist damit einseitig, und das ist gewollt. SkillSafe ist
ein strenger OKF-**Produzent** für den eigenen Bestand und kein allgemeiner
OKF-**Consumer**: die Toleranzpflichten aus §11 gelten für fremde Bundles,
nicht für diesen Bestand, und ein fremdes Bundle läuft hier ohne
Konvertierung nicht. Fremdes OKF-Wissen kommt denselben Weg wie jede andere
Quelle, also über Quarantäne, lokalen Abzug, Registrierung und
Claim-Extraktion. Das ist keine Lücke, sondern die Kernaussage des Tresors.

Drei Feldnamen sind mit OKF v0.2 namensgleich und anders belegt, was jede
pauschale Aussage über „OKF-Kompatibilität" ohne Zielversion unpräzise macht:

| Feld | hier | OKF v0.2 |
|---|---|---|
| `sources` | flache Liste registrierter `S-nnnn` | Liste von Einträgen mit Pflichtangabe `resource` (§5.1) |
| `status` | `aktiv` / `veraltet` / `in-pruefung` | `draft` / `stable` / `deprecated` (§5.4) |
| `confidence` | Belastbarkeit der Aussage | kein Gegenstück; §5.2 trennt Erzeugung von Bestätigung |

Die OKF-Bundle-Wurzel dieses Tresors ist `knowledge/`, nicht der
Skill-Ordner. `INDEX.md` und `log.md` liegen eine Ebene darüber und damit
außerhalb des Bundles; §8 und §9 greifen für sie deshalb nicht, und die
Tabellenform von `INDEX.md` wie der grep-bare Log-Präfix bleiben. Ebenso ist
`references/` hier der Ordner der Workflow-Protokolle und nicht das
`references/` aus §6.3, das gespiegeltes Fremdmaterial aufnimmt.

## Frontmatter

Pflichtfelder jeder Wissensseite:

| Feld | Werte | Zweck |
|---|---|---|
| `type` | Eintrag aus `schema/types.yaml` | Unbekannter Typ stoppt den Ingest |
| `title` | Text | Anzeige und lexikalisches Ranking |
| `domain` | Ordnername unter `knowledge/` | Quellentrennung ist baulich |
| `status` | `aktiv` / `veraltet` / `in-pruefung` | Geltung sichtbar machen |
| `confidence` | `hoch` / `mittel` / `niedrig` | Belastbarkeit der Antwort |
| `version` | SemVer `x.y.z` | Änderungsklasse nachvollziehbar |
| `stand` | `JJJJ-MM-TT` | Zeitstand jeder Antwort |
| `sources` | Liste von `S-nnnn` | Nur registrierte, gehashte Quellen |
| `tags` | nicht leere Textliste | Lexikalische Suche und Router-Pflege |

Optionale Felder:

| Feld | Werte | Zweck |
|---|---|---|
| `relations` | Liste `typ -> domäne/seite.md` | Typisierte Seitenkanten |
| `concepts` | Liste `B-nnnn` | Verknüpfung zur kontrollierten Begriffswelt |
| `externe_quellen` | Liste `X-nnnn` | Aufgeführte externe Bezugsquellen dieser Seite |
| `geprueft_von` | `mensch:<id>`, `prozess:<id>` oder `agent:<name>/<version>` | Wer den Inhalt gegen die Quellen gegengeprüft hat |
| `geprueft_am` | `JJJJ-MM-TT` | Wann diese Prüfung stattgefunden hat |

Die Prüfangabe tritt als Paar auf oder gar nicht: ein Prüfer ohne Datum ist
nicht nachvollziehbar, ein Datum ohne Prüfer nicht zurechenbar. Liegt
`geprueft_am` vor `stand`, ist das kein Fehler, sondern eine Warnung: die
Prüfung darf älter sein als die letzte inhaltliche Änderung, sie deckt den
aktuellen Inhalt dann nur nicht mehr. Fehlt die Angabe ganz, ist das der
Normalfall und keine Auffälligkeit.

### Drei Vertrauensangaben, die nicht dasselbe messen

| Angabe | Ort | Frage |
|---|---|---|
| `confidence` | Seiten-Frontmatter | Wie belastbar ist die Aussage? |
| Trust `T1`/`T2`/`T3` | `sources/REGISTER.md` | Wie nah liegt die Quelle am Original? |
| Trust-Tier | abgeleitet aus `geprueft_von` | Hat ein Mensch das gegengeprüft? |

Alle drei können unabhängig voneinander jeden Wert haben. Eine
hoch-konfidente Aussage aus einer T3-Quelle ist möglich, ebenso eine
menschlich geprüfte Seite mit niedriger Konfidenz. Das Trust-Tier folgt
OKF v0.2 §5.3 und heißt deshalb `unverified`, `machine-confirmed` oder
`human-reviewed`; `mensch:` ergibt `human-reviewed`, jeder andere Aktor
`machine-confirmed`, keine Angabe `unverified`.

Das Tier wird **ausschließlich abgeleitet und niemals gespeichert**, und es
geht **niemals in das Ranking** ein. Sonst würde aus einem reproduzierbaren
Score ein Vertrauensurteil, und die Begründung von AD-01 fällt. Im
Query-Envelope erscheint es als Ausgabefeld, und nur die unterste Stufe
erzeugt zusätzlich das Signal `trust_tier:unverified`, analog zu
`source_trust:T3`.

Frontmatter nutzt nur Skalar, Inline-Liste und Bindestrich-Liste. Kein
Nesting. Listenfelder müssen tatsächlich als Liste geschrieben werden.

Verschachtelung wird abgelehnt, nicht toleriert: jede eingerückte Zeile, die
keine Listenzeile `  - wert` ist, ist ein Validierungsfehler. Das gilt auch
für die YAML-Blockform `schlüssel:` mit eingerückten Unterschlüsseln
darunter. Ohne diese Regel zog die Blockform ihre Unterschlüssel still ins
Top-Level und machte den Wert zur leeren Liste, also Strukturkorruption ohne
Fehlermeldung. Wer verschachtelte Angaben braucht, legt sie als strikte
JSON-Registry unter `sources/derived/` ab, nach dem Muster von
`skillsafe.media/v1`, und weicht nicht den Parser auf.

## Dateinamen und Tag-Zeichen

`index.md` und `log.md` sind nach OKF v0.2 §3.1 reservierte Namen und dürfen
keine Wissensseite sein. Eine Seite mit diesem Namen würde beim Export vom
generierten Verzeichnisindex überschrieben und lautlos aus dem Bundle
verschwinden; `validate` lehnt sie deshalb ab.

Tags dürfen kein `,`, `[` oder `]` enthalten. In der Inline-Listenform ist so
ein Wert nicht darstellbar, und beim Export würde er den Tag zerlegen oder das
YAML brechen.

## Dateiarten im Tresor

Der Tresor liefert Wissen aus, keinen ausführbaren Inhalt. `validate` lässt
im Baum nur zu: `.md`, `.json`, `.yaml`, `.sha256`, die registrierten
Medienformate aus dem Register, die endungslosen Dateien `LICENSE` und
`VERSION` sowie genau ein Python-Script, `scripts/vault.py`. Ein zweites
Script, ein Archiv, ein Binary oder ein gesetztes Ausführungsbit bricht
fail-closed ab. `tools/build_skill_package.py` führt dieselbe Allowlist
unabhängig ein zweites Mal, damit der Paketbau nicht von dem Script abhängt,
das er verpackt.

## Claim-Grammatik

```text
- **C-nnnn** [S-nnnn|X-nnnn | Fundstelle | Wortlaut|Beobachtung|Auslegung] Aussagetext.
```

Eine Zeilenform, Präfix-Dispatch: `S-` ist eine lokal gehashte Quelle, `X-`
eine aufgeführte externe Bezugsquelle.

* `C-nnnn` ist tresorweit eindeutig.
* `S-nnnn` steht im Register und im `sources`-Feld der Seite.
* `X-nnnn` steht in `sources/EXTERN.md` und im `externe_quellen`-Feld der
  Seite. Bei einer externen Quelle enthält die Fundstelle genau eine
  existierende `A-nnnn` — dieselbe mechanische Regel wie `R-nnnn` bei Bild
  und PDF. Ein Anker mit `suspicious_instruction: true` darf keinen Claim
  tragen.
* `Beobachtung` bleibt Bild-/PDF-Quellen vorbehalten. Ein zitierter externer
  Satz ist `Wortlaut`, eine Schlussfolgerung daraus `Auslegung`.
* `sources` darf genau dann leer sein, wenn `externe_quellen` nicht leer ist:
  eine Seite kann ausschließlich extern belegt sein. Ganz ohne Beleg bleibt
  sie unzulässig.
* `Wortlaut` gibt Text oder geprüftes OCR nah an der Quelle wieder.
* `Beobachtung` ist ein unmittelbar sichtbarer Befund und nur für eine
  registrierte Bild-/PDF-Repräsentation erlaubt.
* `Auslegung` ist eine ausdrücklich markierte Schlussfolgerung.
* Bei einer Bild-/PDF-Quelle enthält die Fundstelle genau eine existierende
  `R-nnnn`, etwa `R-0042: Seite 3, Diagramm links`. Verdächtige Regionen
  dürfen nicht referenziert werden.
* Offensichtliche Instruktionssignaturen sind weder im Aussagetext noch in
  der Fundstelle freigabefähig. Sie bleiben als markierte Quelldaten in der
  Medienrepräsentation oder Quarantäne, erscheinen aber nie als Claim.

## Begriffswelten (`schema/begriffswelten.json`)

Die Registry hat Schema `skillsafe.begriffswelten/v1` und exakt drei
Top-Level-Felder:

```json
{
  "schema": "skillsafe.begriffswelten/v1",
  "worlds": [
    {
      "id": "BW-0001",
      "name": "Wissensarchitektur",
      "description": "Kontrollierte Suchbegriffe."
    }
  ],
  "concepts": [
    {
      "id": "B-0001",
      "world": "BW-0001",
      "preferred": "Open Knowledge Format",
      "aliases": ["OKF"],
      "broader": [],
      "related": [],
      "definition_claim": "C-0001"
    }
  ]
}
```

IDs, Referenzen und Suchbegriffe sind eindeutig. `broader` bleibt innerhalb
einer Welt und azyklisch; `related` verlässt die Welt ebenfalls nicht.
Alias-Kollisionen innerhalb einer Welt sind Fehler. Jede Begriffsdefinition
verweist auf einen existierenden Claim, dessen Seite den Begriff in
`concepts` führt. Vorzugsbegriffe, Aliase und Hierarchie erweitern nur die
Discovery — sie sind nie selbst Antwort-Evidenz.

## Medienrepräsentationen (`sources/derived/`)

Originale bleiben unverändert und gehasht unter `sources/raw/`. Für jede
registrierte PNG-, JPEG-, GIF-, WebP-, TIFF- oder PDF-Quelle ist genau eine
Datei `sources/derived/S-nnnn__media.json` erforderlich:

```json
{
  "schema": "skillsafe.media/v1",
  "source_id": "S-0042",
  "source_sha256": "<Hash aus REGISTER>",
  "media_type": "image/png",
  "language": "de",
  "extractor": {
    "kind": "human",
    "name": "lokale Sichtprüfung",
    "version": "1"
  },
  "verified": true,
  "alt_text": "Kurze zugängliche Beschreibung.",
  "regions": [
    {
      "id": "R-0042",
      "kind": "diagram",
      "locator": "Diagramm links",
      "text": "Geprüfte lokale Repräsentation.",
      "confidence": 0.95,
      "bbox": [0.0, 0.0, 0.5, 1.0],
      "suspicious_instruction": false
    }
  ]
}
```

`bbox` ist entweder `null` oder normalisiert als `[x,y,breite,höhe]` in
`0..1`. `kind` ist `text`, `diagram`, `table`, `photo`, `chart` oder
`other`; `extractor.kind` ist `human`, `model`, `ocr` oder `hybrid`.
`verified` muss vor einem Release `true` sein. SVG ist wegen aktiver Inhalte
nicht als Bildquelle erlaubt und muss lokal in ein erlaubtes Rasterformat
umgewandelt werden.

Das `verified` dieser Medienregistry ist nicht das `verified` aus OKF v0.2
§5.2. Hier ist es ein Boolean und beantwortet „wurde diese Extraktion sicht-
und qualitätsgeprüft"; dort ist es eine Liste von Bestätigungsereignissen
und beantwortet „wer hat den Inhalt gegen seine Quellen bestätigt". Gleiches
Wort, verschiedene Namensräume, verschiedene Bedeutung.

Regions-`text`, Regions-`locator` und `alt_text` bleiben untrusted
Ingest-Daten. `query` gibt sie nie als Evidenz aus, sondern nur den
kuratierten Claim mit dessen geprüfter Fundstelle sowie Region-ID, Typ und
Konfidenz. Eine markierte Prompt-Injection darf manifestiert und untersucht,
aber nicht von einem Claim verwendet werden.

## Maschinenabfrage

`query` gibt genau ein JSON-Dokument mit Schema `skillsafe.query/v1` aus.
Vor dem Retrieval müssen Validierung, Index, Graph, Quarantäne und Manifest
grün sein; der Manifest-Digest wird vor und nach dem Snapshot verglichen.
Mögliche Zustände sind:

* `candidates_found` — mindestens ein kuratierter Claim ist
  Retrieval-Kandidat; semantische Voll- oder Teildeckung wird anschließend
  anhand der Claims beurteilt, nicht vom Ranking behauptet;
* `no_candidates` — das deterministische Ranking fand keinen Kandidaten,
  Evidenz bleibt leer und `semantic_coverage` bleibt `not_assessed`;
  `fallback.page_paths` nennt den Umfang einer nötigen semantischen
  Vollprüfung;
* `ambiguous` — Alias ist über Begriffswelten mehrdeutig;
* `invalid_query`, `invalid_vault`, `vault_busy`, `snapshot_changed` —
  fail-closed, immer ohne Evidenz.

Das Ranking `hybrid-local/v1` verwendet ausschließlich Ganzzahlen:
kontrollierte Begriffe/Aliase, lexikalische Token-Treffer und höchstens einen
Graph-Hop. `retrieval_complete` bedeutet nur, dass dieser Ranking-Scan alle
validierten Claims gesehen hat; es ist kein semantischer Vollständigkeits-
beweis.

Keine Embeddings, niemals. Auf dem **Default-Query-Pfad** verlässt außerdem
kein Byte den Skill-Ordner: kein Netzwerk, kein Dateizugriff nach außen, kein
Cache. Erst das ausdrückliche `--extern` liest aufgeführte externe
Bezugsquellen — dann live, gekennzeichnet und in einem eigenen Block. Im
**manifestierten Bestand** gibt es weiterhin keinen Cache; der TTL-Abzug einer
Netzquelle liegt außerhalb des Skill-Ordners im Nutzer-Cache-Verzeichnis und
meldet sein Alter in jeder Ausgabe.

## Externe Bezugsquellen (`sources/EXTERN.md`)

Die Allowlist. Erreichbar ist ausschließlich, was hier namentlich steht; es
gibt keinen Codepfad, der ein Ziel aus einer Anfrage, einem Dokument oder
einer Antwort übernimmt. Acht Spalten:
`ID | Titel | Art | Ziel | Stand/Version | Bindungsschlüssel | Trust | Rechte`.

* `Art` ist `markdown-tree` oder `skillsafe-vault`. Ein fremder Tresor wird
  als **Daten** gelesen; sein `MANIFEST.sha256` rechnet diese Engine selbst
  nach, sein `scripts/vault.py` wird niemals ausgeführt.
* `Ziel` ist ein festes `https://`-Präfix oder `-` für eine lokale Quelle.
  `http`, Query, Fragment, Zugangsdaten im Host und `..` sind verboten. Ein
  absoluter lokaler Pfad steht hier nie — er gehört in die Bindung.
* `Bindungsschlüssel` ist `[a-z0-9][a-z0-9-]{0,63}` und tresorweit eindeutig.
* Bei `skillsafe-vault` nennt `Stand/Version` zusätzlich genau einen Scope aus
  `organisation`, `fachbereich`, `projekt`, `persoenlich` — Grundlage der
  Rangfolge aus `references/mehrere-tresore.md` §8. Der Scope wird berichtet,
  nie in das Ranking eingerechnet.

Eine aufgeführte Quelle ohne Anker und ohne Katalog ist eine Warnung: sie
trägt nichts.

## Satzanker (`sources/derived/X-nnnn__anchors.json`)

Schema `skillsafe.anchors/v1`, das textuelle Gegenstück zu Medienregionen.
Alle Felder sind Pflicht, unbekannte Schlüssel sind Fehler.

```json
{
  "schema": "skillsafe.anchors/v1",
  "source_id": "X-0001",
  "source_kind": "markdown-tree",
  "segmentation": "satzsegmentierung/v1",
  "language": "de",
  "extractor": {"kind": "human", "name": "lokale Sichtprüfung", "version": "1"},
  "verified": true,
  "anchors": [
    {
      "id": "A-0001",
      "document": "handbuch/mietminderung.md",
      "document_sha256": "<sha256 des Dokuments>",
      "sentence_index": 4,
      "block": "absatz",
      "locator": "Abschnitt \"Voraussetzungen\", Satz 2",
      "text": "Der zitierte Satz, nach satzsegmentierung/v1 normalisiert.",
      "text_sha256": "<sha256 über text>",
      "suspicious_instruction": false
    }
  ]
}
```

`block` ist `absatz`, `listenpunkt`, `tabellenzelle`, `ueberschrift` oder
`zitat`. `document` wird lexikalisch geprüft und wirkt damit auch ungebunden.
`verified` muss vor einem Release `true` sein. `text_sha256` macht den Anker
selbstprüfend; `sentence_index` ist nur ein Hinweis, deshalb ist Drift eine
Warnung und kein Fehler.

Wie Region-`text` bleibt Anker-`text` **untrusted** und ist nie Evidenz. Der
Query-Pfad gibt nur Anker-ID, Dokument, Satzposition und Digest aus.

## Satzsegmentierung `satzsegmentierung/v1`

Der Satzindex ist Teil des Ankers, also braucht die Zerlegung einen
versionierten, deterministischen Algorithmus:

* YAML-Frontmatter und eingezäunte Codeblöcke werden **vor** der Zerlegung
  entfernt — sie enthalten keine Sätze und würden Indizes verschieben.
* Jede Blockgrenze beendet einen Satz: Absatz, Listenpunkt, Tabellenzelle,
  Überschrift, Zitat. Ein Satz überschreitet nie eine Blockgrenze.
* Kein Satzende nach Abkürzung, Einzelbuchstabe, reiner Ziffernfolge,
  `§`-Nummer oder einem auf eine Ziffer endenden Token (`v0.2`).
* `sentence_index` ist 1-basiert je Dokument.
* Normalisierung zum Hashen ist **NFC** plus kollabierter Whitespace —
  bewusst nicht das NFKC des Retrievals: NFKC faltet Ligaturen und
  Formatzeichen und verändert damit den Wortlaut. Zwei Normalisierungen,
  zwei Zwecke, beide versioniert.

## Orchestrator (`sources/derived/X-nnnn__orchestrator.json`)

Schema `skillsafe.orchestrator/v1`, nur für `markdown-tree`. Der Katalog ist
**Daten**, kein zweites Script (AD-09): eine `.json`, die `vault.py` liest.

```json
{
  "schema": "skillsafe.orchestrator/v1",
  "source_id": "X-0001",
  "segmentation": "satzsegmentierung/v1",
  "generated_from_sha256": "<sha256 über 'pfad\\0hash\\n' aller Dokumente>",
  "document_count": 4,
  "documents": [
    {
      "path": "handbuch/mietminderung.md",
      "sha256": "<sha256>",
      "title": "Mietminderung bei Mängeln",
      "summary": "Regelt Mangelbegriff, Anzeigepflicht und Minderungsquote.",
      "tags": ["miete", "minderung", "mangel"],
      "sentence_count": 11,
      "token_count": 62,
      "top_tokens": ["minderung", "mangel"]
    }
  ]
}
```

`document_count` muss `len(documents)` entsprechen — bewusst redundant, damit
eine abgeschnittene Datei auffällt. Alle Zahlenfelder sind nachrechenbar und
kommen aus dem Script; `title`, `summary` und `tags` sind Modellarbeit. Genau
diese Trennlinie ist der Prüfpunkt.

Das Ranking `extern-zweistufig/v1` nutzt den Katalog nur als Prefilter
(Stufe 1) und rechnet Stufe 2 immer gegen den **jetzt gelesenen** Text. Ein
Dokument ohne einen einzigen Anfragebegriff als ganzes Token fällt heraus,
unabhängig vom Katalog-Score. Abgeglichen wird ausschließlich an
Tokengrenzen; Substring-Treffer sind strukturell ausgeschlossen.

## Bindung (`.vault-extern.json`)

Schema `skillsafe.bindung/v1`, **nicht manifestiert, nicht paketiert,
gitignoriert** — dieselbe Sonderstellung wie `log.md`, aus demselben Grund:
Sie enthält absolute Pfade dieses Hosts, und die sagen nichts über das
Artefakt.

```json
{
  "schema": "skillsafe.bindung/v1",
  "bindings": [
    {"key": "beispiel-handbuch", "source_id": "X-0001",
     "root": "/absoluter/pfad", "bound_at": "2026-08-06"}
  ],
  "cache_ttl_seconds": 21600
}
```

Nur lokale Quellen stehen hier; eine Netzquelle ist durch ihre Registrierung
gebunden. Eine fehlende Bindung ist **nie** ein Validierungsfehler —
ungebunden ist der Normalzustand eines frisch entpackten Pakets.

Die Bindungswurzel ist die einzige Stelle im System, an der ein absoluter
Pfad zulässig ist. Sie muss kanonisch und symlinkfrei sein, darf den Tresor
weder enthalten noch in ihm liegen, keine andere Wurzel überlappen und keine
Mount-Grenze überschreiten. Gelesen werden nur reguläre Dateien; Budgets für
Tiefe, Einträge, Dokumentzahl und Bytes werden **gezählt**, nie über eine Uhr
gestoppt — ein Zeitlimit bräche die Determinismus-Garantie.

## Quellenregister und Pfadgrenzen

`sources/REGISTER.md` hat sieben Spalten:
`ID | Titel | Stand/Version | SHA-256 | Trust | Rechte | Ablage`.
Trust ist `T1`, `T2` oder `T3`; Rechte müssen eindeutig benannt sein. Die
Ablage ist genau eine reguläre Datei direkt unter `sources/raw/`, deren Name
mit der S-ID beginnt. Absolute Pfade, `..`, Backslashes, Unterordner,
Mehrfachregistrierungen, Symlinks, Junctions/Reparse-Points und Hardlinks
sind verboten.

Jede Seitenrelation zeigt exakt auf eine validierte Markdown-Seite
`domäne/seite.md`. Lokale Markdown-Links bleiben innerhalb derselben Domäne.
Referenzlinks werden wie Inline-Links geprüft; rohe HTML-Links liegen
außerhalb der unterstützten Untermenge.
