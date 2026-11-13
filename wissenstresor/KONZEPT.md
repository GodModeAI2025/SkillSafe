# Wissenstresor — Konzept (Profil oksv-lite/1.3)

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
| Assurance | doctor + Lint-Workflow (Smoke-Evals und Recall-Gold im Entwicklungs-Workspace, nicht im Paket) | nur diagnostisch; **Gold-Holdouts gehören NIE in den Skill** (Leakage) |
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
2. lexikalischen Token-/Phrasentreffern samt ihren Wortformen (Flexion,
   `-ung`, Kompositumteile; `wortform/v1`),
3. genau einem begrenzten Begriffs- oder Seitengraph-Hop.

Erst danach liest das Modell die gelieferten Seiten und formuliert aus den
gelieferten Claims. Es gibt keinen Vektorindex, kein Embedding-Modell und kein
willkürliches Chunking. Auf dem Default-Query-Pfad gibt es außerdem keinen
Netzwerkaufruf, keinen Dateizugriff außerhalb des Skill-Ordners und keinen
Query-Cache; erst das ausdrückliche `--extern` liest aufgeführte externe
Bezugsquellen, in einem eigenen Block und ohne Einfluss auf den lokalen
Fingerprint (AD-10 bis AD-13).

**Begründung:** „RAG" bezeichnet die Arbeitsfolge besser als eine konkrete
Speichertechnik. Für einen kuratierten Bestand bis in den niedrigen
Tausenderbereich liefern Claims, Begriffe und Graphkanten bereits starke
retrievalfähige Einheiten. Sie behalten Fundstelle, Status, Stand und
Quellenbezug. Feste Gewichte und stabile Tie-Breaker machen zwei Läufe
byteidentisch. Das Ranking scannt zwar alle Claims, bewertet aber keine
semantischen Paraphrasen. Es weist deshalb selbst aus, wie viel der Frage es
erkannt hat, und bei schwacher Deckung ist die Vollsichtung Pflicht: Das
Modell liest jeden Claim, das Script prüft die Quittung (AD-14). Erst sie
darf „Nicht im Bestand" begründen. Embeddings würden hier zusätzliche Modell-
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

Jede Seite, die `query` oder eine Quittung von `sweep` ausgibt, nennt ihre
Kanten in beiden Richtungen (`pages[].relations`). Die ausgehenden stehen im
Frontmatter der Seite, die eingehenden nur auf der jeweils anderen: Wer eine
überholte Seite liest, sähe dort sonst nicht, welche sie ersetzt. Nach einer
Vollsichtung gibt es zudem keinen Graph-Hop, der die Nachfolgerin als
Kandidaten hereinholte. Die Angabe ist ein Verweis und nie Evidenz.

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

**Grenze, seit aufgeführte Bezugsquellen existieren (AD-10):** Ein Tresor darf
einen anderen als `X-nnnn` zitieren. Das schafft **keinen** Zugriff — es nutzt
den, den das Betriebssystem der ausführenden Person ohnehin gewährt. Es
schafft aber einen neuen Leckkanal: Wer legitim zwei Tresore hat, kann den
sensibleren als Quelle des weniger sensiblen binden und Inhalte an die falsche
Stelle kuratieren. Kein Mechanismus verhindert das, weil es per AD-06 keine
ACL gibt. Gemildert, nicht gelöst: Der Scope-Typ steht in der Registerzeile,
`doctor` warnt bei invertierter Scope-Richtung, `BETRIEB.md` benennt das
Risiko. Wer eine echte Grenze braucht, braucht getrennte Rechte am
Installationsort — genau wie bisher.

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

**Grenze, seit es externe Bezugsquellen gibt:** Der generierte Orchestrator
könnte nach generiertem Code klingen. Er ist `.json`, wird von
`parse_orchestrators` gelesen und von nichts ausgeführt; `ARTEFAKT_SUFFIXE`
und die zweite Allowlist im Paketbau bleiben deshalb unverändert — das ist der
Beleg, nicht die Behauptung. Ein fremder Tresor wird ebenso als Daten gelesen:
sein Manifest rechnet diese Engine selbst nach, gelesen wird nur, was es pinnt,
und sein `scripts/vault.py` ist eine Datei mit einer Prüfsumme. **Restrisiko außerhalb der Prozessgrenze:** Ein
fremder Baum kann eine `SKILL.md` enthalten, die ein Agent nebenher lädt. Das
kann `vault.py` nicht verhindern; es gehört beim Binden bedacht und steht so
in `references/externe-quellen.md`.

### AD-10 · Externe Bezugsquellen sind Anker, nicht Bestand

**Entscheidung:** Fremdes Material wird satzweise über `X-nnnn` und Satzanker
`A-nnnn` belegt, statt in den Bestand kopiert zu werden. Der Anker speichert
den zitierten Satz und seinen SHA-256; der Claim bleibt die kuratierte,
komprimierte Aussage.

**Begründung:** Ein Bestand, der die Inhalte eines lebenden Fremdrepositoriums
einfriert, ist nach wenigen Wochen falsch — und zwar auf die unangenehmste
Art, weil er weiter richtig klingt. Eingefroren wird deshalb nur das Zitat,
nicht die Quelle. Das ist genau die Bauform, die Bild und PDF schon haben:
`R-nnnn` bindet einen sichtbaren Befund, `A-nnnn` einen Satz. In beiden Fällen
bleibt der Quelltext untrusted und ist nie Evidenz; Evidenz ist der Claim.
Wer `references/multimodal.md` verstanden hat, muss
`references/externe-quellen.md` ohne neues Konzept lesen können.

