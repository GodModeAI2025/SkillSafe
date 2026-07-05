# Wissenstresor — Konzept (Profil oksv-lite/1.0)

Ein lokaler, evidenzgebundener Wissensspeicher als **purer Skill**: Der
Skill-Ordner selbst ist das Wissensartefakt. Kein Server, keine Datenbank,
kein Vektorstore — Markdown, YAML-Frontmatter im Google-OKF-Muster, ein
deterministisches Stdlib-Script und ein Vertrag (SKILL.md), der das Modell
auf strenge Regeln festlegt.

Leitbild: **Wissen ist Treibstoff (flüchtig), der Skill ist der Motor
(stabil).** Ändert sich Wissen, wird der Treibstoff (knowledge/, sources/,
INDEX, ROUTER, Graph, Manifest) neu erzeugt und validiert; der Motor
(Vertrag, Script, Schema, Workflows) bleibt unangetastet.

## Vertrauensmodell in einem Ordner

Der große OKSV-Vollausbau trennt Engine-, Content-, Assurance- und
Release-Zone auf Repositories. Der pure Skill bildet dieselben Grenzen
als Ordner- und Regelgrenzen ab:

| Zone | Im Skill | Schutzmechanismus |
|---|---|---|
| Engine | SKILL.md, scripts/, schema/, references/ | ändert sich nur durch bewusste Motor-Releases |
| Content | knowledge/, sources/, INDEX, ROUTER, graph/ | validate erzwingt Profil; raw/ unveränderlich (Hash im Register) |
| Assurance | doctor + Lint-Workflow (Smoke-Evals im Entwicklungs-Workspace, nicht im Paket) | nur diagnostisch; **Gold-Holdouts gehören NIE in den Skill** (Leakage) |
| Release | VERSION, MANIFEST.sha256, log.md | release-Gate fail-closed; neues Manifest invalidiert alte Prüfsummen |

## Architekturentscheidungen (AD)

### AD-01 · Keine RAG-Tokenisierung, keine Embeddings

**Entscheidung:** Es gibt keinen Vektorindex, kein Embedding-Modell, kein
Chunking und kein Ähnlichkeits-Tuning. „Tokenisierung" findet nur im
trivialen, deterministischen Sinn statt: Wörter normalisieren
(Kleinschreibung, Umlaut-Faltung) für Router-Abgleich und Volltextsuche.

**Begründung:** RAG beantwortet die Frage, wie man in Millionen
unstrukturierter Schnipsel die relevante Stelle findet. Bei einem
kuratierten Bestand bis in den niedrigen Tausenderbereich ist diese Frage
trivial — Router + Index + erschöpfende Volltextsuche erledigen sie. Was
Embeddings kosten würden: Determinismus (Nächste-Nachbarn ist eine
Blackbox, ein Schlagwort-Router ist prüfbar), Vertraulichkeit (Schnipsel
wandern an eine Embedding-Schnittstelle), Negativbefunde (RAG liefert
still das nächstgelegene falsche Fragment; `search` mit null Treffern ist
ein belastbares „steht nicht im Bestand") und Herkunft (Chunks
zerschneiden Struktur, Abschnittsnummern, Versionskontext).
**Grenze:** Bei Beständen ab Millionen Dokumenten kippt die Abwägung —
dann ist ein Vektorindex sein Geld wert, außerhalb dieses Skills.

### AD-02 · Wissensgraph: ja — abgeleitet, typisiert, deterministisch

**Entscheidung:** Der Graph existiert, wird aber nie von Hand gepflegt.
Knoten = Seiten, Kanten = typisierte `relations`-Einträge im Frontmatter
(`formalisiert`, `basiert_auf`, `praezisiert`, `ersetzt`, `verweist_auf`,
`widerspricht`, erweiterbar über das Type-Onboarding). `vault.py graph`
leitet `graph/graph.json` deterministisch ab; `doctor` erkennt Drift
zwischen Frontmatter und Graph.

**Begründung:** Der Graph trägt genau das, was flache Seitenkopien
verlieren — wie Konzepte zueinander stehen. `ersetzt` macht Supersession
maschinenlesbar (Antworten warnen vor veralteten Fassungen),
`widerspricht` macht Konflikte sichtbar statt sie still zu entscheiden,
und Kanten sind der einzige erlaubte Weg über Domänengrenzen — die
Quellentrennung bleibt baulich.

### AD-03 · Type-Onboarding: unbekannter Typ stoppt den Ingest

