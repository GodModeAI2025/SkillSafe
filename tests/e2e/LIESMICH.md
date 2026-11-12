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

Für Runde 2 dasselbe mit `3896b9f` und `runde-2.json`. Das Werkzeug glaubt
dem Protokoll nichts: Es fragt die Trefferstärke jeder Frage neu ab, fährt
jede Quittung erneut gegen die Engine und liest die zitierten Claim-IDs aus
dem Antworttext.

Der Block `ergebnis` in jeder Datei ist die Zusammenfassung dieses Werkzeugs
zum Messzeitpunkt. `tools/check_docs.py` hält die Zahlen in `README.md` und
`index.html` an diese Blöcke gebunden.

## Was die Zahlen sagen und was nicht

44 Fragen, ein Demo-Bestand mit 28 Claims, Agenten desselben Modells, und die
Fragen stammen aus `tests/gold/recall-demo.json`. Gemessen ist damit, dass der
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
beantwortet. `sweep_args` nennt abweichende Schalter der Sichtung, etwa
`["--size", "10"]`. Ein optionaler Block `stand` mit `manifest_sha256` bindet
das Protokoll an einen Stand.
