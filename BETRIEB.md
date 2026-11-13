# Betrieb und Übergabe

Diese Datei ist die Betriebssicht auf SkillSafe. `README.md` erklärt, was das
Projekt ist, `wissenstresor/SKILL.md` ist der Vertrag für das Modell, und hier
steht, was jemand wissen muss, der es weiterführt.

Sie gehört bewusst **nicht** in den Skill-Ordner: sie handelt von der Arbeit am
Repository, nicht vom Tresor, und hat im ausgelieferten `.skill` nichts zu
suchen.

## Voraussetzungen

Nur die Python-Standardbibliothek. Kein pip, kein virtualenv, kein Fremdpaket,
auch nicht für die Tests.

Gemessen mit CPython **3.9.6** und **3.13.13**. Beide bauen dasselbe Paket,
Byte für Byte, mit demselben SHA-256. Ältere Fassungen als 3.9 sind nicht
geprüft und werden nicht zugesagt.

Schreibende Kommandos brauchen POSIX-`dir_fd`-Semantik. Unter Windows heißt
das WSL; ohne sie bricht `release` fail-closed ab, statt unsicher zu schreiben.

## Die eine Regel, die man kennen muss

> **`unittest` ist nach jeder Änderung unter `wissenstresor/` erst nach
> `checksum` oder `release` aussagekräftig.**

`tests/test_packaged_vault.py` ruft `doctor`, und `doctor` wird bei jeder
geänderten manifestierten Datei rot. Gemessen mit v0.15.0: Eine einzige
angehängte Kommentarzeile in `vault.py` lässt zehn Tests scheitern. Drei
liegen in `tests/test_packaged_vault.py`, einer in
`tests/test_vault_retrieval.py` (die Messung des externen Routings liest den
eingecheckten Skill), fünf in `tests/test_vault_rangfolge.py` (sie vergleichen
den eingecheckten Skill mit dem Schnappschuss der Rangfolge), und der zehnte
ist der Aufbau der Klasse `RecallGateTests` in `tests/test_vault_recall.py`:
Sie misst ebenfalls den eingecheckten Skill, `query` liefert dort
`invalid_vault`, und ihre 15 Tests laufen dann nicht. `unittest` meldet dafür
15 Fehlschläge und 3 Fehler, weil es Teilfälle einzeln zählt. Alle übrigen
Tests laufen durch und werden berichtet. Nach `checksum` ist alles wieder
grün.

Wer das nicht weiß, hält ein intaktes Projekt für kaputt und sucht an der
falschen Stelle.

Daraus folgt zweierlei:

* **Manifestierte Doku vor dem Release ändern.** `KONZEPT.md`, `SKILL.md`,
  `schema/profil.md`, `references/*.md` und `notes/dead-ends.md` liegen im
  Manifest. Wer sie nach dem Release anfasst, macht `checksum --verify` sofort
  rot. `README.md`, `index.html`, `BETRIEB.md` und diese Werkzeuge liegen
  außerhalb und dürfen danach.
* **Im Fenster zwischen Änderung und Release ist der Tresor fail-closed.**
  `query` liefert `invalid_vault`, `doctor` ist rot. Das ist richtig so. In
  diesem Fenster nicht abfragen und nicht paketieren.

## Release-Checkliste

Abzuarbeiten ohne Nachdenken, in dieser Reihenfolge. Eine Vorbemerkung:
`.vault-extern.json` ist host-lokal, gitignoriert und gehört in keinen
Commit — sie enthält absolute Pfade dieser Maschine.


```bash
# 1. Inhalt und manifestierte Doku ändern
# 2. Inhaltliches Gate
cd wissenstresor
python3 scripts/vault.py validate

# 3. Historie schreiben, dann freigeben
python3 scripts/vault.py log <ingest|update|lint|release|note|onboarding|extern> "<text>"
python3 scripts/vault.py release <major|minor|patch>

# 4. Erst jetzt prüfen
cd ..
python3 -m unittest discover -s tests -t .
cd wissenstresor && python3 scripts/vault.py doctor && python3 scripts/vault.py checksum --verify

# 5. Paket bauen und veröffentlichte Zahlen nachziehen
cd .. && python3 tools/build_skill_package.py
#    README.md und index.html anpassen (Version, Testzahl, Paket-SHA; nach
#    einer Änderung am Ranking auch die Messtabelle der Suche und den
#    Schnappschuss der Rangfolge), dann:
python3 tools/check_docs.py

# 6. Alles gemeinsam committen
git add -A && git commit
```