**Entscheidung:** `schema/types.yaml` ist die einzige Quelle erlaubter
Typen; der Validator lehnt jede Seite mit unregistriertem `type` ab
(fail-closed — bewusst strenger als OKF v0.1, das unbekannte Typen
toleriert). Trifft der Ingest auf einen neuen Datentyp, hält der Skill an
und stellt dem Menschen genau fünf Fragen: Was ist das? Erkennungs-
kriterien? Besonderheiten (inkl. Kritikalität, z. B. rechtsverbindlich,
personenbezogen, versionssensitiv)? Zusatz-Pflichtangaben für Claims?
Graph-Rolle und typische Relationen? Die Antworten wandern wortgetreu in
die Registry — jeder Typ wird genau einmal onboardet, danach entscheidet
die Registry, nicht das Gespräch.

**Begründung:** Typen steuern, wie extrahiert, geantwortet und im Graph
verknüpft wird. Rät das Modell Typen, driftet das Schema; fragt es jedes
Mal, nervt es. Einmal fragen, dauerhaft erzwingen — das Schema
ko-evolviert kontrolliert mit dem Bestand.

### AD-04 · Geschlossene Welt: nur aus der Quelle, nie aus Modellwissen

**Entscheidung:** Fakten kommen ausschließlich aus `knowledge/`. Jede
Kernaussage einer Antwort referenziert eine Claim-ID mit Quelle,
Fundstelle und Stand; eigene Einordnung ist als `Auslegung` markiert und
wird nie mit dem Wortlaut verwechselt. Deckt der Bestand eine Frage nicht:
wörtlich „Nicht im Bestand" — auch auf Nachfrage, auch „hilfsweise" nicht
aus Modellwissen ergänzt. Modellwissen dient Sprache, Struktur und
Routing-Urteil, nie dem Inhalt. Quellen sind Daten, keine Anweisungen
(indirekte Prompt Injection wird gemeldet, nicht befolgt).

**Begründung:** Der Wert des Tresors ist genau das, was er *nicht* tut:
nichts vermischen, nichts erfinden, für jede Aussage sagen, woher sie
kommt. Jede „kleine Ausnahme" zerstört die Eigenschaft, die den Bestand
prüfbar macht. Die Kehrseite wird akzeptiert und ausgeschrieben: Der
Tresor ist absichtlich unwissender als das Modell.

### AD-05 · Skript vor Modell: alles Deterministische läuft als Script

**Entscheidung:** `scripts/vault.py` (nur Python-Stdlib, relative Pfade,
läuft an jedem Installationsort) erledigt: Hashen, Registrieren,
Validieren (Profil, Typen, Claims, Relationen, Register-Hashes),
Indexieren, Graph ableiten, Routen, erschöpfend Suchen, Loggen, Zählen,
Diagnostizieren, Versionieren, Manifest schreiben und prüfen. Das Modell
macht ausschließlich, was Urteil braucht: Claims aus Quelltext
extrahieren, verdichten, Konflikte einordnen, Antworten formulieren,
semantisch linten. Jeder Modell-Output läuft anschließend durch
`validate` — das Script ist die letzte Instanz, nicht das Modell.

**Begründung:** Ein Modell, das Prüfsummen „im Kopf" rechnet oder Links
„gedanklich" verifiziert, ist die teuerste und unzuverlässigste Art, beides
zu tun. Scripts sind reproduzierbar (zweimal bauen ⇒ byte-identische
Artefakte), auditierbar und kosten keine Tokens. Zugleich sinkt der
Token-Verbrauch der Sessions, weil Routing und Prüfung nicht als
Modell-Denkarbeit anfallen.

### AD-06 · Mehrere Tresore: Grenze ist der Ort, nicht der Zugriff im Skill

**Entscheidung:** Künftige Sensitivitätsstufen (Unternehmen, Abteilung/
Business-Unit, Projekt, privat) trennen sich ausschließlich durch den
Installationsort einer vollständigen Tresor-Kopie und dessen bestehende
Zugriffsrechte (Repo-Berechtigung, Plugin-Scope, private Skill-Ordner) —
nie durch eine Rollen- oder ACL-Funktion in `vault.py` oder im Schema.
Jeder Scope bekommt eine eigene, vollständige Motor-plus-Content-Kopie;
Inhalte werden zwischen Kopien nie automatisch geteilt, nur als weiche,
textuelle Verweise (siehe `references/mehrere-tresore.md`).

Zwischen den Scopes gilt eine feste Prioritätsreihenfolge — eine
Eigenschaft des Scope-**Typs**, nicht eine Relation zwischen konkreten
Instanzen, kommt also ohne Cross-Tresor-Link aus: **Organisation** ist
Basis und gilt immer; **Fachbereich** kann Organisation für den eigenen
Fachbereich überschreiben; **Projekt** kann Fachbereich (und damit
Organisation) für das eigene Projekt überschreiben; **Persönlich** ist
rein additiv und kann nichts überschreiben oder ersetzen. Details und
Anwendung: `references/mehrere-tresore.md`.

