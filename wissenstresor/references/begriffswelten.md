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

Ein exakter Vorzugsbegriff oder Alias aktiviert den gebundenen Begriff.
Danach werden direkte Ober-, Unter- und verwandte Begriffe höchstens einen
Hop erweitert und niedriger gewichtet. Ranking und Tie-Breaker bleiben
ganzzahlig und deterministisch. Definition, Alias und Hierarchie erscheinen
nie als Antwortbehauptung; `evidence` enthält weiterhin nur Claims.
