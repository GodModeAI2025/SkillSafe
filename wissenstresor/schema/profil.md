# Profil oksv-lite/1.1 — Datenvertrag des Wissenstresors

OKF v0.1 verlangt nur `type`. Dieses Profil ist bewusst strenger, bleibt aber
OKF-kompatibel: alles Zusätzliche liegt in flachem Frontmatter, Claims oder
separaten JSON-Registries. `scripts/vault.py validate` erzwingt den Vertrag
fail-closed; unbekannte Felder und JSON-Schlüssel sind Fehler.

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

Frontmatter nutzt nur Skalar, Inline-Liste und Bindestrich-Liste. Kein
Nesting. Listenfelder müssen tatsächlich als Liste geschrieben werden.

## Claim-Grammatik

```text
- **C-nnnn** [S-nnnn | Fundstelle | Wortlaut|Beobachtung|Auslegung] Aussagetext.
```

* `C-nnnn` ist tresorweit eindeutig.
* `S-nnnn` steht im Register und im `sources`-Feld der Seite.
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
beweis. Keine Embeddings, kein Netzwerk, kein Cache im Skill.

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
