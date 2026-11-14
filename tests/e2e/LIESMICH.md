# Ende-zu-Ende-Protokolle

Hier liegen die Antworten frischer Agenten aus den Messläufen, je Runde eine
Datei im Schema `skillsafe.antwort-protokoll/v1`. Ein Agent bekam jeweils nur
einen entpackten Skill-Ordner und die Fragen im Wortlaut, keine Erklärung des
Verfahrens. Aus seiner Rückgabe stehen hier drei Dinge: die Frage, der Wortlaut
der Antwort und die Einträge, die er an `sweep --receipt` übergeben hat.

| Datei | Stand | Commit | Agenten | Fragen |
|---|---|---|---|---|
| `runde-1.json` | v0.12.1 | `0d9f5dd` | 8 | 32 |
| `runde-2.json` | v0.13.0 | `3896b9f` | 4 | 12 |
| `runde-3.json` | v0.14.0 | `94c8481` | 4 | 12 |
| `runde-4.json` | v0.15.0 | `ddb9924` | 4 | 12 |
| `runde-5.json` | v0.17.0 | `d275b06` | 4 | 12 |

## Nachrechnen

Ein Siegel gilt nur für den Stand, für den es ausgegeben wurde. Gegen den
heutigen Tresor wären alle Quittungen ungültig; `tools/antwort_check.py`
bricht deshalb mit Exit 2 ab, wenn Protokoll und Tresor nicht zusammenpassen.
Nachgerechnet wird gegen den Tresor des gebundenen Commits:

```bash
mkdir -p /tmp/stand-runde-1
git archive 0d9f5dd wissenstresor | tar -x -C /tmp/stand-runde-1
python3 tools/antwort_check.py --vault /tmp/stand-runde-1/wissenstresor \
    --antworten tests/e2e/runde-1.json
```

Für Runde 2 dasselbe mit `3896b9f` und `runde-2.json`, für Runde 3 mit
`94c8481` und `runde-3.json`, für Runde 4 mit `ddb9924` und `runde-4.json`.
Runde 5 lief mit gebundener Quelle X-0001 und ohne Netz; so wird sie auch
nachgerechnet:

```bash
mkdir -p /tmp/stand-runde-5
git archive d275b06 wissenstresor beispiel-extern | tar -x -C /tmp/stand-runde-5
(cd /tmp/stand-runde-5/wissenstresor && python3 scripts/vault.py extern bind \
    X-0001 /tmp/stand-runde-5/beispiel-extern)
SKILLSAFE_OFFLINE=1 python3 tools/antwort_check.py \
    --vault /tmp/stand-runde-5/wissenstresor --antworten tests/e2e/runde-5.json
```

Seit v0.18.0 prüft das Werkzeug auch Schritt 4c: Bleibt eine Frage nach der
Vollsichtung ungedeckt und sind Quellen aufgeführt, muss die Antwort externe
Treffer und Ungelesenes ausweisen oder den Verzicht nennen. Seit v0.18.1
verlangt es jeden externen Treffer mit Quelle und Dokument und jede
ungelesene Quelle, einen Verzicht nur mit festgehaltener Vorgabe, und ob der
Schritt Pflicht ist, liest es aus
dem Vertrag des geprüften Tresors; Runde 1 bis 4 liefen gegen Stände, deren
Vertrag ihn freistellte, und werden ohne die Regel geprüft. Die Abfrage mit
`--extern` rechnet es selbst nach, immer offline: Was eine Netzquelle
geliefert hätte, prüft es nur, wenn auch der Lauf offline war. Das sagt
`stand.extern` im Protokoll (siehe unten); fehlt die Angabe, gilt
`SKILLSAFE_OFFLINE` in der Umgebung des Werkzeugs. Runde 5 trägt sie: Auf
einem Host ohne die Bindung von X-0001 bricht die Nachrechnung deshalb ab,
statt Verstöße zu melden, die keine sind.
Das Werkzeug glaubt dem Agenten nichts: Es fragt die Trefferstärke jeder
Frage neu ab, fährt jede Quittung erneut gegen die Engine und liest die
zitierten Claim-IDs aus dem Antworttext. Was der Ersteller der Messung
festhält (`umfang_vorgegeben`, `vorgabe`, `stand.extern`), übernimmt es;
was der Agent behauptet, nicht.

Der Block `ergebnis` in jeder Datei ist die Zusammenfassung dieses Werkzeugs
zum Messzeitpunkt. Eine Ausnahme nennt Runde 3 selbst: Das Werkzeug aus
v0.14.0 meldete dort einen Verstoß, der keiner war. Die Frage „Was steht in
C-9999?" nennt die Kennung, die Antwort wiederholt sie, und das zählte als
erfundene Claim-ID. Seit v0.15.0 ist eine Kennung, nach der gefragt wurde,
Gegenstand der Antwort und kein Zitat; `ergebnis` stammt aus dieser Fassung.
`tools/check_docs.py` hält die Zahlen in `README.md`, `index.html` und
`wissenstresor/KONZEPT.md` an diese Blöcke gebunden.

## Was die Zahlen sagen und was nicht

