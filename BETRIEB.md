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
geänderten manifestierten Datei rot. Gemessen: eine einzige angehängte
Kommentarzeile in `vault.py` ergibt `2 failed, 66 passed`. Nach `checksum`
wieder `68 passed`.

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

Abzuarbeiten ohne Nachdenken, in dieser Reihenfolge:

```bash
# 1. Inhalt und manifestierte Doku ändern
# 2. Inhaltliches Gate
cd wissenstresor
python3 scripts/vault.py validate

# 3. Historie schreiben, dann freigeben
python3 scripts/vault.py log <ingest|update|lint|release|note|onboarding> "<text>"
python3 scripts/vault.py release <major|minor|patch>

# 4. Erst jetzt prüfen
cd ..
python3 -m unittest discover -s tests -t .
cd wissenstresor && python3 scripts/vault.py doctor && python3 scripts/vault.py checksum --verify

# 5. Paket bauen und veröffentlichte Zahlen nachziehen
cd .. && python3 tools/build_skill_package.py
#    README.md und index.html anpassen, dann:
python3 tools/check_docs.py

# 6. Alles gemeinsam committen
git add -A && git commit
```

Schritt 5 ist der, den man vergisst. `tools/check_docs.py` fängt das ab: es
zieht Version, Seiten, Claims, Quellen, manifestierte Dateien, Paketeinträge
und Paket-SHA aus der echten Ausgabe und vergleicht sie mit `README.md` und
`index.html`. Es schreibt nichts und baut das Prüfpaket in ein
Temporärverzeichnis.

**Stufenwahl:** `patch` bei Korrekturen, `minor` bei neuem Wissen oder einer
additiven Profiländerung, `major` erst, wenn ein vorhandener Bestand ohne
Nacharbeit rot würde. Ein neues optionales Feld ist additiv und bleibt `minor`,
auch wenn die Profil-Nummer dabei steigt.

## Was die CI prüft

`.github/workflows/gates.yml` fährt dieselbe Kette bei jedem Push und Pull
Request, über Python 3.9, 3.11 und 3.13 auf Ubuntu und 3.13 auf macOS.

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

## Störfälle

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

## Fallen im Bestand

**Fünf Tabu-Tokens.** `tests/test_vault_retrieval.py` prüft mit der
Paraphrasenfrage „Welche Adresse fungiert als dauerhafter Schlüssel einer
Wissenseinheit?", dass `query` bei fehlender Deckung `no_candidates` liefert.
Die Sonde lebt davon, dass keines ihrer Tokens im Bestand vorkommt. Wirksam
sind `adresse`, `fungiert`, `dauerhafter`, `schluessel`, `wissenseinheit`. Sie
dürfen in keinem Claim-Text, keinem Seitentitel, keinem Tag und in keinem
`preferred` oder `aliases` einer Begriffswelt stehen. Auf Deutsch heißt das
etwa „Pflichtfeld" statt „Pflichtschlüssel".

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
