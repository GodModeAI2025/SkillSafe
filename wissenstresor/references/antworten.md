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
     sind, sagt Schritt 2b. `fallback.exhaustive_review_required` ist dann
     oft `false` und trotzdem keine Entwarnung: Das Feld sagt nur, dass die
     Vollsichtung nicht vorgeschrieben ist, nicht, dass die Kandidaten die
     Frage decken.
   * `no_candidates` → kein semantischer Negativbefund. Evidenz bleibt leer;
     Schritt 4b ist Pflicht (einzige Ausnahme:
     `fallback.unknown_ids_only: true`, die unbekannte Kennung in
     Schritt 2b).
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
   | `strong` | Jeder Inhaltsbegriff ist exakt, als Wortform oder über einen kuratierten Begriff getroffen, jeder getroffene Begriff ist in der Ausgabe vertreten, und jede genannte Kennung gibt es | Weiter mit Schritt 3 und 4: Kandidaten lesen und antworten. Decken sie die Frage nicht, Schritt 4b. |
   | `partial` | Ein Anker trägt (ein vertretener kuratierter Begriff, eine vorhandene ID an einem ausgegebenen Claim oder die ganze Frage als Wortfolge in einem Claim, wenn dabei ein Inhaltswort getroffen ist), oder mindestens zwei Begriffe sind getroffen und das sind mindestens 60 % — aber etwas blieb offen: `unmatched` oder `partial` ist nicht leer, ein Begriff ist unvertreten, oder eine Kennung gibt es nicht | Tragen die getroffenen Begriffe die Frage: weiter mit Schritt 3 und 4. Steht unter den ungetroffenen das, wonach gefragt wird: direkt zu Schritt 4b, wie bei `weak`. Im Zweifel erst Schritt 4; bleibt danach etwas offen, folgt 4b. |
   | `weak` | Weniger als das: ein einzelner getroffener Begriff ohne Anker, Wortteil- oder Zufallstreffer | Schritt 4 entfällt, direkt zu Schritt 4b. Die Kandidaten sind Fingerzeige, keine Antwort. |
   | `none` | Kein Kandidat | Schritt 4 entfällt, direkt zu Schritt 4b. |

   Bei `weak` und `none` steht zusätzlich
   `fallback.exhaustive_review_required: true`, außer die Frage gilt allein
   einer unbekannten Kennung (`fallback.unknown_ids_only: true`, siehe unten).
   Die Vollsichtung legt dann ohnehin jeden Claim vor; die Kandidatenseiten
   vorher zu lesen wäre dieselbe Arbeit zweimal. Bei `partial` bleibt das Feld
   falsch, auch wenn der Kern der Frage ungetroffen ist: Welcher Begriff der
   Kern ist, kann nur das Modell beurteilen.

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

   **Unbekannte Kennungen.** Nennt die Frage eine C-, S- oder B-ID, die es im
   Bestand nicht gibt, steht sie unter `coverage.unknown_ids`, und das
   Ergebnis ist nie `strong`. Als Kennung zählt nur die Schreibung mit
   ASCII-Ziffern; „C-０００１" ist für das Script ein gewöhnliches Wort. Dass
   es eine solche Kennung nicht gibt, ist ein Befund des Scripts, kein Urteil
   des Rankings: Es kennt jede Kennung, eine Vollsichtung fände nichts
   anderes. Bei `--world` steht unter `unknown_ids` auch eine B-ID aus einer
   anderen Begriffswelt; die gibt es, nur nicht in dieser Welt. Nennt die Frage nichts als solche Kennungen („Was
   steht in C-9999?", „Worum geht es in S-0099?"), meldet das Script auch das:
   `fallback.unknown_ids_only` ist `true`, `fallback.reason` heißt
   `unknown_ids_only`, und `fallback.exhaustive_review_required` ist falsch.
   Das gilt vor jeder Zeile der Tabelle, gleich welche Stärke dasteht, auch
   bei `partial`. Die Antwort stellt dann das Fehlen fest, am einfachsten mit
   dem Satz „Die Kennung C-9999 gibt es im Bestand nicht.", gern gefolgt von
   der Rückfrage, ob eine andere gemeint war; eine andere Kennung (C-, S-, B-
   oder X-) schlägt sie dabei nicht vor, denn das wäre ein Zitat. Schritt 4b entfällt, zitiert
   wird kein Claim, und die Formel „Nicht im Bestand" steht dort nicht, sie bleibt der
   Quittung vorbehalten. Die unbekannte Kennung nennt die Antwort nur, um ihr
   Fehlen festzustellen, nachzufragen, was gemeint war, sie ausdrücklich als
   Quelle auszuschließen („nicht aus S-0099") oder die Frage zu wiederholen;
   nie als Quelle („Laut C-9999 …", „- C-9999 (…)"). Ist `fallback.unknown_ids_only` falsch,
   gilt die Tabelle: Dann fragt die Frage auch nach einer Sache
   („Mietminderung C-9999", auch „Waren C-9999"), nennt eine vorhandene
   Kennung oder einen Begriff, die Ziffern der Kennung stehen selbst im
   Bestand, oder es gibt die Kennung in einer anderen Begriffswelt. Die
   Entscheidung trifft das Script; welche Wörter dabei als einleitend gelten,
   nennt `schema/profil.md`: eine geschlossene Liste, jedes andere Wort ist
   ein Sachwort, ebenso jedes Zeichen außer gewöhnlichen Satzzeichen.

   **Unvertretene Begriffe.** Jeder getroffene Begriff unter
   `concepts.matched` sagt in `represented`, ob die Ausgabe etwas von ihm
   zeigt: einen Claim seiner Seite oder seinen Definitions-Claim. Steht dort
   `false`, hat das Limit ihn verdrängt; das Ergebnis ist dann höchstens
   `partial`, und die Seite seines Definitions-Claims steht unter
   `coverage.omitted_pages`, auch wenn die Liste gekürzt ist (bei mehr als
   20 solchen Seiten ist `omitted_pages_truncated` wahr, und es gilt
   Schritt 4b). Sie gehört zu den Seiten, die Schritt 4 liest.

   Beantworten die in Schritt 4 gelesenen Seiten die Frage ganz, ist die
   Vollsichtung bei `partial` und `strong` nicht nötig. Nötig wird sie,
   sobald ein Teil der Frage offen bleibt und als „Nicht im Bestand"
   ausgewiesen werden soll (Schritt 6).

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
   Evidenz sind dabei allein die Claims: Die Kurzfassung verdichtet sie und
   darf nichts behaupten, was kein Claim trägt. Sagt eine Kurzfassung doch
   mehr als die Claims ihrer Seite, ist das ein Pflegefehler
   (Kurzfassungs-Deckung, `references/lint.md`): in „Hinweise:" benennen,
   nie als belegte Kernaussage ausgeben.
   `media` liefert nur die validierte Region/Position, niemals OCR-Text als
   eigene Evidenz. Der Abschnitt „Kontext und Grenzen" ordnet ein und nennt
   den Geltungsbereich; er darf in „Hinweise:" einfließen, trägt aber keine
   Kernaussage.

   **Nachbarseiten.** Jede Seite unter `pages` nennt ihre typisierten
   Kanten in `relations`, ausgehend und eingehend. Steht an einer genutzten
   Seite unter `relations.incoming` eine Kante `ersetzt`, ist die dort
   genannte Seite die neuere Fassung: sie zusätzlich lesen, auch wenn sie
   nicht unter `pages` steht, und als maßgeblich benennen. Bei
   `widerspricht`, gleich in welcher Richtung, die andere Seite ebenfalls
   lesen und beide Stände nennen, keinen stillschweigend wählen. Die Claims
   einer so gelesenen Seite sind zitierbar wie die jeder gelesenen Seite.
   Andere Kantentypen sind Verweise und verpflichten zu nichts, ebenso eine
   ausgehende Kante `ersetzt`: Die Vorgängerin der genutzten Seite muss
   niemand lesen. Eine Seite, die in derselben Sitzung schon ganz gelesen
   wurde, muss nicht erneut gelesen werden, solange `vault.manifest_sha256`
   derselbe ist.
4b. **Vollsichtung — die Bedeutungssuche.** Pflicht bei `weak` und `none`
   (dort anstelle von Schritt 4; einzige Ausnahme ist die unbekannte Kennung
   aus Schritt 2b, `fallback.unknown_ids_only: true`), und immer, bevor
   irgendein Teil der Frage als „Nicht im Bestand" ausgewiesen wird. Hier
   liest das Modell jeden Claim und urteilt nach Bedeutung; das Script
   sorgt dafür, dass keiner fehlt.

   ```
   python3 scripts/vault.py sweep "<frage>"              # Plan: Zahl der Stapel (entbehrlich, s. u.)
   python3 scripts/vault.py sweep "<frage>" --batch 1    # Stapel lesen, Siegel notieren
   python3 scripts/vault.py sweep "<frage>" --receipt 1:<siegel>=C-0401,C-0402 2:<siegel>=-
   ```

   Die Zahl der Stapel steht schon in `fallback.sweep.batches` der Abfrage,
   und jeder Stapel nennt sie selbst in `batches_total`. Der Plan-Aufruf
   ist deshalb entbehrlich, auch wenn `--size`, `--domain` oder `--page`
   den Zuschnitt ändern: Dann sagt der erste Stapel, wie viele es sind.

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
     ein zu wenig gewählter fehlt in der Antwort. Das gilt auch, wenn die
     Antwort am Ende „Nicht im Bestand" lautet: Claims, die den Gegenstand
     einordnen, dürfen gewählt und zitiert werden. `-` heißt nur, dass aus
     diesem Stapel nichts in die Antwort eingeht.
   * **Die Frage nicht verändern.** Das Siegel bindet Stand, Frage,
     Stapelgröße und Zuschnitt. Egal sind nur Groß-/Kleinschreibung, wie viel
     Leerraum steht (mehrere Leerzeichen, Leerraum am Rand; einen
     Zeilenumbruch oder Tabulator nimmt die Engine in einer Frage gar nicht
     an), die typografische Form der Anführungszeichen und Striche („…" wie
     "…", ‚…' wie '…', Halbgeviertstrich wie Bindestrich) und Fragezeichen am
     Ende, auch mehrere. Alles andere ist eine andere Frage: ein anderes Wort,
     aber auch ein Komma, ein Operator, ein Vorzeichen, ein Leerzeichen, wo
     vorher keins stand („a<=b" gegen „a <= b"), einfache statt doppelter
     Anführungszeichen oder „ß" statt „ss". Am sichersten steht sie einmal in
     einer Shell-Variablen (`F='…'`) und in jedem Aufruf als `"$F"`. Jede
     weitere Frage braucht ihre eigene Sichtung, auch wenn dieselben Stapel
     gerade erst gelesen wurden: Geurteilt wird gegen die Frage, und genau das
     bindet das Siegel.
   * **Quittung auswerten.** `sweep_complete` liefert die ausgewählten
     Claims als vollwertige `evidence` (Rolle `sweep_selected`) und ihre
     Seiten in `pages`; diese Seiten lesen wie in Schritt 4, samt der
     Nachbarseiten aus `relations`. Eine Vollsichtung kennt keinen
     Graph-Hop: Liegt ein gewählter Claim auf einer überholten Seite
     (`page_status:veraltet`), nennt nur `relations.incoming` die
     Nachfolgerin. Zitierbar sind danach alle Claims der gelesenen Seiten,
     nicht nur die gewählten.
   * **Die Vollsichtung sichtet Claims**, keine Kurzfassungen und keinen
     Fließtext. Das genügt, weil eine Kurzfassung nichts behaupten darf, was
     kein Claim trägt. Ein „Nicht im Bestand" heißt deshalb genau: Kein
     Claim des Bestands trägt die Aussage.
     `sweep_incomplete` und `invalid_receipt` liefern nichts: fehlende
     Stapel nachholen, nie raten.
   * **Große Bestände.** `fallback.sweep.batches` nennt den Aufwand vorab.
     Stapel dürfen parallel von Subagenten gelesen werden; jeder gibt genau
     `<stapel>:<siegel>=<IDs oder ->` zurück. `--receipt` darf mehrfach
     stehen, die Einträge werden gesammelt. `--domain` und `--page`
     schränken den Umfang ein und sparen Lesearbeit, erlauben dann aber
     kein „Nicht im Bestand", nur „in diesem Umfang nicht gefunden"
     (`abstention.allowed: false`). Maßgeblich ist das Feld: Es ist nur
     wahr, wenn der Umfang gezählt jeden Claim des Bestands enthält. Bei
     `weak` und `none` gilt: Gibt der Mensch einen Umfang vor („such nur in
     demo-okf"), oder nennt die Frage selbst eine Domäne oder Seite als
     Umfang („Was steht in demo-okf zu …?"), erfüllt die Sichtung dieses
     Umfangs die Pflicht, und die Antwort sagt höchstens „in diesem Umfang
     nicht gefunden". In jedem
     anderen Fall erfüllt eine eingeschränkte Sichtung die Pflicht nicht,
     denn der gesuchte Claim kann außerhalb liegen.

   `search` darf mit Synonymen helfen, ersetzt die Vollsichtung aber nicht:
   ein fehlender Lexiktreffer ist kein Negativbeweis.
4c. **Externer Fallback.** Der Schritt ist **Pflicht**, sobald beide
   Bedingungen gelten, und entfällt, sobald eine fehlt:
   * Schritt 4b ist vollständig durchlaufen, und die Frage bleibt ganz oder
     teilweise ungedeckt. Im Kennungsfall aus Schritt 2b gibt es keine Frage
     nach einer Sache und deshalb auch keinen externen Fallback; ebenso
     wenig, wenn der Umfang auf einen Teil des Bestands begrenzt ist, gleich
     ob der Mensch ihn vorgegeben hat oder die Frage selbst eine Domäne oder
     Seite nennt.
   * `fallback.external_lookup_available` ist wahr (das Feld steht auch ohne
     `--extern` im Envelope und sagt, ob überhaupt Quellen aufgeführt sind).

   Dann `python3 scripts/vault.py query --extern "<frage>"` ausführen, mit
   denselben Schaltern wie die lokale Abfrage (etwa `--world`). Das
   liest aufgeführte externe Bezugsquellen live und ist eine bewusste
   Ausnahme von Regel 2 — nie der Default, nie eine Abkürzung um Schritt 4b,
   nie bei gedeckter Frage. In den Skill-Ordner schreibt der Aufruf nichts
   außer einer Zeile je tatsächlichem Netzabruf in `log.md`, das außerhalb
   des Manifests liegt; dazu kommt der Abzug im Cache-Verzeichnis des
   Nutzers. Am manifestierten Bestand ändert er nichts.

   Still ausgelassen wird der Schritt nie. Unterbleibt er — weil der Nutzer
   ausdrücklich nicht extern nachschlagen will oder eine Vorgabe der
   Umgebung den Aufruf nicht zulässt —, steht genau das in der Antwort:
   „Extern nicht gelesen: X-0001, X-0002 nicht nachgeschlagen (<Grund>) —
   kein Negativbefund". Ein Verbot von Internetrecherche ist keine solche
   Vorgabe: Eine aufgeführte Quelle ist keine Recherche (Regel 6). Wer Netzabrufe
   auf einem Host abschalten will, setzt `SKILLSAFE_OFFLINE=1`; der Schritt
   läuft dann trotzdem, liest nichts aus dem Netz und meldet das.

   Gelesen wird dabei nur vom Script. `fallback.external_document_paths`
   nennt, welche externen Dokumente es gelesen hat — ein Nachweis, keine
   Leseliste: Diese Dokumente nicht selbst öffnen
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
     Quelle wurde nicht gelesen, ein Dokument war nicht lesbar, ein gezähltes
     Budget der Abfrage war erschöpft, oder die Vorauswahl einer Netzquelle
     hat einen Teil des Katalogs nicht geöffnet. Das dort
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
   Voraussetzung ist eine Quittung aus Schritt 4b mit
   `state: sweep_complete` und `abstention.allowed: true`. Ohne sie gibt es
   kein „Nicht im Bestand", auch nicht nach `strong`: Dass das Ranking
   einen Begriff kennt, beweist nicht, dass der Bestand zur gefragten
   Eigenschaft schweigt.

## Answer Envelope (feste Form)

```
[Antwortkern — knapp, aus den Claims; Kurzfassungen helfen beim Formulieren]

Belege:
- C-0301 (S-0004, §3, §4, §4.1 und §11, Wortlaut) — Stand 2026-07-28
- C-0310 (S-0004, §5 und §13.2, Auslegung) — Stand 2026-07-28, eigene Einordnung
- C-0401 (X-0001, A-0004, Wortlaut) — Stand 2026-08-06, externe Bezugsquelle

Stand: <ältester 'stand' der genutzten Seiten>; Konfidenz: <niedrigste genutzte>
[Nur falls zutreffend:]
Hinweise: <veraltete Fassung existiert / Konflikt zwischen C-x und C-y / Mischfrage X+Y>
Nicht im Bestand: <ungedeckte Teilfragen>
Sichtung: <claims_swept> von <claims_total> Claims, Quittung <erste 12 Zeichen von sweep_fingerprint>
Extern (nicht im Bestand): <X-nnnn, Dokument, Satzposition, Abrufzeitpunkt>
Extern nicht gelesen: <X-nnnn, Grund; Zustand, falls gar nichts gelesen wurde> — kein Negativbefund
```

Regeln im Envelope:

* Jede Kernaussage referenziert mindestens eine Claim-ID.
* **Registerangaben sind keine Evidenz.** Der Block `source` eines Belegs
  (Titel, Stand, Trust und Rechte der Quelle) sagt, woher ein Claim stammt,
  nicht was der Bestand über den Gegenstand der Frage weiß. Eine Frage nach
  Lizenz, Rechten, Herausgeber oder Aktualität wird deshalb nie aus diesen
  Angaben beantwortet, sondern nur aus Claims; trägt sie kein Claim, lautet
  die Antwort „Nicht im Bestand". Dasselbe gilt für `matched_labels`,
  Begriffsbenennungen, Tags, die Begriffsauszeichnung einer Seite
  (`pages[].concepts`) und ihre Kanten (`relations`). Steht das Gefragte nur
  dort oder unter „Kontext und Grenzen" einer gelesenen Seite, darf die
  Antwort diesen Beinahe-Treffer in „Hinweise:" nennen, ausdrücklich als
  Angabe ohne Belegkraft; sie bleibt „Nicht im Bestand".
* Jede Belegzeile nennt den Stand: den `stand` der Seite des Claims
  (`pages[].stand`), nicht den Stand der Quelle (`source.stand`). Zusätze
  wie „eigene Einordnung", „externe Bezugsquelle" oder „überholte Fassung"
  folgen nach einem Komma.
* Die Zeile „Sichtung:" steht immer dann, wenn eine Vollsichtung lief, und
  sie ist Pflicht neben jedem „Nicht im Bestand". Bei eingeschränktem
  Umfang nennt sie ihn („Sichtung: Domäne demo-okf, 26 von 28 Claims,
  Quittung …") und die Abstention lautet „in diesem Umfang nicht gefunden".
  Sie nennt immer die Zahlen und die Kennung der Quittung, und sie steht
  nur da, wenn es die Quittung gibt.
* **Reine Abstention.** Trägt kein Claim etwas zur Frage bei, beginnt der
  Antwortkern mit „Nicht im Bestand." und sagt, was fehlt; darunter steht
  die Zeile „Sichtung:". „Belege:", „Stand:" und die Zeile „Nicht im
  Bestand:" entfallen; war Schritt 4c fällig, folgen die Zeilen „Extern
  (nicht im Bestand):" oder „Extern nicht gelesen:". Ordnen Claims den Gegenstand ein, werden sie zitiert
  und es stehen alle Zeilen wie sonst; die Zeile „Nicht im Bestand:" nennt
  dann den ungedeckten Teil.
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
  aber sein Wortlaut steht anderswo. Die Belegzeile hat dieselbe Form wie jede
  andere, mit dem Zusatz „externe Bezugsquelle": Quelle ist die `X-nnnn`,
  Fundstelle die Anker-ID. Liegt aus der Pflege ein `doctor`-Hinweis auf
  Anker-Drift vor, gehört er in „Hinweise:". Eigens dafür läuft `doctor` beim
  Antworten nicht: Regel 2 gilt auch hier.
* Ein Treffer auf einer Seite mit `status: veraltet` ist kein Fehler des
  Rankings. Die Gewichte bewerten Geltung nicht, sie hängen nur das Signal
  `page_status:veraltet` an; über die Begriffserweiterung kann eine überholte
  Seite deshalb sogar vor der aktuellen stehen. Dann die `ersetzt`-Kante im
  Graph auflösen, die aktuelle Fassung als maßgeblich benennen und die
  überholte ausdrücklich mitnennen. Nie die überholte Fassung
  kommentarlos ausgeben und nie die überholte kommentarlos weglassen.
  Gemeint sind die Seiten des Ergebnisses, aus dem die Antwort entsteht:
  nach einer Vollsichtung die `pages` der Quittung, nicht die Kandidaten
  der Abfrage davor. Wurde dort kein Claim der überholten Seite gewählt,
  muss sie niemand nennen.
* Steht eine Aussage nur auf der überholten Seite und trägt die maßgebliche
  Fassung dazu keinen eigenen Claim: den Claim mit seinem Stand zitieren und
  in „Hinweise:" sagen, dass er aus der überholten Fassung stammt und die
  aktuelle dazu nichts Eigenes sagt. Ob er fortgilt, entscheidet die Antwort
  nicht; ein Satz unter „Kontext und Grenzen" macht daraus keine belegte
  Aussage.
* **Eine Bedeutungszuordnung wird offengelegt.** Trifft ein Claim die Frage
  nur dem Sinn nach, weil sie andere Wörter benutzt, nennt die Antwort, was
  der Claim wörtlich sagt, samt seiner Bedingung („erheblicher
  Schimmelbefall"), und kennzeichnet die Zuordnung in „Hinweise:" als
  Lesart der Frage („verstanden als …"). Was der Claim offenlässt, etwa ob
  nasse Wände schon erheblicher Schimmelbefall sind, bleibt offen und steht
  als ungedeckter Teil in „Nicht im Bestand:", wofür Schritt 6 die Quittung
  verlangt; es wird nicht aus Modellwissen entschieden. Dasselbe gilt
  für einen Zusatz der Frage, den kein Claim kennt („für Sprachassistenten",
  „in Teilzeit"): Die Antwort sagt, wofür der Claim gilt, und weist den
  Zusatz als ungedeckt aus. Die Grenze: Ein Wort der Frage, das nur anders
  benennt, was der Claim sagt („die Maschine" für „das Modell"), ist Lesart
  und gehört in „Hinweise:". Ein Wort, das eine Bedingung, eine Eigenschaft
  oder einen Gegenstand hinzufügt, den der Claim nicht nennt, ist ein Zusatz
  und gehört in „Nicht im Bestand:".
* **Unbestimmte Fragen.** Lässt die Frage mehrere Lesarten zu und deckt der
  Bestand mehr als eine, werden sie getrennt beantwortet; deckt er nur eine,
  nennt die Antwort diese Lesart. Die übrigen Lesarten muss sie nicht als
  „Nicht im Bestand" ausweisen; tut sie es, gilt Schritt 6. Rückfragen ist
  erlaubt, raten nicht.
* **Der Skill selbst ist kein Bestand.** `SKILL.md`, `KONZEPT.md`,
  `LICENSE`, `references/` und `schema/` gehören zum Motor. Eine Frage an
  den Bestand wird nie aus ihnen beantwortet. Betrifft sie den Tresor
  selbst (Lizenz, Aufbau, Bedienung), darf „Hinweise:" die zuständige Datei
  nennen und in einem Satz sagen, was dort dazu steht, ausdrücklich als
  Auskunft über das Werkzeug ohne Belegkraft. Die Antwort an den Bestand
  bleibt davon unberührt, also in der Regel „Nicht im Bestand".

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
Antwort aus beiden Claims, mit der Zeile „Sichtung: 28 von 28 Claims,
Quittung …".
Die Wortwahl „nasse Wände" steht in keinem Claim; gefunden hat sie das
Lesen, nicht das Ranking. Die Antwort sagt deshalb, worauf sich der Claim
wörtlich bezieht: auf erheblichen Schimmelbefall. Ob nasse Wände das schon
sind, sagt der Bestand nicht. Das steht unter „Nicht im Bestand:", und weil
Quellen aufgeführt sind, folgt Schritt 4c mit seiner Zeile.

**Nur das Subjekt gefunden** — „Wie groß ist OKF?" → `query` liefert
OKF-Claims, womöglich sogar `strong`, aber keiner nennt eine Größe. Vor der
Abstention die Vollsichtung; erst ihre Quittung erlaubt: „Nicht im Bestand:
Der Bestand definiert OKF, enthält aber keine Größenangabe." Danach Schritt
4c, denn Quellen sind aufgeführt.

**Negativbefund** — „Welche Vektordatenbank empfiehlt der Bestand?" →
`query` liefert `weak` oder `none`; die Vollsichtung legt alle Claims vor,
keiner deckt die Frage, die Quittung lautet überall `-`. Weil Quellen
aufgeführt sind, folgt Schritt 4c; auf einem frisch installierten Host mit
gesetztem `SKILLSAFE_OFFLINE` liefert er `unreachable`. Die Antwort ist eine
reine Abstention, die Angaben zur Sichtung und zur externen Suche stehen in
eigenen Zeilen:

```
Nicht im Bestand. Der Tresor enthält keine Aussage zu Vektordatenbanken.

Sichtung: 28 von 28 Claims, Quittung 3f9a1c0b77de
Extern nicht gelesen: X-0001 (nicht gebunden), X-0002 (SKILLSAFE_OFFLINE gesetzt), Zustand unreachable — kein Negativbefund

Soll ich eine Quelle dazu aufnehmen?
```

**Unbekannte Kennung** — „Was steht in C-9999?" → `query` liefert `weak`,
`coverage.unknown_ids` nennt C-9999, unter `unmatched` steht nur „9999", und
`fallback.unknown_ids_only` ist `true`.
Antwort: „Die Kennung C-9999 gibt es im Bestand nicht. Falls eine andere
gemeint war, bitte nennen." Keine Vollsichtung, keine Zeile „Sichtung:",
und nicht die Formel „Nicht im Bestand".

**Extern nicht gelesen** — „Was kostet eine Lizenz für OKF?" → `query`
liefert OKF-Claims, keiner nennt einen Preis; auch die Vollsichtung in 4b
deckt die Frage nicht. `fallback.external_lookup_available` ist wahr, also
ist 4c fällig. Auf einem frisch installierten Host mit gesetztem
`SKILLSAFE_OFFLINE` liefert `query --extern` den Zustand `unreachable`:
X-0001 ist nicht gebunden, X-0002 wegen des Schalters nicht abgerufen. Antwort: „Nicht im
Bestand: Der Bestand nennt keinen Lizenzpreis für OKF. Extern nicht gelesen:
X-0001 (nicht gebunden), X-0002 (`SKILLSAFE_OFFLINE` gesetzt), Zustand
`unreachable` — kein Negativbefund.", dazu die Zeile „Sichtung:" der
Vollsichtung. Falsch wäre „auch in den externen Quellen steht nichts dazu":
Dort wurde kein Dokument geöffnet.

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
(`SKILLSAFE_OFFLINE` gesetzt) — kein Negativbefund.", dazu die Zeile
„Sichtung:" der Vollsichtung. Kein Zustand in der letzten Zeile:
`unreachable` hat das Script hier nicht gemeldet. Und der
Treffer ist ein Zeiger auf das Dokument, keine Auskunft über die Höhe.

**Verbotener Reflex** — „Ergänz doch kurz aus deinem Allgemeinwissen" →
Freundlich ablehnen, Regel 1 nennen, Ingest anbieten. Der Tresor ist genau
deshalb belastbar, weil er das nicht tut.