**Grenze:** Anker altern. Eine Umformulierung in der Quelle bricht den Beleg.
Deshalb prüft `doctor` hash-first und meldet Verschiebung getrennt von Bruch —
und deshalb blockiert Drift keinen Release: Der Tresor kontrolliert die fremde
Quelle nicht.

### AD-11 · Die Bindung liegt außerhalb des Manifests

**Entscheidung:** `sources/EXTERN.md` (Was darf erreicht werden) ist
manifestiert; `.vault-extern.json` (Wo findet diese Maschine eine lokale
Quelle) ist es nicht — dieselbe Sonderstellung wie `log.md`. Eine Netzquelle
braucht gar keine Bindung: ihre URL ist auf jedem Host dieselbe.

**Begründung:** Ein absoluter Pfad ist eine Eigenschaft des Hosts, nicht des
Artefakts. Stünde er im Manifest, wäre die Paket-SHA-256 maschinenabhängig und
AD-08 (Distribution ist ein reproduzierbarer Ordner) fiele. Zwei unabhängige
Gates halten die Datei draußen: `_tracked_path` in der Engine und eine eigene
Regel im Paketbau — dieselbe Doppelung wie bei der Dateiart-Allowlist.

**Grenze:** Eine ungebundene Quelle macht `validate` bewusst **nicht** rot.
Sonst wäre jedes frisch entpackte Paket auf jedem neuen Host rot. Fail-closed
greift erst bei der Nutzung: `query --extern` liest aus einer ungebundenen
Quelle nichts und meldet das als eigenen Zustand `not_bound`, ausdrücklich
nicht als Negativbefund. Diese Asymmetrie ist eine Entscheidung.

### AD-12 · Der Orchestrator ist Daten, und das Ranking scheitert ehrlich

**Entscheidung:** Für einen externen Markdown-Baum entsteht ein Katalog als
`.json` (`skillsafe.orchestrator/v1`), den die Engine liest. Das Ranking
`extern-zweistufig/v2` rechnet Stufe 2 immer gegen den jetzt gelesenen Text.
Den Katalog nutzt es bei einer Netzquelle als Prefilter, weil dort jedes
geöffnete Dokument ein Abruf ist; eine lokale Quelle wird vollständig gelesen,
der Katalog ordnet sie nur. Ein Dokument ohne einen einzigen Anfragebegriff
fällt heraus, unabhängig vom Katalog-Score. Bleibt nichts übrig, kommt nichts
zurück.

**Begründung:** Der Katalogtext ist ein schwaches Signal, der Bestand dahinter
das starke. Im Demo-Bestand liefert „Minderung Mangel Wohnung" in Stufe 1 das
Seerecht mit 78 Punkten **vor** dem Mietrecht mit 60; Stufe 2 dreht das auf
460 zu 152. Eine Rankingstufe reicht nicht. Und ein plausibel aussehender
Fehltreffer ist teurer als kein Treffer, weil er nicht als Fehler auffällt —
deshalb kein alphabetischer Fallback und kein „bester Fehltreffer", sondern
eine Meldung, die sagt, was zu tun ist.

Ehrlich scheitern kann nur, wer gelesen hat. `no_external_candidates` setzt
deshalb mindestens ein tatsächlich gelesenes Dokument voraus. Wurde keines
gelesen — die Quelle ungebunden, nicht erreichbar, ein Budget gesprengt —,
nennt der Zustand die Ursache (`not_bound`, `unreachable`,
`budget_exceeded`), trägt weder `live: true` noch einen Fingerprint und sagt
im Grund wörtlich, dass dies kein Negativbefund ist. Ein leeres Ergebnis ohne
gelesenes Dokument wäre derselbe plausible Fehltreffer mit umgekehrtem
Vorzeichen: „durchsucht und nichts gefunden", wo nichts durchsucht wurde.

Warum lokal kein Prefilter mehr (v2): In v1 öffnete Stufe 1 auch bei einer
lokalen Quelle nur die 24 besten Katalogeinträge. Passte der Katalogtext auf
keine Anfrage, waren das schlicht die alphabetisch ersten, und ein Treffer im
fünfundzwanzigsten blieb ungelesen — ein stiller Fehltreffer, den erst die
Lückenmeldung sichtbar machte. Lokal ist Lesen billig und deterministisch;
der Prefilter sparte dort fast nichts und kostete Trefferquote. Begrenzt wird
stattdessen gezählt: höchstens 64 MiB je Abfrage, was darüber liegt, nennt
der Grund. Bei einer Netzquelle bleibt der Prefilter, dazu höchstens 20
Abrufe je Abfrage.

Abgeglichen wird ausschließlich an Tokengrenzen (`_retrieval_tokens`,
`_phrase_present`). Ein rohes Substring-`in` gibt es im externen Pfad nicht,
sonst fände „himmel" ein „schimmel". Stoppwörter durchlaufen dieselbe
Normalisierung wie die Anfrage; in v1 wirkte „für" deshalb nie als
Stoppwort.

Der Katalog ist ausdrücklich **kein Integritätsartefakt**. Prüfsummen trägt er
nur für lokale Quellen, wo sie überprüfbar bleiben; bei einer Netzquelle sind
sie verboten, weil ein beweglicher Ref sich nicht pinnen lässt. Ein
eingefrorener Hash auf ein bewegliches Ziel wäre genau die stille Alterung,
gegen die AD-10 gebaut ist — nur eine Ebene höher. Integrität kommt von den
Satzankern und vom Manifest, nicht vom Prefilter.

