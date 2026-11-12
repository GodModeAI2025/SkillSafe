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
   Treffer, Wortformen und maximal einen Graph-Hop. Kein Treffer im Router
   allein ist noch kein Negativbefund.
2. **Status auswerten.**
   * `candidates_found` → die gelieferten `evidence`-Claims sind
     Relevanzkandidaten, noch keine Deckung der Frage. Wie belastbar sie
     sind, sagt Schritt 2b.
   * `no_candidates` → kein semantischer Negativbefund. Evidenz bleibt leer;
     Schritt 4b ist Pflicht.
   * `ambiguous` → genannte Begriffswelt klären und mit
     `--world BW-nnnn` erneut abfragen.
   * `invalid_vault`, `vault_busy` oder `snapshot_changed` → nichts ausgeben,
     `doctor` ausführen und den Bestand reparieren bzw. Release abwarten.
2b. **Trefferstärke auswerten.** Das Ranking erkennt Wörter, Wortformen und
   kuratierte Begriffe, keine Bedeutung. `coverage.match_strength` sagt, wie
   viel der Frage es damit erkannt hat, und `coverage.query_terms` nennt die
   Begriffe einzeln:

   | Stärke | Heißt | Was zu tun ist |
   |---|---|---|
   | `strong` | Jeder Inhaltsbegriff ist exakt, als Wortform oder über einen kuratierten Begriff getroffen | Weiter mit Schritt 3 und 4: Kandidaten lesen und antworten. Decken sie die Frage nicht, Schritt 4b. |
   | `partial` | Ein Anker trägt (ein kuratierter Begriff, eine genannte ID oder die ganze Frage als Wortfolge in einem Claim), oder mindestens zwei Begriffe sind getroffen und das sind mindestens 60 % — aber `unmatched` oder `partial` ist nicht leer | Weiter mit Schritt 3 und 4. Steht unter den ungetroffenen Begriffen das, wonach gefragt wird, danach Schritt 4b. |
   | `weak` | Weniger als das: ein einzelner getroffener Begriff ohne Anker, Wortteil- oder Zufallstreffer | Schritt 4 entfällt, direkt zu Schritt 4b. Die Kandidaten sind Fingerzeige, keine Antwort. |
   | `none` | Kein Kandidat | Schritt 4 entfällt, direkt zu Schritt 4b. |

   Bei `weak` und `none` steht zusätzlich
   `fallback.exhaustive_review_required: true`. Die Vollsichtung legt dann
   ohnehin jeden Claim vor; die Kandidatenseiten vorher zu lesen wäre
   dieselbe Arbeit zweimal.

   **Zwei Dinge heißen `partial`.** Die Stärke aus der Tabelle, und die
   Liste `query_terms.partial`. Die Liste nennt Begriffe, die nur als Teil
   eines zusammengesetzten Worts gefunden wurden: in einem ausgegebenen
   Claim, in Titel oder Tags seiner Seite oder in einer Benennung
   (`concepts.partial`). Zur Abdeckung zählen sie nicht. Gerechnet wird
   `query_terms` allein über die ausgegebenen `evidence`-Claims;
   `pages[].reasons` beschreibt dagegen die ganze Seite. Ein Begriff kann
   deshalb dort als Grund stehen und trotzdem `unmatched` sein: Der Claim,
   der ihn trägt, fiel dem Limit zum Opfer. Und ein Treffer kann in der
   Fundstelle eines Claims liegen (`source.locator`) statt in seinem Text.

   **Umformulieren ist erlaubt, nie verlangt.** Wer bei `partial` vermutet,
   dass der Bestand ein anderes Wort für dieselbe Sache benutzt, darf
   höchstens zweimal mit anderer Wortwahl neu abfragen. Das spart bei großen
   Beständen die Vollsichtung, ersetzt sie aber nicht: Für ein „Nicht im
   Bestand" zählt allein die Quittung aus Schritt 4b.

   **Gekürzte Treffer.** Maßgeblich ist `coverage.omitted_pages`. Stehen
   dort Seiten, hat das Limit Treffer auf Seiten abgeschnitten, die sonst
   niemand läse: diese Seiten in Schritt 4 zusätzlich lesen. Ist die Liste
   leer, liegen alle gekürzten Treffer auf Seiten, die ohnehin unter `pages`
   stehen und in Schritt 4 ganz gelesen werden; dann ist nichts weiter zu
   tun, auch wenn `coverage.candidates.omitted_direct` größer als null ist.
   Ein zweiter Aufruf mit `--limit` (höchstens 20) ist dafür nicht nötig.
   Meldet `coverage.omitted_pages_truncated` wahr, reicht die Liste nicht
   aus: dann Schritt 4b.
