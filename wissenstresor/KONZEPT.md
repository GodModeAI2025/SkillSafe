# Wissenstresor — Konzept (Profil oksv-lite/1.2)

Ein lokaler, evidenzgebundener Wissensspeicher als **purer Skill**: Der
Skill-Ordner selbst ist das Wissensartefakt. Kein Server, keine Datenbank,
kein Vektorstore — Markdown, flaches YAML-Frontmatter im Muster von Google
OKF (v0.1 wie v0.2; Verhältnis siehe unten),
strikte JSON-Registries für Begriffswelten und Medienfundstellen, ein
deterministisches Stdlib-Script und ein Vertrag (`SKILL.md`), der das Modell
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
| Engine | SKILL.md, scripts/, schema/, references/ | ändert sich nur durch bewusste Motor-Releases; genau ein ausführbares Script (AD-09) |
| Content | knowledge/, sources/, INDEX, ROUTER, graph/ | validate erzwingt Profil; raw/ nur reguläre registrierte Dateien; Medienregionen und Begriffs-IDs streng referenziert; Links/Aliasse verboten |
| Assurance | doctor + Lint-Workflow (Smoke-Evals im Entwicklungs-Workspace, nicht im Paket) | nur diagnostisch; **Gold-Holdouts gehören NIE in den Skill** (Leakage) |
| Release | VERSION, MANIFEST.sha256, log.md | exklusiver Lock; vorbereiteter Endstand; Rollback bei behandelten Fehlern; Manifest zuletzt |

Eine Randnotiz zur Zonenzuordnung: `schema/begriffswelten.json` liegt
physisch in der Engine-Zone, ist aber kuratierter Inhalt und wird im
Befüllen-Workflow mit dem Bestand gepflegt (`references/befuellen.md`,
Schritt 6). Eine Änderung nur an dieser Registry ist deshalb ein
Inhalts-Release (`minor`), keine Motoränderung.

## Architekturentscheidungen (AD)

### AD-01 · RAG-ähnlich arbeiten, ohne Embeddings

**Entscheidung:** SkillSafe folgt „retrieve then read", aber nicht der
üblichen Vektorspeicher-Implementierung. `vault.py query` prüft zuerst den
manifestierten Release-Snapshot und rankt danach natürliche Einheiten —
Seiten und Claims — mit festen Ganzzahlgewichten aus:

1. exaktem Vorzugsbegriff oder Alias einer kontrollierten Begriffswelt,
2. lexikalischen Token-/Phrasentreffern,
3. genau einem begrenzten Begriffs- oder Seitengraph-Hop.

Erst danach liest das Modell die gelieferten Seiten und formuliert aus den
gelieferten Claims. Es gibt keinen Vektorindex, kein Embedding-Modell, kein
willkürliches Chunking, keinen Netzwerkaufruf und keinen Query-Cache im Skill.

**Begründung:** „RAG" bezeichnet die Arbeitsfolge besser als eine konkrete
Speichertechnik. Für einen kuratierten Bestand bis in den niedrigen
Tausenderbereich liefern Claims, Begriffe und Graphkanten bereits starke
retrievalfähige Einheiten. Sie behalten Fundstelle, Status, Stand und
Quellenbezug. Feste Gewichte und stabile Tie-Breaker machen zwei Läufe
byteidentisch. Das Ranking scannt zwar alle Claims, bewertet aber keine
semantischen Paraphrasen: `no_candidates` löst deshalb eine vollständige
Modellprüfung der angegebenen Fallback-Seiten aus. Erst deren Ergebnis darf
„Nicht im Bestand" begründen. Embeddings würden hier zusätzliche Modell-
und Datenschutzgrenzen einführen, ohne die Evidenzgrenze zu ersetzen.

**Grenze:** Bei Millionen Dokumenten oder bewusst unscharfer externer Suche
kann die Abwägung kippen. Ein Vektorindex wäre dann ein separater,
evaluierter Vertrauensbereich außerhalb dieses portablen Skills; Claims
blieben auch dort die einzige Antwort-Evidenz.

### AD-02 · Wissensgraph: ja — abgeleitet, typisiert, deterministisch

