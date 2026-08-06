# Workflow: Lint (Bestandspflege)

Ziel: Drift finden, bevor sie Antworten verfälscht. Drift ist der größte
Failure-Mode wachsender Wissensbestände: beim Ingest werden Querverweise,
Router-Schlagworte und Kurzfassungen unter-aktualisiert, und der Bestand
löst sich schleichend von sich selbst. Lint läuft darum regelmäßig —
nach jedem größeren Ingest und zusätzlich turnusmäßig, nicht nur „bei Bedarf".

## Rollentrennung (hart)

* **Das Script prüft Struktur.** `python3 scripts/vault.py doctor` findet
  deterministisch: Validierungsfehler, INDEX-/Graph-Drift, Router-Lücken,
  Orphans, ein fehlendes/beschädigtes/abweichendes Manifest, unsichere
  Pfade oder Symlinks, Quarantäne-Payloads, Domänen-überlappende
  Schlagworte, Begriffswelt-Referenzen/Zyklen/Kollisionen,
  Medienrepräsentationen/Regionen und Split-Kandidaten (Seiten über
  Claims-/Zeilenschwelle).
* **Das Modell prüft Semantik** (Schritte 2–4 unten) — das, was kein
  Script sehen kann.
* **Der Linter repariert nur Metadaten und meldet.** Er erstellt keine
  Wissensseiten, löscht keine Seiten und formuliert keine Claims um —
  das ist Aufgabe des Befüllen-Workflows mit Quellenzugang. Einseitige
  „Reparaturen" am Inhalt sind die schnellste Art, Evidenzbindung zu
  zerstören.

## Protokoll

**1. Strukturprüfung (Script).** `python3 scripts/vault.py doctor` —
Ampel und Befundliste sind die Arbeitsgrundlage. Rote Befunde zuerst.

**2. Semantikprüfung (Modell), pro Domäne:**

* **Kurzfassungs-Deckung:** Ist jede Kernaussage der Kurzfassung durch
  einen Claim der Seite gedeckt? Ungedeckte Sätze markieren — der
  Kurzfassung wird zur Abfragezeit vertraut, sie darf nichts behaupten,
  was kein Claim trägt.
* **Widerspruchssuche:** Sagen zwei Claims (auch domänenübergreifend)
  Unvereinbares, ohne dass eine `widerspricht`-Relation existiert?
  Relation setzen, beide Stände stehen lassen, melden.
* **Staleness-Urteil:** Seiten, deren `stand` deutlich zurückliegt oder
  deren Quelle als „im Fluss" markiert ist (z. B. Spezifikationen in
  v0.x): Kandidaten für Re-Validierung listen. Nichts still ändern —
  ohne neue Quelle gibt es nichts zu aktualisieren, nur zu melden.
* **Kompressionsprüfung:** Spiegelt eine Seite im Wesentlichen ein
  einzelnes Quelldokument (Body groß, Verdichtung gering)? Dann kostet
  sie doppelt statt zu sparen — als Merge-/Verdichtungs-Kandidat melden.
  `doctor` markiert ergänzend deterministisch Seiten über Claims-/
  Zeilenschwelle als Split-Kandidat (ℹ️ Hinweis) — das ersetzt dieses
  semantische Urteil nicht, sondern liefert den Ausgangspunkt dafür.
* **Duplikat-/Merge-Kandidaten:** Zwei Seiten mit stark überlappendem
  Gegenstand → Vorschlag zum Mergen (Ausführung: Befüllen-Workflow).
* **Tote Quellen:** Register-Einträge, auf die kein einziger Claim
  verweist — entweder gehören Claims nachgezogen (Befüllen) oder die
  Quelle wird als ungenutzt gemeldet. Ein Register voller Leichen
  täuscht Abdeckung vor, die es nicht gibt.
* **Beförderungs-Check:** Enthält eine `faktensammlung` etwa drei oder
  mehr thematisch verwandte Claims → eigene Konzeptseite vorschlagen
  (Claims ziehen um, IDs bleiben; Ausführung: Befüllen-Workflow).