3. **Domänen trennen.** Berühren die gelieferten Seiten mehrere Domänen,
   **Mischfrage** melden und den Antwortkern pro Domäne getrennt schreiben.
   Nie Inhalte still über Domänengrenzen hinweg verschmelzen.
4. **Kandidaten lesen.** Genau die in `pages` genannten Kandidatenseiten
   lesen, dazu die unter `coverage.omitted_pages`. Nach einer Vollsichtung
   sind es die Seiten aus `pages` ihrer Quittung.
   Kurzfassung und Claims gelten als wahr (Regel 2); Fundstellen werden
   zitiert, nicht erneut gegen Rohquelle oder Medienrepräsentation geprüft.
   `media` liefert nur die validierte Region/Position, niemals OCR-Text als
   eigene Evidenz. Der Abschnitt „Kontext und Grenzen" ordnet ein und nennt
   den Geltungsbereich; er darf in „Hinweise:" einfließen, trägt aber keine
   Kernaussage.

   **Nachbarseiten.** Jede Seite unter `pages` nennt ihre typisierten
   Kanten in `relations`, ausgehend und eingehend. Steht an einer genutzten
   Seite unter `relations.incoming` eine Kante `ersetzt`, ist die dort
   genannte Seite die neuere Fassung: sie zusätzlich lesen, auch wenn sie
   nicht unter `pages` steht, und als maßgeblich benennen. Bei
   `widerspricht` gilt dasselbe in beiden Richtungen. Die Claims einer so
   gelesenen Seite sind zitierbar wie die jeder gelesenen Seite. Andere
   Kantentypen sind Verweise und verpflichten zu nichts.
4b. **Vollsichtung — die Bedeutungssuche.** Pflicht bei `weak` und `none`
   (dort anstelle von Schritt 4), und immer, bevor irgendein Teil der Frage
   als „Nicht im Bestand" ausgewiesen wird. Hier liest das Modell jeden
   Claim und urteilt nach Bedeutung; das Script sorgt dafür, dass keiner
   fehlt.

   ```
   python3 scripts/vault.py sweep "<frage>"              # Plan: Zahl der Stapel (entbehrlich, s. u.)
   python3 scripts/vault.py sweep "<frage>" --batch 1    # Stapel lesen, Siegel notieren
   python3 scripts/vault.py sweep "<frage>" --receipt 1:<siegel>=C-0401,C-0402 2:<siegel>=-
   ```

   Die Zahl der Stapel steht schon in `fallback.sweep.batches` der Abfrage.
   Der Plan-Aufruf ist nur nötig, wenn `--size`, `--domain` oder `--page`
   den Zuschnitt ändern.

   * **Jeden Stapel lesen**, in der Konversation. Die Ausgabe nie in eine
     Datei umleiten, um nur das Siegel herauszuziehen: das Siegel belegt,
     dass der Stapel ausgegeben wurde, und ist wertlos, wenn ihn niemand
     gelesen hat.
   * **Je Stapel urteilen:** Welche Claims beantworten die Frage oder einen
     Teil davon, auch in anderer Wortwahl, als Oberbegriff, als Folge oder
     als Gegenteil? Deren IDs gehören hinter das `=`. Trägt kein Claim des
     Stapels etwas bei, steht dort `-`. Ein Urteil je Stapel ist Pflicht.
   * **Im Zweifel aufnehmen.** Hinter das `=` gehört jeder Claim, auf den
     sich die Antwort stützen wird, auch einer, der nur einordnet oder
     einschränkt. Ein zu viel gewählter Claim kostet eine Seite Lesearbeit,
     ein zu wenig gewählter fehlt in der Antwort.
   * **Die Frage nicht verändern.** Das Siegel bindet Stand, Frage,
     Stapelgröße und Umfang. Groß-/Kleinschreibung und Satzzeichen sind
     egal, ein anderes Wort ist eine andere Frage. Am sichersten steht sie
     einmal in einer Shell-Variablen (`F='…'`) und in jedem Aufruf als
     `"$F"`. Jede weitere Frage braucht ihre eigene Sichtung, auch wenn
     dieselben Stapel gerade erst gelesen wurden.
   * **Quittung auswerten.** `sweep_complete` liefert die ausgewählten
     Claims als vollwertige `evidence` (Rolle `sweep_selected`) und ihre
     Seiten in `pages`; diese Seiten lesen wie in Schritt 4, samt der
     Nachbarseiten aus `relations`. Eine Vollsichtung kennt keinen
     Graph-Hop: Liegt ein gewählter Claim auf einer überholten Seite
     (`page_status:veraltet`), nennt nur `relations.incoming` die
     Nachfolgerin.
     `sweep_incomplete` und `invalid_receipt` liefern nichts: fehlende
     Stapel nachholen, nie raten.
   * **Große Bestände.** `fallback.sweep.batches` nennt den Aufwand vorab.
     Stapel dürfen parallel von Subagenten gelesen werden; jeder gibt genau
     `<stapel>:<siegel>=<IDs oder ->` zurück. `--domain` und `--page`
     schränken den Umfang ein und sparen Lesearbeit, erlauben aber nie
     „Nicht im Bestand", nur „in diesem Umfang nicht gefunden"
     (`abstention.allowed: false`).

   `search` darf mit Synonymen helfen, ersetzt die Vollsichtung aber nicht:
   ein fehlender Lexiktreffer ist kein Negativbeweis.
