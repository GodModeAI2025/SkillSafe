# Workflow: Als OKF-v0.2-Bundle exportieren

Ziel: den freigegebenen Bestand so ausgeben, dass ein fremder
OKF-v0.2-Konsument ihn lesen kann, ohne dass sich am internen Datenvertrag
etwas ändert.

Dieser Workflow ist **kein Automatismus**. Er steht bewusst nicht in der
Workflow-Tabelle von `SKILL.md`: kein Antworten-, Befüllen- oder
Lint-Durchlauf ruft ihn auf. Ein Export gibt Wissen aus der Hand, und diese
Entscheidung trifft ein Mensch, nicht ein Trigger.

## Kommando

```bash
python3 scripts/vault.py export --okf --out <zielordner> [--with-sources]
```

## Sechs Regeln

1. **Menschenakt.** Der Export läuft nur, wenn jemand ihn aufruft. Wird er in
   einem Skript verkettet, gehört an diese Stelle ein Kommentar, warum.
2. **Kein Skill-Ladeort.** Ein Ziel mit dem Pfadsegment `.claude` oder
   `.codex` bricht fail-closed ab, sowohl buchstäblich als auch nach
   Auflösung von Symlinks. Grund: ein exportiertes Bundle hat keine Engine,
   kein Manifest und keine Regeln. Landet es in einem Skill-Ordner, lädt ein
   Agent es als Wissensquelle ohne jede Absicherung, und die Trennung aus
   AD-06 ist aufgehoben.
3. **Kein Ziel im Tresor und kein Fremdinhalt.** Das Ziel muss außerhalb von
   `ROOT` liegen und entweder nicht existieren, leer sein oder ein früherer
   Export sein. Erkannt wird ein früherer Export am `okf_version` im
   Wurzel-`index.md` (§12). Ein Verzeichnis mit fremdem Inhalt wird nie
   angefasst.
4. **Nur ein freigegebener Release.** `validate` muss grün sein und der Stand
   dem Manifest entsprechen. Ein Zwischenstand wird nicht exportiert, sonst
   entstünde ein Bundle, das zu keinem Release gehört.
5. **Rohquellen nur mit `--with-sources`.** Ohne das Flag bleibt
   `sources[].resource` ein nicht folgbarer Deskriptor, was §5.1
   ausdrücklich erlaubt. Die Rechte-Spalte des Registers ist Freitext; ob
   eine Ablage weitergegeben werden darf, kann kein Script entscheiden. Wer
   das Flag setzt, bestätigt damit, die Rechte geprüft zu haben.
6. **Einbahnstraße.** Es gibt kein `import-okf`. Fremdes OKF-Wissen kommt
   denselben Weg wie jede andere Quelle: Quarantäne, lokaler Abzug,
   Registrierung, Claim-Extraktion (`references/befuellen.md`).

## Was der Export abbildet

| intern | im Bundle |
|---|---|
| `status: aktiv` / `veraltet` / `in-pruefung` | `status: stable` / `deprecated` / `draft` (§5.4) |
| `sources: [S-nnnn]` plus Registerzeile | `sources`-Liste mit `id`, `resource`, `title`, `last_modified` (§5.1) |
| Trust `T1`/`T2`/`T3` | `oksv_trust` pro Quelleneintrag, ausdrücklich kein v0.2-Feld |
| `geprueft_von` / `geprueft_am` | `verified: { by, at }` mit `mensch:` zu `human:`, `prozess:` zu `process:`, `agent:x/y` zu `x/y` (§5.2, §7) |
| Claim-Zeile | unverändert plus Fußnote `[^S-nnnn]`; das Label ist die S-ID, weil §5.1 sie als Join-Key nennt |
| `relations` | Abschnitt „Beziehungen" mit bundle-relativen Links, führender Slash (§6.1) |
| erster Satz der Kurzfassung | `description` (§4.1) |
| `confidence`, `domain`, `version`, `stand`, `concepts` | `oksv_`-Zusatzschlüssel, nach §4.1 erlaubt |
| Vorzugsbegriffe der `concepts` | `oksv_concept_labels` im Frontmatter, nicht im Rumpf |
| `INDEX.md` (Tabelle) | `index.md` pro Verzeichnis als Bullet-Liste (§8), Wurzel mit `okf_version` (§12) |
| `log.md` (grep-barer Präfix) | `log.md` datumsgruppiert, neueste zuerst (§9) |