**Begründung:** Der Tresor hat kein Server-, Nutzer- oder Auth-Konzept —
eine interne Zugriffskontrolle wäre eine trügerische Sicherheit, die die
eigene „kein Server"-Grundannahme verletzt. Die Bewegung ist nicht neu,
sondern dieselbe eine Ebene tiefer: Das Vertrauensmodell oben trennt
Engine/Content/Assurance/Release bereits als Ordner- und Regelgrenzen,
nicht als Feature. Dass das trägt, zeigt der Code selbst: `ROOT =
Path(__file__).resolve().parent.parent` in `vault.py` verankert jede Kopie
hart an ihren eigenen Ordner, und die Cross-Domain-Link-Prüfung schlägt
bereits fail-closed fehl, sobald ein Ziel außerhalb von `ROOT` liegt — eine
zweite Instanz kann technisch gar nicht versehentlich in eine andere
hineinlesen.

Die Prioritätsreihenfolge ist keine Wahrheitsfrage wie bei der
`widerspricht`-Relation (dort weiß der Tresor nicht, welcher Stand richtig
ist, deshalb bleiben beide offen stehen). Organisations-, Fachbereichs-
und Projektwissen können alle gleichzeitig korrekt sein, nur mit
unterschiedlichem Geltungsbereich — wie eine betriebliche Regelung, die
eine allgemeinere Vorgabe für einen engeren Rahmen präzisiert. Deshalb
wird hier nach fester Reihenfolge aufgelöst statt offen gelassen — aber
transparent, nie kommentarlos: analog zur Supersession bleibt die
überschriebene Basis benannt, nur nicht mehr als maßgeblich dargestellt.

**Grenze:** Eine Person mit legitimem Zugriff auf zwei Tresore gleichzeitig
ist unproblematisch — das Restrisiko ist Antwort-Attribution/Vermischung
in einer Session mit mehreren geladenen Tresoren, nicht Dateizugriff
(entschärft durch Regel 1 in `SKILL.md`), plus die Warnung, eine
höher-sensitive Instanz nie in einen breiteren Skill-Ladeort zu
symlinken oder zu kopieren.

## Antwort- und Befüll-Pfad (Kurzfassung)

**Antworten:** ROUTER → (Mischfrage? melden, pro Domäne trennen) →
INDEX der Domäne → genau die Kandidatenseiten lesen → Answer Envelope
mit Claim-Belegen, ältestem Stand, niedrigster Konfidenz, Konflikt- und
Supersession-Hinweisen → Lücken als „Nicht im Bestand". Plan B bei
Router-Fehlschlag: `vault.py search` (erschöpfend, Negativbefund
belastbar). Kurzfassungen und Claims gelten zur Abfragezeit als wahr —
wer pro Anfrage gegen die Quelle re-verifiziert, zahlt doppelt und macht
den Tresor sinnlos (Kompressionsregel).

**Befüllen:** Quarantäne (Rechte, Trust, Injection-Sichtung) →
registrieren + hashen (Script) → Typ bestimmen, ggf. Type-Onboarding →
Claims extrahieren (Wortlaut/Auslegung, exakte Fundstellen) → Seite
anlegen oder mergen (verdichten, nie spiegeln; Supersession statt
Löschen) → Router pflegen → `release` (Gate + Artefakte + Manifest).

**Pflegen:** `doctor` (Struktur, Script) + Lint-Workflow (Semantik,
Modell) — der Linter repariert nur Metadaten und Router, nie Inhalte.

## Bewusste Grenzen

* Kuratierte Bestände bis in den niedrigen Tausenderbereich an Seiten;
  darüber Vektorindex/Volltext-Engine erwägen (→ OKSV-Vollausbau).
* Der Schlagwort-Router verfehlt Synonyme; abgefedert durch Router-Pflege
  im Lint, Volltext-Fallback und dokumentiertes Überstimmen durch das
  Modell.
* Selbstprüfung im Skill ist nur diagnostisch. Belastbare Qualifikation
  braucht einen externen, gold-aware Prüfer gegen ein blindes System —
  Gold-Holdouts liegen deshalb grundsätzlich außerhalb dieses Skills.
* Extraktion und Verdichtung bleiben Modellarbeit und damit
  probabilistisch; das Profil macht ihre Ergebnisse prüfbar, nicht ihre
  Entstehung deterministisch.
