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
("Fall" in "Schimmelbefall"), sichtbar am Grund compound:.

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

## [2026-11-12] Begriffs-Fingerzeig von 30 auf 10 Punkte senken — erst verworfen, in hybrid-local/v3 umgesetzt
Im Ende-zu-Ende-Test fiel auf, dass sieben Claims einer Seite mit bloss
gestreifter Benennung (concept-page:partial, 30 Punkte) zwei Claims mit
eigenem Wortteil-Treffer (12) aus dem Limit draengten. Geprueft wurde die
Senkung auf 10, also unter jeden eigenen Treffer: auf den 28 Fragen der Gruppe
'entwicklung' ohne jede Wirkung (19 direkt gefunden, 9 in der Pflicht, in
beiden Faellen). Ohne messbaren Nutzen schien ein Profilwechsel nicht
gerechtfertigt, und so stand es in v0.13.0. Der Review hat am selben Tag den
Nutzen nachgewiesen, den die eigenen Fragen nicht zeigten: Bei 7 von 42
Abfragen mit exaktem Treffer fehlte dieser Treffer, weil die gestreifte
Begriffsseite das Limit fuellte ("Wissen verdichten": drei Claims nur mit
concept-page:partial vor C-0301 mit token:wissen). Da hybrid-local/v3 wegen
zweier schwererer Fehler ohnehin faellig war, liegt der Fingerzeig jetzt bei
10. Lehre: "auf den eigenen Fragen ohne Wirkung" ist kein Befund ueber die
Aenderung, sondern ueber die Fragen.

## [2026-11-12] Geschwister eines Treffers als Fueller vor den Graph-Nachbarn — verworfen
Der Review wies darauf hin, dass seit v2 die Geschwister-Claims einer
Trefferseite keine Kandidaten mehr sind, die Claims ihrer Graph-Nachbarn aber
schon (graph:one-hop, 5 Punkte); bei "C-0001" fuellen fremde Seiten die
Evidenz. Geprueft wurde ein Fueller page-sibling mit 6 Punkten. Er kostete auf
der Gruppe 'entwicklung' einen Treffer (18 statt 19 von 28, Seitentreffer 21
statt 22): Der Graph-Nachbar brachte dort die Seite mit dem gesuchten Claim
herein, die Geschwister verdraengten sie. Verworfen. Die Geschwister liest der
Antworten-Workflow ohnehin, weil die Trefferseite unter pages steht.

## [2026-11-12] Kompositum-Traeger nachruecken lassen — verworfen
Nachruecken darf nur, wer den Fragebegriff als Wort oder Wortform traegt. Ein
Wortteil-Treffer ("Miete" in "Mietminderung") bleibt bei "Miete OKF" auch mit
Limit 20 abgeschnitten, obwohl Kontext weichen koennte. Die Lockerung wurde
nicht umgesetzt: Wortteil-Treffer sind zu oft Zufall, und jeder nachgerueckte
verdraengt einen Kontext-Claim einer direkt getroffenen Begriffsseite. Die
Kuerzung bleibt gemeldet (unmatched, omitted_pages). Die Einschraenkung steht
seit v0.14.0 in schema/profil.md; vorher war sie undokumentiert.

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

## [2026-11-12] Siegel ohne Stapelausgabe, wenn die Claims schon im Kontext stehen — verworfen
In der dritten Abnahmerunde stoerte mehrere Agenten, dass jede weitere Frage
dieselben Stapel erneut ausgibt, obwohl sie bei unveraendertem Manifest schon
im Kontext stehen. Erwogen wurde ein Schalter, der nur die Siegel liefert.
Verworfen: Das Siegel belegt genau, dass der Stapel fuer diese Frage
ausgegeben wurde. Ein Aufruf, der es ohne Ausgabe hergibt, waere die
eingebaute Fassung der Abkuerzung, die der Vertrag verbietet (Ausgabe
umleiten, Siegel herausziehen), und die Engine kann nicht pruefen, was in
einem Kontext steht. Die Kosten bleiben: Jede Frage, die eine Vollsichtung
braucht, liest den Bestand einmal. Ersatz: Der Vertrag nennt den Grund, und
eine Frage, die allein einer unbekannten Kennung gilt, braucht seit v0.15.0
keine Vollsichtung mehr.

## [2026-11-13] Einleitende Verben ("sagt", "steht", "enthaelt") als Funktionswoerter — verworfen
Die vierte Abnahmerunde und ein Review zeigten: In v0.15.0 fiel "Was steht
in C-9999?" unter die Ausnahme fuer unbekannte Kennungen, "Was sagt C-9999?"
nicht, weil "steht" zufaellig in einem Claim vorkommt und "sagt" nicht; und
"Mietminderung C-9999" fiel darunter, obwohl die Frage eine Sache nennt.
Erwogen wurde, solche Verben in die Funktionswortliste aufzunehmen.
Verworfen: Das waere eine Aenderung am Ranking (neues Profil, neue Messung,
neuer Schnappschuss) und hoebe Fragen eher zu 'strong', also genau dorthin,
wo das harte Gate am wenigsten misst. Ersatz seit v0.16.0: eine eigene,
kleine Liste einleitender Woerter (KENNUNG_RAHMENWOERTER), die nur fuer die
Frage zaehlt, ob eine Frage nichts als unbekannte Kennungen nennt. Fuer das
Ranking bleiben die Woerter Inhaltswoerter.

## [2026-11-13] Rahmenliste nur gegen die Inhaltswoerter des Rankings — verworfen
Die erste Fassung von KENNUNG_RAHMENWOERTER pruefte nur die Inhaltswoerter
des Rankings und enthielt Substantive wie "Aussage", "Quelle" und "Claim".
Ein Review am Kandidaten fand drei Loecher: Homographe aus der
Funktionswortliste ("Waren", "Soll und Haben") fehlen unter den
Inhaltswoertern und fielen deshalb nicht als Sachwort auf; "Was ist eine
Aussage laut S-0099?" fragt nach der Aussage und wurde trotzdem erlassen; und
die Ziffern wurden nur an der Ausgabe geprueft, sodass ein knappes --limit
ueber den Erlass entschied. Ersatz: eine geschlossene Liste gegen jedes Wort
der Frage, benennende Substantive nur unmittelbar vor der Kennung, Ziffern
am ganzen Bestand, und eine B-ID aus einer anderen Begriffswelt gilt nicht
als fehlend. Lieber eine Vollsichtung zu viel als ein falscher Erlass.
Eine zweite Pruefrunde fand dieselbe Luecke in der eigenen Liste: Verben, die
auch Substantive sind ("Regeln", "Sagen"), und "und", das eine zweite Frage
anhaengt ("Welche Regeln gibt es und was steht in C-9999?"). Seither ist ein
grossgeschriebenes Wort mitten in der Frage ein Sachwort, Bindewoerter zaehlen
nur zwischen zwei Kennungen, und die Ziffern zaehlen auch als Wortteil.
Die dritte Pruefrunde zeigte, dass Grossschreibung allein nicht traegt: Wer
klein schreibt ("was ist ein laut in c-9999"), umging die Regel. Seither ist
jedes Wort hinter einem Artikel ein Substantiv, "laut" zaehlt nur vor einer
Kennung, "aus", "stehen" und "lauten" sind gestrichen, ein Zeichen wie "§"
ist ein Sachwort, und als Kennung zaehlt nur die Schreibung mit
ASCII-Ziffern.