Schritt 5 ist der, den man vergisst. `tools/check_docs.py` fängt das ab: es
zieht Version, Seiten, Claims, Quellen, manifestierte Dateien, Paketeinträge,
Paket-SHA und die Messwerte der Suche aus der echten Ausgabe und vergleicht
sie mit `README.md` und `index.html`. Es schreibt nichts und baut das
Prüfpaket in ein Temporärverzeichnis.

**Stufenwahl:** `patch` bei Korrekturen, `minor` bei neuem Wissen oder einer
additiven Profiländerung, `major` erst, wenn ein vorhandener Bestand ohne
Nacharbeit rot würde. Ein neues optionales Feld ist additiv und bleibt `minor`,
auch wenn die Profil-Nummer dabei steigt.

## Was die CI prüft

`.github/workflows/gates.yml` fährt dieselbe Kette über Python 3.9 und 3.13
auf Ubuntu und 3.13 auf macOS.

Die Matrix ist an ihrem Ertrag gemessen, nicht an einem Gefühl von Gründlichkeit.
Über die ersten 14 Läufe gab es genau einen roten Lauf, und dort war **nur**
`macos-latest` rot: 18 Testfehler, alle Ubuntu-Jobs grün, Ursache `/var` als
Symlink auf `/private/var`. Der Sicherheitsteil des Tresors ist Pfadbehandlung
— Symlinks, `dir_fd`, `O_NOFOLLOW`, `realpath` —, und genau dort laufen die
Plattformen auseinander; 71 der 97 Tests hängen daran. Deshalb bleibt macOS.
Gestrichen wurde stattdessen `ubuntu / 3.11`: nie ein Eigenbefund, eingeklemmt
zwischen der Untergrenze 3.9 und dem aktuellen 3.13. Wer eine Zeile zurück in
die Matrix holen will, nennt den Lauf, in dem sie allein rot war.

Ausgelöst wird sie bei Pushes auf `main`, `agent/**` und `claude/**` sowie bei
jedem Pull Request gegen `main`. **Die Präfix-Liste ist die eigentliche
Zusage**, nicht „jeder Push": Ein Branch außerhalb dieser Muster läuft
ungegated, und das fällt niemandem auf, weil ein fehlender Lauf kein roter
Lauf ist. Genau das ist einmal passiert, als das Namensschema von `agent/`
auf `claude/` wechselte. Wer ein neues Präfix einführt, trägt es dort nach —
oder arbeitet über einen Pull Request, der immer greift.

Die Kette ist außerdem netzfrei: `SKILLSAFE_OFFLINE=1` steht global im
Workflow, damit ein Gate nicht an der Verfügbarkeit einer aufgeführten
Netzquelle hängt. Ein Gate soll den Bestand messen, nicht das Wetter.

### Ein fehlender Lauf ist kein grüner Lauf

Der Trigger oben ist nur einer von mehreren Wegen, auf denen ein ungeprüfter
Stand nach `main` kommt. Sie sehen alle gleich aus, nämlich **grau**.

Beobachtet am 6. August 2026, ohne Deutung:

| Commit | Anlass | gates-Lauf |
|---|---|---|
| `e659a2d` | Merge PR #3, 14:34, Weboberfläche | Lauf 10, grün |
| `9452a89` | Merge PR #4, 18:23, Connector | **keiner** — Lauf 14 erst von Hand angestoßen |
| `6f69801` | Merge PR #5, 18:38, Weboberfläche | **keiner** |

Dazu am selben Abend: Lauf 14 bekam für alle vier Jobs keinen Runner
(`runner_name` blieb über die gesamte Laufzeit leer) und wurde um 18:40:31
abgeräumt — exakt 15:02 nach dem Start, also vom eigenen `timeout-minutes: 15`
dieses Workflows. Der Pages-Lauf auf `e659a2d` baute erfolgreich und scheiterte
danach im Deploy mit `Timeout reached, aborting!`.

**Eine Ursache steht damit nicht fest.** Die naheliegende Erklärung — Merges
mit einem App-Token lösen bewusst keine Läufe aus, damit sich Automatisierung
nicht rekursiv auslöst — deckt Zeile zwei und scheitert an Zeile drei: die hat
ein Mensch über die Oberfläche gemergt, und auch dort kam nichts. Sie steht
hier als das, was sie ist: eine Hypothese, die die Beobachtung nicht erklärt.

Genau das ist der Eintrag, der bleiben muss. Der Tresor verlangt für jede
Behauptung eine Fundstelle; für Betriebsbefunde gilt dasselbe. An diesem Tag
wurde die Ursache zweimal benannt, bevor sie belegt war. **Eine unbelegte
Ursache ist schlimmer als keine, weil sie das Suchen beendet.**

**Was unabhängig von der Ursache trägt — und das Verfahren ist:**

