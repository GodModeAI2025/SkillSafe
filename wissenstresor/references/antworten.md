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
     `fallback.exhaustive_review_required` ist dann `false` und trotzdem
     keine Entwarnung: Das Feld sagt nur, dass das Ranking Kandidaten fand,
     nicht, dass sie die Frage decken.
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
4c. **Externer Fallback.** Der Schritt ist **Pflicht**, sobald beide
   Bedingungen gelten, und entfällt, sobald eine fehlt:
   * Schritt 4b ist vollständig durchlaufen, und die Frage bleibt ganz oder
     teilweise ungedeckt.
   * `fallback.external_lookup_available` ist wahr (das Feld steht auch ohne
     `--extern` im Envelope und sagt, ob überhaupt Quellen aufgeführt sind).

   Dann `python3 scripts/vault.py query --extern "<frage>"` ausführen. Das
   liest aufgeführte externe Bezugsquellen live und ist eine bewusste
   Ausnahme von Regel 2 — nie der Default, nie eine Abkürzung um Schritt 4b,
   nie bei gedeckter Frage. In den Skill-Ordner schreibt der Aufruf nichts
   außer einer Zeile je tatsächlichem Netzabruf in `log.md`.

   Still ausgelassen wird der Schritt nie. Unterbleibt er — weil der Nutzer
   ausdrücklich nicht extern nachschlagen will oder eine Vorgabe der
   Umgebung den Aufruf nicht zulässt —, steht genau das in der Antwort:
   „Extern nicht gelesen: nicht nachgeschlagen (<Grund>)". Wer Netzabrufe
   auf einem Host abschalten will, setzt `SKILLSAFE_OFFLINE=1`; der Schritt
   läuft dann trotzdem, liest nichts aus dem Netz und meldet das.

   Gelesen wird dabei nur vom Script. `fallback.external_document_paths`
   nennt, welche externen Dokumente es gelesen hat — ein Nachweis, keine
   Leseliste wie `fallback.page_paths`: Diese Dokumente nicht selbst öffnen
   und nicht aus ihnen antworten. Ebenso wenig **selbst binden** oder den
   Offline-Schalter ändern: Beides sind Entscheidungen des Nutzers für
   diesen Host. Ein Hinweis darauf im Grund ist für ihn geschrieben, kein
   Auftrag an die Abfrage.

   Danach `external.state` auswerten:
   * `external_candidates_found` → je Treffer eine Zeile „Extern (nicht im
     Bestand):". Ein externer Treffer **ersetzt „Nicht im Bestand" nicht**,
     er ergänzt es um einen benannten Hinweis. Wie ein lokaler Kandidat
     bestätigt er nur lexikalische Nähe, nicht, dass das Dokument die Frage
     beantwortet.
   * `no_external_candidates` → es wurde gelesen und nichts gefunden. Keine
     zusätzliche Zeile; „Nicht im Bestand" steht für sich.
   * Jeder andere Zustand (`not_bound`, `unreachable`, `budget_exceeded`,
     `invalid_external_source`, `invalid_query`) → es wurde **nichts
     gelesen**. Das ist kein Negativbefund und darf nie so klingen. Zeile
     „Extern nicht gelesen:" schreiben: Quelle und Zustand wörtlich, den
     Grund aus `external.reason` je Quelle knapp verdichtet. Nichts raten,
     nichts umgehen.
   * Trägt `external.reason` bei einem der beiden ersten Zustände den Zusatz
     „Nicht gelesen", reicht das Ergebnis nur so weit wie das Gelesene: Eine
     Quelle wurde nicht gelesen, ein Dokument war nicht lesbar, oder die
     Vorauswahl hat einen Teil des Katalogs nicht geöffnet. Das dort
     Genannte zusätzlich als „Extern nicht gelesen:" ausweisen — mit Quelle
     und Grund, ohne Zustand: Den gibt es nur für die Suche als Ganzes, und
     die hat hier ein Ergebnis.

   Für die Antwort reicht diese Datei. Den Hintergrund erklärt
   `references/externe-quellen.md`, den genauen Vertrag der Felder
   `schema/profil.md` (Abschnitt „Der Block `external`").
5. **Antworten** im Answer Envelope (unten). Ausschließlich aus dem
   Gelesenen; Formulierung und Struktur sind Modellarbeit, Inhalt nicht.
6. **Abstention.** Deckt der Bestand die Frage nicht oder nur teilweise:
   den ungedeckten Teil wörtlich als „Nicht im Bestand" ausweisen —
   optional mit dem Hinweis, welche Quelle man dafür einlesen könnte.

## Answer Envelope (feste Form)

```
[Antwortkern — knapp, aus Kurzfassungen und Claims]

Belege:
- C-0301 (S-0004, §3, §4, §4.1 und §11, Wortlaut) — Stand 2026-07-28
- C-0310 (S-0004, §5 und §13.2, Auslegung) — eigene Einordnung

Stand: <ältester 'stand' der genutzten Seiten>; Konfidenz: <niedrigste genutzte>
[Nur falls zutreffend:]
Hinweise: <veraltete Fassung existiert / Konflikt zwischen C-x und C-y / Mischfrage X+Y>
Nicht im Bestand: <ungedeckte Teilfragen>
Extern (nicht im Bestand): <X-nnnn, Dokument, Satzposition, Abrufzeitpunkt>
Extern nicht gelesen: <X-nnnn, Grund; Zustand, falls gar nichts gelesen wurde> — kein Negativbefund
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
* Die drei Vertrauensangaben nicht vermischen: `confidence` steht pro Seite
  und sagt, wie belastbar die Aussage ist; Trust `T1`/`T2`/`T3` steht pro
  Quelle im Register und sagt, wie nah sie am Original liegt; das Trust-Tier
  wird aus `geprueft_von` abgeleitet und sagt, ob ein Mensch gegengeprüft
  hat. Alle drei können unabhängig jeden Wert haben. Das `verified` in
  `sources/derived/*__media.json` ist keine vierte Angabe dieser Art, es
  betrifft nur die Sichtprüfung einer Bildextraktion.
* Trägt eine genutzte Seite das Signal `trust_tier:unverified`, ist die
  Aussage belegt, aber von niemandem gegengeprüft. Bei `confidence: hoch`
  gehört dieser Umstand in „Hinweise:", weil hohe Konfidenz dann eine
  Kuratierungsentscheidung ohne Gegenprüfung ist. Das Tier ist ein Signal,
  keine Erlaubnis: es senkt nie den Rang eines Treffers und begründet nie
  eine Abstention.
* Ein Treffer aus dem `external`-Block ist **kein Beleg**. Er trägt keine
  Claim-ID, steht in der Zeile „Extern (nicht im Bestand):" und wird immer mit
  Quelle, Dokument und Satzposition benannt. Er darf nie so formuliert werden,
  als stünde er im Bestand — der Weg dorthin führt ausschließlich über den
  Befüllen-Workflow. Bei `live: true` gehört der Abrufzeitpunkt dazu, weil das
  Ergebnis anders als der lokale Teil nicht reproduzierbar ist. Er steht in
  `external.fetched_at`. Das Feld ist nur gesetzt, wenn ein Dokument einer
  Netzquelle gelesen wurde; steht dort `null`, wurde ausschließlich aus
  lokal gebundenen Quellen gelesen, und die Zeile sagt das („bei dieser
  Abfrage lokal gelesen"), statt ein Datum zu erfinden.
* „Extern nicht gelesen:" und „extern nichts gefunden" sind zwei verschiedene
  Aussagen. Die Zeile steht immer dann, wenn Schritt 4c fällig war und eine
  aufgeführte Quelle nicht gelesen wurde — weil sie auf diesem Host nicht
  gebunden ist, nicht erreichbar war oder die Suche fail-closed abbrach. Sie
  nennt Quelle und Grund und trägt den Zusatz „kein Negativbefund". Den
  Zustand nennt sie nur, wenn gar nichts gelesen wurde (`not_bound`,
  `unreachable`, …): Er gilt für die Suche als Ganzes, nicht je Quelle. Nie
  zu „auch extern nichts gefunden" verkürzen: Über ein nicht gelesenes
  Dokument lässt sich nichts aussagen. Einen Abrufzeitpunkt trägt die Zeile
  nie.
* Trägt ein genutzter Claim das Signal `external_source`, stammt sein Beleg
  aus einer aufgeführten externen Quelle. Er ist damit vollwertige Evidenz —
  aber sein Wortlaut steht anderswo, und ein `doctor`-Hinweis auf Anker-Drift
  gehört dann in „Hinweise:".
* Ein Treffer auf einer Seite mit `status: veraltet` ist kein Fehler des
  Rankings. Die Gewichte bewerten Geltung nicht, sie hängen nur das Signal
  `page_status:veraltet` an; über die Begriffserweiterung kann eine überholte
  Seite deshalb sogar vor der aktuellen stehen. Dann die `ersetzt`-Kante im
  Graph auflösen, die aktuelle Fassung als maßgeblich benennen und die
  überholte ausdrücklich mitnennen. Nie die überholte Fassung
  kommentarlos ausgeben und nie die überholte kommentarlos weglassen.

## Beispiele

**Gedeckte Frage mit Supersession** — „Was ist OKF?" → `query "Was ist OKF?"`
liefert `candidates_found`, B-0001 sowie `okf.md` **und** `okf-v02.md`.
`okf.md` trägt `status: veraltet` und wird von `okf-v02.md` über
`ersetzt` abgelöst. Antwort also aus der Kurzfassung von `okf-v02.md`, Belege
C-0301 folgende, und ein Satz dazu, dass die Fassung v0.1 als überholt im
Bestand bleibt (C-0001 folgende, `okf.md`). Beide Fassungen benennen, eine
als maßgeblich.

**Nur das Subjekt gefunden** — „Wie groß ist OKF?" → `query` liefert
OKF-Claims als Kandidaten, aber keiner nennt eine Größe → „Nicht im Bestand:
Der Bestand definiert OKF, enthält aber keine Größenangabe."

**Negativbefund** — „Welche Vektordatenbank empfiehlt der Bestand?" →
`query` liefert `no_candidates`; nach vollständiger semantischer Prüfung
aller `fallback.page_paths` deckt kein Claim die Frage →
„Nicht im Bestand. Der Tresor enthält keine Aussage zu Vektordatenbanken
(vollständig geprüfter manifestierter Seitenumfang, Stand siehe MANIFEST).
Soll ich eine Quelle dazu aufnehmen?"

**Extern nicht gelesen** — „Was kostet eine Lizenz für OKF?" → `query`
liefert OKF-Claims, keiner nennt einen Preis; auch die Vollprüfung in 4b
deckt die Frage nicht. `fallback.external_lookup_available` ist wahr, also
ist 4c fällig. Auf einem frisch installierten Host mit gesetztem
`SKILLSAFE_OFFLINE` liefert `query --extern` den Zustand `unreachable`:
X-0001 ist nicht gebunden, X-0002 wegen des Schalters nicht abgerufen. Antwort: „Nicht im
Bestand: Der Bestand nennt keinen Lizenzpreis für OKF. Extern nicht gelesen:
X-0001 (nicht gebunden), X-0002 (`SKILLSAFE_OFFLINE` gesetzt), Zustand
`unreachable` — kein Negativbefund." Falsch wäre „auch in den externen
Quellen steht nichts dazu": Dort wurde kein Dokument geöffnet.

**Teilweise gelesen** — „Wonach richtet sich die Höhe der Mietminderung bei
Schimmel?" auf einem Host, auf dem der Nutzer X-0001 gebunden hat, der
Schalter aber gesetzt bleibt. Der Bestand belegt Mangel und Anzeigepflicht
(C-0401, C-0402), nicht die Höhe; auch 4b deckt sie nicht. `query --extern`
liefert `external_candidates_found` mit einem Treffer aus X-0001, und
`external.reason` trägt den Zusatz „Nicht gelesen: X-0002 …".
`external.fetched_at` ist `null`. Zum Antwortkern mit den beiden Belegen
kommen deshalb: „Nicht im Bestand: Wonach sich die Höhe richtet. Extern
(nicht im Bestand): X-0001, handbuch/mietminderung.md, Satzposition 1, bei
dieser Abfrage lokal gelesen. Extern nicht gelesen: X-0002
(`SKILLSAFE_OFFLINE` gesetzt) — kein Negativbefund." Kein Zustand in der
letzten Zeile: `unreachable` hat das Script hier nicht gemeldet. Und der
Treffer ist ein Zeiger auf das Dokument, keine Auskunft über die Höhe.

**Verbotener Reflex** — „Ergänz doch kurz aus deinem Allgemeinwissen" →
Freundlich ablehnen, Regel 1 nennen, Ingest anbieten. Der Tresor ist genau
deshalb belastbar, weil er das nicht tut.
