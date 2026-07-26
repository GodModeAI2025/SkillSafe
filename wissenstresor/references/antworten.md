# Workflow: Antworten

Ziel: eine Antwort, die vollständig aus dem Bestand stammt, jede Kernaussage
belegt, ihren Stand nennt und Lücken ehrlich macht. Die eisernen Regeln 1–3
(Geschlossene Welt, Vertrauen zur Abfragezeit, Retrieve then read) tragen
alles.

Sind in der Session mehrere Tresore geladen und mehr als einer zum Thema
einschlägig: zuerst die Prioritätsreihenfolge aus
`references/mehrere-tresore.md` anwenden (Organisation < Fachbereich <
Projekt, Persönlich nur additiv, nie überschreibend), dann dieses
Protokoll für den jeweils maßgeblichen Tresor durchlaufen — eine
überschriebene Basis dabei immer benennen, nie kommentarlos auslassen.

## Protokoll

1. **Freigegebenen Snapshot abfragen.**
   `python3 scripts/vault.py query "<frage>"` ausführen. Das Kommando prüft
   Profil, Quarantäne, Index, Graph und Manifest vor der Ausgabe und liefert
   genau ein JSON-Dokument. Es sucht erschöpfend über validierte Claims,
   gewichtet exakte Begriffe, Alias-/Begriffswelt-Treffer, lexikalische
   Treffer und maximal einen Graph-Hop. Kein Treffer im Router allein ist
   noch kein Negativbefund.
2. **Status auswerten.**
   * `candidates_found` → ausschließlich die gelieferten `evidence`-Claims
     prüfen. Dieser Status bestätigt Relevanzkandidaten, noch nicht die
     semantische Deckung der ganzen Frage. Decken sie nur das Subjekt, aber
     nicht das erfragte Merkmal, vor einer Abstention Schritt 4b ausführen.
   * `no_candidates` → kein semantischer Negativbefund. Evidenz bleibt leer;
     alle unter `fallback.page_paths` genannten Seiten in Schritt 4b prüfen.
   * `ambiguous` → genannte Begriffswelt klären und mit
     `--world BW-nnnn` erneut abfragen.
   * `invalid_vault`, `vault_busy` oder `snapshot_changed` → nichts ausgeben,
     `doctor` ausführen und den Bestand reparieren bzw. Release abwarten.
3. **Domänen trennen.** Berühren die gelieferten Seiten mehrere Domänen,
   **Mischfrage** melden und den Antwortkern pro Domäne getrennt schreiben.
   Nie Inhalte still über Domänengrenzen hinweg verschmelzen.
4. **Kandidaten lesen.** Genau die in `pages` genannten Kandidatenseiten lesen.
   Kurzfassung und Claims gelten als wahr (Regel 2); Fundstellen werden
   zitiert, nicht erneut gegen Rohquelle oder Medienrepräsentation geprüft.
   `media` liefert nur die validierte Region/Position, niemals OCR-Text als
   eigene Evidenz.
4b. **Semantischer Fallback.** Bei `no_candidates` oder wenn die Kandidaten
   die erfragte Aussage nicht decken, jede Seite aus `fallback.page_paths`
   lesen und alle Claims semantisch gegen die Frage prüfen. `search` darf
   mit Synonymen helfen, aber ein fehlender Lexiktreffer ist kein
   Negativbeweis. Erst die vollständige Prüfung dieses manifestierten
   Seitenumfangs erlaubt „Nicht im Bestand".
5. **Antworten** im Answer Envelope (unten). Ausschließlich aus dem
   Gelesenen; Formulierung und Struktur sind Modellarbeit, Inhalt nicht.
6. **Abstention.** Deckt der Bestand die Frage nicht oder nur teilweise:
   den ungedeckten Teil wörtlich als „Nicht im Bestand" ausweisen —
   optional mit dem Hinweis, welche Quelle man dafür einlesen könnte.

## Answer Envelope (feste Form)

```
[Antwortkern — knapp, aus Kurzfassungen und Claims]

Belege:
- C-0001 (S-0001, Abschnitt "How it works", Wortlaut) — Stand 2026-07-04
- C-0005 (S-0001, Gesamtdokument, Auslegung) — eigene Einordnung

Stand: <ältester 'stand' der genutzten Seiten>; Konfidenz: <niedrigste genutzte>
[Nur falls zutreffend:]
Hinweise: <veraltete Fassung existiert / Konflikt zwischen C-x und C-y / Mischfrage X+Y>
Nicht im Bestand: <ungedeckte Teilfragen>
```

Regeln im Envelope:

* Jede Kernaussage referenziert mindestens eine Claim-ID.
* `Auslegung`-Claims werden ausdrücklich als eigene Einordnung markiert —
  nie mit dem Wortlaut der Quelle verwechselt.
* Der genannte Stand ist der **älteste** Stand der genutzten Seiten
  (konservativ); bei `status: veraltet` oder vorhandener Nachfolgeseite
  (`ersetzt`-Relation im Graph) auf die neuere Fassung hinweisen.
* Widersprechen sich Claims (`widerspricht`-Relation oder inhaltlich):
  beide Stände mit Quelle und Datum nennen, keinen stillschweigend wählen.
* Konfidenz `niedrig` oder Trust `T3` der Quelle → vorsichtig formulieren
  („laut S-0002, unbestätigte Webquelle …").

## Beispiele

**Gedeckte Frage** — „Was ist OKF?" → `query "Was ist OKF?"` liefert
`candidates_found`, B-0001 und `okf.md`; nach Claim-Prüfung ist die
Definition gedeckt → Kern aus Kurzfassung, Belege C-0001, C-0002, C-0004.

**Nur das Subjekt gefunden** — „Wie groß ist OKF?" → `query` liefert
OKF-Claims als Kandidaten, aber keiner nennt eine Größe → „Nicht im Bestand:
Der Bestand definiert OKF, enthält aber keine Größenangabe."

**Negativbefund** — „Welche Vektordatenbank empfiehlt der Bestand?" →
`query` liefert `no_candidates`; nach vollständiger semantischer Prüfung
aller `fallback.page_paths` deckt kein Claim die Frage →
„Nicht im Bestand. Der Tresor enthält keine Aussage zu Vektordatenbanken
(vollständig geprüfter manifestierter Seitenumfang, Stand siehe MANIFEST).
Soll ich eine Quelle dazu aufnehmen?"

**Verbotener Reflex** — „Ergänz doch kurz aus deinem Allgemeinwissen" →
Freundlich ablehnen, Regel 1 nennen, Ingest anbieten. Der Tresor ist genau
deshalb belastbar, weil er das nicht tut.