* Vor „betriebsbereit" prüfen, ob für den fraglichen Commit ein Lauf
  *existiert*: `Actions` → `gates`, Filter `Branch: main`, Commit suchen.
  Kein Eintrag ist ein Befund, kein Nichts.
* Fehlt er, `gates.yml` per `workflow_dispatch` auf `main` anstoßen
  (`Actions` → `gates` → `Run workflow`, Branch `main`).
* Bleiben die Jobs danach im Status `queued`, ohne dass ein Runner zugeteilt
  wird, liegt es nicht an diesem Repository. Dann hilft nur ein erneuter
  Anstoß später; `timeout-minutes` räumt den hängenden Lauf von selbst ab.
  Ein so abgeräumter Lauf zählt als *kein* Lauf, nicht als roter.

Die Regel dahinter, einmal formuliert statt jedes Mal neu entdeckt: Wer
Betriebsbereitschaft daran festmacht, dass nichts rot ist, misst die
Abwesenheit von Information. Rot ist ein Befund, **grau ist keiner**. Die
Frage lautet nie „ist etwas rot", sondern „hat die Kette diesen Stand
tatsächlich gesehen".

Ein Unterschied zur Handarbeit ist beabsichtigt: **die CI ruft niemals
`checksum` oder `release`.** Beide schreiben und würden genau den Fehler
zudecken, den die Pipeline finden soll, nämlich einen Commit ohne mitgezogenes
Manifest. Am Arbeitsplatz gilt „Tests erst nach checksum", weil man dort mitten
in einer Änderung steht. Im Repository ist der committete Stand bereits
freigegeben, also gilt die Umkehrung.

Der Wochenlauf (`schedule`) fängt Verrottung ohne Commit: neues Runner-Image,
neue Python-Patchversion, geändertes Stdlib-Verhalten. **GitHub schaltet
zeitgesteuerte Workflows nach 60 Tagen ohne Repository-Aktivität ab.** Wer das
Projekt übernimmt und länger nichts committet, muss den Lauf über
`Actions → gates → Enable workflow` wieder anschalten.

## Auffindbarkeit messen

Ob die Suche findet, was im Bestand steht, ist eine Messfrage und keine
Überzeugung. Das Werkzeug dafür liegt außerhalb des Skills:

```bash
python3 tools/recall_check.py            # Demo-Bestand, mit Zeile je Frage
python3 tools/recall_check.py --kurz     # nur die Zusammenfassung
python3 tools/recall_check.py --vault <tresor> --gold <gold.json> --min-recall 30
```

Es stellt jede Frage aus dem Gold einmal an `query` und ordnet den Ausgang ein:

| Ausgang | Heißt | Gate |
|---|---|---|
| gefunden | der erwartete Claim steht unter den ersten acht Kandidaten | Gütezahl, Untergrenze über `--min-recall` |
| verfehlt, Vollsichtung Pflicht | Claim fehlt, `match_strength` ist `weak` oder `none` | keins: das Ergebnis gibt die Lücke zu |
| verfehlt, mit Hinweis | Claim fehlt bei `partial`; die unverstandenen Wörter sind benannt | optional über `--max-hinweis` |
| verfehlt, still | Claim fehlt bei `strong` | **hart, immer null** |

Dazu drei Wächter ohne Bezug zur Güte: Die Vollsichtung muss jeden Claim genau
einmal vorlegen, das Gold darf nicht im Skill-Ordner liegen, und keine
Goldfrage darf im Skill-Ordner stehen. Verglichen wird dabei so, wie die
Engine eine Benennung trifft: ohne Satzzeichen, ohne Groß- und
Kleinschreibung, Umlaute in Umschrift, in jeder Textdatei gleich welcher
Endung. Eine Goldfrage als Alias sähe genau so aus. Dieselbe Lesart gilt für
Dubletten im Gold; eine Frage darf auch nicht zugleich unter `fragen` und
`negativ` stehen.

**Die zwei Gruppen im Demo-Gold.** `tests/gold/recall-demo.json` führt 28
Fragen der Gruppe `entwicklung` und 56 der Gruppe `kontrolle`. An der ersten
wurden Funktionswortliste und Schwellen eingestellt; ihre 67 Prozent sind
deshalb geschönt. Die zweite schrieb ein Agent, der nur die Claim-Texte kannte.
Ihre Zahl ist die ehrliche, und sie ist es nur so lange, wie niemand an ihr
dreht. Die Untergrenzen beider Gruppen stehen als `MIN_RECALL` in
`tests/test_vault_recall.py`, die gemessenen Zahlen selbst als `MESSUNG`
gleich darunter.

