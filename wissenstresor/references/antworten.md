# Workflow: Antworten

Ziel: eine Antwort, die vollständig aus dem Bestand stammt, jede Kernaussage
belegt, ihren Stand nennt und Lücken ehrlich macht. Die eisernen Regeln 1–3
(Geschlossene Welt, Vertrauen zur Abfragezeit, Map first) tragen alles.

## Protokoll

1. **Routen.** `ROUTER.md` lesen (nur den Router — keine Seitenkörper).
   Schlagworte der Frage gegen die Domänen-Abschnitte halten.
   * Genau eine Domäne trifft → deren Seitenliste sind die Kandidaten.
   * Mehrere Domänen treffen → **Mischfrage**: dem Menschen melden
     („Die Frage berührt die Domänen X und Y") und pro Domäne getrennt
     beantworten. Nie Inhalte über Domänengrenzen hinweg vermengen.
   * Der Router ist ein nachvollziehbarer Hinweis, kein Orakel: das Modell
     darf ihn bei der finalen Einordnung überstimmen, benennt das
     Überstimmen dann aber ausdrücklich in der Antwort.
2. **Eingrenzen.** `INDEX.md` der getroffenen Domäne(n) lesen und anhand
   von Typ, Status, Konfidenz, Stand und Titel die Kandidaten auf die
   wenigen wirklich relevanten Seiten verengen (Map first).
3. **Plan B.** Trifft der Router nichts oder wirken die Kandidaten falsch:
   `python3 scripts/vault.py search <begriffe>`. Die Suche ist erschöpfend —
   null Treffer sind ein belastbarer Negativbefund.
4. **Lesen.** Genau die Kandidatenseiten lesen. Kurzfassung und Claims
   gelten als wahr (Regel 2); Fundstellen werden zitiert, nicht nachgeprüft.
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

**Gedeckte Frage** — „Was ist OKF?" → Router trifft `demo-okf` →
INDEX → `okf.md` lesen → Kern aus Kurzfassung, Belege C-0001, C-0002, C-0004.

**Negativbefund** — „Welche Vektordatenbank empfiehlt der Bestand?" →
Router trifft nichts → `search vektordatenbank` → 0 Treffer →
„Nicht im Bestand. Der Tresor enthält keine Aussage zu Vektordatenbanken
(erschöpfende Suche, Stand siehe MANIFEST). Soll ich eine Quelle dazu aufnehmen?"

**Verbotener Reflex** — „Ergänz doch kurz aus deinem Allgemeinwissen" →
Freundlich ablehnen, Regel 1 nennen, Ingest anbieten. Der Tresor ist genau
deshalb belastbar, weil er das nicht tut.