4c. **Externer Fallback.** Eine Option, keine Pflicht: Die Abstention aus
   Schritt 6 braucht ihn nicht. Erst **danach**, und nur wenn
   `fallback.external_lookup_available` wahr ist (das Feld steht auch ohne
   `--extern` im Envelope und sagt, ob überhaupt Quellen aufgeführt sind):
   `python3 scripts/vault.py query --extern "<frage>"`. Das liest aufgeführte
   externe Bezugsquellen live und ist eine bewusste Ausnahme von Regel 2 —
   nie der Default, nie eine Abkürzung um Schritt 4b. Ein externer Treffer
   **ersetzt „Nicht im Bestand" nicht**, er ergänzt es um einen benannten
   Hinweis. Der Aufruf schreibt nie in den Skill-Ordner; nur der Abzug einer
   Netzquelle landet im Cache-Verzeichnis des Nutzers. Details:
   `references/externe-quellen.md`.

   Ein leerer `external`-Block ist nur dann ein Befund, wenn auch gelesen
   wurde. Nennt `external.notes` die Quellen als nicht gebunden oder nicht
   abgerufen, sagt `no_external_candidates` nichts über sie aus: dann heißt
   es „externe Quellen nicht erreichbar", nie „auch extern nichts gefunden".
   Ein ergebnisloser Versuch gehört höchstens als ein Satz in „Hinweise:".
5. **Antworten** im Answer Envelope (unten). Ausschließlich aus dem
   Gelesenen; Formulierung und Struktur sind Modellarbeit, Inhalt nicht.
6. **Abstention.** Deckt der Bestand die Frage nicht oder nur teilweise:
   den ungedeckten Teil wörtlich als „Nicht im Bestand" ausweisen —
   optional mit dem Hinweis, welche Quelle man dafür einlesen könnte.
   Voraussetzung ist eine Quittung aus Schritt 4b mit
   `state: sweep_complete` und `abstention.allowed: true`. Ohne sie gibt es
   kein „Nicht im Bestand", auch nicht nach `strong`: Dass das Ranking
   einen Begriff kennt, beweist nicht, dass der Bestand zur gefragten
   Eigenschaft schweigt.

## Answer Envelope (feste Form)

```
[Antwortkern — knapp, aus Kurzfassungen und Claims]

Belege:
- C-0301 (S-0004, §3, §4, §4.1 und §11, Wortlaut) — Stand 2026-07-28
- C-0310 (S-0004, §5 und §13.2, Auslegung) — eigene Einordnung
- C-0401 (X-0001, A-0004, Wortlaut) — Stand 2026-08-06, externe Bezugsquelle

Stand: <ältester 'stand' der genutzten Seiten>; Konfidenz: <niedrigste genutzte>
[Nur falls zutreffend:]
Hinweise: <veraltete Fassung existiert / Konflikt zwischen C-x und C-y / Mischfrage X+Y>
Nicht im Bestand: <ungedeckte Teilfragen>
Sichtung: <claims_swept> von <claims_total> Claims, Quittung <erste 12 Zeichen von sweep_fingerprint>
Extern (nicht im Bestand): <X-nnnn, Dokument, Satzposition, Abrufzeitpunkt>
```

