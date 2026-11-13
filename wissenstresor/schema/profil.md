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

Ebenso fail-closed prüft `validate` alle manifestierten `.md`-, `.json`- und
`.yaml`-Dateien auf Zugangsdaten: private Schlüsselblöcke, Cloud- und
Plattform-Token in ihren festen Präfixformen, JWTs und URLs mit Benutzer und
Passwort. Die Muster sind bewusst eng statt heuristisch, denn jeder Treffer
blockiert den Release. Gemeldet werden Datei, Zeile und Form, **nie der
Treffer selbst**, damit das Geheimnis nicht über Log oder CI-Ausgabe
weiterwandert. Erkennbare Doku-Platzhalter (`ghp_xxxx…`, Schlüssel mit
`EXAMPLE`, das Beispiel-JWT von jwt.io, `user:password@` oder `${TOKEN}` in
URLs) gelten nicht als Treffer. Liegt es in einer Rohquelle, wird die Quelle geschwärzt und
neu registriert (neuer Hash); ein Wissensinhalt, der ein Zugangsdatum
braucht, gehört nicht in einen portablen Tresor. Medien werden dabei nicht
dekodiert.

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
  Titel, Tags, Kurzfassung und Registerangaben prüft der Stolperdraht nicht;
  sie sind kuratierter Text, und die Vollsichtung gibt Titel und Tags jeder
  Seite mit aus.
