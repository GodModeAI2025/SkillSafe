# Mehrere Tresore (Organisation, Abteilung, Projekt, Privat)

Kein Pro-Frage-Workflow wie `antworten.md`/`befuellen.md`/`lint.md` —
dieses Dokument beschreibt, wie eine **neue, eigenständige Tresor-Instanz**
für einen anderen Wissensbereich entsteht, und was dabei bewusst
unverändert bleibt bzw. bewusst nicht gebaut wird.

## 1. Zweck

Künftige Wissensbereiche (Unternehmen, Fachabteilung/Business-Unit,
Projekt, privat) bekommen jeweils eine eigene, vollständige Kopie dieses
Skills — nie eine gemeinsame Domäne in einem geteilten Tresor. Warum:
AD-06 in `KONZEPT.md`. Kurzfassung: Der Tresor hat kein Auth-/ACL-Konzept;
die einzige tragfähige Grenze zwischen Sensitivitätsstufen ist der
Installationsort (Repo-Rechte, Plugin-Scope, private Skill-Ordner), nicht
ein Feature im Skript.

## 2. Wann eine neue Instanz — statt einer neuen Domäne

Analog zur Heuristik „neue Domäne nur bei wirklich getrenntem
Wissensraum" (`befuellen.md`), eine Ebene höher: eine neue **Instanz**
(statt nur einer neuen Domäne im bestehenden Tresor) immer dann, wenn sich
die Zielgruppe/Zugriffsberechtigung ändert — nicht nur das Thema. Beispiele:

* **Organisation:** unternehmensweit lesbar, breiteste Zielgruppe.
* **Abteilung/Business-Unit:** auf die Abteilung begrenzt.
* **Projekt:** auf ein Projektteam begrenzt, lebt typischerweise im
  Projekt-Repo selbst (wie dieser Tresor in SkillSafe).
* **Privat:** auf eine Person begrenzt, typischerweise im privaten
  Skill-Ordner (`~/.claude/skills/`), nie in einem geteilten Repo.

Bleibt die Zielgruppe gleich und nur das Thema wechselt, genügt eine neue
Domäne im bestehenden Tresor (`knowledge/<domäne>/`) — keine neue Instanz.

## 3. Namenskonvention

`wissenstresor-<scope>[-<bezeichner>]`, z. B. `wissenstresor-org`,
`wissenstresor-bu-legal`, `wissenstresor-projekt-skillsafe`,
`wissenstresor-privat`. Der Ordnername entspricht dem `name:`-Feld in
`SKILL.md`.

**Wichtig:** Jede Kopie dieses Skills trägt aktuell `name: wissenstresor`
im Frontmatter. Sind mehrere Kopien in derselben Session/demselben Host
gleichzeitig ladbar, ist ein identischer Name ein reales Risiko für
Verwechslung oder Shadowing beim Skill-Aufruf. Beim Bootstrap **zwingend**
umbenennen (Schritt 1 unten) — und vor Verlass empirisch prüfen, dass
beide Kopien tatsächlich getrennt und eindeutig aufrufbar sind, statt das
nur anzunehmen.

## 4. Bootstrap-Rezept (neue Instanz anlegen)

1. Ganzen `wissenstresor/`-Ordner an den neuen Ort kopieren, Ordner nach
   Konvention aus Abschnitt 3 umbenennen und für die folgenden Befehle in
   genau diesen Skill-Ordner wechseln.