* **Begriffswelt-Check:** Sind Aliase echte Synonyme oder nur lose
  verwandte Begriffe? Fehlt einer relevanten Seite ihre B-ID? Änderungen
  folgen `references/begriffswelten.md`; Aliastext wird nie zur Evidenz.
* **Medien-Check:** Ist jede freigegebene Repräsentation durch mindestens
  einen Claim genutzt, jede Claim-Region weiterhin korrekt lokalisiert und
  jede verdächtige Instruktion markiert? Inhaltliche Änderungen laufen über
  `references/multimodal.md`, nicht als stille Metadatenreparatur.

**3. Router-Pflege (einzige erlaubte Direktreparatur neben Metadaten).**
Fehlende Schlagworte und offensichtliche Synonyme in `ROUTER.md`
ergänzen; von `doctor` gemeldete Domänen-Überschneidungen prüfen:
gewollt (Mischfragen-Signal) oder Präzisierungsbedarf?

**4. Dead-End-Abgleich.** Steht ein gemeldeter Befund schon in
`notes/dead-ends.md` als bewusst verworfen? Dann nicht erneut aufreißen.

**5. Abschluss (Script).**

```
python3 scripts/vault.py log lint "Befunde: <n> rot / <n> gelb — <Kurzliste>"
```

Wurden dabei Metadaten oder Router geändert:
`python3 scripts/vault.py release patch` (Gate → Artefakte → VERSION → Log → Manifest).

## Externe Bezugsquellen im doctor-Report

`doctor` führt einen eigenen Abschnitt „Externe Bezugsquellen": je Quelle Art
und Bindungszustand, und bei gebundenen lokalen Quellen jeden Satzanker gegen
den heutigen Text.

Die Prüfung ist **hash-first**: Findet `doctor` den Satz-Hash an anderer
Position, meldet er „verschoben, nicht gebrochen"; findet er ihn gar nicht,
meldet er Drift. Beides ist **gelb**, nie rot, und blockiert keinen Release.

Das ist Absicht und keine Nachlässigkeit: Der Tresor kontrolliert die fremde
Quelle nicht. Würde ihre Änderung die eigene Ampel rot färben, hinge die
Betriebsbereitschaft dieses Bestands an fremden Bytes. Drift ist ein
Kuratierungsauftrag, keine Störung.

Ebenso bewusst gelb bzw. nur Hinweis: eine **ungebundene** lokale Quelle.
Sonst wäre jedes frisch entpackte Paket auf jedem neuen Host rot und AD-08
(reproduzierbarer Ordner) fiele. Fail-closed greift erst bei der Nutzung.

Deutung im Lint-Report:

| Meldung | Was zu tun ist |
|---|---|
| `verschoben, nicht gebrochen` | Nichts Dringendes. `sentence_index` beim nächsten Anfassen nachziehen. |
| `zitierter Satz nicht mehr gefunden` | Beleg prüfen: Formulierung geändert, Abschnitt entfernt oder Aussage überholt. Anker neu setzen oder Claim zurückziehen. |
| `ist auf diesem Host nicht gebunden` | Normal nach Installation. `extern bind` nur, wenn hier tatsächlich nachgeschlagen werden soll. |
| `weder belegt noch katalogisiert` | Die Quelle trägt nichts. Entweder verankern, katalogisieren oder aus dem Register nehmen. |

## Report-Form an den Menschen

```
Lint-Report <Datum> — Ampel: 🟢/🟡/🔴
Struktur (doctor): <Zusammenfassung>
Semantik:
- <Seite>: <Befund> → <Vorschlag, wer handelt: Befüllen/Mensch/nichts>
Router: <ergänzte Schlagworte / Überschneidungen>
Nicht behandelt (dead-ends): <…>
```

Jeder Befund nennt, **wer** handeln soll — der Linter selbst handelt nur
bei Metadaten und Router. Alles andere ist Vorschlag, nie vollendete Tatsache.