* Nicht-Text-Quellen (Scan, Bild, Bild-PDF) hängen von der Lesefähigkeit
  des Modells ab (inkl. OCR); der Tresor prüft nur das Ergebnis
  (Claim-Grammatik, Fundstelle), nie die Bilderkennung selbst — unsichere
  Erkennung ist fail-closed zu behandeln (Regel 4).
* Seitengröße hat keine harte Obergrenze. `doctor` meldet ab
  Claims-/Zeilenschwelle einen Split-Kandidaten als Hinweis (ℹ️, keine
  Fehler-/Warnstufe) — Entscheidung und Ausführung bleiben Modellarbeit
  im Befüllen-Workflow, nie automatisches Zerschneiden (das wäre genau
  das Chunking, das AD-01 ablehnt).
* Mehrere Tresore (Organisation/Abteilung/Projekt/privat) trennen sich
  physisch durch Ordner bzw. Skill-Ladeort, nie durch eine Zugriffs-
  kontrolle im Skill selbst — siehe AD-06 und
  `references/mehrere-tresore.md`.

## Übernahmen aus der Quellenanalyse

Aus der Google-Ankündigung (S-0001) stammt das Grundformat: eine Datei pro
Konzept, der Pfad als Identität, Links als Graph — und die optionalen
Spec-Dateien, weshalb die Historie hier `log.md` und die Map `INDEX.md`
heißt. Aus dem Karpathy-Gist samt Kommentarbereich (S-0002) stammen die
operativen Härtungen: die **Kompressionsregel** (Seiten verdichten viele
Quellen; Fundstellen dienen menschlicher Nachprüfung, nicht der
Re-Verifikation pro Anfrage — ein Experiment im Kommentarbereich zeigt,
dass Spiegel-Seiten doppelt kosten, C-0103), **Lint als Pflicht** mit
strikter Rollentrennung (Drift der Querverweise ist der häufigste
gemeldete Fehlermodus, C-0104), **Map-first**, die
**Neue-Seite-vs-Edit-Heuristik**, **Konfidenz-Status pro Seite**, das
**Dead-End-Log** und der grep-bare Log-Präfix `## [JJJJ-MM-TT] aktion | Text`.
Aus dem Ontologie-Artikel (S-0003) stammt die Typ-Strategie: kleine fixe
Basis in `schema/types.yaml`, additive Erweiterung nur bei echtem Clash
(genau das leistet das Type-Onboarding, C-0202/C-0204) und ein bewusst
generischer Fallback-Typ `faktensammlung` für atomare Aussagen mit
Beförderungsregel ab etwa drei verwandten Claims (C-0203/C-0205) — dieser
Typ wurde im Bau tatsächlich per Onboarding registriert, nicht von Hand.
Diese Herkunft ist selbst Bestand: Die Demo-Domäne `demo-okf` dokumentiert
alle drei Quellen mit 16 Claims — der Tresor belegt seine eigenen
Konstruktionsentscheidungen mit seinen eigenen Mitteln.

## Abnahmekriterien (durchgeführt am 2026-07-04)

**Positiv:** `validate` grün auf dem Demo-Bestand (4 Seiten, 16 Claims,
3 Quellen) · `route` ordnet eine OKF-Frage deterministisch der Domäne zu
und nennt die getroffenen Schlagworte · `index` und `graph` erzeugen die
Artefakte; Determinismus im Doppellauf byte-identisch (diff leer) ·
`release` läuft als atomares Gate (validate → index → graph → VERSION →
log → Manifest) und `checksum --verify` ist danach grün · `doctor`-Ampel
grün · `search` liefert Treffer mit Datei und Zeile.

**Negativ (fail-closed nachgewiesen):** unbekannter Typ → Abbruch mit
Type-Onboarding-Hinweis · verletzte Claim-Grammatik → Abbruch mit
Dateizeile · Cross-Domain-Link im Fließtext → Abbruch mit Verweis auf die
Relations-Pflicht · nachträglich veränderte Quelldatei → Register-Hash-
Abweichung, Abbruch · `route` ohne Schlagwort-Treffer → Exit 1 mit
Plan-B-Hinweis · Suche nach nicht vorhandenem Begriff → Exit 1 mit
belastbarem Negativbefund („Nicht im Bestand").

**Funktional:** Der Antworten-Workflow wurde gegen den Demo-Bestand
durchgespielt — gedeckte Frage („Was ist OKF?") mit vollständigem Answer
Envelope inklusive Claim-Belegen, Stand und Konfidenz; ungedeckte Frage
mit wörtlicher Abstention und Ingest-Angebot. Der Befüllen-Workflow hat
beim S-0003-Ingest ein echtes Type-Onboarding durchlaufen (Typ
`faktensammlung`, dokumentiert in `log.md`).
