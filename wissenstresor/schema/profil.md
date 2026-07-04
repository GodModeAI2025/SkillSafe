# Profil oksv-lite/1.0 — Datenvertrag des Wissenstresors

OKF v0.1 verlangt nur `type`. Dieses Profil ist bewusst strenger, bleibt aber
OKF-kompatibel: alles Zusaetzliche liegt in Frontmatter-Feldern und einer
festen Claim-Grammatik. Der Validator (`scripts/vault.py validate`) erzwingt
jedes Feld dieses Vertrags — nichts davon ist Konvention, alles ist Pruefung.

## Frontmatter (Pflichtfelder jeder Wissensseite)

| Feld | Werte | Zweck |
|---|---|---|
| `type` | Eintrag aus `schema/types.yaml` | Fail-closed: unbekannter Typ stoppt Ingest (Type-Onboarding) |
| `title` | Freitext | Anzeige in INDEX und Graph |
| `domain` | = Ordnername unter `knowledge/` | Quellentrennung ist baulich, nicht stilistisch |
| `status` | `aktiv` / `veraltet` / `in-pruefung` | Supersession sichtbar machen |
| `confidence` | `hoch` / `mittel` / `niedrig` | Belastbarkeit; steuert Formulierung der Antwort |
| `version` | SemVer `x.y.z` | Aenderungsklassen nachvollziehbar |
| `stand` | `JJJJ-MM-TT` | Jede Antwort nennt den Stand |
| `sources` | Liste von `S-nnnn` | Nur registrierte Quellen; Register prueft Hash der Ablage |
| `tags` | Liste | Suche und Router-Pflege |
| `relations` | Liste `typ -> domaene/seite.md` | Typisierte Graph-Kanten; einziger erlaubter Weg ueber Domaenengrenzen |

Frontmatter nutzt eine flache Profil-Untermenge von YAML (Skalar, Inline-Liste,
Bindestrich-Liste). Kein Nesting — damit genuegt genau ein einfacher,
deterministischer Parser, und jede Datei bleibt in jedem Editor trivial lesbar.

## Claim-Grammatik (belegpflichtige Aussagen)

```
- **C-nnnn** [S-nnnn | Fundstelle | Wortlaut|Auslegung] Aussagetext.
```

* `C-nnnn` — tresorweit eindeutige Claim-ID (Validator prueft Kollisionen).
* `S-nnnn` — Quelle; muss im Register UND im `sources:`-Feld der Seite stehen.
* `Fundstelle` — so praezise wie moeglich: Abschnitt, Seite, Absatz.
* `Wortlaut` — die Aussage gibt den Quellinhalt wieder (Paraphrase nah am Text).
* `Auslegung` — eigene Einordnung/Schlussfolgerung. Wird in Antworten immer
  als solche markiert und nie mit dem Wortlaut der Quelle verwechselt.

## Abschnitte einer Wissensseite

1. `## Kurzfassung` — 3–6 dichte Saetze. Das ist die Schicht, der zur
   Abfragezeit vertraut wird (Kompressionsregel). Jede Kernaussage der
   Kurzfassung muss durch einen Claim gedeckt sein (prueft der Lint).
2. `## Claims` — die belegten Einzelaussagen in obiger Grammatik.
3. `## Kontext und Grenzen` — optional: Geltungsbereich, offene Punkte.

## Quellenregister (`sources/REGISTER.md`)

Spalten: `| ID | Titel | Stand/Version | SHA-256 | Trust | Rechte | Ablage |`

* **Trust:** `T1` amtlich/primaer · `T2` Hersteller/Sekundaerquelle · `T3` Web/unbestaetigt.
* **SHA-256** ist der Hash der Datei unter *Ablage*; der Validator rechnet nach.
  Aendert sich die Ablage nach Registrierung, schlaegt validate fehl —
  das ist die Pruefsummenlogik: eine neue Version invalidiert alte Hashes.
* **Rechte:** Was darf gespeichert werden? Fuer externe Web-Quellen gilt im
  Zweifel: nur Pointer-Record (URL, Abrufdatum), kein Volltext.