**Entscheidung:** Der Graph existiert, wird aber nie von Hand gepflegt.
Knoten = Seiten, Kanten = typisierte `relations`-Einträge im Frontmatter
(`formalisiert`, `basiert_auf`, `praezisiert`, `ersetzt`, `verweist_auf`,
`widerspricht`, erweiterbar über das Type-Onboarding). `vault.py graph`
leitet `graph/graph.json` deterministisch ab; `doctor` erkennt Drift
zwischen Frontmatter und Graph. Seitenknoten führen zusätzlich ihre
validierten `B-nnnn`; die Begriffshierarchie selbst bleibt in der strikten
Registry und wird bei der Abfrage nur einen Hop expandiert.

**Begründung:** Der Graph trägt genau das, was flache Seitenkopien
verlieren — wie Konzepte zueinander stehen. `ersetzt` macht Supersession
maschinenlesbar (Antworten warnen vor veralteten Fassungen),
`widerspricht` macht Konflikte sichtbar statt sie still zu entscheiden,
und Kanten sind der einzige erlaubte Weg über Domänengrenzen — die
Quellentrennung bleibt baulich.

### AD-03 · Type-Onboarding: unbekannter Typ stoppt den Ingest

**Entscheidung:** `schema/types.yaml` ist die einzige Quelle erlaubter
Typen; der Validator lehnt jede Seite mit unregistriertem `type` ab
(fail-closed — bewusst strenger als OKF, das in v0.1 wie in v0.2 von
Konsumenten Toleranz gegenüber unbekannten Typen verlangt, §11). Trifft der Ingest auf einen neuen Datentyp, hält der Skill an
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
Validieren (Profil, Typen, Claims, Begriffe, Medienregionen, Relationen,
Register-Hashes), Indexieren, Graph ableiten, lokales Hybrid-Retrieval,
Routen, erschöpfend Suchen, Loggen, Zählen, Diagnostizieren, Versionieren,
Manifest schreiben und prüfen. Das Modell
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
Fachbereich sowohl überschreiben (bestehende Aussage ersetzen) als auch
ergänzen (eigenes Wissen ohne Gegenstück auf Organisationsebene
hinzufügen); **Projekt** kann Fachbereich (und damit Organisation) für
das eigene Projekt ebenso überschreiben und ergänzen; **Persönlich** kann
nur ergänzen — nie überschreiben oder ersetzen. Details und Anwendung:
`references/mehrere-tresore.md`.

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

**Exportgrenze:** `vault.py export --okf` gibt einen Stand nach außen und
steht damit quer zu „die Grenze ist der Installationsort". Deshalb ist das
Ziel mechanisch eingeschränkt: außerhalb von `ROOT`, kein Pfadsegment
`.claude` oder `.codex` (ein Bundle ohne Engine und Manifest darf nie als
Skill geladen werden), und entweder leer oder ein früherer Export. Rohquellen
wandern nur mit `--with-sources` mit, weil die Rechte-Spalte Freitext ist und
ein Script daraus nichts ableiten kann. Ein Rückweg existiert nicht: fremdes
OKF kommt über den regulären Ingest, nie über einen Import. Details:
`references/export-okf.md`.

**Grenze:** Eine Person mit legitimem Zugriff auf zwei Tresore gleichzeitig
ist unproblematisch — das Restrisiko ist Antwort-Attribution/Vermischung
in einer Session mit mehreren geladenen Tresoren, nicht Dateizugriff
(entschärft durch Regel 1 in `SKILL.md`), plus die Warnung, eine
höher-sensitive Instanz nie in einen breiteren Skill-Ladeort zu
symlinken oder zu kopieren.

### AD-07 · Multimodalität als gebundene Fundstelle, nicht zweite Wahrheit

**Entscheidung:** Bild- und PDF-Originale bleiben unverändert unter
`sources/raw/`. Eine kleine JSON-Repräsentation unter `sources/derived/`
bindet Originalhash, MIME, lokalen Extractor, Alttext und stabile
`R-nnnn`-Regionen. `validate` prüft Schema, Dateisignatur, Hashbindung,
Koordinaten und Region-Referenzen. Ein Claim auf eine Medienquelle nennt
genau eine Region; sichtbare Befunde tragen die eigene Art `Beobachtung`.