## Ersetzen statt ergänzen

Der Export schreibt zuerst vollständig in ein frisches Staging-Verzeichnis
neben dem Ziel und ersetzt das Ziel danach in einem Zug. Das hat drei Gründe.
Das Staging enthält keine Symlinks, also kann kein vorbereiteter Link im
Zielordner den Schreibvorgang aus dem Ziel heraustragen. Ein Abbruch
hinterlässt keinen Halbstand, das Ziel bleibt unverändert. Und ein früherer
Export wird ersetzt, nicht übermischt: eine Seite, die es im Bestand nicht
mehr gibt, bleibt sonst als vollständig konformes Dokument im Bundle stehen
und ist von echtem Inhalt nicht zu unterscheiden.

Wer ein Bundle behalten will, kopiert es weg, bevor er neu exportiert.

## Was der Export bewusst nicht kann

* **`generated`.** Der Tresor weiß, wer geprüft hat, nicht wer geschrieben
  hat. Das Feld bleibt leer statt einen Aktor zu erfinden.
* **`sources[].author`.** Das Register hat keine Urheberspalte. Eine achte
  Spalte wäre nachrüstbar, ist aber eine eigene Entscheidung.
* **`usage_count` und `usage_window`.** Ein lokaler Tresor ohne Telemetrie
  hat diese Zahlen nicht.
* **`last_modified` bei nicht-datumsförmigem Stand.** Steht in der Spalte
  „Stand/Version" etwas wie `v0.2 / 2026-07-24`, bleibt das Feld weg. Ein
  Datum daraus zu raten wäre genau die Art Vermutung, die Regel 4 verbietet.
* **`stale_after`.** Der interne Vertrag kennt kein Verfallsdatum. Kommt es,
  wandert es hier mit.
* **`Attested Computation`.** Bewusst abgelehnt, siehe AD-09 in
  `KONZEPT.md`.
* **Das Trust-Tier.** Es wird nicht geschrieben. Das Profil sagt zu, dass es
  nur abgeleitet und nie gespeichert wird, und ein Konsument leitet es nach
  §5.3 ohnehin selbst aus `verified` ab.
* **§11-Konformanz mit `--with-sources`.** Die kopierten Rohquellen sind
  byteidentisch zum Original, damit ihr Hash gegen das Register prüfbar
  bleibt. Markdown-Rohquellen tragen deshalb weiterhin ihr eigenes
  Frontmatter mit dem Schlüssel `typ` statt `type` und sind damit keine
  OKF-Konzeptdokumente. Ein Bundle mit `--with-sources` erfüllt §11
  Bedingung 2 also bewusst nicht. Wer strikte Konformanz braucht, exportiert
  ohne das Flag; wer die Evidenz braucht, nimmt die Abweichung in Kauf. Einen
  konformen Kopf voranzustellen wäre der dritte Weg und scheidet aus, weil er
  die Byte-Identität und damit die Hash-Prüfbarkeit zerstört.

## Nach dem Export

Der Export schreibt nichts im Tresor und ist kein Release-Ziel. `VERSION`,
`MANIFEST.sha256` und `log.md` bleiben unberührt. Zwei Exporte desselben
Stands sind byteidentisch; wer das prüfen will, vergleicht die Hashes der
Zielbäume.

Das Ergebnis ist eine Momentaufnahme, kein zweiter Tresor. Es trägt keine
Prüfsummen und keine Regeln, und es wird nicht mitgepflegt. Wer es weitergibt,
gibt einen Stand weiter, nicht ein System.