2. In `SKILL.md`: `name:` und `description:` an den neuen Scope anpassen.
   Die Beschreibung muss den Scope-Typ explizit als eines von
   Organisation/Fachbereich/Projekt/Persönlich benennen (z. B.
   „Scope: Fachbereich") — das ist die Grundlage für die
   Prioritätsreihenfolge in Abschnitt 8 und macht den Tresor in einer
   Session mit mehreren Instanzen unterscheidbar.
3. Demo-Inhalt entfernen: `knowledge/demo-okf/` löschen und `sources/raw/`
   leeren. Unter `sources/derived/` alle `S-nnnn__media.json` entfernen,
   aber `README.md` behalten. Unter `sources/quarantine/` ebenfalls nur
   Payloads entfernen und die vertrauenswürdige `README.md` behalten.
4. `sources/REGISTER.md` auf die Kopfzeile zurücksetzen (keine Einträge).
5. `schema/begriffswelten.json` auf eine valide leere Registry zurücksetzen:
   `{"schema":"skillsafe.begriffswelten/v1","worlds":[],"concepts":[]}`.
   Demo-Begriffe dürfen ohne ihre Definition-Claims nicht stehen bleiben.
6. `ROUTER.md` von Hand auf die Kopfzeile zurücksetzen — der Router ist
   kuratiert, nicht generiert, `vault.py` schreibt ihn nie.
7. `log.md` auf seine Überschrift zurücksetzen; die Demo-Historie gehört
   nicht in den neuen Scope. `VERSION` auf `0.0.0` setzen.
8. `python3 scripts/vault.py log note "abgeleitet vom SkillSafe-Motor
   v<X>, Scope: <scope>, <Datum>"` — Herkunft der Kopie im Log dokumentiert.
9. `python3 scripts/vault.py release major` — ergibt v1.0.0, exakt wie
   beim ursprünglichen Bootstrap dieses Tresors und erzeugt Index, Graph
   und Manifest atomar vorbereitet neu.
10. `python3 scripts/vault.py doctor` — muss 🟢 sein, bevor Inhalt
    einzieht. Vorsicht: auf einem komplett leeren Bestand vorher kurz
    prüfen, dass `doctor`/`validate` sich sinnvoll verhalten (keine
    Domänen, kein Router-Eintrag ist der Normalfall bei null Domänen).

## 5. Was unverändert bleibt

`scripts/vault.py`, `schema/profil.md`, `schema/types.yaml` (nur die
Basistypen — keine demo-spezifischen Präzisierungen übernehmen),
`sources/derived/README.md`, `sources/quarantine/README.md` und alle
`references/*.md` sind der wiederverwendbare Motor und werden wörtlich
kopiert, nicht neu geschrieben. `schema/begriffswelten.json` bleibt als
Schema-Datei erhalten, wird beim Bootstrap aber wie oben beschrieben
inhaltlich geleert.

## 6. Querverweise zwischen Tresoren

Nur weich und textuell — z. B. ein Satz unter `## Kontext und Grenzen`
einer Seite („verwandtes Konzept im Organisations-Tresor, Seite X").
**Nie** ein `relations:`-Eintrag im Frontmatter: Relationsziele werden von
`vault.py` als Datei relativ zu `KNOWLEDGE` aufgelöst und geprüft — ein
Ziel in einer anderen Tresor-Instanz liegt außerhalb von `ROOT` und würde
entweder die Prüfung zum Scheitern bringen oder die Portabilitäts-Garantie
(„läuft an jedem Installationsort unverändert") verletzen.

Besteht echter Inhaltsbedarf (nicht nur ein Hinweis): die fremde Seite ganz
normal über den Befüllen-Workflow als externe Quelle in den Tresor holen,
der sie braucht (Quarantäne → Registrieren → Claims extrahieren). Kein
automatischer Sync-/Spiegel-Mechanismus zwischen Tresoren — das würde
Provenienz und Kompressionsregel unterlaufen.

## 7. Mischfrage über Tresore hinweg

Innerhalb eines Tresors erkennt `ROUTER.md` Domänen-Überschneidungen
deterministisch. Zwischen Tresoren gibt es keinen gemeinsamen Router —
„welcher Tresor deckt das?" ist bestenfalls Modell-Urteil, sobald mehrere
Tresor-Beschreibungen in derselben Session sichtbar sind. Das ist
**Best-Effort, nie vollständig**: anders als die Mischfragen-Erkennung
innerhalb eines Tresors gibt es keine Garantie, dass eine Überschneidung
bemerkt wird. Diese Grenze in Antworten so benennen, nicht Vollständigkeit
suggerieren.

## 8. Prioritätsreihenfolge zwischen Scopes

Sind in einer Session mehrere Tresore geladen und mehr als einer zum
selben Thema einschlägig, gilt eine feste Rangfolge — eine Eigenschaft
des **Scope-Typs**, nicht eine Relation zwischen zwei konkreten Instanzen
(kein Cross-Tresor-Link nötig, keine Verletzung der Pfad-Portabilität):

1. **Organisation** — Basis, gilt immer.
2. **Fachbereich** — kann Organisation für den eigenen Fachbereich
   **überschreiben** (bestehende Aussage ersetzen) **und ergänzen**
   (eigenes Wissen ohne Gegenstück auf Organisationsebene hinzufügen).
3. **Projekt** — kann Fachbereich (und damit Organisation) für das eigene
   Projekt ebenso überschreiben **und** ergänzen.
4. **Persönlich** — kann **nur ergänzen**, nie überschreiben oder
   ersetzen.

Überschreiben und Ergänzen sind zwei verschiedene Dinge: Überschreiben
setzt voraus, dass die breitere Ebene zum selben Thema schon etwas sagt
(die überschriebene Aussage bleibt sichtbar, siehe unten). Ergänzen
braucht kein Gegenstück — reines scope-eigenes Wissen ohne Pendant auf
einer breiteren Ebene ist kein Überschreiben und unterliegt auch nicht der
Transparenzpflicht, weil es nichts zu überschreiben gibt.

Unterschied zur `widerspricht`-Relation (innerhalb eines Tresors): dort
weiß der Tresor nicht, welcher Stand richtig ist, deshalb bleiben beide
Stände offen stehen, nie still entschieden. Zwischen Scopes ist das keine
Wahrheitsfrage — Organisations-, Fachbereichs- und Projektwissen können
alle gleichzeitig korrekt sein, nur mit unterschiedlichem Geltungsbereich
(wie eine betriebliche Regelung, die eine allgemeinere Vorgabe für einen
engeren Rahmen präzisiert). Deshalb wird hier nach fester Reihenfolge
aufgelöst — aber **transparent**, nie kommentarlos: Wer nach der
spezifischsten geladenen Stufe fragt, bekommt deren Antwort, die
überschriebene Basis wird aber immer benannt (analog zur Supersession:
die ältere Fassung verschwindet nie kommentarlos, sie gilt nur nicht mehr
als maßgeblich).

**Persönlich überschreibt nie.** Widerspricht ein persönlicher Inhalt
einer Organisations-, Fachbereichs- oder Projektaussage, ist das ein
Konflikt (wie `widerspricht`), keine gültige Überschreibung — beide
Stände nennen, nie zugunsten der persönlichen Notiz auflösen.

**Wo das deklariert wird:** Jede Instanz nennt ihren Scope-Typ explizit in
der `SKILL.md`-`description` (Bootstrap-Rezept, Schritt 2) — nur so kann
das Modell die Rangfolge anwenden, wenn mehrere Tresor-Beschreibungen in
einer Session sichtbar sind.

**Grenze:** Wie die Mischfrage über Tresore hinweg (Abschnitt 7) ist das
Best-Effort-Modellurteil, sobald mehrere Tresor-Beschreibungen sichtbar
sind — kein Script prüft das mechanisch (kein gemeinsamer Router über
Tresor-Grenzen hinweg). Nicht als Vollständigkeitsgarantie missverstehen.

## 9. Aktorkonvention für `geprueft_von` (Personenbezug)

`geprueft_von` steht im Frontmatter einer Seite, und Seiten wandern: der
Tresor wird als ZIP paketiert und in fremde Skill-Ordner entpackt. Ein
Klarname darin verlässt damit den Ort, an dem er entstanden ist, und zwar
ohne dass jemand das noch einmal bewusst entscheidet.

Deshalb gilt für alle Instanzen ab Organisation aufwärts: **Rollenkennung
statt Klarname.** `mensch:kuratorin`, `mensch:fachbereich-hr`,
`mensch:qs-team` sind gute Werte, `mensch:mark-zimmermann` ist einer, den man
später nicht mehr zurücknehmen kann, weil der Bestand die Historie behält.
Wer eine Person zweifelsfrei zuordnen muss, tut das außerhalb des Tresors,
etwa in einem Verzeichnis, das die Rollenkennung auflöst und dessen Zugriff
getrennt geregelt ist.

In einer rein persönlichen Instanz ist ein Kürzel unbedenklich, solange diese
Instanz nie in einen breiteren Skill-Ladeort kopiert oder symlinkt wird. Das
ist dieselbe Grenze wie in AD-06: der Installationsort entscheidet, nicht
ein Feature im Skill.

`prozess:<id>` und `agent:<name>/<version>` sind unkritisch, sie bezeichnen
Systeme. Der Validator prüft nur die Grammatik, nicht die Konvention; die
Konvention durchzusetzen ist Kuratierungsarbeit und gehört in den
Befüllen-Workflow, Schritt 5.

## 10. Was das hier NICHT ist

Kein ACL-/Rollensystem, kein Meta-Router-Script, kein
`vault.py identity`/`whoami`-Kommando, kein Content-Sync zwischen
Tresoren, keine neue Profil-Version für „verlinkte Tresore" — all das
bleibt bewusst ungebaut, bis eine zweite reale Instanz einen echten Bedarf
zeigt (Details und Auslöser: `KONZEPT.md`, AD-06 und „Bewusste Grenzen").
Additive Erweiterung nur bei echtem Clash, nie spekulativ — dieselbe Regel
wie beim Type-Onboarding (AD-03).