OCR, Transkript und Bildbeschreibung bleiben untrusted Quelldaten.
`query` liefert sie nie aus und rankt sie nicht direkt. Erst der kuratierte
Claim ist Antwort-Evidenz. Regionen mit eingebetteten Instruktionen werden
als `suspicious_instruction` markiert und können von keinem Claim
referenziert werden.

**Begründung:** So kann derselbe Skill Bilder in Claude Code, Codex oder
einer anderen Laufzeit nutzen, ohne ein bestimmtes OCR-Modell, eine API oder
einen Server vorauszusetzen. Das Original beweist, was eingelesen wurde; die
Region macht die Fundstelle portabel; der Claim trägt das geprüfte Wissen.

### AD-08 · Distribution ist ein reproduzierbarer Ordner, kein Dienst

**Entscheidung:** Der universelle Vertrag bleibt der eine Skill-Ordner mit
relativen Pfaden, Standard-Python und plattformneutralem `SKILL.md`.
`tools/build_skill_package.py` validiert den freigegebenen Bestand, baut
zweimal ein sortiertes ZIP mit festen Zeiten und Modi, vergleicht die
Hashes, prüft das Archiv und startet `doctor` aus einem fremden
Claude-ähnlichen Projektpfad. Ergebnis ist
`wissenstresor-<version>.skill`; entpackt wird immer derselbe Ordner, keine
zweite Implementierung.

**Begründung:** Codex und Claude Code unterscheiden sich beim Installations-
ort, nicht beim Fachvertrag. Ein reproduzierbares Archiv schützt Struktur
und Inhalt, während der entpackte Ordner weiterhin ohne Plattform-API,
MCP-Server oder Setup-Abhängigkeit funktioniert.

### AD-09 · Keine ausführbaren Verweise im Tresor

**Entscheidung:** Kein Tresorinhalt benennt einen Ausführungspfad, und aus
dem Tresor heraus wird genau ein Script ausgeführt: `scripts/vault.py`.
`validate` und `tools/build_skill_package.py` erzwingen das unabhängig
voneinander über eine Allowlist erlaubter Dateiarten; ein zweites Script,
ein Archiv, ein Binary oder ein gesetztes Ausführungsbit bricht fail-closed
ab. Der OKF-v0.2-Typ `Attested Computation` (§10) mit `executor` und
`attester` wird deshalb **nicht** übernommen.

**Begründung:** §10 verlangt, dass eine Content-Seite auf ausführbaren Code
oder Laufanweisungen zeigt. Code kennt der Tresor bisher nur in der
Engine-Zone, die sich ausschließlich durch bewusste Motor-Releases ändert.
Fünf Punkte tragen die Ablehnung je einzeln:

1. **Injection eskaliert.** Regel 6 hält Quellen als Daten, und die
   Injection-Prüfung greift heute an Claim-Text und Fundstelle. Darf Content
   einen Ausführungspfad benennen, wird aus „falsche Antwort" ein
   „Codeausführung". Der Weg läuft über kuratierten Content, und Kuratierung
   bleibt probabilistisch (siehe Bewusste Grenzen).
2. **Pfadhärtung.** Zwei der drei in §6.2 erlaubten Pfadformen fallen an
   `_safe_relative_path` durch: absolute URLs und bundle-relative Pfade mit
   führendem `/`, ebenso `..`. Nur ein relativer Pfad unterhalb `ROOT` wäre
   vereinbar.
3. **Nesting.** §10.2 braucht verschachteltes Frontmatter, das der
   Ein-Parser-Entwurf ausschließt. Der Verzicht ist eine Sicherheits- und
   keine Bequemlichkeitsentscheidung. Braucht eine Angabe wirklich Struktur,
   ist die zulässige Ablage eine strikte JSON-Registry unter
   `sources/derived/` nach dem Muster von `skillsafe.media/v1`.
4. **Kein Vertrauensanker.** Das Manifest ist selbstbezeugt. Der Tresor kann
   Integrität von Code nur relativ zu sich selbst behaupten, nicht gegenüber
   einem Empfänger, der das `.skill` entpackt.
5. **Asymmetrie.** Der Aufwand fällt vollständig im Tresor an, der Ertrag
   nicht: Receipt und Verdict entstehen laut §10.5 und §10.6 ausdrücklich
   außerhalb des Bundles und erreichen es nie. Receipt-Format und
   Attester-ABI sind in §12 zudem noch als offen markiert.