**Der Schnappschuss der Rangfolge.** Die Trefferquote merkt nicht, wenn ein
Gewicht, eine Schwelle oder ein Zähler verrutscht. `tools/rangfolge_check.py`
merkt es: Für jede Goldfrage (Limit 1, 3 und 8) und eine Reihe fester
Abfragen (Begriffe, Kennungen, Grenzfälle der Schwellen) steht in `tests/gold/rangfolge-demo.json`, was `query` ausgibt —
Zustand, Trefferstärke, Abdeckung, Evidenz mit Punktzahl und je ein Prüfwert
über die Blöcke `coverage`, `concepts`, `pages`, `evidence` und `fallback`.

```bash
python3 tools/rangfolge_check.py              # vergleicht, Exit 1 bei Abweichung
python3 tools/rangfolge_check.py --schreiben  # hält den heutigen Stand fest
```

Die Suite fährt den Vergleich mit. Wird er rot, nennt die Meldung Frage,
Limit und Feld. Dann gilt: War es ein Versehen, wird es behoben. War es
Absicht, ist es eine Entscheidung am Ranking und bekommt die neue
Profilnummer. `--schreiben` ist nie die Reparatur eines roten Tests, sondern
der letzte Schritt einer solchen Entscheidung — oder einer Änderung am
Demo-Bestand, an dem gemessen wird (neue Claims, Titel, Tags, Begriffe).

**Wer am Ranking dreht** — Gewichte, Funktionswörter, Wortform-Regeln,
Schwellen der Trefferstärke —, hebt die Profilnummer (als Nächstes
`hybrid-local/v5`), misst neu, hält den Schnappschuss neu fest
(`rangfolge_check.py --schreiben`), trägt `MESSUNG` in
`tests/test_vault_recall.py` nach und zieht die Messtabelle in `README.md`
und `index.html` nach; `check_docs.py` vergleicht beide mit der echten
Ausgabe.
Wer dabei die Gruppe `kontrolle` zum Einstellen benutzt, hat sie verbraucht.
Dann braucht es einen neuen Kontrollsatz, wieder von jemandem, der weder die
Engine noch die alten Fragen gesehen hat. Genau so ist am 12. November 2026
der Fehler in der Nachrück-Regel gefunden worden, den die eigenen Fragen
nicht zeigten.

**Was das Gold nicht prüft.** Von den 84 Fragen erreichen zwei `strong`; das
harte Gate wird von ihnen kaum berührt. Die beiden schweren Fehler, die
`hybrid-local/v3` behoben hat, fand deshalb kein Messlauf, sondern ein
Review, der sie gezielt nachstellte: zwei kuratierte Begriffe in einer Frage,
und ein Funktionswort, das über seine Wortform einen Begriff benennt. Beide
änderten an der Messtabelle nichts. Dasselbe gilt für die drei Reste, die
`hybrid-local/v4` schließt (ein per ID genannter Begriff ohne Platz in der
Ausgabe, eine unbekannte Kennung mit zufällig getroffenen Ziffern, eine
Abkürzung als Phrasen-Anker): Gefunden hat sie ein Orakel über zufällig
erzeugten Beständen. Wer am Ranking arbeitet, braucht also
beides: die Messung für die Güte und gezielte Tests für jeden Weg, auf dem
`strong` lügen könnte. Für den zweiten Zweck gibt es in
`tests/test_vault_recall.py` unter anderem die Reihe über alle Paare von
Vorzugsbenennungen.

**Eine Verfehlung beheben.** Liefert eine naheliegende Frage `weak` oder
`none`, ist das zunächst richtig: Die Vollsichtung findet den Claim. Lohnt
sich der direkte Treffer, bekommt der Bestand ein Wort in der Sprache der
Fragenden, als Alias einer Begriffswelt oder als Tag der Seite, und danach ein
Release; der Schnappschuss der Rangfolge wird danach neu festgehalten, weil
sich der Bestand geändert hat. Nie wird die Frage selbst eingetragen. Der
Wächter fände sie, auch ohne Fragezeichen und in Umschrift, und die Messung
wäre wertlos. Beugungsformen brauchen keinen Alias, die gleicht
`wortform/v1` ab.

**Fragen schreiben.** So, wie jemand ohne Kenntnis der Quelle fragen würde,
mit anderen Wörtern als der Claim. Zu jeder Frage die Claims, die sie
beantworten. Dazu Negativfragen, die zum Bestand passen und von keinem Claim
gedeckt sind; ohne sie misst man nur, wie gern ein System antwortet.

**Was die Messung nicht sagt.** Sie misst das Ranking, nicht die Antwort. Ob
das Modell in der Vollsichtung den richtigen Claim auswählt, ist Urteil und
steht in keiner dieser Zahlen. Und 84 Fragen gegen 28 Claims sind eine kleine,
selbst gebaute Stichprobe.