80 Fragen, ein Demo-Bestand mit 28 Claims, Agenten aus derselben
Modellfamilie, und die Fragen stammen bis auf fünfzehn aus
`tests/gold/recall-demo.json`; Runde 3 und 4 fragten zusätzlich nach zwei
kuratierten Begriffen in einer Frage, nach Kennungen, die es nicht gibt,
nach einem unvertretenen Begriff, mit einem Vergleichsoperator und nach dem
Werkzeug selbst; Runde 5 nach Fragen, die nach der Vollsichtung ganz oder
teilweise offen bleiben, mit und ohne externen Treffer, nach einer Domäne im
Wortlaut und mit einem erbetenen Verzicht auf externe Quellen. Gemessen ist damit, dass der
Antworten-Vertrag befolgbar ist und befolgt wurde: keine Abstention ohne
vollständige Quittung, keine ausgelassene Pflicht-Vollsichtung, kein
erfundener Claim. Nicht gemessen ist, wie sorgfältig ein Modell einen Bestand
mit Hunderten Stapeln liest.

## Einen eigenen Lauf auswerten

Das Protokoll ist eine JSON-Datei außerhalb des Skill-Ordners:

```json
{
  "schema": "skillsafe.antwort-protokoll/v1",
  "antworten": [
    {
      "id": "F1",
      "frage": "Wie jemand wirklich fragen würde",
      "antwort": "Der vollständige Antworttext des Agenten",
      "quittung": ["1:0123456789abcdef=C-0401,C-0402"],
      "erwartet": ["C-0401"]
    }
  ]
}
```

`quittung` sind die Argumente von `--receipt`, unverändert; ohne Vollsichtung
bleibt die Liste leer. `erwartet` ist optional und macht aus der Prüfung eine
Messung. `art: "negativ"` kennzeichnet eine Frage, die der Bestand nicht
beantwortet. `sweep_args` nennt den Zuschnitt der Sichtung, wenn er vom
Standard abweicht, und nur ihn: Paare aus `--size`, `--domain` oder `--page`
und ihrem Wert, etwa `["--size", "10"]`. Alles andere weist das Werkzeug ab,
weil die Engine jedes weitere Wort an die Frage anhängte. Gibt der Mensch
einen Umfang vor („such nur in demo-okf"), oder nennt die Frage selbst eine
Domäne oder Seite als Umfang, trägt der Eintrag
`"umfang_vorgegeben": true` und den Umfang in `sweep_args` (`--domain` oder
`--page`). Dann erfüllt die Sichtung dieses Umfangs die Pflicht, und „in
diesem Umfang nicht gefunden" zählt als korrekte Ablehnung; ohne die Angabe
ist eine eingeschränkte Sichtung bei `weak` und `none` eine ausgelassene
Pflicht. Bittet der Mensch darum, nicht extern nachzuschlagen, oder lässt
die Umgebung den Aufruf nicht zu, trägt der Eintrag diese Vorgabe im
Wortlaut unter `vorgabe`. Nur dann zählt ein ausgewiesener Verzicht auf
Schritt 4c, und dann müssen die Zeilen „… nicht nachgeschlagen" zusammen
jede aufgeführte Quelle nennen. Ohne Vorgabe ist ein Verzicht, der alle
nennt, ein Verstoß; Zeilen „… nicht nachgeschlagen", die zusammen nicht jede
Quelle nennen, liest das Werkzeug dann als Zeilen nach dem Aufruf. Ein optionaler Block `stand` mit
`manifest_sha256` bindet das Protokoll an einen Stand. Hing der Lauf an
gebundenen externen Quellen oder an der Netzlage, hält `stand.extern` beides
fest: `{"gebunden": ["X-0001"], "offline": true}`. Bindet der prüfende Host
andere Quellen, bricht das Werkzeug mit Exit 2 ab wie bei einem fremden
Manifest, und `offline` gilt vor der Umgebung des Werkzeugs. Ohne die Angabe
gehört die Prüfung auf einen Host mit derselben Bindung. Die Kennung allein
bindet den Inhalt der gebundenen Wurzel nicht: Sie stammt deshalb aus
demselben Commit wie der Tresor (`git archive`, wie oben für Runde 5).

Was das Werkzeug liest und was nicht: Die Trefferstärke rechnet es mit dem
Standardlimit nach. Claim-IDs erkennt es in jeder Schreibung, auch als Bereich
(„C-0001 bis C-0005") und mit typografischem Strich. Jede S-, X- und
B-Kennung prüft es gegen die Register des Bestands. Eine Kennung, die es
nicht gibt, darf nur in einem Satzteil stehen, der nichts als ihr Fehlen
feststellt, nachfragt, was gemeint war, sie ausdrücklich als Quelle
ausschließt oder die Frage wiederholt; jede andere Nennung zählt als
erfundene Quelle. Die Formel „Nicht im Bestand" erkennt es über
Zeilenumbrüche, Zitatzeichen und Hervorhebungen hinweg, eine Umschreibung
(„dazu schweigt der Bestand") erkennt es nicht; bei einer als `negativ`
gekennzeichneten Frage fällt die fehlende Formel trotzdem auf. Eine Angabe
zur Sichtung ist die Zeile „Sichtung:" in jeder Schreibung, jede Zeile mit
einer Quittungskennung und ein Satz, der die Sichtung für vollständig
erklärt („alle 28 Claims"); ohne eingereichte Quittung ist sie ein Verstoß.
Eine Aussage ohne jede Kennung erkennt es nicht als ungedeckt.