**Geprüfte Restmenge:** Eine rein deskriptive Variante wäre denkbar, also
ein Typ, der eine sanktionierte Berechnung nur dokumentiert, ohne
`executor`, ohne `attester` und ohne Pfad auf Code. Sie ginge über das
reguläre Type-Onboarding und bräuchte keine Parseränderung. Sie ist geprüft
und bewusst zurückgestellt, nicht übersehen. Sollte sie kommen, muss
`besonderheiten` ausdrücklich festhalten, dass die Seite nie eine Ausführung
auslöst, und `pflicht_extra` den Sanktionierungsgeber samt Stand als Claim
verlangen.

**Grenze:** Ausführbare Artefakte mit belastbarer Herkunft gehören in den
OKSV-Vollausbau mit getrennten Vertrauenszonen und Signaturen, nicht in
einen portablen Ordner ohne Vertrauensanker.

## Verhältnis zu OKF v0.2

OKF v0.2 (2026-07-24) macht Provenienz, Vertrauen, Lebenszyklus und
Attestierung zu Feldern erster Klasse. Der Bestand dokumentiert die
Spezifikation selbst in `knowledge/demo-okf/okf-v02.md` (S-0004,
C-0301 bis C-0310). Für das Profil gilt:

| v0.2 | Profil | Verhältnis |
|---|---|---|
| `sources` mit Glaubwürdigkeitssignalen (§5.1) | Claim-Grammatik plus gehashtes `sources/REGISTER.md` | Profil ist strenger: erzwungene Evidenzart, Prüfsumme, geklärte Rechte. Die Fußnotenattribution aus §5.1 leistet die Claim-ID bereits |
| `verified` (§5.2) und Trust-Tiers (§5.3) | `geprueft_von` plus `geprueft_am`, Tier abgeleitet | übernommen, flach und deutsch. Das Tier trägt die §5.3-Namen, wird nie gespeichert und geht nie in den Score ein |
| `generated` (§5.2) | keine Entsprechung | bewusst offen: der Tresor weiß, wer geprüft hat, nicht wer geschrieben hat. Ein Aktor für die Erzeugung wäre eine zweite Angabe ohne zweiten Nutzen |
| `status` (§5.4) | `status` plus typisierte `ersetzt`-Kante | Der Status sagt, dass etwas nicht mehr gilt; die Kante sagt, was stattdessen gilt. v0.2 kennt nur ungetypte Links und kann das nicht ausdrücken |
| `stale_after` (§5.5) | `stand` | Echte Lücke: `stand` ist deskriptiv, kein Verfallsdatum |
| Attestierung (§10) | `MANIFEST.sha256`, Register-Hashes, reproduzierbares Paket | Verschiedene Ebenen: hier ruhende Bytes, dort ein einzelner Rechenlauf. Ablehnung siehe AD-09 |

Die Abbildung nach außen leistet `vault.py export --okf`, und zwar
ausschließlich dort: der interne Datenvertrag bleibt unangetastet. `aktiv` zu
`stable`, `veraltet` zu `deprecated`, `in-pruefung` zu `draft` ist die einzige
Stelle exakter semantischer Deckung zwischen beiden Welten. Alles Weitere ist
Übersetzung mit benannten Verlusten (`generated`, `sources[].author`,
`usage_count`), und was nicht abbildbar ist, bleibt leer statt geraten zu
werden. Protokoll und Grenzen: `references/export-okf.md`. Die
Namenskollisionen selbst stehen in `schema/profil.md`.

Der Tresor bleibt dabei einseitig: er produziert OKF, er konsumiert keins.
Ein Import fremder Bundles gibt es nicht, weil die Evidenzbindung an eine
gehashte lokale Datei nicht importierbar ist. Fremdes OKF-Wissen kommt
denselben Weg wie jede andere Quelle.

## Antwort- und Befüll-Pfad (Kurzfassung)