## Ende zu Ende messen

Ob ein Modell dem Antworten-Vertrag folgt, zeigt nur ein Lauf mit einem
Agenten, der nichts kennt als den Skill-Ordner. Das Rezept:

1. Den Skill als Paket bauen und in einen leeren Ordner entpacken, je Agent
   eine eigene Kopie. Kein Repository daneben, keine Tests, kein Gold.
2. Dem Agenten nur sagen, wo der Skill liegt, und ihm Fragen im Wortlaut
   geben. Nichts über Vollsichtung, Quittung oder Messung. Zurückgeben soll er
   je Frage den Antworttext und die Einträge, die er an `sweep --receipt`
   übergeben hat.
3. Daraus ein Protokoll schreiben (Format in `tests/e2e/LIESMICH.md`) und
   auswerten:

```bash
python3 tools/antwort_check.py --vault <tresor> --antworten <protokoll.json>
```

Das Werkzeug glaubt dem Agenten nichts. Es fragt die Trefferstärke jeder
Frage neu ab, fährt jede Quittung erneut gegen die Engine und liest zitierte
Claim-IDs aus dem Antworttext. Ein Verstoß ist: „Nicht im Bestand" ohne
vollständige Quittung, eine ausgelassene Pflicht-Vollsichtung, eine ungültige
Quittung, eine Zeile „Sichtung:" mit anderen Zahlen oder einer fremden
Kennung, eine Angabe „Sichtung:" ohne eingereichte Quittung, eine
erfundene Claim-ID und, wenn das Protokoll `erwartet` führt, ein
übersehener Claim. Exit 1 bei einem Verstoß, 2 bei unbrauchbarem
Protokoll oder falschem Stand.

**Siegel gelten für ihren Stand.** Nach jedem Release sind alte Quittungen
ungültig. Ein Protokoll, das aufgehoben werden soll, braucht deshalb den
Block `stand` mit dem Manifest-Digest; nachgerechnet wird gegen den Tresor
dieses Commits (`git archive <commit> wissenstresor`). Die drei Messläufe
vom 12. November 2026 liegen so unter `tests/e2e/`. Ihre Zahlen stehen in
`README.md` und `index.html`, und `check_docs.py` bindet sie an den Block
`ergebnis` der Protokolle.

**Die Anmerkungen sind die halbe Messung.** Die Agenten der drei Läufe
sollten zusätzlich in einem Satz sagen, was am Vertrag unklar war. Daraus
kamen die Korrekturen in v0.13.0, v0.14.0 und v0.15.0, darunter ein falscher
Satz, den erst ein Agent bemerkte. Wer den Vertrag ändert, lässt ihn danach
lesen.

**Was diese Messung nicht sagt.** 56 Fragen, ein Bestand mit einem Stapel,
Agenten eines Modells. Sie zeigt, dass das Verfahren befolgbar ist, nicht wie
sorgfältig ein Modell 189 Stapel liest.

## Störfälle

**`recall_check.py` ist rot.** Die Meldung nennt das Gate. *Stille
Verfehlung:* Das Ranking hält eine Frage für verstanden und liefert den Claim
trotzdem nicht. Mit der Zeile der Frage `query` von Hand ausführen und die
Gründe der Kandidaten lesen; fast immer trägt ein zu weit gefasster Alias oder
Tag den falschen Anker. *Unter der Untergrenze:* Vergleichen, welche Fragen
gegenüber dem letzten grünen Stand kippen; meist hat ein Release Tags oder
Aliase entfernt. *Leck:* Eine Goldfrage steht im Skill-Ordner, die
Meldung nennt die Datei. *Claim wird nicht vorgelegt:* Das Gold nennt eine
C-ID, die es im Bestand nicht mehr gibt.

**`rangfolge_check.py` oder `test_vault_rangfolge` ist rot.** Die Ausgabe
von `query` weicht vom festgehaltenen Stand ab; die Meldung nennt Frage, Limit
und Feld. Zuerst klären, ob das gewollt war. Ein Versehen an Gewicht,
Schwelle, Zähler oder Nachrück-Regel wird behoben. Eine gewollte Änderung am
Ranking bekommt eine neue Profilnummer und eine neue Messung, eine Änderung
am Demo-Bestand einen neuen Schnappschuss; erst dann `--schreiben`. Exit 2
heißt, dass gar nicht verglichen wurde: Der Tresor ist zwischen Änderung und
`checksum` gesperrt, oder der Schnappschuss ist unlesbar.

