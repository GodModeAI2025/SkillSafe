---
type: konzept
title: Open Knowledge Format v0.2
domain: demo-okf
status: aktiv
confidence: hoch
version: 1.0.0
stand: 2026-07-28
sources: [S-0004]
tags: [okf, okf-v02, provenienz, vertrauen, lebenszyklus, attestierung, spezifikation]
concepts: [B-0001, B-0005, B-0006, B-0007, B-0008, B-0009]
relations:
  - ersetzt -> demo-okf/okf.md
---

# Open Knowledge Format v0.2

## Kurzfassung
OKF v0.2 löst v0.1 ab und behält dessen Grundform: ein Verzeichnisbaum aus
Markdown-Dateien mit YAML-Frontmatter, `type` als einziges stets
erforderliches Feld. Neu ist eine Schicht maschinenlesbarer
Vertrauenssignale, die alle optional bleiben: `sources` mit
Glaubwürdigkeitssignalen pro Quelle, `generated` und `verified` mit einer
gemeinsamen Aktorkonvention, daraus abgeleitete Trust-Tiers, sowie `status`
und `stale_after` für Geltung und Verfall. Ausdrücklich nicht aufgenommen
wurde ein gespeicherter Glaubwürdigkeitswert, weil er subjektiv und schnell
veraltet ist. Dazu kommt der Konzepttyp `Attested Computation`, der eine
sanktionierte Berechnung samt Ausführungs- und Prüfschnittstelle beschreibt,
ohne dass das Format selbst etwas ausführt. Zwei Bruchstellen sind benannt:
`timestamp` weicht `generated.at`, die Rumpfliste `# Citations` weicht
`sources`.

## Claims
- **C-0301** [S-0004 | §3, §4, §4.1 und §11 | Wortlaut] OKF v0.2 stellt Wissen als Verzeichnisbaum von UTF-8-Markdown-Dateien mit YAML-Frontmatter dar; ein Bundle ist konform, wenn jede nicht reservierte .md-Datei einen parsebaren Frontmatter-Block mit nicht leerem `type` enthält, und `type` bleibt das einzige stets erforderliche Feld.
- **C-0302** [S-0004 | §5.1 | Wortlaut] Provenienz liegt im Frontmatter-Feld `sources`, einer Liste von Einträgen mit dem Pflichtfeld `resource` sowie den optionalen Angaben `id`, `title`, `author`, `usage_count` und `last_modified`; ein `usage_window` als Geschwisterfeld rahmt jeden `usage_count` mit einem Zeitraum aus `from` und `to`.
- **C-0303** [S-0004 | §5.1, Abschnitt Source credibility signals | Wortlaut] OKF v0.2 speichert bewusst keinen Glaubwürdigkeitswert, sondern nur objektive Signale pro Quelle; Glaubwürdigkeit wird vom Konsumenten abgeleitet, weil ein gespeicherter Wert subjektiv, zwischen Konsumenten nicht portabel und schnell veraltet wäre.
- **C-0304** [S-0004 | §5.2 und §7 | Wortlaut] `generated` mit `by` und `at` hält fest, wer den aktuellen Inhalt erzeugt hat, `verified` als Liste von `by`- und `at`-Einträgen hält unabhängige Bestätigungen fest; beide nutzen dieselbe Aktorkonvention mit `<producer>/<version>` für Agenten, `human:<id>` für Personen und `process:<id>` für automatisierte Prozesse.
- **C-0305** [S-0004 | §5.3 | Wortlaut] Konsumenten leiten drei Trust-Tiers aus `verified` ab: fehlt das Feld, gilt unverified; bestätigen nur Akteure ohne `human:`-Präfix, gilt machine-confirmed; bestätigt mindestens ein `human:`-Akteur, gilt human-reviewed. Die Tiers sind beratende Signale und keine Zugriffskontrolle.
- **C-0306** [S-0004 | §5.4 und §5.5 | Wortlaut] Der Lebenszyklus läuft über `status` mit den Werten draft, stable und deprecated, wobei ein fehlendes Feld stable bedeutet, sowie über `stale_after` als absolutes Datum im Format JJJJ-MM-TT; ein Konzept gilt als veraltet, sobald das heutige Datum größer oder gleich `stale_after` ist.
- **C-0307** [S-0004 | §10.1 und §10.2 | Wortlaut] Der Typ Attested Computation macht eine sanktionierte Berechnung zu einem eigenen Konzept mit `runtime` als Pflichtangabe dieses Typs, `parameters` als typisierter Liste, optionalem `computation`-Pfad statt Inline-Block, `executor` mit Laufanweisung und deklarierten `receipt`-Feldern sowie `attester` als deterministischem Prüfcode ohne LLM; OKF legt die Schnittstelle fest und führt selbst nichts aus.
- **C-0308** [S-0004 | §10.3 und §10.6 | Wortlaut] Ein Agent darf ausschließlich Werte für die deklarierten `parameters` liefern und die Berechnung weder verfassen noch ändern; `verified` bestätigt dokumentweise, dass die Definition weiterhin zur Richtlinie passt, und steht im Bundle, während die Attestierung einen einzelnen Lauf zur Laufzeit prüft und nicht im Bundle gespeichert wird.
- **C-0309** [S-0004 | §12, §13 und §13.1 | Wortlaut] v0.2 löst v0.1 ab und ist nach der Regel major.minor ein Minor-Sprung mit zwei ausdrücklich benannten Bruchstellen: `timestamp` wird durch `generated.at` ersetzt und die Rumpfliste # Citations durch das Frontmatter-Feld `sources`; Konsumenten dürfen beide Altformen für v0.1-Dokumente weiterhin als Rückfall lesen.
- **C-0310** [S-0004 | §5 und §13.2 | Auslegung] Für dieses Bundle heißt das: OKF v0.2 regelt Provenienz, Vertrauen und Lebenszyklus jetzt selbst, aber in anderer Gestalt als das hiesige Profil. Das v0.2-Feld `sources` ist eine Liste von Einträgen mit Pflichtangabe `resource`, das gleichnamige Profilfeld eine flache Liste registrierter S-IDs; v0.2 `status` nutzt draft, stable und deprecated, das Profil nutzt aktiv, veraltet und in-pruefung. Beide Felder sind namensgleich und unterschiedlich belegt, weshalb jede Aussage über OKF-Kompatibilität die Zielversion nennen muss.

## Kontext und Grenzen
Geltungsbereich dieser Seite ist die Spezifikation v0.2 selbst, nicht ihre
Abbildung im hiesigen Profil. Quelle ist der Volltext mit Stand 2026-07-24;
Paragraphennummern sind nur innerhalb einer Version stabil, bei einem
Versionssprung ist diese Seite deshalb neu zu prüfen. Die Vorgängerfassung
bleibt als [okf.md](okf.md) mit Status `veraltet` erhalten und wird über die
`ersetzt`-Relation benannt, nicht gelöscht. Welche Anteile des Formats das
Profil übernimmt, abbildet oder begründet ablehnt, gehört nicht hierher,
sondern nach `KONZEPT.md`.