**Antworten:** `query` → Snapshot-/Manifest-Gate → Begriff/Alias +
Lexik + ein Graph-Hop → genau die Kandidatenseiten lesen → Answer Envelope
mit Claim-Belegen, ältestem Stand, niedrigster Konfidenz, Konflikt- und
Supersession-Hinweisen → bei fehlenden oder unzureichenden Kandidaten die
`fallback.page_paths` semantisch vollständig prüfen → erst danach Lücken als
„Nicht im Bestand" ausweisen.
Kurzfassungen und Claims gelten zur Abfragezeit als wahr — wer pro Anfrage
gegen Rohquelle oder Medienrepräsentation re-verifiziert, zahlt doppelt und
macht den Tresor sinnlos (Kompressionsregel).

**Befüllen:** Quarantäne (Rechte, Trust, Injection-Sichtung) →
registrieren + hashen (Script) → Typ bestimmen, ggf. Type-Onboarding →
bei Medien geprüfte Regionen erzeugen → Claims extrahieren
(Wortlaut/Beobachtung/Auslegung, exakte Fundstellen) → Begriff IDs binden →
Seite anlegen oder mergen (verdichten, nie spiegeln; Supersession statt
Löschen) → Router pflegen → `release` (Gate + Artefakte + Manifest).
Solange außer der echten `sources/quarantine/README.md` irgendein Eintrag
in der Quarantäne liegt, bleiben Validierung, Manifest und Release gesperrt.
Quarantäne-Payloads gelangen nie ins Manifest; die vertrauenswürdige README
ist die einzige Allowlist-Datei und bleibt selbst per Prüfsumme geschützt.

**Pflegen:** `doctor` (Struktur, Script) + Lint-Workflow (Semantik,
Modell) — der Linter repariert nur Metadaten und Router, nie Inhalte.

## Bewusste Grenzen

* Kuratierte Bestände bis in den niedrigen Tausenderbereich an Seiten;
  darüber Vektorindex/Volltext-Engine erwägen (→ OKSV-Vollausbau).
* Kontrollierte Begriffswelten decken nur kuratierte Synonyme. Nicht
  gepflegte Sprache kann weiterhin verfehlt werden; lexikalische
  Claim-Suche liefert deshalb nur Kandidaten. `no_candidates` ist ein
  Rückfallsignal zur vollständigen Seitenprüfung, kein Negativbefund.
* Selbstprüfung im Skill ist nur diagnostisch. Belastbare Qualifikation
  braucht einen externen, gold-aware Prüfer gegen ein blindes System —
  Gold-Holdouts liegen deshalb grundsätzlich außerhalb dieses Skills.
* Extraktion und Verdichtung bleiben Modellarbeit und damit
  probabilistisch; das Profil macht ihre Ergebnisse prüfbar, nicht ihre
  Entstehung deterministisch.
* Nicht-Text-Extraktion bleibt Modell-/OCR-Arbeit. Der Tresor prüft
  Dateisignatur, Originalhash, Repräsentationsschema und Claim-Bindung,
  nicht die semantische Richtigkeit der Bilderkennung selbst. Diese muss
  vor `verified: true` lokal oder menschlich geprüft werden.
* Seitengröße hat keine harte Obergrenze. `doctor` meldet ab
  Claims-/Zeilenschwelle einen Split-Kandidaten als Hinweis (ℹ️, keine
  Fehler-/Warnstufe) — Entscheidung und Ausführung bleiben Modellarbeit
  im Befüllen-Workflow, nie automatisches Zerschneiden (das wäre genau
  das willkürliche Chunking, das AD-01 vermeidet).
* Der Tresor führt keine sanktionierten Berechnungen aus und attestiert
  keine. Er kann sie höchstens dokumentieren. Wer einen Zahlenwert gegen
  einen Rechenlauf prüfen will, braucht eine Ausführungsschicht, und die
  hätte der Tresor nur um den Preis ausführbarer Inhalte (AD-09).
* Mehrere Tresore (Organisation/Abteilung/Projekt/privat) trennen sich
  physisch durch Ordner bzw. Skill-Ladeort, nie durch eine Zugriffs-
  kontrolle im Skill selbst — siehe AD-06 und
  `references/mehrere-tresore.md`.