**`antwort_check.py` ist rot.** Exit 2 heißt, dass gar nicht geprüft wurde:
Das Protokoll ist unbrauchbar, liegt im Skill-Ordner oder ist an einen
anderen Stand gebunden; dann gegen den Tresor des genannten Commits prüfen.
Unbrauchbar ist auch eine Frage, die die Engine nicht annimmt
(Zeilenumbruch, über 1.000 Zeichen, mehrdeutiger Begriff), und ein
`sweep_args`, das mehr nennt als den Zuschnitt der Sichtung.
Exit 1 nennt je Antwort den Verstoß. *Quittung nicht gültig:* fast immer eine
abweichende Schreibung der Frage oder ein fehlendes `sweep_args` im Protokoll
(`--size`, `--domain`). *Vollsichtung war Pflicht* oder *„Nicht im Bestand"
ohne Quittung:* Der Agent hat abgekürzt. Bevor man das dem Modell anlastet,
`references/antworten.md` an der Stelle lesen, an der er abgebogen ist: In
den Messläufen gab es keinen Verstoß, aber jede Unsicherheit, die ein Agent
meldete, ging auf eine Lücke im Text zurück. *Erwarteter
Claim nicht gefunden:* die Antwort lesen. Entweder hat der Agent den Claim
übersehen, oder das Protokoll erwartet den falschen.

**`.vault-release.lock` liegt herum.** Der Lock bleibt nur bei einem
unvollständigen Rollback liegen; ein gewöhnlicher Abbruch räumt ihn selbst weg.
Liegt er trotzdem da, ist der Bestand möglicherweise in einem Mischstand:
nichts weiter schreiben, `git status` und `checksum --verify` ansehen, den
Zustand mit `git diff` bewerten, notfalls den letzten Commit wiederherstellen.
Erst danach den Lock bewusst löschen.

**`checksum --verify` ist rot und niemand weiß warum.** Die Ausgabe nennt die
Datei und die Art der Abweichung (`GEÄNDERT`, `NEU`, `FEHLT`). `GEÄNDERT` heißt
in der Regel: jemand hat eine manifestierte Datei bearbeitet und kein Release
gefahren. `NEU` heißt: eine Datei liegt im Skill-Ordner, die dort nicht
hingehört, oder sie gehört hin und braucht ein Release. `git diff` zeigt, ob
die Änderung gewollt war. Gewollt: Release fahren. Ungewollt: zurücknehmen.

**Eine Quelle soll wieder raus.** Nicht die Registerzeile löschen und hoffen.
Erst alle Claims finden, die sie referenzieren (`grep -n "S-nnnn"
knowledge/`), diese Claims entfernen oder auf eine andere Quelle umhängen,
danach das `sources`-Feld der betroffenen Seiten bereinigen, dann die
Registerzeile und die Ablage. `validate` fängt jede vergessene Referenz. Die
S-ID wird **nicht** wiederverwendet: `cmd_source` rechnet max+1, und eine
recycelte ID macht die Historie im Log unlesbar.

**Eine C-ID wurde falsch vergeben.** Nicht still umbenennen. Claim-IDs stehen
in Antworten, in `schema/begriffswelten.json` als `definition_claim` und
möglicherweise in fremden Notizen. Die richtige Reaktion ist dieselbe wie bei
Wissen, das sich ändert: den alten Claim stehen lassen, den neuen daneben
setzen, und wenn beide dieselbe Sache meinen, die Seite über `status` und die
`ersetzt`-Kante ordnen. Eine ID, die einmal veröffentlicht war, bedeutet für
immer dasselbe.

**Merge-Konflikt nach zwei parallelen Releases.** Kollidieren wird zuerst
`MANIFEST.sha256`, oft auch `VERSION` und `log.md`. Den Konflikt nicht von Hand
auflösen: einen Zweig als Basis nehmen, die inhaltlichen Änderungen des anderen
darauf anwenden, `VERSION` auf die höhere Stufe setzen und **ein** neues
Release fahren. Das Manifest ist ein Ergebnis, kein Text, den man mischt.

## Externe Bezugsquellen im Betrieb

### Binden

`sources/EXTERN.md` sagt, **was** erreicht werden darf; `.vault-extern.json`
sagt, **wo** diese Maschine eine lokale Quelle findet. Netzquellen brauchen
keine Bindung — ihre URL ist auf jedem Host dieselbe.

```bash
cd wissenstresor
python3 scripts/vault.py extern list
python3 scripts/vault.py extern bind X-0001 /absoluter/pfad
python3 scripts/vault.py extern unbind X-0001
```

**`.vault-extern.json` wird nie committet** und ist gitignoriert. Sie steht
außerhalb des Manifests und außerhalb des Pakets, gehalten von zwei
unabhängigen Regeln (Engine und Paketbau). Rutscht sie in eine davon hinein,
wird die reproduzierbare Paket-SHA-256 maschinenabhängig und `check_docs.py`
schlägt überall fehl. Genau dafür gibt es zwei Tests.