**Grenze:** Die Trefferqualität hängt an der Struktur fremder Dokumente. Wer
dort schludert, bekommt schlechtere Treffer; kein Ranking heilt das. Bei einer
Netzquelle hängt zusätzlich am Katalogtext, welche Dokumente überhaupt
abgerufen werden.

### AD-13 · Netz nur im Fallback, Cache außerhalb des Artefakts

**Entscheidung:** Eine aufgeführte Bezugsquelle darf ein festes
https-Präfix sein. Abgerufen wird nur unter diesem Präfix, nur bei
ausdrücklichem `--extern`, mit Zertifikatsprüfung, Zeit-, Byte-, Redirect- und
Abrufgrenzen (höchstens 20 je Abfrage), und jeder Abruf steht in `log.md`.
Einer Weiterleitung folgt nie die HTTP-Schicht selbst: das Ziel wird
aufgelöst und an Pfadgrenzen gegen das Präfix geprüft, bevor die nächste
Anfrage hinausgeht. Kann `log.md` nicht geschrieben werden, findet der Abruf
nicht statt. Der TTL-Abzug liegt außerhalb des Skill-Ordners im
Nutzer-Cache-Verzeichnis.

**Begründung:** Eine aufgeführte Bezugsquelle ist keine Internetrecherche.
Recherche heißt offene Suche und unbekannte Ziele; aufgeführt heißt: ein
namentlich benanntes, über das Manifest gepinntes Ziel. Das ist dieselbe
Kategorie wie eine Zeile im Quellenregister, und deshalb wird eine aufgeführte
Netzquelle behandelt wie eine interne — auch dort, wo Internetrecherche
ausdrücklich untersagt ist. Damit das überprüfbar bleibt statt behauptet,
existiert das Herkunftsprotokoll — und deshalb ist es Vorbedingung, nicht
Nachtrag: Ein Abruf, der nicht protokolliert werden kann, ließe sich danach nur
noch melden, nicht mehr nachweisen. Aus demselben Grund folgt `urllib` keiner
Weiterleitung von selbst; sonst sähe ein fremdes Ziel die Anfrage, bevor die
Präfixprüfung greift. Der Cache liegt außerhalb, weil er innerhalb von `ROOT`
durch Dateiart- und Manifest-Walk liefe und das Artefakt verunreinigte.

**Grenze, offen benannt:** Der Satz „kein Netzwerk im Skill" gilt jetzt für den
Default-Query-Pfad statt absolut. Er ist damit schwächer, und die Landingpage
sagt das genauso deutlich wie vorher die harte Fassung. Der Netzpfad ist
außerdem **nicht deterministisch** — ein Socket-Timeout kann das Ergebnis
formen. Deshalb bleiben Netztreffer aus dem lokalen `retrieval_fingerprint`
heraus, tragen `live: true`, Abrufzeitpunkt und Cache-Alter, und `doctor` wie
CI kennen mit `SKILLSAFE_OFFLINE=1` eine harte Schaltung ohne Socket-Aufruf.
Der lokale externe Pfad bleibt dagegen deterministisch: Budgets werden
gezählt, nie über eine Uhr gestoppt.

Zweite offene Folge: Weil eine Netzquelle durch ihre Registrierung gebunden
ist, greift beim Empfänger eines `.skill`-Pakets kein zusätzlicher lokaler
Schalter. Wer ein Paket weitergibt, gibt seine aufgeführten Netzquellen mit.
Das ist die gewollte Folge der Gleichbehandlung und steht so in `README.md`
und `BETRIEB.md`.

### AD-14 · Bedeutung liest das Modell, Vollständigkeit belegt das Script

**Entscheidung:** Der Tresor bekommt eine Bedeutungssuche, aber keinen
Bedeutungsindex. Drei Bausteine tragen sie gemeinsam:

1. **Das Ranking wird ehrlich.** `hybrid-local/v4` weist aus, welche
   Fragebegriffe es erkannt hat (`coverage.match_strength`,
   `coverage.query_terms`), meldet jede Kürzung durch das Limit und macht bei
   `weak` und `none` die Vollsichtung zur Pflicht.
2. **Wortformen sind keine Bedeutungsfrage.** `wortform/v1` gleicht Flexion,
   Umlaut-Plural, `-ung` und Kompositumteile ab, nachrechenbar und mit eigenem
   Grund am Treffer. Mehr nicht.
3. **Die Vollsichtung ist die Bedeutungssuche.** `sweep` legt jeden Claim in
   Stapeln vor, das Modell urteilt nach Bedeutung, und das Script prüft per
   Siegel und Quittung, dass kein Stapel fehlt. „Nicht im Bestand" setzt eine
   vollständige Quittung voraus.