* Der Mehrdatei-Release ist transaktional für behandelte Fehler, aber nicht
  stromausfall-atomar. Das Manifest wird als letzter Commit-Marker ersetzt;
  ein Prozessabbruch außerhalb des Rollbacks erzeugt deshalb keinen
  fälschlich grünen Stand, sondern eine erkennbare Manifestabweichung.
  Der Marker deckt den manifestierten Bestand ab; `log.md` wird während der
  Transaktion geprüft, bleibt als fortlaufendes Journal aber bewusst
  außerhalb des Manifests. Mutationen werden durch einen gemeinsamen Lock
  serialisiert, Zielverzeichnisse über geprüfte `dir_fd`s verankert.

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
Die Namen `index.md` und `log.md` sind aus der Spezifikation übernommen, ihre
dortigen Strukturen (§8, §9) aber bewusst nicht: `INDEX.md` ist eine Tabelle,
weil sie eine menschliche Audit-Map ist, und `log.md` trägt den grep-baren
Präfix. Beide liegen ohnehin oberhalb der Bundle-Wurzel `knowledge/` und
damit außerhalb des Geltungsbereichs von §8 und §9. Die Übernahme der Namen
ist also eine Herkunftsnotiz und keine Konformitätsaussage.

Aus der Spezifikation v0.2 (S-0004) stammt kein Feld, aber eine Präzisierung
des eigenen Standpunkts: die Vertrauenssignale, die v0.2 einführt, sind hier
teils schon strenger gelöst, teils bewusst abgelehnt (AD-09), und in einem
Punkt fehlt sie tatsächlich (Verfallsdatum). Das steht oben unter
„Verhältnis zu OKF v0.2".

Diese Herkunft ist selbst Bestand: Die Demo-Domäne `demo-okf` dokumentiert
alle vier Quellen mit 26 Claims — der Tresor belegt seine eigenen
Konstruktionsentscheidungen mit seinen eigenen Mitteln und hält seine eigene
Supersession im Graphen fest, statt die überholte Fassung zu löschen.

## Abnahmekriterien (zuletzt durchgeführt am 2026-07-28)

**Positiv:** `validate` und `doctor` grün auf 5 Seiten, 26 Claims und
4 Quellen · `query OKF`, `query "offenes Wissensformat"` und `query C-0001`
liefern deterministisch C-0001 · zehn identische Läufe erzeugen
byteidentisches JSON · Bild-Fixture mit Originalhash, Repräsentation und
Region liefert ausschließlich den gebundenen Beobachtungs-Claim ·
`release` ersetzt Manifest zuletzt und rollt injizierte Schreibfehler an
jeder Position zurück · zwei `.skill`-Archive sind byteidentisch, bestehen
ZIP-Prüfung und laufen nach Installation unter `.claude/skills/` aus einem
fremden Projekt-CWD.

**Negativ (fail-closed nachgewiesen):** unbekannter Typ oder Begriff,
Alias-Kollision und `broader`-Zyklus → Abbruch · fehlende Medienrepräsentation,
unbekannte oder als Injection markierte Region → Abbruch · OCR-Injection-
Canary erscheint nie in Query-Evidenz · Instruktionssignatur in Claim-Text
oder Fundstelle → Abbruch · verschachteltes Frontmatter in jeder Form
(Blockform, Map-Liste, Tabulator) → Abbruch, und Unterschlüssel gelangen
nie ins Frontmatter-Dictionary · fremde Dateiart, zweites Script oder
gesetztes Ausführungsbit im Tresorbaum → Abbruch in `validate` und im
Paketbau · kein Retrieval-Treffer sowie Treffer nur im
Router → `no_candidates`, semantische Deckung `not_assessed` und explizite
Fallback-Seiten · Manifestdrift oder Quarantäne-Payload → `invalid_vault`
ohne Claims · absolute/traversierende Pfade, Symlinks, Hardlinks,
getarntes SVG und beschädigte Registries/Manifeste → Abbruch.

**Funktional:** Der Antworten-Workflow nutzt den stabilen JSON-Vertrag und
formuliert weiterhin ein Answer Envelope mit Claim-Belegen, Stand und
Konfidenz; die Begriffswelt verbessert Discovery, ohne Evidenz zu erfinden.
Der Medien-Workflow bewahrt Original, Region und Injection-Fund, ohne
Regions-Text zur Antwortquelle zu machen. Type-Onboarding,
Kompressionsregel und wörtliche Abstention bleiben unverändert.
