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