* Eine Wissensseite liegt nie unter einem Pfad, den das Manifest ausnimmt
  (`__pycache__`). Ihr Wortlaut wäre sonst nach dem Release änderbar, ohne
  dass Sperre oder Siegel es bemerken.

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
  anhand der Claims beurteilt, nicht vom Ranking behauptet. Wie belastbar die
  Kandidaten sind, sagt `coverage.match_strength` (siehe „Trefferstärke");
* `no_candidates` — das deterministische Ranking fand keinen Kandidaten,
  Evidenz bleibt leer und `semantic_coverage` bleibt `not_assessed`;
  die Vollsichtung ist Pflicht. `fallback.sweep` nennt ihren Aufwand.
  `fallback.page_paths` war die Arbeitsliste des früheren Rückfalls („alle
  Seiten lesen") und bleibt als Feld bestehen, nennt aber höchstens 50
  Seiten; `fallback.page_paths_total` zählt alle. Maßgeblich ist die
  Vollsichtung, nicht diese Liste.
  `fallback.external_lookup_available` sagt zusätzlich, ob überhaupt externe
  Bezugsquellen aufgeführt sind — das Feld steht auch ohne `--extern`, weil
  der Antwort-Workflow daran erkennt, ob nach der Vollsichtung noch ein
  Schritt möglich ist. `fallback.external_live_lookup_used` sagt danach, ob
  tatsächlich live gelesen wurde. Zwei Felder, zwei Fragen: Angebot und
  Ergebnis;
* `ambiguous` — Alias ist über Begriffswelten mehrdeutig;

Der Block `external` führt eigene Zustände, damit der Top-Level-`state` für
bestehende Konsumenten eingefroren bleibt: `not_requested`, `not_declared`,
`not_bound`, `external_candidates_found`, `no_external_candidates`,
`budget_exceeded`, `unreachable`, `invalid_external_source` und
`invalid_query`. Der letzte greift, wenn `--source` eine nicht aufgeführte
ID nennt: Dann wird **nichts** durchsucht, und das Ergebnis ist ausdrücklich
kein Negativbefund.
* `invalid_query`, `invalid_vault`, `vault_busy`, `snapshot_changed` —
  fail-closed, immer ohne Evidenz.

Das Ranking `hybrid-local/v4` verwendet ausschließlich Ganzzahlen:
kontrollierte Begriffe/Aliase, lexikalische Token-Treffer, Wortformen nach
`wortform/v1` und höchstens einen Graph-Hop. `retrieval_complete` bedeutet
nur, dass dieser Ranking-Scan alle validierten Claims gesehen hat; es ist
kein semantischer Vollständigkeitsbeweis. Den liefert allein die
Vollsichtung, und auch sie nur in dem Sinn, der unter „Vollsichtung" steht.

Keine Embeddings, niemals. Auf dem **Default-Query-Pfad** verlässt außerdem
kein Byte den Skill-Ordner: kein Netzwerk, kein Dateizugriff nach außen, kein
Cache. Erst das ausdrückliche `--extern` liest aufgeführte externe
Bezugsquellen — dann live, gekennzeichnet und in einem eigenen Block. Im
**manifestierten Bestand** gibt es weiterhin keinen Cache; der TTL-Abzug einer
Netzquelle liegt außerhalb des Skill-Ordners im Nutzer-Cache-Verzeichnis und
meldet sein Alter in jeder Ausgabe.

### Wortform `wortform/v1`

Ein Fragebegriff trifft einen Bestandsbegriff auf einer von drei Stufen. Die
Stufe steht als Grund am Treffer und trägt ein eigenes Gewicht:

| Stufe | Grund | Trifft | Claim | Kontext der Seite | Seite: Titel / Tag / Claim |
|---|---|---|---|---|---|
| exakt | `token:` | dasselbe Token | 20 | 10 | 30 / 24 / 12 |
| Wortform | `stem:` | dieselbe Wortform-Familie | 16 | 8 | 24 / 20 / 10 |
| Kompositum | `compound:` | Kopf oder Schwanz eines zusammengesetzten Worts | 12 | 6 | 12 / 10 / 5 |

„Kontext der Seite" bekommt ein Claim, wenn Titel oder Tags seiner Seite den
Begriff tragen und er selbst nicht (`page-token:`, `page-stem:`,
`page-compound:`). Die Staffel hält eine Ordnung je Fragebegriff fest: Ein
Claim, der den Begriff selbst trägt, steht vor einem, der denselben Begriff
nur von seiner Seite erbt, und beide vor dem reinen Graph-Nachbarn (5). Über
mehrere Begriffe summiert sich Geerbtes, und die Seite eines direkt
getroffenen kuratierten Begriffs hebt jeden ihrer Claims um 100 Punkte
(`concept-page`): Reiner Kontext einer Begriffsseite kann deshalb vor einem
einzelnen Worttreffer einer anderen Seite stehen. Das ist gewollt, und die
Nachrück-Regel unten sorgt dafür, dass der Worttreffer trotzdem nicht fehlt.

Die Wortform-Familie wird aus dem normalisierten Token gebildet: Umlaut-
Digraphen falten (`ae`→`a`, `oe`→`o`, `ue`→`u`), dann höchstens dreimal die
erste passende Endung aus `en`, `em`, `er`, `es`, `e`, `n`, `s` entfernen,
dann einmal `-ung` und danach erneut die Endungen. Der Reststamm behält
mindestens drei Zeichen, bei `-er`, `-em` und `-ung` vier; ein `-s` fällt nur
nach `b c d f g h k l m n p r t v w`, damit „Prozess" und „Status" ganz
bleiben. Tokens unter vier Zeichen und Tokens mit Ziffern bleiben
unverändert. So finden „Wände" und „Wand",
„Vertrauensstufen" und „Vertrauensstufe", „Prüfungen" und „prüfen"
zueinander.

Ein Kompositumteil zählt nur am Wortanfang oder Wortende, und beide Seiten
der Nahtstelle brauchen mindestens vier Zeichen. „Miete" findet
„Mietminderung", „Nachweis" den „Herkunftsnachweis"; „himmel" findet nie
„schimmel", weil der Rest „sc" kein Wortteil ist. Ein Wörterbuch gibt es
nicht, deshalb bleibt die Stufe schwach und zählt nie als verstandener
Begriff.

**Nicht geleistet**, und zwar mit Absicht: Partizipien („geprüft"), finite
Verbformen auf `-t` („bestätigt"), unregelmäßige Formen („gilt"/„gelten"),
`-heit`, `-keit`, `-lich`. Und vor allem keine Bedeutung: „nasse Wände" findet
auf keiner Stufe den „Schimmelbefall". Was hier nicht trifft, steht als
`unmatched` im Ergebnis.

**Kollisionen**, ebenfalls ausgeschrieben: Die Faltung trifft jede Folge
`ae`, `oe`, `ue`, nicht nur Umlaute. „Förderung" und „Forderung" fallen
dadurch in eine Familie, „zählen" und „zahlen" ebenso; umgekehrt wird aus
„neuer" ein „neur", das „neu" nicht mehr findet. Ein solcher Treffer zählt
wie jeder Wortform-Treffer als verstanden und kann eine Frage `strong`
machen. Er trägt seinen Grund (`stem:`), und er ist ein Kandidat, nie ein
Beleg für die Bedeutung.

Funktionswörter (Artikel, Pronomen, Präpositionen, Konjunktionen, Hilfs- und
Modalverben, Partikeln) zählen im lokalen Ranking nicht als Fragebegriff. Die
Liste ist eine eigene und lässt die ältere Stoppwortliste unberührt, an der
`extern-zweistufig/v1` und die nachrechenbaren Katalogzahlen hängen.
Homographen wie „Macht"/„macht" gelten als Funktionswort; als kuratierte
Benennung einer Begriffswelt bleiben sie exakt auffindbar, weil Begriffe
gegen die ungefilterte Frage abgeglichen werden. Eine Abkürzung in
Großbuchstaben ist nie ein Funktionswort: „die IT" ist nicht das englische
„it". Erkannt wird sie in gemischt geschriebenem Text und als einzelnes
Wort; wer einen ganzen Satz groß schreibt, meint keine Abkürzungen.
Englische Einträge, die nach der Normalisierung ein deutsches Hauptwort
wären („Not", „All", „Most", „Same"), führt die Liste nicht.

Begriffe einer Begriffswelt werden zuerst exakt, sonst über die Wortform
ihrer Benennung getroffen (`concepts.matched[].match` ist `exact`,
`wortform` oder `id`). Die exakte Stufe hat Vorrang: Ist eine Phrase exakt
getroffen, zieht ihre Wortform keinen zweiten Begriff herein. Die
Wortform-Stufe trifft eine Benennung nur über Inhaltswörter: Mindestens eines
muss sie tragen, und ein Funktionswort der Frage zählt dabei nur wörtlich.
„sich" benennt deshalb nicht „Sicherung" und „seit" nicht „Seite"; eine
Benennung, die selbst nur aus Funktionswörtern besteht, ist ausschließlich
exakt auffindbar. Treffen zwei
Welten nur über die Wortform, ist die Frage `ambiguous`; innerhalb einer
Welt gelten beide Begriffe als getroffen. Der `definition_claim` eines direkt
getroffenen Begriffs bekommt 40 Punkte (`concept-definition:B-nnnn`). Trägt
eine einwortige Benennung einen Fragebegriff nur als Kompositumteil, steht der
Begriff in `concepts.partial`: ein Fingerzeig mit 40 Punkten für die Seite
und 10 für ihre Claims (`concept-page:partial`), ohne Begriffserweiterung und
nie ein Anker. Der Fragebegriff selbst steht dann unter
`query_terms.partial`. Mit 10 Punkten liegt der Fingerzeig wie jeder geerbte
Treffer unter dem kleinsten eigenen (12); bis `hybrid-local/v2` waren es 30,
und die gestreifte Begriffsseite drängte Claims mit dem Fragewort selbst aus
dem Limit.

### Trefferstärke

Das Ranking gibt an, wie viel der Frage es erkannt hat. Gerechnet wird nur
über das, was es tatsächlich ausgibt:

* `coverage.query_terms.content` — die Fragebegriffe: Inhaltstokens ohne
  Funktionswörter und ohne die Ziffern genannter IDs, sofern es die ID im
  Bestand gibt. Eine vertippte oder fremde ID bleibt als Wort stehen und
  steht dann unter `unmatched`; `coverage.unknown_ids` nennt sie zusätzlich
  im Wortlaut (C- und S-IDs, die es nicht gibt, sowie B-IDs, die es nicht
  oder nicht in der gewählten Welt gibt). Das ist ein Befund des Scripts,
  kein Urteil des Rankings; was daraus für die Antwort folgt, regelt
  `references/antworten.md` in Schritt 2b. Stehen die Ziffern zufällig
  irgendwo im Bestand („S-2026" und eine Jahreszahl), gelten sie als
  getroffenes Wort; verstanden ist die Kennung damit nicht, und das
  Ergebnis ist mit einer unbekannten Kennung nie `strong`;
* `.matched` — exakt oder als Wortform getroffen, in einem **ausgegebenen**
  Claim, in Titel oder Tags seiner Seite, oder als Teil einer getroffenen
  Benennung, deren Begriff in der Ausgabe **vertreten** ist: durch einen
  Claim einer seiner Seiten oder durch seinen Definitions-Claim;
* `.partial` — nur als Kompositumteil getroffen: in einem ausgegebenen
  Claim, in Titel oder Tags seiner Seite, oder in einer Benennung
  (`concepts.partial`). Zur Abdeckung zählt er nicht;
* `.unmatched` — nirgends getroffen. Ein Begriff, den nur ein gekürzter
  Kandidat trägt, steht hier: das Modell hat ihn nicht gesehen. Die Gründe
  unter `pages[].reasons` beschreiben dagegen die ganze Seite samt ihrer
  gekürzten Claims und können einen solchen Begriff deshalb nennen;
* `coverage.term_coverage_percent` — Anteil von `matched` an `content`,
  ganzzahlig abgerundet; ohne Fragebegriff 100 mit Anker, sonst 0.

Ein **Anker** ist ein direkt getroffener und in der Ausgabe vertretener
Begriff, eine genannte und vorhandene C- oder S-ID an einem ausgegebenen
Claim, oder die ganze Frage als Phrase in einem Claim, sofern dabei
mindestens ein Inhaltswort getroffen ist. Eine Frage nur aus Funktionswörtern
(„nicht", „und") steht wörtlich in vielen Claims und ist deshalb nie
`strong`; dasselbe gilt für eine Abkürzung wie „IT", die im Bestand nur als
englisches „it" einer Fundstelle vorkommt.

Jeder direkt getroffene Begriff unter `concepts.matched` trägt
`represented`: wahr, wenn ein ausgegebener Claim auf einer seiner Seiten liegt
oder sein Definitions-Claim ist. Ein Begriff kann unvertreten bleiben, wenn
das Limit knapp ist und kein reiner Kontext-Kandidat weichen kann.

Zum Text eines Claims zählt beim Abgleich seine Fundstelle. Wer nach „§ 4"
oder einer Anker-ID fragt, findet so die Claims, die dort belegt sind; ein
Fragebegriff, der nur in der Fundstelle steht, gilt deshalb als getroffen.

| `coverage.match_strength` | Bedingung |
|---|---|
| `none` | kein Kandidat |
| `strong` | Abdeckung 100 %, jeder direkt getroffene Begriff ist vertreten, und die Frage nennt keine unbekannte Kennung |
| `partial` | nicht `strong`, aber ein Anker, oder mindestens zwei getroffene Begriffe bei mindestens 60 % |
| `weak` | alles andere |
| `null` | nicht bewertet: Fehlerzustand (`invalid_query`, `ambiguous`, `invalid_vault`, `vault_busy`, `snapshot_changed`) |

`fallback.exhaustive_review_required` ist genau bei `weak` und `none` wahr,
`fallback.reason` dann `weak_candidates_only` oder
`no_retrieval_candidates`. Der Top-Level-`state` bleibt davon unberührt und
eingefroren. Ein Fehlerzustand ist kein „kein Kandidat": Dort ist die Stärke
`null` und die Pflicht-Vollsichtung kein Thema, weil es nichts zu sichten
gibt, solange der Fehler besteht.

`strong` heißt: das Ranking hat jedes Wort der Frage wiedererkannt, zeigt zu
jedem genannten Begriff etwas und kennt jede genannte Kennung. Die beiden
letzten Bedingungen gelten seit `hybrid-local/v4`; bis v3 konnte ein per ID
genannter Begriff in der Ausgabe fehlen und eine unbekannte Kennung über ihre
Ziffern als verstanden gelten. Es heißt
nicht, dass die Kandidaten die Frage beantworten, und es erlaubt nie ein
„Nicht im Bestand". Auch eine Frage nach etwas, das der Bestand nicht enthält,
kann `strong` sein, wenn sie nur bekannte Wörter benutzt.

`coverage.candidates` zählt `total`, `returned`, `omitted_direct` und
`omitted_context`. Direkt ist ein Kandidat, der den Treffer selbst trägt
(eigener Begriffstreffer, ID, Phrase, Definition); Kontext ist, wer nur über
seine Seite hereinkam. `coverage.omitted_pages` nennt bis zu 20 Seiten, deren
direkte Kandidaten dem Limit zum Opfer fielen und die nicht unter `pages`
stehen, je mit `path`, der Zahl ihrer gekürzten direkten `claims` sowie
`best_claim` und `best_score` des besten davon; gibt es mehr, ist
`coverage.omitted_pages_truncated` wahr. Ein unvertretener Begriff steht
dort mit der Seite seines Definitions-Claims, denn der ist ein direkter
Kandidat. Eine leere
Liste bei `omitted_direct` größer null heißt: Jeder gekürzte direkte Kandidat
liegt auf einer Seite, die ohnehin unter `pages` steht und ganz gelesen wird.

Jede Seite unter `pages` trägt `relations` mit den Listen `outgoing` und
`incoming`: ihre typisierten Kanten als `{"type", "page"}`, sortiert nach Typ
und Pfad. Ausgehende Kanten stehen im Frontmatter der Seite, eingehende nur
auf der jeweils anderen; ohne diese Angabe sähe niemand an einer überholten
Seite, welche sie ersetzt. Die Angabe ist ein Verweis: Sie hebt keinen Rang,
macht die Nachbarin nicht zur Evidenz und geht in keinen Fingerabdruck ein.
Dasselbe Feld tragen die Seiten einer Quittung der Vollsichtung, dort über
den ganzen Bestand gerechnet, auch wenn der Umfang eingeschränkt war.

**Kontext weicht, Treffer nie.** Nachgerückt wird in zwei Durchgängen,
erst für Begriffe, dann für Wörter. Ist ein direkt getroffener Begriff in der
Auswahl nicht vertreten, rückt der beste gekürzte Kandidat nach, der auf
einer seiner Seiten liegt oder ihn definiert. Trägt die Auswahl danach einen
Fragebegriff nicht, rückt der beste gekürzte Kandidat nach, der ihn als Wort
oder Wortform selbst trägt; ein bloßer Wortteil (`compound:`) genügt dafür
nicht, weil er zu oft Zufall ist. In beiden Fällen weicht der rangniedrigste
reine Kontext-Kandidat, dessen Seite auch ohne ihn vertreten bleibt. Ein
Kandidat mit eigenem Treffer wird nie verdrängt. Gibt es keinen Kontext zum
Weichen, bleibt die Rangfolge stehen, der Begriff gilt als ungetroffen und
die Kürzung wird gemeldet.

Die Auswahl ist im Limit nicht monoton. Bei größerem `--limit` kann ein
Kontext-Kandidat von selbst hereinrücken, dessen Seite einen Fragebegriff im
Titel trägt; dann gilt der Begriff als getragen, und der Claim mit eigenem
Treffer, den das kleinere Limit nachgezogen hatte, wird nicht mehr
nachgezogen. Seine Seite steht in beiden Fällen unter `pages` oder
`omitted_pages`.

**Gründe und Exit-Codes.** Zu den Gründen an einem Treffer gehören neben den
genannten `concept-page` (Seite eines direkt getroffenen oder erweiterten
Begriffs), `concept-page:partial` (Fingerzeig), `concept-definition:B-nnnn`,
`id:C-nnnn` und `id:S-nnnn`, `exact:claim`, `graph:one-hop` und in einer
Quittung der Vollsichtung `sweep:selected`. `coverage.wortform` nennt das
Wortform-Profil. `query` endet mit 0 bei `candidates_found` und
`no_candidates`; mit 2 bei `ambiguous` und bei unzulässigem `--world` oder
`--limit`; mit 1 bei gesperrtem Tresor und bei leerer oder zu langer Frage.
`sweep` endet mit 0 bei `plan`, `batch` und `sweep_complete`; mit 2 bei
`sweep_incomplete`, `invalid_receipt`, fehlender Frage und unzulässigen
Schaltern; mit 1 bei gesperrtem Tresor und zu langer Frage. Maßgeblich ist
immer `state`, nicht der Exit-Code.

## Vollsichtung (`sweep`)

Schema `skillsafe.sweep/v1`. Die Vollsichtung ist die Bedeutungssuche des
Tresors: Sie legt jeden Claim eines Umfangs vor, das Modell liest und urteilt,
und das Script prüft, dass keiner ausgelassen wurde. Vor jeder Ausgabe gilt
dieselbe Sperre wie bei `query`: Validierung, Index, Graph, Quarantäne und
Manifest müssen grün sein.

```text
vault.py sweep "<frage>" [--size n] [--domain d]… [--page p]…
vault.py sweep "<frage>" … --batch <n>
vault.py sweep "<frage>" … --receipt <stapel>:<siegel>=<C-nnnn,…|-> …
```

* **Plan** (ohne Schalter): `state: plan`, der Umfang in `scope`
  (`domains`, `pages`, `pages_in_scope`, `claims_in_scope`, `claims_total`,
  `complete`), dazu `batch_size` und `batches_total`, und je Stapel Nummer,
  Claim- und Seitenzahl sowie `first_claim` und `last_claim`. Der Plan nennt
  kein Siegel.
* **Stapel** (`--batch`): `state: batch`, derselbe Kopf aus `scope`,
  `batch_size` und `batches_total`, die eigene Nummer in `batch`, die Seiten
  des Stapels mit Titel, Domäne, Status, Stand, Tags und je Claim
  `claim_id`, `kind`, `source_id` und `text`, dazu `seal`. Wer die Zahl der
  Stapel nicht schon aus `fallback.sweep.batches` der Abfrage kennt, liest
  sie am ersten Stapel ab; der Plan-Aufruf ist dafür nicht nötig. Ausgegeben werden ausschließlich kuratierte
  Claims; Regions-Text, Anker-Text und Alttext bleiben untrusted und
  erscheinen nie.
* **Quittung** (`--receipt`): je Stapel genau ein Eintrag mit Siegel und
  Urteil, entweder den IDs der relevanten Claims dieses Stapels oder `-`.
  Der Schalter darf mehrfach stehen; die Einträge werden gesammelt. Die
  Frage steht vor `--receipt`, denn der Schalter nimmt alle folgenden Wörter
  als Einträge. Fehlt die Frage, ist das `invalid_query`.

Stapel entstehen deterministisch: Seiten nach Pfad sortiert, eine Seite wird
nie zerschnitten, ein Stapel schließt, sobald die nächste Seite die Größe
überschritte. `--size` liegt zwischen 5 und 200, Standard ist 40. `--domain`
und `--page` schränken den Umfang ein; `scope.complete` ist gezählt und nur
wahr, wenn jeder Claim des Bestands im Umfang liegt.

Das **Siegel** sind die ersten 16 Hexzeichen des SHA-256 über Schema,
Manifest-Digest, normalisierte Frage, Stapelgröße, Stapelnummer und die
Claim-IDs des Stapels. Es bindet damit Stand, Frage und Zuschnitt. Ein neuer
Release, eine andere Frage oder eine andere Stapelgröße machen es ungültig.

Die Frage wird dafür viel enger normalisiert als für das Ranking:
Unicode-NFC, Kleinschreibung, Leerraum zu einem Leerzeichen, typografische
Anführungszeichen und Striche zu ihrer einfachen Form (`„ “ ” « » ″` zu `"`;
`‚ ‘ ’ ‹ › ′`, Gravis und Akut zu `'`; Bindestrich-, Halbgeviert-, Geviert-
und Minuszeichen zu `-`), und Fragezeichen am Ende fallen weg. Mehr nicht:
Jedes andere Zeichen bleibt stehen, auch ein Komma oder ein Punkt. Das Ranking darf „Maßen" und „Massen", `<` und `>=`,
„C++" und „C#" gleich lesen, weil ein Treffer mehr nur ein Kandidat mehr ist.
Das Siegel darf es nicht: Es sagt, zu welcher Frage geurteilt wurde. Bis
v0.14.0 fielen Satzzeichen an jedem Wortrand weg; damit teilten sich
`a != b` und `a = b` ein Siegel, ebenso `.5` und `5`.

Zustände der Quittungsprüfung:

* `sweep_complete` — jeder Stapel des Umfangs trägt ein gültiges Siegel und
  ein Urteil. `evidence` enthält die ausgewählten Claims in derselben Form
  wie bei `query`, mit Rolle `sweep_selected`; `pages` ihre Seiten;
  `coverage.semantic_coverage` ist `swept`; `sweep_fingerprint` fasst Stand,
  Frage, Siegel und Auswahl zusammen;
* `sweep_incomplete` — Stapel fehlen, `missing_batches` nennt sie;
* `invalid_receipt` — falsches Siegel, doppelter oder unbekannter Stapel,
  Claim aus einem anderen Stapel, kaputte Form;
* `invalid_query` — unbekannte Domäne oder Seite, Größe oder Stapelnummer
  außerhalb des Zulässigen. Ausdrücklich kein Negativbefund.

`selected`, `evidence` und `abstention` stehen in jeder Ausgabe von `sweep`,
auch im Plan, im Stapel und in den Sperrzuständen `invalid_vault`,
`vault_busy` und `snapshot_changed`. Außer bei `sweep_complete` sind
`evidence` und `selected` leer und `abstention.allowed` ist falsch.

`abstention.allowed` ist die mechanische Vorbedingung für „Nicht im
Bestand": wahr nur bei `sweep_complete` **und** `scope.complete`. Ein
eingeschränkter Umfang erlaubt höchstens „in diesem Umfang nicht gefunden".
Ob die ausgewählten Claims die Frage decken, beurteilt das Modell; das Feld
ist eine Erlaubnis, kein Befund.

**Was die Quittung belegt und was nicht.** Sie belegt, dass jeder Stapel für
genau diesen Stand und genau diese Frage ausgegeben wurde und dass zu jedem
ein ausdrückliches Urteil vorliegt. Sie belegt nicht, dass sorgfältig gelesen
wurde. Das Siegel schützt gegen Abkürzen und Vergessen, nicht gegen einen
Leser, der vorsätzlich täuscht: Wer die Stapelausgabe in eine Datei umleitet
und nur das Siegel herauszieht, hält eine gültige Quittung über nichts.

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
eine abgeschnittene Datei auffällt.

**Prüfsummen nur dort, wo sie wahr bleiben können.** `generated_from_sha256`
und `documents[].sha256` sind bei einer **lokalen** Quelle Pflicht: Der Baum
ist greifbar, der Hash ist überprüfbar. Bei einer **Netzquelle** müssen beide
`null` sein. Ein registriertes Präfix zeigt auf einen beweglichen Ref; ein dort
eingefrorener Hash ist nach dem nächsten fremden Commit unwahr und nur noch
endlos nachziehbar — also eine Zahl im Bestand, die etwas Falsches behauptet
und dabei richtig aussieht. Ein Katalog behauptet nichts, was er nicht halten
kann. `validate` erzwingt die Regel in **beide** Richtungen; eine Regel, die
nur eine Richtung prüft, ist keine.

Das kostet nichts: Der Katalog ist ausschließlich Prefilter, Stufe 2 rechnet
immer gegen den jetzt gelesenen Text, und die Drift-Erkennung läuft über die
Satzanker, nicht über den Katalog. Alle Zahlenfelder sind nachrechenbar und
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
Pfad zulässig ist. Sie wird beim Binden **aufgelöst** und in aufgelöster Form
gespeichert — nicht abgelehnt, wenn sie über einen Symlink führt: Auf macOS
ist `/var` selbst ein Symlink auf `/private/var`, und das Betriebssystem
liefert Temporärpfade so aus. Die tragende Zusage ist nicht „die Eingabe war
kanonisch", sondern „gearbeitet wird auf einer vollständig aufgelösten Wurzel,
und darunter wird nie einem Link gefolgt". Sie darf den Tresor weder enthalten
noch in ihm liegen, keine andere Wurzel überlappen und keine Mount-Grenze
überschreiten. Gelesen werden nur reguläre Dateien; Budgets für
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