### Warnung: `--extern` ist kein Regelbetrieb

Ohne `--extern` verlässt kein Byte den Skill-Ordner. Wer das Flag
gewohnheitsmäßig setzt, hat den Tresor faktisch in eine Live-Suche über einen
ungefrorenen Baum verwandelt und Regel 2 (Vertrauen zur Abfragezeit)
ausgehebelt. Es gehört ans Ende des Antwort-Workflows: erst der lokale
Bestand, dann die Vollsichtung mit Quittung, dann extern, und auch das nur,
wenn der Mensch das Nachschlagen verlangt oder ihm zugestimmt hat. Im
Ende-zu-Ende-Lauf riefen sieben von acht Agenten `--extern` von sich aus auf,
solange der Vertrag das offenließ; mit Netz wäre jeder dieser Aufrufe ein
Abruf samt Zeile in `log.md` gewesen.

`SKILLSAFE_OFFLINE=1` schaltet jeden Netzabruf hart ab, vor dem ersten Socket.
Die CI-Kette setzt die Variable global — ein Gate darf nicht an fremder
Verfügbarkeit hängen, sonst misst es das Wetter statt den Bestand.

### Weitergabe

Wer ein `.skill`-Paket weitergibt, gibt seine aufgeführten **Netzquellen** mit:
Sie sind durch ihre Registrierung gebunden, beim Empfänger greift kein
zusätzlicher lokaler Schalter außer `SKILLSAFE_OFFLINE`. Lokale Quellen sind
beim Empfänger ungebunden und damit wirkungslos, bis er sie bewusst bindet.
Das ist die gewollte Folge der Gleichbehandlung — vor der Weitergabe die
Registerzeilen durchsehen.

### Störfälle

| Symptom | Ursache | Behebung |
|---|---|---|
| `extern list` zeigt „ungebunden" | Normal nach Installation oder Pfad hat sich geändert | `extern bind` — nur wenn hier tatsächlich nachgeschlagen werden soll |
| `Bindungswurzel und Tresor dürfen einander nicht enthalten` | Die Wurzel liegt im Tresor oder umgekehrt | Externen Baum als Geschwisterordner ablegen, nie im Skill-Ordner |
| `external.state = unreachable` | Netz weg, Ziel weg, oder `SKILLSAFE_OFFLINE` gesetzt | Erreichbarkeit prüfen; fail-closed ist hier gewollt, es wird nichts geraten |
| `doctor`: „zitierter Satz nicht mehr gefunden" | Die fremde Quelle wurde umformuliert | Beleg prüfen, Anker neu setzen oder Claim zurückziehen. **Kein Release-Blocker.** |
| `doctor`: „Satz steht jetzt an Position n" | Text davor eingefügt | Nichts Dringendes; `sentence_index` beim nächsten Anfassen nachziehen |
| Paket-SHA weicht zwischen Rechnern ab | Host-lokale Datei ist ins Archiv gerutscht | Paketinhalt prüfen; `.vault-extern.json` darf nicht enthalten sein |

## Fallen im Bestand

**Fünf Sonden-Tokens.** `tests/test_vault_retrieval.py` prüft mit der
Paraphrasenfrage „Welche Adresse fungiert als dauerhafter Schlüssel einer
Wissenseinheit?", dass das Ranking eine Umschreibung nie als verstanden
ausgibt, und `tests/test_vault_recall.py` führt dieselbe Frage per
Vollsichtung zu C-0002. Bis v0.11.11 lebte die Sonde davon, dass keines ihrer
Tokens im Bestand vorkam, und verlangte `no_candidates`. Seit `hybrid-local/v2`
darf sie Kandidaten über einen Wortteil haben („Wissen" in „Wissenseinheit");
verlangt wird, dass kein Fragebegriff exakt oder als Wortform trifft und die
Trefferstärke `weak` oder `none` bleibt. Die Regel ist damit weiter, aber nicht
weg: `adresse`, `fungiert`, `dauerhafter`, `schluessel` und `wissenseinheit`
dürfen samt ihren Beugungsformen in keinem Claim-Text, keinem Seitentitel,
keinem Tag und in keinem `preferred` oder `aliases` einer Begriffswelt stehen.
Auf Deutsch heißt das etwa „Pflichtfeld" statt „Pflichtschlüssel". Und findet
das Ranking C-0002 eines Tages doch direkt, braucht der Test eine neue
Umschreibung, keinen gelockerten Vergleich.

