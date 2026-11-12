# Dead-End-Log — verworfene Ansaetze

Zweck: Entscheidungen gegen etwas festhalten, damit spaetere Sessions sie
nicht erneut pruefen. Format: `## [JJJJ-MM-TT] Ansatz — Grund der Verwerfung`.

## [2026-07-04] Embeddings/Vektorindex im Tresor — verworfen
Nachbarschaftssuche im Einbettungsraum ist eine Blackbox ("Warum diese
Quelle?" nicht beantwortbar), erzeugt Infrastruktur (Store, Modell,
Re-Indexierung, Tuning) und schickt je nach Setup Inhalte an externe
Schnittstellen. Ersatz: ROUTER (kuratiert) + INDEX (generiert) +
manifestgebundenes Hybrid-Retrieval aus kontrollierten Begriffen,
lexikalischen Claim-Treffern und genau einem Graph-Hop; erschöpfende
Volltextsuche bleibt manueller Audit-Plan. Details: KONZEPT.md AD-01.

## [2026-07-04] Claims in separaten Ledger-Dateien — verworfen
Getrennte Ledger (wie im OKSV-Vollausbau) erhoehen im puren Skill nur die
Zahl der Dateien pro Lesevorgang. Claims leben in der Seite, die sie stuetzen;
die tresorweite Eindeutigkeit der IDs prueft der Validator.

## [2026-07-04] POLE+O-Vokabular als Basis-Registry — verworfen
POLE+O (Person, Object, Location, Event, Organization) zielt auf
Entitaeten-Extraktion fuer persoenliche Assistenten und Ermittlungsarbeit.
Der Tresor ist dokument-/konzeptzentriert; uebernommen wird das PRINZIP
(kleine fixe Basis, additiv erweitern, Clash-getrieben), nicht das Vokabular.
Quelle der Abwaegung: S-0003.

## [2026-07-04] Facts als Embedding-Triplets — verworfen
Iusztins Fact-Primitiv (Subjekt/Praedikat/Objekt + Vektor, nur semantisch
auffindbar) uebernommen als faktensammlung-Typ MIT Claim-Grammatik statt
Triplet-Zwang und Volltextsuche statt Embedding (Determinismus). Bi-temporale
Gueltigkeit (valid_from/valid_until) nicht uebernommen — stand/status/
Supersession decken den Bedarf; bei Bedarf Ausbaupfad.

## [2026-07-05] Interne Mandanten-/Rollentrennung (ACL) fuer mehrere Tresore im selben Skill — verworfen
Statt eines Rollen-/Rechte-Features in vault.py oder Schema, um Organisation-,
Abteilungs-, Projekt- und Privat-Wissen in einem gemeinsamen Tresor zu trennen:
verworfen, weil der Tresor kein Server-/Auth-Konzept hat und eine interne
Zugriffskontrolle nur truegerische Sicherheit waere. Ersatz: eigene,
vollstaendige Tresor-Kopie pro Sensitivitaetsstufe, Grenze ist der
Installationsort/Skill-Ladeort (Repo-Rechte, privater Skill-Ordner), nie ein
Feature im Skill. Details: KONZEPT.md AD-06, references/mehrere-tresore.md.

## [2026-07-28] OKF-v0.2-Typ "Attested Computation" mit executor/attester — verworfen
§10 der Spezifikation v0.2 laesst eine Content-Seite auf ausfuehrbaren Code
oder Laufanweisungen zeigen (executor.resource, attester.resource). Verworfen,
weil damit die Content-Zone einen Ausfuehrungspfad benennen darf, waehrend Code
bisher nur in der Engine-Zone existiert: indirekte Prompt Injection eskaliert
von "falsche Antwort" zu "Codeausfuehrung", zwei der drei §6.2-Pfadformen
fallen ohnehin an der Pfadhaertung durch, §10.2 braucht verschachteltes
Frontmatter, das Manifest ist selbstbezeugt und kann Codeintegritaet gegenueber
einem Empfaenger nicht behaupten, und der Ertrag (Receipt, Verdict) entsteht
laut §10.5/§10.6 ausserhalb des Bundles. Ersatz: keiner, die Faehigkeit fehlt
bewusst. Der Bestand dokumentiert den Typ als Wissen (C-0307, C-0308) und
fuehrt ihn nicht. Geprueft und zurueckgestellt, nicht uebersehen: eine rein
deskriptive Variante ohne executor/attester und ohne Codepfad waere ueber das
regulaere Type-Onboarding moeglich. Details: KONZEPT.md AD-09.

## [2026-07-28] LinkedIn-Ankuendigung zu OKF v0.2 als eigene Quelle — verworfen
Ein zweiter Registereintrag fuer den Ankuendigungstext haette nichts getragen,
was die Spezifikation selbst nicht sagt; S-0004 ist der Volltext der Norm. Der
Lint-Workflow meldet claimlose Registereintraege zu Recht als tote Quelle, und
die Kompressionsregel verlangt Verdichtung statt Spiegelung. Aufnahme waere nur
gerechtfertigt, wenn der Text eine Aussage traegt, die die Spec nicht deckt
(etwa zur Verbreitung); dann als T3-Pointer mit ein bis zwei Claims in
knowledge/demo-okf/fakten.md, nicht auf der Konzeptseite.