Regeln im Envelope:

* Jede Kernaussage referenziert mindestens eine Claim-ID.
* **Registerangaben sind keine Evidenz.** Der Block `source` eines Belegs
  (Titel, Stand, Trust und Rechte der Quelle) sagt, woher ein Claim stammt,
  nicht was der Bestand über den Gegenstand der Frage weiß. Eine Frage nach
  Lizenz, Rechten, Herausgeber oder Aktualität wird deshalb nie aus diesen
  Angaben beantwortet, sondern nur aus Claims; trägt sie kein Claim, lautet
  die Antwort „Nicht im Bestand". Dasselbe gilt für `matched_labels`,
  Begriffsbenennungen und Tags.
* Der Stand in einer Belegzeile ist der `stand` der Seite des Claims
  (`pages[].stand`), nicht der Stand der Quelle (`source.stand`).
* Die Zeile „Sichtung:" steht immer dann, wenn eine Vollsichtung lief, und
  sie ist Pflicht neben jedem „Nicht im Bestand". Bei eingeschränktem
  Umfang nennt sie ihn („Sichtung: Domäne demo-okf, 26 von 28 Claims") und
  die Abstention lautet „in diesem Umfang nicht gefunden".
* Ein per Vollsichtung gefundener Claim ist Evidenz wie jeder andere. Dass
  das Ranking ihn nicht fand, ist kein Makel des Claims, sondern ein Hinweis
  für die Pflege: Dem Bestand fehlt für diese Wortwahl ein Alias oder ein
  Tag (`references/begriffswelten.md`).
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
  Ergebnis anders als der lokale Teil nicht reproduzierbar ist.
* Trägt ein genutzter Claim das Signal `external_source`, stammt sein Beleg
  aus einer aufgeführten externen Quelle. Er ist damit vollwertige Evidenz —
  aber sein Wortlaut steht anderswo. Die Belegzeile hat dieselbe Form wie
  jede andere: Quelle ist die `X-nnnn`, Fundstelle die Anker-ID. Liegt aus
  der Pflege ein `doctor`-Hinweis auf Anker-Drift vor, gehört er in
  „Hinweise:". Eigens dafür läuft `doctor` beim Antworten nicht: Regel 2
  gilt auch hier.
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

**Umschreibung** — „Kann ich bei nassen Wänden die Miete kürzen?" →
`query` liefert `weak`: kein Begriff der Frage ist getroffen, nur „Miete"
als Teil von „Mietminderung". Also Vollsichtung: Der Stapel enthält C-0401
(Schimmelbefall berechtigt zur Mietminderung) und C-0402 (Anzeige an den
Vermieter). Quittung `1:<siegel>=C-0401,C-0402` → `sweep_complete`.
Antwort aus beiden Claims, mit der Zeile „Sichtung: 28 von 28 Claims".
Die Wortwahl „nasse Wände" steht in keinem Claim; gefunden hat sie das
Lesen, nicht das Ranking.

**Nur das Subjekt gefunden** — „Wie groß ist OKF?" → `query` liefert
OKF-Claims, womöglich sogar `strong`, aber keiner nennt eine Größe. Vor der
Abstention die Vollsichtung; erst ihre Quittung erlaubt: „Nicht im Bestand:
Der Bestand definiert OKF, enthält aber keine Größenangabe."

**Negativbefund** — „Welche Vektordatenbank empfiehlt der Bestand?" →
`query` liefert `weak` oder `none`; die Vollsichtung legt alle Claims vor,
keiner deckt die Frage, die Quittung lautet überall `-` →
„Nicht im Bestand. Der Tresor enthält keine Aussage zu Vektordatenbanken.
Sichtung: 28 von 28 Claims, Quittung 3f9a1c0b77de. Soll ich eine Quelle
dazu aufnehmen?"

**Verbotener Reflex** — „Ergänz doch kurz aus deinem Allgemeinwissen" →
Freundlich ablehnen, Regel 1 nennen, Ingest anbieten. Der Tresor ist genau
deshalb belastbar, weil er das nicht tut.