**Begründung:** Gemessen wurde zuerst, was ist. 28 umformulierte Fragen gegen
den Demo-Bestand unter `hybrid-local/v1`: 15 gefunden, 5 nur jenseits des
Limits, 5 verfehlt bei `candidates_found`, 3 verfehlt und gemeldet. Zehn von
dreizehn Verfehlungen waren also still. Die Rückfallebene gab es, aber sie
sprang nur bei null Kandidaten an, und eine natürliche Frage teilt fast immer
ein Wort mit irgendeinem Claim: „darf", „wird", „muss". Ein Zufallstreffer
auf einem Hilfsverb schaltete genau die Prüfung ab, die die Frage gebraucht
hätte. Dazu war die Rückfallebene eine Anweisung („alle Seiten lesen") und
kein geprüfter Schritt.

Daraus folgt die Arbeitsteilung, die AD-05 schon vorgibt. Was ein Script
entscheiden kann, entscheidet es: ob ein Wort der Frage im Ergebnis vorkommt,
ob das Limit etwas abschnitt, ob jeder Stapel ausgegeben und beurteilt wurde.
Was Urteil braucht, bleibt beim Modell: ob „nasse Wände" den Claim zum
Schimmelbefall meint. In einem Skill ist der Leser mit Sprachverständnis
ohnehin anwesend. Bei höchstens 10.000 kurzen Claims ist sein vollständiges
Lesen ein stärkeres Relevanzurteil als jede Nachbarschaft in einem
Einbettungsraum, und es lässt sich durch Bauart vollständig machen. Ein
Ähnlichkeitsranking, lexikalisch wie vektoriell, liefert immer etwas zurück
und kann Abwesenheit nie belegen. Die Frage „übersieht er nichts" beantwortet
deshalb kein besseres Ranking, sondern nur ein Verfahren, das alles vorlegt
und das nachweist.

Gemessen nach dem Umbau, Limit 8: Von den 28 Fragen findet das Ranking 19
direkt, 9 gehen in die Pflicht-Vollsichtung, keine bleibt still. Diese Zahl
ist geschönt, weil Funktionswortliste und Schwellen an genau diesen Fragen
eingestellt wurden. Die ehrlichere stammt aus einer Kontrolle: 56 Fragen von
einem zweiten Agenten, der nur die Claim-Texte kannte und ihren Wortlaut mit
Absicht mied, einmal gegen den fertigen Stand gemessen. Dort findet das
Ranking 17 direkt, 37 gehen in die Pflicht-Vollsichtung, 2 tragen einen
Hinweis, keine bleibt still. Etwa ein Drittel also: Das Ranking ist eine
Abkürzung für Fragen in der Sprache des Bestands. Bedeutung findet das Lesen.

Die Kontrolle fand außerdem einen Fehler, den die eigenen Fragen nicht
zeigten. Eine frühere Fassung der Nachrück-Regel ließ den rangniedrigsten
Kandidaten weichen, sobald ein ungedeckter Fragebegriff einen Träger hatte;
Füllwörter wie „stehen" holten so ihren zufälligen Träger herein und
verdrängten einen Definitions-Claim von Rang 6. Seither weicht nur reiner
Kontext. Mit dieser Korrektur stehen 18 von 56 direkt, 37 in der Pflicht, 1
mit Hinweis; diese zweite Zahl ist nicht mehr blind gemessen und steht
deshalb neben der ersten, nicht an ihrer Stelle.

**Was das Gold nicht zeigte, zeigte der Review.** Am selben Tag prüften
unabhängige Durchgänge den Stand v0.12.0, getrennt nach Ranking, Vollsichtung
sowie Vertrag und Dokumentation, je mit dem Auftrag, Fehler zu finden und
nachzustellen. Zwei Befunde waren schwer; beide wurden vor der Korrektur ein
zweites Mal nachgestellt, und beide lagen außerhalb
dessen, was 84 Fragen an einem Bestand mit 28 Claims berühren: Nur zwei davon
erreichen überhaupt `strong`, das harte Gate wird vom Demo-Gold also kaum
geprüft. Erstens galt eine getroffene Benennung pauschal als verstanden. Bei
zwei kuratierten Begriffen in einer Frage füllte die Seite des einen das
Limit, die des anderen fehlte samt Definitions-Claim, und das Ergebnis hieß
`strong`; in 8 von 72 Paarfragen. Zweitens traf die Wortform-Stufe der
Begriffe auch Funktionswörter: „sich" benannte „Sicherung", „seit" die
„Seite". Das gab einen Anker und schaltete die Pflicht-Vollsichtung ab —
derselbe Fehler wie beim Hilfsverb im Ausgangsbefund, nur über die
Begriffswelt, und im Demo-Bestand unsichtbar, weil dort keine solche Benennung
steht. Dazu kamen eine Abkürzung („die IT" als englisches „it"), vertippte
IDs, die spurlos aus der Frage verschwanden, und ein Fingerzeig, der mit 30
Punkten Claims mit dem Fragewort selbst verdrängte.

`hybrid-local/v3` behebt das: Ein Begriff zählt nur, wenn er in der Ausgabe
vertreten ist, und rückt sonst nach; die Wortform-Stufe trifft Benennungen
nur über Inhaltswörter; Abkürzungen in Großbuchstaben sind nie Funktionswort;
unbekannte IDs bleiben als unverstandenes Wort stehen; eine Frage ohne
Inhaltswort ist nie `strong`; der Fingerzeig liegt bei 10. An den Messzahlen
ändert das nichts (19 und 18 direkt, 0 still), und genau das ist die Lehre:
Die Zahlen maßen diese Fehler nie. Jeder ist jetzt ein eigener Test.

**Ein zweiter Review, derselbe Ort.** Die Änderungen von v0.14.0 wurden
wieder unabhängig geprüft, diesmal mit zufällig erzeugten Beständen und einem
Orakel, das die zugesagten Eigenschaften je Abfrage nachrechnet. Es fand drei
Reste desselben Fehlers: `strong`, obwohl etwas an der Frage unverstanden
blieb. Ein per ID genannter Begriff (oder einer, dessen Benennung nur aus
Funktionswörtern besteht) steuert kein Inhaltswort bei; fehlte er in der
Ausgabe, blieb die Abdeckung bei 100 %. Die Ziffern einer Kennung, die es
nicht gibt, standen zufällig im Bestand („S-2026" und eine Jahreszahl). Und
die Abkürzung „IT" traf als ganze Frage das englische „it" einer Fundstelle
und galt als Anker. `hybrid-local/v4` schließt alle drei: `strong` verlangt
zusätzlich, dass jeder direkt getroffene Begriff vertreten ist
(`concepts.matched[].represented`) und dass die Frage keine unbekannte
Kennung nennt; die ganze Frage als Wortfolge ist nur mit getroffenem
Inhaltswort ein Anker. Rangfolge und Punktzahlen sind dieselben wie in v3,
die Messzahlen ebenfalls. Derselbe Review fand, dass das Siegel der
Vollsichtung „a != b" und „a = b" gleich las, weil Satzzeichen am Wortrand
wegfielen; seit v0.15.0 bleibt jedes Zeichen stehen. Egal sind nur Groß- und
Kleinschreibung, die Menge des Leerraums, Fragezeichen am Ende und die
typografische Form der Anführungszeichen und Striche; einfache und doppelte
bleiben verschieden.

**Und was die Tests nicht zeigten.** Ein vierter Durchgang prüfte nicht den
Code, sondern seine Absicherung: 86 Einzelfehler in der Engine und 17 im
Messwerkzeug, je einer zur Zeit, am Stand v0.12.0. Die Hälfte blieb grün,
darunter die Schwellen der Trefferstärke, vertauschte Kürzungszähler, jedes
Gewicht der veröffentlichten Tabelle und das entfernte Gate für stille
Verfehlungen, das am Demo-Gold noch nie angeschlagen hatte. Der Leck-Wächter
fand eine Goldfrage nur in wörtlicher Schreibung, nicht ohne Fragezeichen
und nicht in Umschrift, also gerade nicht so, wie ein Alias sie trüge. Seit
v0.15.0 hält ein Schnappschuss fest, was `query` für jede Goldfrage bei Limit
1, 3 und 8 und für eine Reihe fester Abfragen ausgibt
(`tools/rangfolge_check.py`, `tests/gold/rangfolge-demo.json`): Zustand,
Stärke, Abdeckung, Evidenz mit Punktzahl und je ein Prüfwert über die übrigen
Blöcke. Jedes Gate des Messwerkzeugs hat einen Test, der es auslöst, die
Messzahlen selbst stehen als Soll in der Suite, und der Leck-Wächter liest
mit der Normalisierung der Engine, seit v0.16.0 auch in ihrer Wortform: Eine
Goldfrage, die als Alias in anderer Beugung dastand, fiel vorher nicht auf,
obwohl die Engine sie traf. Ein Schnappschuss beweist keine
Richtigkeit, er macht Bewegung sichtbar: Wer am Ranking dreht, sieht jede
Folge und entscheidet sie, statt sie zu übersehen. Gegengeprüft mit einer
eigenen Probe am Stand v0.15.0: Von 117 gezielt gewählten Einzelfehlern in
Engine und Werkzeugen fallen 116 auf, der verbleibende ist gleichwertig (das
Siegel ohne Stapelnummer; die Claim-IDs unterscheiden die Stapel ohnehin).
Die Probe ist selbst gebaut. Sie zeigt, dass die bekannten Lücken geschlossen
sind, nicht dass es keine weiteren gibt.

**Ende zu Ende gemessen.** Ob ein Modell dem Vertrag tatsächlich folgt, zeigt
weder das Gold noch ein Review, sondern nur ein Lauf. Zwanzig frische Agenten
bekamen je einen entpackten Skill-Ordner und Nutzerfragen, sonst nichts: keine
Erklärung des Verfahrens, kein Hinweis auf die Messung. Ausgewertet hat
`tools/antwort_check.py`, das dem Agenten nichts glaubt: Aus dem Protokoll
liest es nur Frage, Antworttext und Quittungseinträge, und fährt jede Quittung
erneut gegen die Engine.

| Runde | Stand | Fragen | mit erwartetem Claim | gefunden | davon vom Ranking verfehlt | trotzdem gefunden | Negativfragen | korrekt abgelehnt | Verstöße |
|---|---|---|---|---|---|---|---|---|---|
| 1, acht Agenten | v0.12.1 | 32 | 24 | 24 | 19 | 19 | 8 | 8 | 0 |
| 2, vier Agenten | v0.13.0 | 12 | 8 | 8 | 8 | 8 | 4 | 4 | 0 |
| 3, vier Agenten | v0.14.0 | 12 | 7 | 7 | 5 | 5 | 5 | 5 | 0 |
| 4, vier Agenten | v0.15.0 | 12 | 7 | 7 | 4 | 4 | 5 | 5 | 0 |

In den ersten drei Runden reichte jeder Agent zu jeder Frage eine gültige,
vollständige Quittung ein, in Runde 4 zu zehn von zwölf Fragen; die beiden
übrigen brauchten keine (eine Kennung, die es nicht gibt, und eine Frage,
die die gelesenen Seiten ganz beantworteten). Jede eingereichte Quittung war
gültig; in Runde 2 bis 4 liefen je sechs davon über drei Stapel. Kein „Nicht im
Bestand" stand ohne Quittung da, keine Negativfrage wurde beantwortet, kein
Agent veränderte seine Kopie. Die Protokolle liegen unter `tests/e2e/`; ihre
Siegel gelten nur für den Stand, an den sie gebunden sind.

Der zweite Ertrag waren die Anmerkungen der Agenten. Sie fanden, was am
Vertrag unklar war (wann `partial`, ob der externe Rückfall Pflicht ist, was
in die Quittung gehört), was die Ausgabe verschwieg (die Nachfolgerin einer
überholten Seite nach einer Vollsichtung) und was sie falsch behauptete: Der
externe Rückfall meldete „kein Dokument enthält die Anfragebegriffe", obwohl
kein Dokument gelesen worden war. Sieben von acht Agenten der ersten Runde
haben das beanstandet. Der Antworten-Vertrag sagte bis v0.16.0, wie diese
Ausgabe zu lesen ist; seit v0.17.0 meldet die Engine selbst `not_bound` oder
`unreachable` (aus der parallelen Linie v0.11.12 bis v0.12.0, AD-12). Und sie fanden in v0.13.0 einen Satz,
der falsch war, weil er
ungeprüft in den Vertrag geschrieben wurde (ein Netzabruf schreibe nichts in
den Skill-Ordner; er schreibt eine Zeile nach `log.md`). Runde 3 lief am
Stand v0.14.0 und brachte kleinere Unklarheiten: ob die Frage nach einer
Kennung, die es nicht gibt, eine Vollsichtung braucht (seit v0.15.0 nicht
mehr, das weiß das Script selbst), wie eine reine Abstention aussieht, ob die
Belegzeile einer Auslegung den Stand trägt, und einen Satz unter „Kontext
und Grenzen" einer Demo-Seite, der mehr behauptete, als ein Claim trug.
Runde 4 lief am Stand v0.15.0 und prüfte gezielt die neuen Regeln: Die Frage
nach einer unbekannten Kennung beantwortete der Agent ohne Vollsichtung mit
einem Satz, eine unbekannte Kennung neben einer Sache führte zur
Vollsichtung, und bei einem per Kennung genannten, unvertretenen Begriff
stand seine Seite unter den gekürzten; gefunden hat der Agent den Claim in
der Vollsichtung. Die Anmerkungen betrafen nur noch Feinheiten:
dass die Engine den Kennungsfall selbst melden sollte, statt ihn ableiten zu
lassen (seit v0.16.0 `fallback.unknown_ids_only: true`), die Grenze
zwischen Lesart und ungedecktem Zusatz und wie viel eine Antwort über die
Dateien des Werkzeugs selbst sagen darf.

Grenzen dieser Messung, ausdrücklich: 68 Fragen, ein Demo-Bestand, in dem die
Vollsichtung ein einziger Stapel ist, Agenten aus derselben Modellfamilie,
und die Fragen stammen bis auf sieben aus dem Gold: Die mit erwartetem Claim
sind also Fragen, die zu einem Claim gehören.
Das zeigt, dass das Verfahren befolgbar ist und befolgt wurde. Es zeigt
nicht, wie sorgfältig ein Modell 189 Stapel liest.

**Grenze:** Die Quittung belegt Vorlage und Urteil, nicht Sorgfalt. Sie
schützt gegen Abkürzen und Vergessen; wer die Stapelausgabe umleitet und nur
das Siegel herauszieht, hält eine gültige Quittung über nichts. Das steht so
im Antworten-Workflow, weil kein Script es verhindern kann.

Die Vollsichtung kostet Lesearbeit im Verhältnis zum Bestand. Im Demo-Bestand
ist es ein Stapel mit rund 14.000 Zeichen; ein synthetischer Bestand mit
1.506 Seiten und 7.528 Claims braucht 189 Stapel. `--domain` und `--page`
senken den Aufwand, erlauben dann aber nur „in diesem Umfang nicht gefunden".
Wo auch das zu teuer wird, greift die Grenze aus AD-01.

`strong` kann irren. Gemessen sind 0 stille Verfehlungen auf 84 Fragen, und
das ist eine kleine, selbst gebaute Stichprobe an einem Bestand mit 28
Claims, von der nur zwei Fragen `strong` überhaupt erreichen. Der Review hat
zwei Wege gefunden, auf denen `strong` log, und beide lagen außerhalb dieser
Stichprobe. Deshalb erlaubt `strong` nie eine Abstention, und deshalb liegt das
Gold außerhalb des Skills: Ein eigener Bestand braucht eigene Fragen, gemessen
mit `tools/recall_check.py` im Entwicklungs-Workspace. Steht eine Goldfrage
wörtlich im Bestand, misst sie nur noch, ob er sich selbst wiederfindet; ein
Wächter im selben Werkzeug bricht dann ab.

Wortformen kollidieren. „Zeit" und „Zeitung", „Bild" und „Bildung" teilen
eine Familie, „Nutzer" und „Nutzen" ebenso, und weil die Umlaut-Faltung jede
Folge `oe` trifft, auch „Förderung" und „Forderung". Das erzeugt zusätzliche
Kandidaten, nie Evidenz, und jeder trägt seinen Grund (`stem:`, `compound:`).
Ein solcher Treffer zählt allerdings als verstandenes Wort und kann eine
Frage `strong` machen.

Die Vollsichtung sichtet Claims, keine Kurzfassungen. Das genügt nur, solange
die Kurzfassungs-Deckung gilt (`references/lint.md`): Eine Kurzfassung darf
nichts behaupten, was kein Claim trägt. Der Demo-Bestand selbst verstieß
dagegen; die Kurzfassung von `okf.md` nannte „anbieterneutral" und „Juni
2026" ohne Claim. Eine Frage danach endete in einem „Nicht im Bestand" mit
gültiger Quittung, während die Seite die Angabe führte. Die Kurzfassung ist
bereinigt; die Regel bleibt eine Prüfung, die nur ein Leser leisten kann.

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
Lexik + Wortform + ein Graph-Hop → Trefferstärke lesen → genau die
Kandidatenseiten lesen → bei `weak`, `none` und vor jeder Abstention die
Vollsichtung: `sweep` legt jeden Claim vor, das Modell urteilt, die Quittung
wird geprüft → bleibt danach ein Teil ungedeckt und sind Quellen aufgeführt,
`query --extern` (Schritt 4c; nicht gelesen ist kein Negativbefund) → Answer
Envelope mit Claim-Belegen, ältestem Stand, niedrigster Konfidenz, Konflikt-
und Supersession-Hinweisen → Lücken nur mit vollständiger Quittung als „Nicht
im Bestand" ausweisen, externe Treffer als benannte Hinweise daneben.
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
  gepflegte Sprache wird vom Ranking weiterhin verfehlt, gemessen bei rund
  zwei von drei bewusst umformulierten Fragen; es liefert deshalb nur
  Kandidaten und weist aus, was es nicht erkannt hat. `weak` und `none` sind
  Rückfallsignale zur Vollsichtung, kein Negativbefund.
* Die Vollsichtung ist so vollständig wie ihr Umfang und so gut wie ihr
  Leser. Ihre Quittung belegt, dass jeder Stapel vorgelegt und beurteilt
  wurde, nicht mit welcher Sorgfalt; und sie deckt nur, was als Claim im
  Bestand steht, nicht was beim Befüllen nie extrahiert wurde (AD-14).
* Externe Bezugsquellen altern außerhalb der eigenen Kontrolle. Anker-Drift
  ist deshalb gelb und kein Release-Blocker; die Trefferqualität des
  Nachschlagens hängt an fremder Dokumentqualität. Ein fremder Baum kann
  zudem eine `SKILL.md` enthalten, die ein Agent nebenher lädt — außerhalb
  der Prozessgrenze dieses Scripts.
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
(genau das leistet das Type-Onboarding, C-0202/C-0203) und ein bewusst
generischer Fallback-Typ `faktensammlung` für atomare Aussagen, die bei
Verdichtung zu Konzeptseiten befördert werden (C-0205; die Schwelle von etwa
drei verwandten Claims ist eine Pflegeregel in `schema/types.yaml`, kein
Claim) — dieser Typ wurde im Bau tatsächlich per Onboarding registriert,
nicht von Hand.
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

## Abnahmekriterien (zuletzt vollständig durchgeführt am 2026-11-13, Stand v0.16.0)

Die Suite in `tests/` prüft jedes dieser Kriterien bei jedem Lauf; Blöcke mit
eigenem Messdatum nennen den Stand, an dem ihre Zahlen erhoben wurden. Die
Ende-zu-Ende-Zahlen stehen in einem eigenen Block: Sie lassen sich nur gegen
den Stand nachrechnen, an den ihre Quittungen gebunden sind, und das tut die
Suite nicht. `tools/check_docs.py` hält sie an den Block `ergebnis` der
Protokolle unter `tests/e2e/` gebunden.

**Positiv:** `validate` und `doctor` grün auf 6 Seiten, 28 Claims,
4 Quellen und 2 aufgeführten externen Bezugsquellen · `query OKF`, `query "offenes Wissensformat"` und `query C-0001`
liefern deterministisch C-0001 · zehn identische Läufe erzeugen
byteidentisches JSON · Bild-Fixture mit Originalhash, Repräsentation und
Region liefert ausschließlich den gebundenen Beobachtungs-Claim ·
`release` ersetzt Manifest zuletzt und rollt injizierte Schreibfehler an
jeder Position zurück · zwei `.skill`-Archive sind byteidentisch, bestehen
ZIP-Prüfung und laufen nach Installation unter `.claude/skills/` aus einem
fremden Projekt-CWD · externes Routing gegen `beispiel-extern/`
(4 Dokumente): 10 Positivanfragen mit Top-1 100 %, 5 Negativanfragen mit
Fehltrefferquote 0 %, Abdeckung richtiger Treffer ≥ 50 % gegen 0 % bei den
verworfenen. Diese Stichprobe ist klein und selbst gebaut: Sie zeigt, dass
zweite Rankingstufe und Abdeckungsschwelle wirken, nicht wie sich das Routing
auf einem gewachsenen Fremdbestand schlägt.

**Negativ (fail-closed nachgewiesen):** unbekannter Typ oder Begriff,
Alias-Kollision und `broader`-Zyklus → Abbruch · fehlende Medienrepräsentation,
unbekannte oder als Injection markierte Region → Abbruch · OCR-Injection-
Canary erscheint nie in Query-Evidenz · Instruktionssignatur in Claim-Text
oder Fundstelle → Abbruch · verschachteltes Frontmatter in jeder Form
(Blockform, Map-Liste, Tabulator) → Abbruch, und Unterschlüssel gelangen
nie ins Frontmatter-Dictionary · fremde Dateiart, zweites Script oder
gesetztes Ausführungsbit im Tresorbaum → Abbruch in `validate` und im
Paketbau · kein Retrieval-Treffer sowie Treffer nur im
Router → `no_candidates`, semantische Deckung `not_assessed` und
Pflicht-Vollsichtung (außer bei `fallback.unknown_ids_only: true`) · Manifestdrift oder Quarantäne-Payload → `invalid_vault`
ohne Claims · absolute/traversierende Pfade, Symlinks, Hardlinks,
getarntes SVG und beschädigte Registries/Manifeste → Abbruch.

**Export und Prüfangabe (seit v0.8.0/v0.9.0):** Trust-Tier wird aus
`geprueft_von` abgeleitet, verändert nachweislich keinen Score und wird nie
gespeichert, auch nicht im Bundle · zwei Exporte desselben Stands sind
byteidentisch · die Ausgabe erfüllt §11 Bedingung 1 und 2 für jedes
Konzeptdokument · ein Symlink im Zielordner trägt den Export nicht heraus,
ein Abbruch lässt das Ziel unverändert, ein früherer Export wird ersetzt
statt übermischt · Ziel im Tresor, in `.claude`/`.codex` oder mit fremdem
Inhalt bricht ab · `stats` läuft auch auf einem roten Bestand ohne Traceback.

**Auffindbarkeit und Vollsichtung (seit v0.12.0, gemessen am 2026-11-12 mit
`hybrid-local/v4`):**
`tools/recall_check.py` gegen `tests/gold/recall-demo.json`, Limit 8 ·
Gruppe „entwicklung" (28 Fragen): 19 direkt gefunden, 9 in der
Pflicht-Vollsichtung, 0 still · Gruppe „kontrolle" (56 blind geschriebene
Fragen): 18 direkt gefunden, bei 38 steht die Seite des Claims unter `pages`,
37 in der Pflicht-Vollsichtung, 1 mit Hinweis, 0 still · 27 Negativfragen:
bei 16 verlangt das Signal die Vollsichtung, 10 sind `partial`, 1 ist
`strong`; kein Feld der Abfrage erlaubt eine Abstention, und dass auch die
übrigen 11 in der Vollsichtung enden, ist Vertragsregel und nur am Agenten
messbar · 72 Paarfragen aus je zwei Vorzugsbenennungen:
`strong` nur, wenn beide Begriffe in der Ausgabe vertreten sind · ein per ID
genannter Begriff, den die Ausgabe nicht zeigt, verhindert `strong` und
steht mit `represented: false` da · ein
Funktionswort benennt keinen Begriff („sich" nicht „Sicherung") · eine
unbekannte ID steht unter `coverage.unknown_ids` und verhindert `strong`,
auch wenn ihre Ziffern zufällig im Bestand stehen · die Vollsichtung legt bei
Stapelgrößen 5, 7, 40 und 200 jeden der 28 Claims genau einmal vor ·
falsches Siegel, fehlender, doppelter oder fremder Stapel, andere Frage,
andere Stapelgröße und neuer Release machen die Quittung ungültig und liefern
keine Evidenz · ein eingeschränkter Umfang quittiert vollständig und erlaubt
trotzdem keine Abstention · das Siegel unterscheidet Fragen, die sich nur
in einem Operator, einem Vorzeichen, einem Satzzeichen oder in ß gegen ss
unterscheiden („a != b" gegen „a = b", „.5" gegen „5") ·
mehrfaches `--receipt` wird gesammelt, widersprüchliche Einträge zum selben
Stapel machen die Quittung ungültig · eine Seite außerhalb des Manifests
(`knowledge/__pycache__/`) stoppt den Release · Regions-Text und Alttext
erscheinen in keinem
Stapel · keine Goldfrage steht im Skill-Ordner. Zeitmessung am synthetischen
Bestand mit 1.506 Seiten und 7.528 Claims: `query` rund 3,5 Sekunden, davon
knapp 3 für das unveränderte Validierungs-Gate; eine Frage mit 105 Begriffen
(990 Zeichen) 4,7 Sekunden; die Ausgabe einer Abfrage rund 15.000 Zeichen.

**Ende zu Ende (Messläufe vom 2026-11-12 und 2026-11-13, Stände v0.12.1 bis v0.15.0, nachgerechnet mit `tools/antwort_check.py` gegen den jeweils gebundenen Stand):**
Zwanzig frische Agenten, 68 Fragen, 0 Verstöße · bei 46 von 46 Fragen mit
erwartetem Claim wurde er gefunden, 36 davon nach verfehltem Ranking · 22 von
22 Negativfragen korrekt abgelehnt, 21 mit gültiger Quittung und eine Frage
nach einer Kennung, die es nicht gibt, mit dem Befund des Scripts.

**Funktional:** Der Antworten-Workflow nutzt den stabilen JSON-Vertrag und
formuliert weiterhin ein Answer Envelope mit Claim-Belegen, Stand und
Konfidenz; die Begriffswelt verbessert Discovery, ohne Evidenz zu erfinden.
Der Medien-Workflow bewahrt Original, Region und Injection-Fund, ohne
Regions-Text zur Antwortquelle zu machen. Type-Onboarding,
Kompressionsregel und wörtliche Abstention bleiben unverändert.
