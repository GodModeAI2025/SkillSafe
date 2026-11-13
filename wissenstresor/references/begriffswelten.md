# Workflow: Begriffswelt pflegen

Ziel: Fachsprache, Synonyme und Hierarchien als kontrollierte Discovery-
Schicht pflegen. Begriffe helfen beim Finden; Fakten bleiben Claims.

## Protokoll

1. **Welt wählen.** Prüfen, ob der Begriff in eine vorhandene `BW-nnnn`
   gehört. Nur eine wirklich getrennte Fachsprache rechtfertigt eine neue
   Welt.
2. **Evidenz sichern.** Vorzugsbegriff und Bedeutung müssen bereits durch
   einen Claim gedeckt sein. Falls nicht: zuerst Quelle und Claim über den
   Befüllen-Workflow aufnehmen.
3. **ID vergeben.** Nächste freie `B-nnnn` verwenden. IDs werden nie
   wiederverwendet oder umnummeriert.
4. **Eintrag anlegen.** In `schema/begriffswelten.json` Vorzugsbegriff,
   echte Synonyme, höchstens einen Hierarchie-Hop (`broader`) und
   sachlich verwandte Begriffe (`related`) eintragen. `definition_claim`
   zeigt auf den belegenden Claim.
5. **Seite binden.** Die Seite des Definitions-Claims führt die B-ID im
   optionalen Frontmatter-Feld `concepts`. Weitere passende Seiten dürfen
   dieselbe ID führen.
6. **Kollisionen klären.** Bedeutet derselbe Ausdruck in einer Welt zwei
   Dinge, nicht still priorisieren: Begriffe präziser benennen. Gleiche
   Aliase in getrennten Welten bleiben zulässig; eine weltübergreifende
   Query meldet dann `ambiguous` und verlangt `--world BW-nnnn`.
7. **Validieren und releasen.** `vault.py validate`, danach
   `vault.py release <stufe>`. Der Validator erkennt unbekannte IDs,
   Alias-Kollisionen, Selbstkanten, Weltwechsel und `broader`-Zyklen.

## Retrieval-Wirkung

Ein Vorzugsbegriff oder Alias aktiviert den gebundenen Begriff, exakt oder
über seine Wortform: „Vertrauensstufen" trifft den Alias „Vertrauensstufe",
„attestierte Berechnungen" die „Attestierte Berechnung". Beugungsformen
gehören deshalb nicht in die Alias-Liste. Danach werden direkte Ober-, Unter-
und verwandte Begriffe höchstens einen Hop erweitert und niedriger gewichtet,
und der `definition_claim` eines getroffenen Begriffs rückt nach vorn.
Ranking und Tie-Breaker bleiben ganzzahlig und deterministisch. Definition,
Alias und Hierarchie erscheinen nie als Antwortbehauptung; `evidence` enthält
weiterhin nur Claims.

## Was ein Alias leisten soll

Wortformen findet das Ranking selbst, Bedeutung nicht. Ein Alias ist der
Ort, an dem Bedeutung einmal von Hand in den Bestand kommt: das Wort, das
Fragende tatsächlich benutzen, wenn es ein anderes ist als das der Quelle.
„Verfallsdatum" für `stale_after`, „Herkunftsnachweis" für Provenienz.

Der Anlass ist messbar. Liefert `query` für eine naheliegende Frage `weak`
oder `none` und findet erst die Vollsichtung den Claim, dann nennt
`coverage.query_terms.unmatched` die Wörter, die dem Bestand fehlen. Ist
eines davon ein echtes Synonym eines belegten Begriffs, wird es Alias. Ist es
nur lose verwandt, bleibt es draußen: Ein Alias, der zu viel trifft, macht
aus einer ehrlichen Lücke einen falschen Anker.

Nie wird eine ganze Frage als Alias eingetragen. Das hebt jede Messung auf
100 Prozent und sagt danach nichts mehr; der Wächter in
`tools/recall_check.py` bricht bei einer wörtlichen Goldfrage im Skill-Ordner
ab.