## [2026-07-28] Praezisierung zum verworfenen bi-temporalen Gueltigkeitsfenster
Der Eintrag vom 2026-07-04 verwarf valid_from/valid_until aus dem
Ontologie-Artikel, weil stand/status/Supersession den Bedarf decken. Das gilt
weiter fuer ein Gueltigkeits-INTERVALL. OKF v0.2 §5.5 fuehrt mit stale_after
etwas anderes ein: ein einzelnes absolutes Verfallsdatum, das eine Aussage
ohne Bestandsaenderung unbelastbar werden laesst. Das ist eine echte Luecke des
Profils und ausdruecklich NICHT durch den alten Eintrag mitverworfen. Eine
Uebernahme als optionales Feld gueltig_bis bleibt offen; sie braucht dann ein
Bezugsdatum als Eingabe (kein impliziter Vergleich gegen "heute"), weil die
Query-Ausgabe sonst tagesabhaengig wird und die Determinismus-Zusage bricht.

## [2026-11-12] RETRIEVAL_STOPWORDS um Funktionswoerter erweitern — verworfen
Die alte Liste formt auch extern-zweistufig/v1 und die nachrechenbaren
Katalogzahlen (token_count, top_tokens) in sources/derived/. Jede Erweiterung
haette dort Werte verschoben, ohne dass sich an einer externen Quelle etwas
geaendert haette. Ersatz: eigene Liste FUNKTIONSWOERTER, nur im lokalen
Ranking hybrid-local/v2. Nebenbefund, bewusst nicht behoben: in der alten
Liste steht 'für' in Umlautschreibung, geprueft wird gegen das normalisierte
'fuer'; der Eintrag hat nie getroffen. Wer das korrigiert, zieht die Kataloge
neu. Details: KONZEPT.md AD-14.

## [2026-11-12] Kompositum nur bei vollstaendiger Zerlegung gegen das Bestandsvokabular — verworfen
Die strengere Regel (beide Teile muessen als eigenes Wort im Bestand stehen)
haette "Miete" nicht zur "Mietminderung" gefuehrt, solange "Minderung" nirgends
allein steht, also gerade in kleinen Bestaenden nichts gefunden. Ersatz:
Kopf-/Schwanz-Abgleich mit Mindestlaenge vier auf beiden Seiten der Naht,
schwach gewichtet, nie ein Anker. Preis: gelegentliche Zufallstreffer
("after" in "dauerhafter"), sichtbar am Grund compound:.

## [2026-11-12] Verbformen auf -t und Partizipien in wortform/v1 — verworfen
Ein -t zu streichen fuehrt "bestaetigt" zu "bestaetigen", aber auch "Recht"
zu "rech", "Wert" zu "wer" und "Seite" ueber "seit" zu "sei". Nach casefold
ist ein Substantiv nicht mehr von einer Verbform zu unterscheiden. Die Regel
haette mehr Kollisionen als Treffer gebracht. Was deshalb nicht trifft, steht
als unmatched im Ergebnis und faellt in die Vollsichtung.

## [2026-11-12] Trefferstaerke 'partial' schon ab 50 Prozent — verworfen
Bei zwei Fragebegriffen reichte dann ein einziger Zufallstreffer, um die
Pflicht-Vollsichtung abzuschalten; gemessen an einer Frage nach dem
Verfallsdatum, bei der nur das Allerweltswort "Eintrag" traf. Ersatz: ohne
Anker mindestens zwei getroffene Begriffe und mindestens 60 Prozent.

## [2026-11-12] Nachruecken auf Kosten des rangniedrigsten Kandidaten — verworfen
Die erste Fassung der Regel "jeder Fragebegriff bleibt vertreten" liess den
rangniedrigsten Kandidaten weichen, dessen Begriffe anderswo vertreten waren.
Fuellwoerter wie "stehen" und "mindestens" holten so je ihren zufaelligen
Traeger herein und verdraengten einen Definitions-Claim von Rang 6. Gefunden
hat das erst die blind geschriebene Kontrollgruppe, nicht die eigenen Fragen.
Ersatz: Es weicht nur reiner Kontext, nie ein Claim mit eigenem Treffer.

## [2026-11-12] Begriffs-Fingerzeig von 30 auf 10 Punkte senken — verworfen
Im Ende-zu-Ende-Test fiel auf, dass sieben Claims einer Seite mit bloss
gestreifter Benennung (concept-page:partial, 30 Punkte) zwei Claims mit
eigenem Wortteil-Treffer (12) aus dem Limit draengten. Geprueft wurde die
Senkung auf 10, also unter jeden eigenen Treffer: auf den 28 Fragen der Gruppe
'entwicklung' ohne jede Wirkung (19 direkt gefunden, 9 in der Pflicht, in
beiden Faellen). Ohne messbaren Nutzen kein Profilwechsel, denn jede Aenderung
an den Gewichten hebt die Profilnummer und verbraucht die Kontrollgruppe. Der
beobachtete Fall war 'weak', die Vollsichtung also ohnehin Pflicht, und die
Kuerzung stand in coverage.candidates. Erneut pruefen erst an einem Bestand,
der gross genug ist, dass das Limit ueberhaupt etwas entscheidet.

## [2026-11-12] Trefferstaerke ueber alle Claims der gezeigten Seiten rechnen — verworfen
Die Seitengruende (pages[].reasons) nennen auch Treffer in Claims, die das
Limit gekuerzt hat; query_terms zaehlt sie nicht. Das wirkt uneinheitlich, und
weil die gezeigten Seiten ohnehin ganz gelesen werden, lag es nahe, die
Abdeckung ueber die ganze Seite zu rechnen. Verworfen, weil die Staerke dann
nur steigen kann: Zwei Fragebegriffe auf derselben Seite ergaeben 'strong'
statt 'weak' und schalteten die Pflicht-Vollsichtung genau dort ab, wo die
Antwort auf einer anderen, nicht gezeigten Seite stehen kann. Die enge
Rechnung ist die vorsichtige. Ersatz: Der Unterschied steht im Vertrag, und
ein Fragebegriff aus concepts.partial steht jetzt auch in query_terms.partial.