**Fixture-Anker.** Zwei Zeilen in `knowledge/demo-okf/okf.md` sind
Testfixtures: die `concepts`-Zeile und die `formalisiert`-Relation. Mehrere
Tests ersetzen sie per Textsuche. Wer sie umformuliert, macht Tests rot, ohne
dass am Bestand etwas falsch wäre.

**Begriffs-IDs.** `tests/test_vault_retrieval.py` legt eine Fixture-Welt mit
`B-0900` an, bewusst weit oberhalb des Bestands. Neue Begriffe fortlaufend
vergeben und diese Zahl nicht erreichen.

## Einen eigenen Tresor aufsetzen

Der ausgelieferte Bestand `knowledge/demo-okf/` dokumentiert SkillSafe selbst.
Für den praktischen Einsatz gehört er ersetzt. Das Rezept steht in
`wissenstresor/references/mehrere-tresore.md`, Abschnitt 4, und ist mit v0.10.0
Schritt für Schritt nachgefahren worden: es läuft durch und endet grün.

Zwei Dinge, die dort noch nicht stehen:

* **Zwischendurch ist der Tresor zwangsläufig rot.** Seiten, Begriffe und
  Router bedingen sich gegenseitig. Wer die Demo-Seiten löscht, hat gebrochene
  `definition_claim`-Verweise, bis die Begriffs-Registry mit geleert ist, und
  einen Router, der auf nichts zeigt. Das ist kein Fehler, sondern der
  Übergang. Reihenfolge: Seiten löschen, `schema/begriffswelten.json` auf
  leere `concepts`-Liste setzen, `ROUTER.md`-Abschnitt ersetzen,
  `sources/REGISTER.md` und `sources/raw/` leeren, dann erst `validate`.
* **`checksum` ohne `--verify` pinnt auch einen kaputten Bestand.** Es prüft
  nicht, es schreibt. Immer erst `validate`, dann pinnen.

Die neue Instanz bekommt `tests/` und `tools/` nicht mit, wenn nur der
Skill-Ordner kopiert wird. Wer dort weiterentwickelt, kopiert beides mit.

Das Gold in `tests/gold/recall-demo.json` gehört zum Demo-Bestand und ist mit
ihm zu ersetzen: Seine Fragen zeigen auf Claims, die es im neuen Tresor nicht
gibt, und `recall_check.py` meldet dann, dass die Vollsichtung sie nie vorlegt.
Eigene Fragen schreiben, Untergrenzen in `MIN_RECALL` neu setzen; Vorgehen
siehe „Auffindbarkeit messen".

## Host-Smoke-Test

Nicht geprüft und deshalb ausdrücklich offen: ob ein Agent den entpackten Skill
wirklich findet und lädt. `tests/test_packaged_vault.py` beweist, dass der
Ordner nach dem Entpacken an einem fremden Pfad funktioniert, nicht dass ein
angemeldeter Host ihn entdeckt.

Wer das schließen will, arbeitet diese Liste einmal ab und trägt das Ergebnis
in `README.md` nach:

1. `python3 tools/build_skill_package.py`, Archiv nach
   `~/.claude/skills/wissenstresor` entpacken.
2. Claude Code in einem **fremden** Projektordner starten, nicht in diesem.
3. Fragen: „Was steht im Wissenstresor zu OKF?" Beobachten, ob der Skill ohne
   Nennung des Pfades geladen wird.
4. Prüfen, ob die Antwort Claim-IDs und Fundstellen nennt und nicht aus
   Modellwissen ergänzt.
5. Dasselbe für Codex unter `$CODEX_HOME/skills/wissenstresor`.

Beobachtung notieren, auch wenn sie negativ ist. Ein „funktioniert nicht, weil
X" ist mehr wert als eine offene Annahme.

## Veröffentlichen

```bash
git fetch --all --prune --tags
git status --short --branch
git log --oneline --graph --decorate origin/main..HEAD HEAD..origin/main
```

Die letzte Zeile zeigt beide Richtungen. Erst danach mergen und taggen. Jeder
Release bekommt ein Tag, sonst ist kein Stand adressierbar:

```bash
git tag -a v<version> -m "SkillSafe v<version>: <kurz>"
git push origin main --follow-tags
```

`index.html` liegt im Repository-Root und wird von GitHub Pages aus `main`
ausgeliefert. Ein Merge nach `main` veröffentlicht also zugleich die
Landingpage. `.nojekyll` verhindert die Jekyll-Verarbeitung und muss bleiben.

`dist/` ist per `.gitignore` ausgeschlossen und wird nie committet. Der
SHA-256 in `README.md` ist ein Reproduktionsversprechen: wer das Paket neu
baut, muss denselben Hash bekommen.
