#!/usr/bin/env python3
"""Prüft nach, ob Antworten eines Agenten dem Antworten-Vertrag gefolgt sind.

``recall_check.py`` misst das Ranking. Ob ein Modell die Vollsichtung
tatsächlich fährt, bevor es „Nicht im Bestand" sagt, misst es nicht: Das zeigt
nur ein Lauf mit einem Agenten, der nichts kennt als den Skill-Ordner. Dieses
Werkzeug wertet so einen Lauf aus, und zwar ohne dem Agenten etwas zu glauben.
Aus seinem Protokoll werden nur drei Dinge gelesen: die Frage, der Wortlaut
der Antwort und die Quittungseinträge, die er an ``sweep --receipt`` übergeben
hat. Alles andere rechnet die Engine hier neu:

* die Trefferstärke der Frage, also ob die Vollsichtung Pflicht war (auch
  wegen einer gekürzten Liste omitted_pages);
* die Quittung: gültig, vollständig, Abstention erlaubt, ausgewählte Claims,
  Fingerabdruck;
* ob jede zitierte Claim-ID existiert und zu einer Seite gehört, die der
  Vertrag zu lesen gab.

Ein Verstoß ist, was der Vertrag verbietet: „Nicht im Bestand" ohne
vollständige Quittung, eine ausgelassene Pflicht-Vollsichtung, eine ungültige
Quittung, eine Zeile „Sichtung:", die andere Zahlen oder eine andere Kennung
nennt als die Quittung, eine erfundene Claim-ID, ein still ausgelassener
Schritt 4c. Trägt ein Eintrag ``erwartet``, kommt die Messfrage dazu: Wurde
der erwartete Claim gefunden?

Eine einzige Antwort kommt ohne Vollsichtung aus, obwohl das Ranking nichts
verstanden hat: die auf eine Frage, die nichts als Kennungen nennt, die es
nicht gibt (``coverage.unknown_ids``). Das weiß die Engine selbst und meldet
es seit v0.16.0 als ``fallback.unknown_ids_only``; für ältere Stände, deren
Ausgabe das Feld nicht kennt, leitet das Werkzeug den Fall nach der Regel
ihres Standes aus coverage ab. Die Antwort muss die Kennungen nennen, darf
keinen Claim zitieren und nicht „Nicht im Bestand" sagen; diese Formel bleibt
der Quittung vorbehalten, und sie muss das Fehlen jeder Kennung feststellen.
Eine Kennung, die es nicht gibt, darf eine Antwort nur in einem Satzteil
nennen, der nichts sagt als ihr Fehlen, der nachfragt, was gemeint war, der
sie ausdrücklich als Quelle ausschließt („nicht aus S-0099"), der die Frage
wiederholt oder der als „Nicht im Bestand: …" abgrenzt, was fehlt; die
letzten drei Formen nur für eine Kennung aus der Frage. Jeder andere
Satzteil trägt eine Aussage, und eine Kennung darin führt sie als Quelle:
Dann ist sie erfunden, bei einer C-Kennung wie bei einer S-, X- oder
B-Kennung. Das gilt für jede Antwort, nicht nur im Kennungsfall; welche S-,
X- und B-Kennungen es gibt, liest das Werkzeug aus den Registern des
Bestands. Umgekehrt ist es ein Verstoß, eine Kennung, die es gibt, als
fehlend hinzustellen; nur bestritten zählt sie weder als Zitat noch als
Fund. Eine externe Quelle hinter „in", „aus", „bei" oder „innerhalb"
oder in einer Angabe zu Schritt 4c ist dabei der Ort der Suche, nicht
bestritten („in X-0001 nichts gefunden"). Im Kennungsfall nennt die
Antwort keine andere Kennung: Ein Vorschlag („Meinten Sie S-0004?") ist
ein Zitat.

Gibt der Mensch einen Umfang vor, oder nennt die Frage selbst eine Domäne
oder Seite als Umfang, erfüllt die Sichtung dieses Umfangs die Pflicht, und
„in diesem Umfang nicht gefunden" ist eine korrekte Ablehnung. Das weiß nur,
wer die Messung baut: Der Eintrag trägt dann ``umfang_vorgegeben: true`` und
den Umfang in ``sweep_args``.

Schritt 4c ist seit dem Vertrag von v0.17.0 Pflicht. Ob er es für den
geprüften Tresor ist, liest das Werkzeug aus dessen references/antworten.md,
nicht aus einer Versionsnummer: Ein eigener Tresor beginnt bei 1.0.0, ein
alter Stand stellte den Schritt frei. Bleibt eine Frage nach der
Vollsichtung des ganzen Bestands ganz oder teilweise ungedeckt (die Antwort
sagt „Nicht im Bestand", auch als Zeile „Nicht im Bestand: …") und sind
externe Quellen aufgeführt (``fallback.external_lookup_available``), weist
die Antwort aus, was extern gefunden oder nicht gelesen wurde: je Treffer
eine Angabe „Extern (nicht im Bestand):" mit Quelle und Dokument, für jede
ungelesene Quelle „Extern nicht gelesen:". Beide Etiketten gelten am Anfang
einer Zeile oder eines Satzes, auch als Überschrift mit einer Liste
darunter; dann ist jeder Listenpunkt eine eigene Angabe. Eine Rückfrage ist
keine Angabe, auch umbrochen, in Klammern oder direkt hinter dem Etikett
(„Soll ich X-0001 binden lassen?"): Eine Kennung darin weist die Quelle
nicht als ungelesen aus, ebenso wenig in einem Listenpunkt, der als Ganzes
fragt, oder als Teilsatz. Ob ein Satz fragt, entscheidet sein Ende außerhalb
von Zitaten: Endet er mit einem Fragezeichen, wächst die Rückfrage vom
letzten Teilsatz rückwärts über jeden Teil, der wie eine Frage beginnt
(Frageverb, „oder", Fragewort, „falls", „wenn", „damit" …, Verb vor der
Anrede) und keinen Lesestatus, Zustand oder Treffer nennt, und vor einer
Nachfrage wie „passt das?" über einen Teil, der nichts aussagt; ein Segment
zwischen Semikolon, Doppelpunkt oder Gedankenstrich, das so beginnt, gehört
ganz dazu. Was davor steht, bleibt Angabe („X-0001 ist hier nicht
eingebunden, soll ich es binden?"); ein Vorsatz, der selbst fragt oder
bedingt, gehört zur Frage („Falls du X-0001 nutzen willst, soll ich es
binden?", „X-0001 binden, passt das?"). Eine zitierte Frage ist keine
Rückfrage, und eine Frage in Klammern macht den Satz nicht zur Frage.
Umgekehrt nennt jede Angabe zu einem Treffer ein Dokument, das die Abfrage
für eine genannte Quelle geliefert hat, auch in Anführungszeichen, mit „./"
oder im Klammerzusatz des Etiketts, und jeder Pfad darin ist ein solches
Dokument, auch in Anführungszeichen. Ausgenommen sind zitierte Sätze und
Dateien des geprüften Tresors, eine Datei außerhalb von knowledge/ aber nur,
solange die Angabe sie keiner Quelle zuschreibt („X-0001, INDEX.md" ist eine
Fundstelle in X-0001). Eine Angabe ohne geliefertes Dokument behauptet nur
dann nichts, wenn sie ausdrücklich keinen Treffer meldet („keine Treffer",
„kein Zeiger", „Treffer: keine", „nichts gefunden"), sonst nichts über den
Inhalt einer Quelle sagt (neben Kennung, Zustand, Lesestatus und den Wörtern
der Frage höchstens zwei Inhaltswörter; ein Zahlwort zählt mit, außer vor
„Dokumente", „Quellen" oder „Treffer") und nichts nennt, was nach einer
Fundstelle aussieht: eine URL, eine Datei mit Dokumentendung, einen Pfad mit
„./", „../", „/", zwei Schrägstrichen oder kleingeschrieben ohne Endung
(nicht hinter „Ordner" und nicht mit Schrägstrich am Ende; ein
kleingeschriebenes Begriffspaar wie „miete/kaution" und ein Ordnerpfad ohne
beides zählen mit, ein Fehlalarm als Preis), eine Satz-, Absatz-, Zeilen-
oder Seitenzahl (auch in der Mehrzahl), einen Paragrafen (außer als Thema
der Suche: aus der Frage oder hinter „zu", „für", „bei" …), ein Kapitel oder
einen Abschnitt mit Nummer, Titel oder Präposition („Abschnitt über …";
verneint zählt er nicht: „kein passender Abschnitt zur Kaution", „ein
Kapitel dazu gibt es nicht"). Bei bekannter Bindung (lokale Quelle) und bei
einem Lauf ohne Netz (Netzquelle) ist eine erfundene Angabe ein Verstoß,
sonst ein Hinweis. Weist eine Antwort eine Quelle als ungelesen aus, die die
Nachrechnung bei bekannter Bindung gelesen hat, oder nennt sie einen
Zustand, den die Abfrage nicht meldet, ist das ein Hinweis. Den Verzicht
(„Extern nicht gelesen: X-0001, X-0002 nicht nachgeschlagen (<Grund>) — kein
Negativbefund") nimmt es an, wenn das Protokoll die Vorgabe dafür festhält
(``vorgabe``: den Wunsch des Nutzers oder die Vorgabe der Umgebung im
Wortlaut) oder wenn solche Zeilen zusammen jede aufgeführte Quelle nennen;
ohne Vorgabe ist der Verzicht ein Verstoß. Nie im Kennungsfall, nie bei
begrenztem Umfang. Die Abfrage mit ``--extern`` rechnet das Werkzeug selbst
nach, mit gesetztem Offline-Schalter: Es ruft nichts ab und schreibt nichts
in log.md. Was eine Netzquelle geliefert hätte, weiß es deshalb nur, wenn
auch der Lauf offline war. Das sagt ``stand.extern.offline`` im Protokoll,
sonst ``SKILLSAFE_OFFLINE`` in der Umgebung des Werkzeugs; ohne beides
bleibt die Netzquelle ein Hinweis. Welche Quellen der Lauf gebunden hatte,
sagt ``stand.extern.gebunden``: Bindet der prüfende Host andere, bricht das
Werkzeug ab wie bei einem fremden Manifest. Endet jede Frage des Protokolls
extern in invalid_query, liest keine etwas, und die Probe entfällt. Fehlt
die Angabe und nennt die Antwort Treffer einer Quelle, die die Nachrechnung
nicht lesen kann, ist das ein Hinweis auf eine abweichende Bindung. Nennt
das Protokoll eine Version, die nicht zum Tresor passt, bricht das Werkzeug
bei gebundenem Manifest ab; ohne Manifest ist das ein Hinweis.

Kennungen mit typografischem Strich (C‑0001 mit U+2011, C–0001) liest das
Werkzeug als Kennung. Eine Angabe zur Sichtung ist die Zeile „Sichtung:" in
jeder Schreibung (auch „Vollsichtung", „## Sichtung", auch auf zwei Zeilen),
jede Zeile mit einer Quittungskennung und jeder Satzteil einer Zeile, die die
Sichtung nennt, mit „N von M Claims" oder „alle N Claims", ohne Verneinung
im selben Satzteil und ohne Wort, das ein Ergebnis nennt („0 von 28 Claims
nennen …", „alle 10 Claims zu OKF stammen aus …"). Ohne eingereichte
Quittung ist die Zeile ein Verstoß und ebenso ein Satz, der so viele Claims
nennt, wie der Bestand hat; ein Satz über weniger beschreibt eine Teilmenge.
Mit Quittung wird jede Angabe abgeglichen. Eine Zeile des Envelopes
(„Stand:", „Nicht im Bestand:", „Sichtung:" …) setzt keinen Satz fort.
„in diesem Umfang nicht gefunden" braucht eine vollständige Quittung über
diesen Umfang.

Was das Werkzeug nicht kann: Es erkennt die Formel „Nicht im Bestand", auch
über einen Zeilenumbruch, ein Zitatzeichen oder eine Hervorhebung hinweg, aber
keine Umschreibung („dazu schweigt der Bestand"). Bei einer als ``negativ``
gekennzeichneten Frage fällt eine fehlende Formel auf, sonst nicht. Eine
Aussage ohne jede Kennung erkennt es nicht als ungedeckt: Ob jede
Kernaussage einen Claim nennt, prüft es nicht. Und es prüft, ob eine Antwort
dem Verfahren folgt, nicht ob sie inhaltlich stimmt.

Die Quittungen sind an den Stand gebunden. Nennt das Protokoll einen
Manifest-Digest, muss der Tresor auf genau diesem Stand stehen; sonst bricht
das Werkzeug ab, statt lauter ungültige Quittungen zu melden.

Read-only, nur Standardbibliothek. Aus der Repository-Wurzel:

    python3 tools/antwort_check.py --antworten <protokoll.json>
    python3 tools/antwort_check.py --vault <tresor> --antworten <protokoll.json>

Exit 0 ohne Verstoß, 1 mit Verstoß, 2 bei unbrauchbarem Protokoll oder
falschem Stand.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import unicodedata
from collections import Counter
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
STANDARD_VAULT = REPOSITORY / "wissenstresor"
PROTOKOLL_SCHEMA = "skillsafe.antwort-protokoll/v1"
# Striche, die ein Modell statt des Bindestrichs setzt. In einer Kennung
# liest das Werkzeug sie als Bindestrich, wie die Engine im Siegel.
STRICHE = "\u2010\u2011\u2012\u2013\u2014\u2212"
KENNUNG_STRICH_RE = re.compile(
    rf"(?<![A-Za-z0-9])([A-Za-z]{{1,2}})[{STRICHE}](?=\d)")
# Eine Claim-ID im Antworttext, gleich in welcher Schreibung. Ein Bereich
# ("C-0001 bis C-0005") zitiert auch, was dazwischen liegt.
CLAIM_RE = re.compile(r"(?<![A-Za-z0-9])C-(\d{4})(?!\d)", re.IGNORECASE)
BEREICH_RE = re.compile(
    rf"(?<![A-Za-z0-9])C-(\d{{4}})\s*(?:bis|[-{STRICHE}])\s*C-(\d{{4}})(?!\d)",
    re.IGNORECASE)
QUITTUNG_RE = re.compile(r"^\d{1,6}:[0-9a-f]{16}=(-|C-\d{4}(,C-\d{4})*)$")
# Eine Angabe zur Sichtung ist eine Zeile, die die Sichtung beim Namen nennt
# (Sichtung, Vollsichtung, gleich in welcher Schreibung) und dazu Zahlen oder
# eine Quittungskennung, oder eine Zeile mit einer Quittungskennung allein.
# Ein Satz wie "Hinweise zur Sichtung: ein Stapel" ist keine Angabe.
SICHTUNG_WORT_RE = re.compile(r"(?i)sichtung|gesichtet")
ZAHL = r"\d{1,3}(?:[.\u202f\u00a0' ]\d{3})+|\d+"
ZAHLEN_RE = re.compile(
    rf"(?<![\d.])({ZAHL})\s+von\s+(?:insgesamt\s+)?({ZAHL})(?![\d])"
    rf"(\s+Claims?\b)?", re.IGNORECASE)
KENNUNG_RE = re.compile(
    r"Quittung\w*(?:[\s-]*ID)?\W{0,3}([0-9a-f]{4,64})\b", re.IGNORECASE)
KENNUNG_FREI_RE = re.compile(r"(?<![0-9A-Za-z])([0-9a-f]{8,64})(?![0-9A-Za-z])")
KENNUNG_MIN = 8
ABSTENTION = "nicht im bestand"
# Was die Formel im Antworttext unterbrechen kann, ohne sie zu ändern.
FORMEL_STOERER = re.compile(r"[*_`\u00ad\u200b\u200c\u200d\u2060\ufeff]")
# Schalter, die den Zuschnitt einer Sichtung ändern, je mit genau einem Wert.
SWEEP_SCHALTER = {"--size", "--domain", "--page"}
# Kanten, denen der Antworten-Workflow zu einer weiteren Seite folgt.
LESEKANTEN = {"ersetzt", "widerspricht"}
# Schritt 4c (externer Fallback) ist seit dem Vertrag von v0.17.0 Pflicht. Ob
# ein Tresor ihn verlangt, liest vertrag_4c aus seinem eigenen Vertrag; diese
# Grenze gilt nur, wenn der nicht lesbar ist.
VERTRAG_4C = (0, 17, 0)
# Der Vertrag erst ohne Zeilenumbrüche gelesen (vertrag_4c): Die Formel steht
# direkt hinter der Überschrift des Schritts.
VERTRAG_4C_RE = re.compile(
    r"4c\.\s*\*\*Externer Fallback\.\*\*\s*Der Schritt ist \*\*Pflicht\*\*")
VERTRAG_4C_KOPF_RE = re.compile(r"4c\.\s*\*\*Externer Fallback\.\*\*")
# Die Zeilen, mit denen eine Antwort Schritt 4c ausweist (antworten.md, 4c).
# Ein Zusatz in Klammern vor dem Doppelpunkt gehört zum Etikett
# („Extern nicht gelesen (Zustand unreachable):"); nennt er eine Kennung
# oder einen Pfad, gehört er auch zur Angabe („Extern nicht gelesen
# (X-0002, offline)").
ETIKETT_TREFFER = r"extern\s*\(\s*nicht\s+im\s+bestand\s*\)"
ETIKETT_UNGELESEN = r"extern\s+nicht\s+gelesen"
EXTERN_TREFFER_RE = re.compile(
    r"(?i)^" + ETIKETT_TREFFER + r"\s*(?P<zusatz>\([^)]*\)\s*)?(?::|$)")
EXTERN_UNGELESEN_RE = re.compile(
    r"(?i)^" + ETIKETT_UNGELESEN + r"\s*(?P<zusatz>\([^)]*\)\s*)?(?::|$)")
X_KENNUNG_RE = re.compile(r"(?i)(?<![A-Za-z0-9])X-\d{4}(?!\d)")
EXTERN_ETIKETT_TEXT_RE = re.compile(
    r"(?i)\b" + ETIKETT_TREFFER + r"|\b" + ETIKETT_UNGELESEN + r"\b")
# Satzgrenze in einer Angabe zu Schritt 4c, auch hinter bis zu zwei
# schließenden Zeichen: Klammer, Anführungszeichen, Hervorhebung
# („… gelesen.) Extern …", „**Nicht im Bestand.** Extern …", „»…?« Extern …").
_SCHLIESSER = ")\\]“”\"'»«’‘›‹*_`"
SATZGRENZE_RE = re.compile(
    rf"(?:(?<=[.!?…])|(?<=[.!?…][{_SCHLIESSER}])|(?<=[.!?…][{_SCHLIESSER}]{{2}}))"
    r"\s+(?=\S)")
# Ein Satz, der eine Frage ist, auch mit schließenden Zeichen dahinter.
FRAGE_RE = re.compile(rf"\?[{_SCHLIESSER}]*$")
# Eine Zeile, deren letzter Satz zu Ende ist (oder die ein Etikett einleitet).
SATZENDE_RE = re.compile(rf"[.!?…:][{_SCHLIESSER}]*\s*$")
# Ein Dokumentpfad in einer Angabe, etwa handbuch/mietminderung.md, auch
# mit ./, ../ oder absolutem Präfix und mit einer anderen Dokumentendung.
DOKUMENT_ENDUNGEN = ("md|markdown|txt|pdf|html?|rst|adoc|docx?|odt|rtf|json|"
                     "ya?ml|csv|xml")
DOKUMENT_RE = re.compile(
    r"(?<![\w/.-])((?:\.{1,2}/|/)?(?:[\w.-]+/)*[\w.-]+\.(?:"
    + DOKUMENT_ENDUNGEN + r"))(?![\w/-])", re.IGNORECASE)
# Eine Angabe, die ausdrücklich keinen Treffer meldet: „keine Treffer",
# „kein Zeiger", „keine passenden Treffer", „Treffer: keine", „nichts
# Passendes gefunden", „kein Dokument … enthält", „ohne Treffer" …
KEIN_TREFFER_RE = re.compile(
    r"(?i)\b(?:kein|keine|keinen|keiner|keinerlei)\b(?:\s+[\w-]+){0,2}?\s+"
    r"(?:treffer|zeiger|funde?|fundstellen?|ergebnis(?:se)?|"
    r"übereinstimmung(?:en)?|uebereinstimmung(?:en)?)\b"
    r"|\bohne\s+(?:[\w-]+\s+)?treffer\b"
    r"|\btreffer\s*:\s*(?:keine?|0|null)\b"
    r"|\b(?:nichts|null|0)\b(?:\s+[\w-]+){0,2}?\s+(?:gefunden|getroffen|treffer)\b"
    r"|\bkein(?:e|en)?\b(?:\s+[\w-]+)?\s+dokumente?\b(?:\s+[\w-]+){0,3}?\s+"
    r"enth(?:ä|ae)lt\b"
    r"|\bno_external_candidates\b"
    r"|\bno\s+(?:external\s+)?(?:hits?|candidates|matches)\b")
# Eine Angabe, die für sich nur „keine" sagt.
NUR_VERNEINUNG_RE = re.compile(r"(?i)[\W_]*(?:keine?r?|nichts|null|0)[\W_]*")
# Wörter, die eine Leermeldung umgeben dürfen, ohne etwas über den Inhalt
# einer Quelle zu sagen: Lesestatus, Zustand, Abfrage. Eine Leermeldung mit
# mehr als zwei anderen Inhaltswörtern sagt etwas über die Quelle aus
# („… die Kaution beträgt höchstens drei Monatsmieten; sonst keine
# Treffer") und gilt nicht als Leermeldung.
NEUTRALE_WOERTER = frozenset("""
der die das den dem des ein eine einen einem einer eines in im ins an am auf
aus bei beim mit nach von vom zu zum zur fuer für ueber über unter vor ohne
gegen durch um und oder sowie aber auch nur noch sonst weitere weiteren
weiterer es sie er ist sind war waren wurde wurden wird werden hat haben
hatte gab gibt ergab ergaben ergibt lieferte lieferten liefert dazu dafuer
dafür davon darin hier dort diese dieser dieses diesem diesen kein keine
keinen keiner keinerlei nichts treffer zeiger fund funde fundstelle
fundstellen ergebnis ergebnisse abfrage frage quelle quellen lokal gelesen
gelesenen offline online netz netzquelle abgerufen abruf abrufbar nicht
gebunden ungebunden erreichbar zustand negativbefund dokument dokumente
dokumenten anfragebegriffe anfragebegriff begriffe begriff suchbegriffe
suchbegriff enthält enthaelt enthalten passend passende passenden passendes
relevant relevante relevanten relevantes extern externe externen externer
externes bestand tresor ordner katalog volltext stufe gefunden getroffen
ab bis seit abschnitt abschnitte kapitel lokalen
lokale nachschlagen nachgeschlagen nachschlag kam kamen zustande
möglich moeglich gelang gelungen erfolgt erfolgte durchgeführt
durchgefuehrt ich wir du mir mich uns dir dich habe hast hatten bin bist
werde konnte konnten
alle alles allen beide beiden einige mehrere jede jeder jedes jeden jedem
insgesamt sämtliche saemtliche durchsucht gesucht geprüft geprueft
nachgesehen abgefragt anfragebegriffen suchbegriffen begriffen
angefragt untersucht leider ebenfalls jedoch allerdings also somit daher
deshalb fachbegriffe statt eigennamen verwenden bewusst bester fehltreffer
geliefert befund gilt
""".split())
# Ein Zahlwort zählt nur vor einem dieser Wörter nicht als Inhalt („alle
# vier Dokumente"); „drei Monatsmieten" sagt etwas über die Quelle.
ZAHLWOERTER = frozenset(
    "eins zwei drei vier fünf fuenf sechs sieben acht neun zehn".split())
ZAEHLWOERTER = frozenset("""
dokument dokumente dokumenten quelle quellen treffer zeiger datei dateien
seiten fundstellen
""".split())
# Was nach einer Fundstelle aussieht: eine URL, eine Datei mit
# Dokumentendung, ein Pfad mit ./, ../, / oder mindestens zwei
# Schrägstrichen, eine Satz-, Absatz-, Zeilen- oder Seitenzahl, ein
# Kapitel oder Abschnitt mit Nummer, Titel oder Zitat (nicht verneint).
STELLENARTIG_RE = re.compile(
    r"(?i)\b[a-z][a-z0-9+.-]*://"
    r"|(?<![\w/.-])[\w.-]+\.(?:" + DOKUMENT_ENDUNGEN + r")\b"
    r"|(?<![\w/.-])(?:\.{1,2}/|/)[\w./-]*\w"
    r"|(?<![\w/.-])[\w.-]+/[\w.-]+/[\w./-]*\w"
    r"|\b(?:satz(?:position(?:en)?|nummern?)?|s(?:ä|ae)tzen?|sentence(?:_index)?|"
    r"abs(?:atz|(?:ä|ae)tzen?)|zeilen?|seiten?|s\.|rn\.?)\s*[:=]?\s*\d")
KAPITEL_RE = re.compile(r"\b(?i:kapitel|abschnitt)\s+(?:\d|[„\"»«]|[A-ZÄÖÜ])")
VERNEINUNG_DAVOR_RE = re.compile(r"(?i)\b(?:kein|keine|keinen|keinem|keiner|ohne)\s+$")
# Ein Kapitel oder Abschnitt mit Thema („der Abschnitt über Mietminderung")
# ist eine Fundstelle, außer der Satzteil verneint ihn („kein passender
# Abschnitt zur Kaution", „ein Kapitel dazu gibt es dort nicht", „weder ein
# Kapitel noch ein Abschnitt …").
KAPITEL_THEMA_RE = re.compile(
    r"(?i)\b(?:kapitel|abschnitt)\s+(?:über|ueber|zu|zum|zur|für|fuer)\s")
SATZTEIL_GRENZE_RE = re.compile(r"[,;:()\[\]–—]|\s-\s|[.!?](?=\s|$)")
VERNEINUNG_NAH_DAVOR_RE = re.compile(
    r"(?i)(?:\b(?:kein\w*|ohne)\s+(?:\S+\s+){0,2}"
    r"|\bweder\s+(?:\S+\s+){0,4})$")
NICHT_DANACH_RE = re.compile(r"(?i)\bnichts?\b")
# Ein kleingeschriebener Pfad ohne Endung ist ein Zeiger („am ehesten
# handbuch/mietminderung"), außer er nennt einen Ordner („Ordner
# beispiel-extern/handbuch", „beispiel-extern/handbuch/") oder liegt im
# geprüften Tresor (knowledge/…). Glieder unter drei Zeichen („km/h") und
# „und/oder" sind keine Pfade; ein kleingeschriebenes Begriffspaar
# („miete/kaution") ist von einem Pfad nicht zu unterscheiden und zählt mit.
SCHRAEG_PFAD_RE = re.compile(
    r"(?<![\w/.-])(?!und/oder(?![\w/.-])|and/or(?![\w/.-]))"
    r"([a-z0-9][a-z0-9._-]*(?:/[a-z0-9][a-z0-9._-]*)+/?)(?![\w/.-])")
ORDNER_DAVOR_RE = re.compile(
    r"(?i)\b(?:ordner|verzeichnis|unterordner|quellordner|wurzel)\s+$")
# Ein Paragraf ist eine Fundstelle („§ 4 regelt nur die Minderung"), außer er
# nennt das Thema der Suche: Er steht in der Frage, oder eine Präposition des
# Themas steht davor („keine Treffer für § 551 BGB", „zu §§ 535 ff.").
PARAGRAF_RE = re.compile(r"§§?\s*(\d+)")
THEMA_DAVOR_RE = re.compile(
    r"(?i)\b(?:zu|zum|zur|über|ueber|für|fuer|bei|hinsichtlich|nach|wegen|"
    r"bezüglich|bezueglich|bzgl\.?|betreffend|um)\s+$")
# Ein Pfad ohne Endung, dem eine Satzposition folgt: auch das ist eine
# Fundstelle („handbuch/eigenbedarf, Satzposition 2"). Ein Pfad ist es nur
# mit kleinem Anfang jedes Glieds; „Mieter/Vermieter, Satzposition 7" nennt
# ein Stichwort.
FREMDE_STELLE_RE = re.compile(
    r"(?i)(?<![\w/.-])((?-i:(?:[a-z0-9_.-][\w.-]*/)+[a-z0-9_.-]*[a-z][\w.-]*)"
    r")(?=\s*[,:(]?\s*"
    r"(?:satz(?:position|nummer)?|sentence(?:_index)?|absatz|zeile|seite)"
    r"\s*[:=]?\s*\d)")
# Ein Pfad, den die Angabe einer Quelle zuschreibt: eine Kennung direkt
# davor („X-0001, INDEX.md", nicht in einer Klammer dahinter: „X-0001
# (sources/EXTERN.md: lokal gebunden)") oder eine Satzposition direkt
# dahinter („INDEX.md (Satzposition 2)"; ein Abschnitt kann zur Tresordatei
# selbst gehören).
QUELLBEZUG_DAVOR_RE = re.compile(r"(?i)X-\d{4}[\s,:/—–-]*$")
QUELLBEZUG_DAHINTER_RE = re.compile(
    r"(?i)\s*[,:(]?\s*(?:satz(?:position|nummer)?|sentence(?:_index)?|"
    r"seite|zeile)\b")
# Eine Rückfrage in einer Angabe: eine Klammer mit Fragezeichen, oder der
# Schluss eines Satzes, der mit einem Fragezeichen endet. Gefragt ist das
# letzte Segment nach Semikolon, Doppelpunkt oder Gedankenstrich, wenn es
# wie eine Frage beginnt (Verb, „oder", Fragewort), sonst nur sein letzter
# Teilsatz nach einem Komma.
RUECKFRAGE_KLAMMER_RE = re.compile(r"\s*[(\[][^()\[\]]*\?[^()\[\]]*[)\]]")
STARKE_GRENZE_RE = re.compile(r"[;:]|\s[—–-]\s|[—–]")
WORT_IM_SATZ_RE = re.compile(r"[^\W\d_][\w']*")
FRAGE_VERBEN = frozenset("""
soll sollen sollte sollten möchtest moechtest möchten moechten möchte moechte
willst wollen will kann kannst können koennen könnte koennte könntest
koenntest darf darfst dürfen duerfen hilft helfen passt passen beantwortet
beantworten ist sind gibt gäbe gaebe hast haben habe hat wäre waere wären
waeren würde wuerde würdest wuerdest brauchst brauchen reicht genügt genuegt
stimmt meinst meinen magst oder
""".split())
FRAGEWORT_ANFANG = frozenset("""
wie was wann wo wer wen wem wessen welche welcher welches welchen welchem
warum wieso weshalb wozu wohin woher ob
""".split())
# Ein Befehl in Code (eine Code-Spanne mit Leerraum): Er weist keine Quelle
# aus, auch wenn er ihre Kennung nennt.
BEFEHL_RE = re.compile(r"`[^`\n]*\s[^`\n]*`")
# Hervorhebung an Wortgrenzen; ein Unterstrich im Wort bleibt
# (miet_kaution.md, not_bound).
HERVORHEBUNG_RE = re.compile(
    r"[*`\u00ad\u200b\u200c\u200d\u2060\ufeff]|(?<![^\W_])_+|_+(?![^\W_])")
# Ein zitierter Satz: Was darin steht, nennt die Angabe nicht als Fundstelle.
ZITAT_RE = re.compile(
    r"„[^“”\"\n]*[“”\"]|“[^”\n]*”|«[^»\n]*»|»[^«\n]*«|\"[^\"\n]*\"")
# Die Zustände von external.state, die nichts gelesen haben (antworten.md, 4c).
EXTERN_ZUSTAENDE = ("not_bound", "unreachable", "budget_exceeded",
                    "invalid_external_source", "invalid_query")
# So heißt der Offline-Schalter der Engine (vault.py, EXTERN_OFFLINE_ENV),
# und so liest sie ihn (_netz_erlaubt).
OFFLINE_SCHALTER = "SKILLSAFE_OFFLINE"
OFFLINE_WERTE = {"1", "true", "yes"}


class ProtokollFehler(ValueError):
    """Das Protokoll ist kaputt oder passt nicht zum Stand des Tresors."""


# Ein Lauf von main() rechnet mit einem Stand: query und sweep schreiben
# nichts, query --extern ruft hier nur mit Offline-Schalter ab, und Tresor
# und Bindung gelten, wie sie zu Beginn des Laufs waren. Derselbe Aufruf läuft
# deshalb einmal je Lauf. Der Speicher gehört dem Thread, der main()
# ausführt; außerhalb von main() ruft lauf() die Engine jedes Mal auf.
_LAUF = threading.local()


def _engine(vault, argv, umgebung):
    return subprocess.run(
        [sys.executable, "-B", str(vault / "scripts" / "vault.py"), *argv],
        cwd=str(vault),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=120,
        env=dict(os.environ, **umgebung) if umgebung else None,
    )


def lauf(vault, *argv, umgebung=None):
    """Die Engine so aufrufen, wie ein Agent es täte: als Prozess, über JSON."""
    vault = Path(vault).resolve()
    laeufe = getattr(_LAUF, "laeufe", None)
    if laeufe is None:
        ergebnis = _engine(vault, argv, umgebung)
    else:
        schluessel = (str(vault), argv,
                      tuple(sorted((umgebung or {}).items())))
        if schluessel not in laeufe:
            laeufe[schluessel] = _engine(vault, argv, umgebung)
        ergebnis = laeufe[schluessel]
    try:
        return json.loads(ergebnis.stdout)
    except json.JSONDecodeError as exc:
        raise ProtokollFehler(
            f"vault.py {' '.join(argv[:1])} lieferte kein JSON "
            f"(Exit {ergebnis.returncode}): "
            f"{(ergebnis.stdout + ergebnis.stderr)[-400:]}"
        ) from exc


def lade_protokoll(pfad, vault):
    pfad = Path(pfad).resolve()
    vault = Path(vault).resolve()
    if pfad == vault or vault in pfad.parents:
        raise ProtokollFehler(
            f"{pfad} liegt im Skill-Ordner. Ein Protokoll gehört nie in den "
            f"Skill: dort würde es mit ausgeliefert und vom Modell mitgelesen."
        )
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProtokollFehler(f"{pfad} ist nicht lesbar: {exc}") from exc
    if not isinstance(daten, dict) or daten.get("schema") != PROTOKOLL_SCHEMA:
        raise ProtokollFehler(f"{pfad}: Schema {PROTOKOLL_SCHEMA!r} erwartet")
    antworten = daten.get("antworten")
    if not isinstance(antworten, list) or not antworten:
        raise ProtokollFehler(f"{pfad}: 'antworten' fehlt oder ist leer")
    gesehen = set()
    for nummer, eintrag in enumerate(antworten, 1):
        wo = f"{pfad}: Antwort {nummer}"
        if not isinstance(eintrag, dict):
            raise ProtokollFehler(f"{wo} ist kein Objekt")
        for feld in ("frage", "antwort"):
            if not isinstance(eintrag.get(feld), str) or not eintrag[feld].strip():
                raise ProtokollFehler(f"{wo}: '{feld}' fehlt oder ist leer")
        # Eine Frage mit Zeilenumbruch oder Steuerzeichen nimmt die Engine
        # nicht an; so kann sie kein Agent gestellt haben.
        if any(ord(zeichen) < 32 or ord(zeichen) == 127
               for zeichen in eintrag["frage"]):
            raise ProtokollFehler(
                f"{wo}: 'frage' enthält einen Zeilenumbruch oder ein "
                f"Steuerzeichen; die Engine nimmt so eine Frage nicht an")
        for feld in ("quittung", "sweep_args", "erwartet"):
            wert = eintrag.setdefault(feld, [])
            if not isinstance(wert, list) or not all(
                    isinstance(teil, str) for teil in wert):
                raise ProtokollFehler(f"{wo}: '{feld}' muss eine Textliste sein")
        # Was hier stünde, hängte die Engine an die Frage an: Ein Wort mehr,
        # und die Quittung gälte für eine andere Frage als die geprüfte.
        argumente = eintrag["sweep_args"]
        if len(argumente) % 2 or any(
                schalter not in SWEEP_SCHALTER or wert.startswith("-")
                or not wert.strip()
                for schalter, wert in zip(argumente[::2], argumente[1::2])):
            raise ProtokollFehler(
                f"{wo}: 'sweep_args' nennt nur den Zuschnitt der Sichtung, "
                f"als Paare aus {', '.join(sorted(SWEEP_SCHALTER))} und Wert"
            )
        if eintrag.get("art") not in (None, "positiv", "negativ"):
            raise ProtokollFehler(f"{wo}: 'art' ist positiv, negativ oder fehlt")
        # Gibt der Mensch einen Umfang vor, oder nennt die Frage selbst eine
        # Domäne oder Seite als Umfang, erfüllt die Sichtung dieses Umfangs
        # die Pflicht (antworten.md, Schritt 4b). Das weiß nur,
        # wer die Messung gebaut hat; also steht es im Protokoll.
        umfang = eintrag.setdefault("umfang_vorgegeben", False)
        if not isinstance(umfang, bool):
            raise ProtokollFehler(f"{wo}: 'umfang_vorgegeben' ist wahr oder falsch")
        if umfang and not set(argumente[::2]) & {"--domain", "--page"}:
            raise ProtokollFehler(
                f"{wo}: 'umfang_vorgegeben' verlangt in 'sweep_args' den "
                f"Umfang (--domain oder --page)")
        if eintrag.get("art") == "negativ" and eintrag["erwartet"]:
            raise ProtokollFehler(f"{wo}: eine Negativfrage erwartet keinen Claim")
        # Schritt 4c entfällt nur auf Wunsch des Nutzers oder nach einer
        # Vorgabe der Umgebung (antworten.md, 4c). Auch das weiß nur, wer die
        # Messung gebaut hat: Der Eintrag trägt den Wortlaut der Vorgabe.
        vorgabe = eintrag.setdefault("vorgabe", None)
        if vorgabe is not None and (
                not isinstance(vorgabe, str) or not vorgabe.strip()):
            raise ProtokollFehler(
                f"{wo}: 'vorgabe' ist der Wortlaut einer Vorgabe des Nutzers "
                f"oder der Umgebung")
        kennung = eintrag.get("id", nummer)
        if isinstance(kennung, bool) or not isinstance(kennung, (str, int)):
            raise ProtokollFehler(f"{wo}: 'id' ist ein Text oder eine Zahl")
        kennung = eintrag["id"] = str(kennung)
        if kennung in gesehen:
            raise ProtokollFehler(f"{wo}: Kennung {kennung!r} ist doppelt")
        gesehen.add(kennung)
    stand = daten.get("stand") or {}
    if not isinstance(stand, dict):
        raise ProtokollFehler(f"{pfad}: 'stand' muss ein Objekt sein")
    digest = stand.get("manifest_sha256")
    if digest is not None and not (
            isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest)):
        raise ProtokollFehler(
            f"{pfad}: 'stand.manifest_sha256' ist ein SHA-256 in Hexschreibung")
    for feld in ("commit", "version"):
        if stand.get(feld) is not None and not isinstance(stand[feld], str):
            raise ProtokollFehler(f"{pfad}: 'stand.{feld}' muss Text sein")
    # Bindung und Netzlage des Laufs: {"gebunden": ["X-0001"], "offline": true}.
    extern = stand.get("extern")
    if extern is not None:
        if (not isinstance(extern, dict)
                or set(extern) - {"gebunden", "offline"}
                or ("offline" in extern and not isinstance(extern["offline"], bool))
                or ("gebunden" in extern and (
                    not isinstance(extern["gebunden"], list)
                    or not all(isinstance(kennung, str)
                               and X_KENNUNG_RE.fullmatch(kennung)
                               for kennung in extern["gebunden"])))):
            raise ProtokollFehler(
                f"{pfad}: 'stand.extern' ist ein Objekt mit 'gebunden' "
                f"(Liste von X-Kennungen) und 'offline' (wahr oder falsch)")
    return antworten, stand


def bestand_lesen(vault):
    """Jede Claim-ID des Stands mit ihrer Seite, über die Vollsichtung."""
    frage = "Bestandsaufnahme für die Nachprüfung"
    plan = lauf(vault, "sweep", frage, "--size", "200")
    if plan.get("state") != "plan":
        raise ProtokollFehler(
            f"Der Tresor ist nicht bereit ({plan.get('state')}): "
            f"{plan.get('errors')}"
        )
    seite_von, kennungen = {}, set()
    for eintrag in plan["batches"]:
        stapel = lauf(vault, "sweep", frage, "--size", "200",
                      "--batch", str(eintrag["batch"]))
        for seite in stapel["pages"]:
            for claim in seite["claims"]:
                seite_von[claim["claim_id"]] = seite["path"]
                if claim.get("source_id"):
                    kennungen.add(str(claim["source_id"]).upper())
    # Quellen und Begriffe stehen in ihren Registern, auch ohne Claim.
    texte = {}
    for name in ("sources/REGISTER.md", "sources/EXTERN.md",
                 "schema/begriffswelten.json"):
        try:
            texte[name] = (Path(vault) / name).read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        kennungen.update(kennung.upper() for kennung in re.findall(
            r"(?i)(?<![A-Za-z0-9])[SXB]-\d{4}(?!\d)", texte[name]))
    extern = sorted({kennung.upper() for kennung in re.findall(
        r"(?im)^\|\s*(X-\d{4})\s*\|", texte.get("sources/EXTERN.md", ""))})
    return {
        "seite_von": seite_von,
        "kennungen": kennungen | set(seite_von),
        "extern": extern,
        "manifest": plan["vault"]["manifest_sha256"],
        "version": plan["vault"]["version"],
    }


def _lesbare_seiten(*ausgaben):
    """Seiten, die der Vertrag nach diesen Ausgaben zu lesen gibt."""
    seiten = set()
    for ausgabe in ausgaben:
        if not ausgabe:
            continue
        for seite in ausgabe.get("pages", []):
            seiten.add(seite["path"])
            kanten = seite.get("relations") or {}
            for richtung in ("incoming", "outgoing"):
                for kante in kanten.get(richtung, []):
                    if kante.get("type") in LESEKANTEN:
                        seiten.add(kante["page"])
        for seite in ausgabe.get("coverage", {}).get("omitted_pages", []) or []:
            seiten.add(seite["path"])
    return seiten


def _striche(text):
    """Kennungen mit typografischem Strich in die Schreibung C-0001 bringen."""
    return KENNUNG_STRICH_RE.sub(r"\1-", text)


def _ohne_zitatzeichen(text):
    """Markdown-Zitatzeichen am Zeilenanfang entfernen ("> ")."""
    return re.sub(r"(?m)^[ \t]*(?:>[ \t]?)+", "", text)


def _sagt_im_umfang_nicht(antwort):
    """Die Abstention einer eingeschränkten Sichtung: „in diesem Umfang nicht
    gefunden", auch umbrochen, zitiert oder hervorgehoben."""
    return ("in diesem umfang nicht gefunden"
            in _wortlaut(_ohne_zitatzeichen(antwort)))


def _sagt_nicht_im_bestand(antwort):
    """Steht die Formel da, auch umbrochen, zitiert oder hervorgehoben?"""
    return ABSTENTION in _wortlaut(_ohne_zitatzeichen(antwort))


def _zitierte_claims(text, bestand_ids):
    """Jede genannte Claim-ID, Bereiche aufgelöst, in fester Schreibung."""
    zitiert = {f"C-{ziffern}" for ziffern in CLAIM_RE.findall(text)}
    for von, bis in BEREICH_RE.findall(text):
        unten, oben = sorted((int(von), int(bis)))
        zitiert.update(
            cid for cid in bestand_ids if unten <= int(cid[2:]) <= oben)
    return sorted(zitiert)


# Wann eine Kennung, die es nicht gibt, nur erwähnt ist: in einem Satzteil,
# der nichts sagt als ihr Fehlen ("Die Kennung C-9999 gibt es im Bestand
# nicht"), der nur nachfragt ("Falls mit C-9999 eine andere gemeint war"),
# der sie ausdrücklich als Quelle ausschließt ("nicht aus S-0099") oder der
# die Frage wiederholt. Ein Satzteil mit irgendeinem anderen Wort trägt eine
# Aussage, und eine Kennung darin ist eine Quelle.
KENNUNG_TEXT_RE = re.compile(r"(?i)(?<![A-Za-z0-9])[CSBX]-\d{4}(?!\d)")
ZIEL = "zzzielzz"
ANDERE = "zzkennungzz"
ABSENZ_WOERTER = frozenset("""
die der das den dem des ein eine einen einem einer eines diese dieser dieses
diesen diesem es sie kennung kennungen id ids claim claims quelle quellen
begriff begriffe begriffen eintrag eintraege eintraegen nummer nummern gesuchte
gesuchten erfragte erfragten genannte genannten angefragte angefragten gefragte
gefragten angegebene angegebenen gueltige gueltigen gueltiger gueltiges solche
solchen unter nichts verzeichnet eingetragen gibt geben
existiert existieren ist sind war waere wird werden lautet lauten heisst heissen
kennt kennen enthaelt enthalten fehlt fehlen kommt kommen vor vorhanden vergeben
bekannt im in mit diesem dem bestand bestands tresor tresors wissenstresor hier
dort darin nicht kein keine keinen keiner nirgends unbekannt und oder sowie
aber jedoch leider also auch so daher deshalb noch weil da zu zur zum fuer
ueber von mir uns ich wir konnte konnten kann koennen finden gefunden
auffindbar wurde wurden register quellenregister begriffsregister verzeichnis
finde findet sich teil namens
""".split())
# Eine Klammer, die nur sagt, was für eine Kennung es ist ("C-9998 (Claim)"),
# ist keine Fundstelle.
TYP_WOERTER = frozenset("""
claim claims quelle quellen begriff begriffe kennung kennungen eintrag id ids
nummer aus der die das ihrer deiner ihre deine frage gesucht gesuchte
gesuchten angefragt angefragte genannt genannte
""".split())
# Zeilen des Envelopes beginnen mit einem Etikett; sie setzen keinen Satz der
# Zeile davor fort, und keine Zeile setzt sie fort.
ETIKETT_RE = re.compile(
    r"(?i)^\s*(?:stand|hinweise?|nicht im bestand|(?:voll)?sichtung|"
    r"extern\b[^:\n]{0,40}|belege?|konfidenz|quellen?|antwort|ergebnis|"
    r"fundstellen?)\s*:")
UEBERSCHRIFT_RE = re.compile(
    r"^\s*(?:#{1,6}\s+\S.*|\*\*[^*\n]+\*\*:?|__[^_\n]+__:?)\s*$")
# "laut Bestand" nennt den Bestand, nicht die Kennung, als Quelle; "laut
# C-9999" bleibt eine Quellenangabe.
LAUT_BESTAND_RE = re.compile(
    r"\b(?:laut|gemaess|nach) (?:(?:dem|des) )?(?=(?:bestand|bestands|tresor|"
    r"tresors|wissenstresor)\b)")
ABSENZ_KERN = frozenset(
    "nicht nichts kein keine keinen keiner nirgends unbekannt fehlt fehlen"
    .split())
KLAERUNG_WOERTER = frozenset("""
falls wenn ob mit eine einer einen andere anderer anderes anderen gemeint war
ist sei waere bitte nennen nenne angeben dann schlage ich sie nach meinten
meinst meinen du die der das den kennung quelle claim id begriff eintrag nummer
""".split())
KLAERUNG_KERN = frozenset("gemeint meinten meinst meinen".split())
FRAGE_WOERTER = frozenset("""
was wer wie wo wozu worum woraus woran welche welcher welches welchen welchem
steht stehen sagt besagt bedeutet bedeuten heisst meint regelt beschreibt nennt
erklaert erklaere zeigt lautet existiert gibt es ist sind in im zu zum zur
ueber von vom bei mit der die das den dem des ein eine einen einem einer eines
und oder kennung quelle claim id begriff eintrag nummer
""".split())
# "Sie fragen nach C-9999": die Frage in eigenen Worten.
NACHFRAGE_WOERTER = frozenset("""
sie du ihr fragen fragst fragt gefragt frage ihre deine nach ist war wurde
worden die der das den kennung quelle claim id begriff eintrag nummer zu um es
geht hier dabei
""".split())
NACHFRAGE_KERN = frozenset("fragen fragst fragt gefragt frage".split())
# "S-0099 ist nicht ihre Quelle": ausdrücklich keine Quelle.
NICHT_QUELLE_WOERTER = frozenset("""
ist sind war nicht keine kein die ihre deren dessen quelle quellen fundstelle
beleg belege dieser diese der aussagen aussage angaben claims claim dafuer
hier also auch aber jedoch
""".split())
NICHT_QUELLE_KERN = frozenset("quelle quellen fundstelle beleg belege".split())
AUSSCHLUSS_VOR = (("nicht", "aus"), ("nicht", "von"), ("statt",),
                  ("anstatt",), ("anstelle",), ("anstelle", "von"))
ERLAUBTE_NENNUNG = {"fehlen", "rueckfrage", "ausschluss", "frage", "abgrenzung"}
# Eine externe Quelle hinter „in", „aus", „bei", „innerhalb" oder in einer
# Angabe zu Schritt 4c ist der Ort der Suche, nicht das, was fehlt („in
# X-0001 nichts gefunden", „Extern (nicht im Bestand): X-0001 – nichts
# gefunden").
ORT_VOR = {("in",), ("aus",), ("bei",), ("innerhalb",)}
LISTENPUNKT_RE = re.compile(r"^\s*(?:[-*•+–—]|\d{1,3}[.)])\s+")


def _abschnitte(text):
    """Die Sätze einer Antwort; eine eingeleitete Liste bleibt beim Satz.

    Ein Satz endet an ". ! ?" vor Leerraum, an einer Leerzeile und an einem
    Zeilenende nach einem Satzzeichen. Eine Zeile ohne Satzzeichen am Ende
    setzt sich in der nächsten fort. Eine Liste gehört zu dem Satz davor,
    wenn er mit einem Doppelpunkt endet: "Diese Kennungen gibt es nicht:\n-
    C-9998"; ihre Listenmarken ("-", "1.") fallen dabei weg.
    """
    bloecke, aktuell, liste = [], [], False
    etikett_davor = False

    def abschliessen():
        if aktuell:
            bloecke.append(" ".join(aktuell))
        aktuell.clear()

    for roh in _ohne_zitatzeichen(text).splitlines():
        zeile = FORMEL_STOERER.sub("", roh)
        inhalt = zeile.strip()
        if not inhalt:
            abschliessen()
            liste = etikett_davor = False
            continue
        # Eine Überschrift ("**Ergebnis**", "## Sichtung") steht für sich.
        if UEBERSCHRIFT_RE.match(roh):
            abschliessen()
            aktuell.append(inhalt)
            abschliessen()
            liste = etikett_davor = False
            continue
        punkt = LISTENPUNKT_RE.match(zeile)
        if punkt:
            eingeleitet = liste or (
                aktuell and aktuell[-1].rstrip().endswith(":"))
            if not eingeleitet:
                abschliessen()
            aktuell.append(zeile[punkt.end():].strip())
            liste = True
            continue
        # Eine Zeile, die mit einer Kennung beginnt, ist eine eigene Angabe
        # (eine Belegzeile), auch ohne Satzzeichen davor; ebenso eine Zeile
        # des Envelopes ("Stand: …", "Nicht im Bestand: …").
        etikett = bool(ETIKETT_RE.match(inhalt))
        fortsetzung = (aktuell and not liste and not etikett
                       and not etikett_davor
                       and not re.search(r"[.!?:]$", aktuell[-1])
                       and not KENNUNG_TEXT_RE.match(inhalt))
        if not fortsetzung:
            abschliessen()
            liste = False
        aktuell.append(inhalt)
        etikett_davor = etikett
    abschliessen()
    saetze = []
    for block in bloecke:
        saetze.extend(teil for teil in re.split(r"(?<=[.!?])\s+", block)
                      if teil.strip())
    return saetze


def _woerter(text):
    text = unicodedata.normalize("NFKC", text).casefold()
    text = (text.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
            .replace("ß", "ss"))
    return re.findall(r"[a-z0-9]+", text)


def _art_des_satzteils(teil, ist_frage):
    """Was ein Satzteil über eine Kennung darin sagt."""
    woerter = LAUT_BESTAND_RE.sub("", " ".join(_woerter(teil))).split()
    inhalt = [wort for wort in woerter if wort not in (ZIEL, ANDERE)]
    if not inhalt:
        return None
    if (any(wort in ABSENZ_KERN for wort in inhalt)
            and all(wort in ABSENZ_WOERTER for wort in inhalt)):
        return "fehlen"
    if (any(wort in KLAERUNG_KERN for wort in inhalt)
            and all(wort in KLAERUNG_WOERTER for wort in inhalt)):
        return "rueckfrage"
    if ist_frage and all(wort in FRAGE_WOERTER for wort in inhalt):
        return "frage"
    if (any(wort in NACHFRAGE_KERN for wort in inhalt)
            and all(wort in NACHFRAGE_WOERTER for wort in inhalt)):
        return "frage"
    if (any(wort in NICHT_QUELLE_KERN for wort in inhalt)
            and any(wort in ("nicht", "keine", "kein") for wort in inhalt)
            and all(wort in NICHT_QUELLE_WOERTER for wort in inhalt)):
        return "ausschluss"
    return "aussage"


def _ohne_typklammern(text):
    """Klammern, die nur die Art einer Kennung nennen, fallen weg."""
    def ersetze(treffer):
        woerter = _woerter(treffer.group(1))
        if woerter and all(wort in TYP_WOERTER for wort in woerter):
            return " "
        return treffer.group(0)
    return re.sub(r"\(([^()]*)\)", ersetze, text)


def _nennungen(text, kennung):
    """Jede Nennung einer Kennung mit der Art des Satzteils, in dem sie steht.

    "beleg" heißt: Die Antwort führt sie als Quelle. Ein Satzteil aus nichts
    als Kennungen ("C-9998, C-9999" hinter einem Doppelpunkt) gehört zu dem
    Satzteil davor.
    """
    muster = re.compile(rf"(?i)(?<![A-Za-z0-9]){re.escape(kennung)}(?!\d)")
    arten = []
    zuletzt_genannt = False
    for satz in _abschnitte(text):
        if not muster.search(satz):
            # "Sie fragen nach C-9999. Diese Kennung gibt es nicht.": Ein Satz
            # ohne jede Kennung, der nichts sagt als ein Fehlen, gilt der
            # Kennung des Satzes unmittelbar davor.
            if (zuletzt_genannt and not KENNUNG_TEXT_RE.search(satz)
                    and _art_des_satzteils(satz, False) == "fehlen"):
                arten.append("fehlen")
            zuletzt_genannt = False
            continue
        zuletzt_genannt = True
        # Die Etiketten von Schritt 4c sind Hüllzeilen, keine Aussage: Ihr
        # „(nicht im Bestand)" sagt nichts über eine Kennung daneben
        # („**Extern (nicht im Bestand)** (X-0001, lokal gelesen):").
        roh = _ohne_typklammern(EXTERN_ETIKETT_TEXT_RE.sub(
            " ", muster.sub(f" {ZIEL} ", satz)))
        # In eckigen Klammern ist eine Kennung immer eine Quellenangabe, ebenso
        # vor einer Klammer mit Fundstelle: "C-9999 (S-0001, Einleitung)".
        if (re.search(rf"\[[^\]]*{ZIEL}", roh)
                or re.search(rf"{ZIEL}\s*\((?![\s\W]*\))", KENNUNG_TEXT_RE.sub(
                    f" {ANDERE} ", roh).replace(f"( {ANDERE} )", ""))):
            arten.extend("beleg" for _ in muster.finditer(satz))
            continue
        roh = KENNUNG_TEXT_RE.sub(f" {ANDERE} ", roh)
        # Eine Klammer um nichts als Kennungen ändert am Satz nichts.
        roh = re.sub(
            rf"\(\s*((?:{ZIEL}|{ANDERE})(?:\s*(?:,|und|oder|sowie)\s*"
            rf"(?:{ZIEL}|{ANDERE}))*)\s*\)", r" \1 ", roh)
        ist_frage = satz.rstrip().endswith("?")
        # Satzteile mit ihrer Klammertiefe: Eine Kennung, die allein steht,
        # gehört zum Satzteil davor auf derselben Ebene, nicht zum Inhalt
        # einer Klammer ("Extern (nicht im Bestand): X-0003").
        teile, tiefen, trenner, tiefe, vorher = [], [], [], 0, None
        for nummer, stueck in enumerate(
                re.split(r"([,;:()\[\]–—]|\s-\s)", roh)):
            if nummer % 2:
                if stueck in ("(", "["):
                    tiefe += 1
                elif stueck in (")", "]"):
                    tiefe = max(0, tiefe - 1)
                vorher = stueck
                continue
            teile.append(stueck)
            tiefen.append(tiefe)
            trenner.append(vorher)
        einordnung = [_art_des_satzteils(teil, ist_frage) for teil in teile]
        # "Nicht im Bestand: Inhalt von C-9999" grenzt ab, was fehlt; das gilt
        # für das Etikett und den einen Satzteil nach seinem Doppelpunkt,
        # nicht für den Rest des Satzes ("…; nach S-0005 sind es 20 Prozent").
        if _woerter(roh)[:3] == ["nicht", "im", "bestand"]:
            ende = next((nummer for nummer in range(1, len(teile))
                         if trenner[nummer] == ":" and tiefen[nummer] == 0), 1)
            for stelle in range(min(ende + 1, len(teile))):
                if einordnung[stelle] is not None:
                    einordnung[stelle] = "abgrenzung"
        for stelle, teil in enumerate(teile):
            woerter = _woerter(teil)
            for position, wort in enumerate(woerter):
                if wort != ZIEL:
                    continue
                davor = tuple(w for w in woerter[:position]
                              if w not in (ZIEL, ANDERE))
                if any(davor[-len(muster_vor):] == muster_vor
                       for muster_vor in AUSSCHLUSS_VOR):
                    arten.append("ausschluss")
                    continue
                art = einordnung[stelle]
                if art is None:
                    # Nur Kennungen: der nächste Satzteil davor, sonst danach,
                    # auf derselben Klammerebene.
                    ebene = [nummer for nummer in range(len(teile))
                             if tiefen[nummer] == tiefen[stelle]]
                    nachbarn = (
                        [einordnung[nummer] for nummer in reversed(ebene)
                         if nummer < stelle and einordnung[nummer]]
                        + [einordnung[nummer] for nummer in ebene
                           if nummer > stelle and einordnung[nummer]])
                    art = nachbarn[0] if nachbarn else "beleg"
                if (art == "fehlen" and kennung.upper().startswith("X-")
                        and (davor[-1:] in ORT_VOR
                             or EXTERN_ETIKETT_TEXT_RE.search(satz))):
                    art = "beleg"
                arten.append(art if art in ERLAUBTE_NENNUNG else "beleg")
    return arten


def _nur_als_fehlend(text, kennung):
    """Nennt die Antwort diese Kennung nur so, wie der Vertrag es erlaubt?

    Für eine Kennung, die es nicht gibt: im Satz, der ihr Fehlen feststellt,
    in einer Rückfrage, als ausdrücklich ausgeschlossene Quelle oder in der
    wiederholten Frage. Jede andere Nennung führt sie als Quelle, gleich in
    welcher Form. Kommt sie gar nicht vor, ist das Ergebnis falsch.
    """
    arten = _nennungen(text, kennung)
    return bool(arten) and all(art in ERLAUBTE_NENNUNG for art in arten)


def _erlaubt(text, kennung, aus_frage):
    """Nennt die Antwort diese Kennung nur so, wie der Vertrag es erlaubt?

    Eine Kennung aus der Frage darf sie als fehlend feststellen, nachfragen,
    als Quelle ausschließen, in der wiederholten Frage oder in der Abgrenzung
    nennen. Jede andere Kennung nur als fehlend oder ausgeschlossen: Eine
    Rückfrage, die eine andere Kennung vorschlägt, ist ein Zitat.
    """
    arten = _nennungen(text, kennung)
    erlaubt = ERLAUBTE_NENNUNG if aus_frage else {"fehlen", "ausschluss"}
    return bool(arten) and all(art in erlaubt for art in arten)


def _stellt_fehlen_fest(text, kennung):
    """Steht wenigstens ein Satz da, der das Fehlen der Kennung feststellt?"""
    return "fehlen" in _nennungen(text, kennung)


def _zahl(text):
    return int(re.sub(r"\D", "", text))


SICHTUNG_ZEILE_RE = re.compile(r"(?i)^[\s>*_`#-]*(?:voll)?sichtung\b")
PAAR_RE = re.compile(
    rf"(?i)(?<![\d.])(?:({ZAHL})\s*(?:von|/)\s*(?:insgesamt\s+)?({ZAHL})"
    rf"|alle(?:\s+(?:der|gesichteten))?\s+({ZAHL}))(?![\d])(\s+Claims?\b)?")
VERNEINT_RE = re.compile(r"(?i)\b(?:nicht|kein\w*|ohne)\b")
# "Sichtung: entfällt" behauptet keine Sichtung.
VERNEINT_ZEILE_RE = re.compile(
    r"(?i)\b(?:nicht|kein\w*|ohne|entf(?:ä|ae)llt|entfallen)\b")
# Ein Zahlenpaar vor "Stapel" oder "Seiten" zählt keine Claims.
ANDERE_EINHEIT_RE = re.compile(r"(?i)\s*(?:stapel\w*|batch\w*|seiten?)\b")
# Ein Satzteil mit einem dieser Wörter sagt, was die Sichtung fand, nicht wie
# weit sie reichte: "0 von 28 Claims nennen das", "alle 10 Claims zu OKF
# stammen aus S-0004". Ebenso eine Zeile, die ein Ergebnis ankündigt.
ERGEBNIS_RE = re.compile(
    r"(?i)\b(?:nenn\w*|nannt\w*|enth(?:ä|ae)lt|enthalt\w*|enthielt\w*|"
    r"betr(?:ifft|af\w*|eff\w*)|pass\w*|tr(?:ä|ae)gt|trag\w*|stamm\w*|"
    r"erw(?:ä|ae)hn\w*|beantwort\w*|tr(?:ifft|af\w*|eff\w*)|sag\w*|"
    r"beleg\w*|gefund\w*|find\w*|ergab\w*|ergeb\w*|w(?:ä|ae)hl\w*|"
    r"gew(?:ä|ae)hlt\w*|einschl(?:ä|ae)gig\w*|relevant\w*|zutreffend\w*|"
    r"behandel\w*|beschreib\w*|regel\w*|bezieh\w*|befund\w*)\b")
SATZTEIL_RE = re.compile(
    r"[;:!?]|,(?!\d)|\.(?!\d)|\s(?:und|aber|doch|jedoch)\s", re.IGNORECASE)


def _paarwerte(paar):
    if paar.group(3):
        return (_zahl(paar.group(3)), _zahl(paar.group(3)))
    return (_zahl(paar.group(1)), _zahl(paar.group(2)))


def _sichtungsangaben(antwort):
    """Jede Angabe zu einer Sichtung, mit Zahlen und Quittungskennung.

    art "zeile": die Zeile „Sichtung:" (auch „Vollsichtung", „## Sichtung",
    gleich in welcher Schreibung; steht dort nur das Wort, zählt die nächste
    Zeile dazu). Eine verneinte Zeile ohne Zahlen und Kennung („Sichtung:
    entfällt") ist keine Angabe. art "kennung": jede Zeile mit einer
    Quittungskennung. art "satz": jeder Satzteil einer Zeile, die die
    Sichtung nennt („Sichtung", „gesichtet"), mit „N von M Claims" oder „alle
    N Claims", ohne Verneinung und ohne Wort, das ein Ergebnis nennt („0 von
    28 Claims nennen …"). Ob ein Satz eine Vollsichtung behauptet oder nur
    eine Teilmenge beschreibt, entscheidet pruefe mit den Zahlen.

    Zahlenpaare vor „Stapel" oder „Seiten" zählen keine Claims, und eine
    Hexfolge nach „Siegel" ist keine Quittungskennung.
    """
    angaben = []
    text = FORMEL_STOERER.sub("", _ohne_zitatzeichen(antwort))
    zeilen = text.splitlines()
    for nummer, zeile in enumerate(zeilen):
        als_zeile = bool(SICHTUNG_ZEILE_RE.match(zeile))
        if als_zeile and re.fullmatch(r"(?i)[\s>*_`#-]*(?:voll)?sichtung\W*",
                                      zeile) and nummer + 1 < len(zeilen):
            zeile = zeile + " " + zeilen[nummer + 1]
        paare = [paar for paar in PAAR_RE.finditer(zeile)
                 if not ANDERE_EINHEIT_RE.match(zeile, paar.end())]
        mit_claims = [paar for paar in paare if paar.group(4)]
        paar = (mit_claims or paare or [None])[0]
        kennung = KENNUNG_RE.search(zeile)
        nennt_sichtung = bool(SICHTUNG_WORT_RE.search(zeile))
        if not kennung and nennt_sichtung:
            kennung = next((
                frei for frei in KENNUNG_FREI_RE.finditer(zeile)
                if re.search("[a-f]", frei.group(1))
                and not re.search(r"(?i)siegel\W*$", zeile[:frei.start()])),
                None)
        zahlen = _paarwerte(paar) if paar else None
        schon = set()
        verneint = (als_zeile and not paar and not kennung
                    and VERNEINT_ZEILE_RE.search(zeile))
        if (als_zeile or kennung) and not verneint:
            angaben.append({
                "zahlen": zahlen,
                "claims": bool(paar and paar.group(4)),
                "kennung": kennung.group(1) if kennung else None,
                "art": "zeile" if als_zeile else "kennung",
            })
            schon.add(zahlen)
        # Jeder Satzteil zählt, auch in derselben Zeile: Eine zweite, falsche
        # Angabe stünde sonst unbemerkt hinter der richtigen.
        if not nennt_sichtung or (
                not als_zeile and re.search(
                    r"(?i)\b(?:ergebnis|treffer|befund)\w*", zeile)):
            continue
        for teil in SATZTEIL_RE.split(zeile):
            if VERNEINT_RE.search(teil) or ERGEBNIS_RE.search(teil):
                continue
            for treffer in PAAR_RE.finditer(teil):
                if not treffer.group(4):
                    continue
                werte = _paarwerte(treffer)
                if werte not in schon:
                    schon.add(werte)
                    angaben.append({"zahlen": werte, "claims": True,
                                    "kennung": None, "art": "satz"})
    return angaben


def _engine_entscheidet(abfrage):
    """Meldet die Engine den Kennungsfall selbst (seit v0.16.0)?

    Erkannt am Feld, nicht an der Versionsnummer: VERSION ist der Stand des
    Bestands, und ein eigener Tresor zählt unabhängig von der Engine.
    """
    return "unknown_ids_only" in (abfrage.get("fallback") or {})


def _gilt_allein_der_kennung(abfrage, antwort, belegt, abstention):
    """Antwortet hier jemand nur „diese Kennung gibt es nicht"?

    Das ist der eine Fall, in dem der Vertrag die Vollsichtung erlässt
    (antworten.md, Schritt 2b). Ob die Frage nichts als unbekannte Kennungen
    nennt, entscheidet seit v0.16.0 die Engine (fallback.unknown_ids_only).
    Für ältere Stände, deren Ausgabe das Feld nicht kennt, gilt ihre Regel:
    Die Ziffern der unbekannten Kennungen sind ungetroffen, und unter
    unmatched und partial steht sonst nichts. Dazu muss die Antwort nichts
    tun, wofür es eine Quittung bräuchte, und jede unbekannte Kennung nennen,
    und zwar nur in einem Satz, der ihr Fehlen feststellt.
    """
    abdeckung = abfrage.get("coverage", {})
    unbekannte_ids = list(abdeckung.get("unknown_ids") or [])
    if not unbekannte_ids or abstention or belegt:
        return False
    # Jede unbekannte Kennung genannt, mindestens einmal in einem Satz, der
    # ihr Fehlen feststellt, und nirgends als Quelle.
    if not all(_nur_als_fehlend(antwort, kennung)
               and _stellt_fehlen_fest(antwort, kennung)
               for kennung in unbekannte_ids):
        return False
    if _engine_entscheidet(abfrage):
        if abfrage["fallback"]["unknown_ids_only"] is not True:
            return False
    else:
        ziffern = {kennung.split("-", 1)[1] for kennung in unbekannte_ids}
        begriffe = abdeckung.get("query_terms") or {}
        ungetroffen = set(begriffe.get("unmatched") or [])
        offen = ungetroffen | set(begriffe.get("partial") or [])
        if not ziffern <= ungetroffen or offen - ziffern:
            return False
    return True


def _version(text):
    """Eine Versionsangabe dreistellig: „0.17" ist (0, 17, 0)."""
    teile = [int(teil) for teil in re.findall(r"\d+", str(text or ""))[:3]]
    return tuple(teile + [0] * (3 - len(teile))) if teile else None


def vertrag_4c(vault, stand=None):
    """Gilt für den geprüften Tresor die Pflicht zu Schritt 4c?

    Maßgeblich ist sein eigener Vertrag, references/antworten.md, das im
    Manifest liegt: Seit v0.17.0 heißt es dort in Schritt 4c „Der Schritt ist
    **Pflicht**", davor war er freigestellt. Die Nummer in VERSION taugt
    dafür nicht, denn ein eigener Tresor beginnt nach dem Rezept bei v1.0.0,
    gleich wie alt sein Motor ist. Nur wenn die Datei fehlt, gilt die Angabe
    stand.version des Protokolls, ohne Angabe der heutige Vertrag."""
    text = _vertragstext(vault)
    if text is None:
        version = _version((stand or {}).get("version"))
        return version is None or version >= VERTRAG_4C
    return bool(VERTRAG_4C_RE.search(text))


def _vertragstext(vault):
    """references/antworten.md ohne Zeilenumbrüche, None wenn nicht lesbar."""
    try:
        text = (Path(vault) / "references" / "antworten.md").read_text(
            encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    return " ".join(text.split())


def vertrag_4c_hinweis(vault):
    """Ein Hinweis, wenn das Werkzeug Schritt 4c im Vertrag gar nicht findet.

    Ein Vertrag, der den Schritt freistellt, nennt ihn trotzdem. Fehlt die
    Überschrift ganz, prüft das Werkzeug ohne die Pflicht, sagt das aber,
    statt die Regel still abzuschalten."""
    text = _vertragstext(vault)
    if text is not None and VERTRAG_4C_KOPF_RE.search(text):
        return None
    return ("Schritt 4c im Vertrag des Tresors nicht gefunden "
            "(references/antworten.md): geprüft ohne die Pflicht zu 4c")


def _angabeartig(text):
    """Nennt ein Text eine X-Kennung oder einen Dokumentpfad?"""
    return bool(X_KENNUNG_RE.search(text) or DOKUMENT_RE.search(text))


def _ohne_hervorhebung(text):
    """Text ohne Hervorhebung an Wortgrenzen (*, `, _ um ein Wort) und ohne
    unsichtbare Zeichen. Anders als FORMEL_STOERER bleibt ein Unterstrich im
    Wort stehen, damit Dateinamen und Zustandsnamen bleiben, wie sie sind."""
    return HERVORHEBUNG_RE.sub("", str(text))


def _maske(text):
    """Der Text mit jedem Zitat durch Platzhalter gleicher Länge ersetzt: Ein
    Fragezeichen im Zitat („nur lexikalisch nah an „Welche …?“") macht keinen
    Satz zur Rückfrage, und die Stellen bleiben dieselben."""
    return ZITAT_RE.sub(lambda fund: "Z" * len(fund.group(0)), text)


# Woran ein Vorsatz vor einer Rückfrage als Aussage zu erkennen ist: Er
# nennt einen Lesestatus, einen Zustand, einen Grund oder einen Treffer wie
# eine Angabe zu Schritt 4c. „Falls du X-0001 nutzen willst, soll ich es
# binden?" fragt als Ganzes; „X-0001 ist nicht gebunden, soll ich es
# binden?" sagt zuerst etwas aus.
AUSSAGE_RE = re.compile(
    r"(?i)\b(?:nicht\s+gebunden|ungebunden|nicht\s+erreichbar|offline|"
    r"skillsafe_offline|nicht\s+gelesen|ungelesen|gelesen|nicht\s+abgerufen|"
    r"abgerufen|nicht\s+nachgeschlagen|nachgeschlagen|negativbefund|"
    r"nicht\s+verf(?:ü|ue)gbar|satzposition|sentence_index|lexikalisch|"
    r"zeiger|treffer|nicht\s+(?:ein|an)gebunden|keine\s+bindung|"
    r"nicht\s+lesbar|nicht\s+abgefragt|(?:ü|ue)bersprungen|"
    r"nicht\s+ge(?:ö|oe)ffnet|nicht\s+geladen|gefunden|ergebnis(?:se)?|"
    r"satz\s*\d+|" + "|".join(EXTERN_ZUSTAENDE) + r")\b")
# Wie eine Rückfrage über _fragt hinaus beginnt: mit einer Bedingung oder
# einem Zweck („Falls du …, soll ich …?", „Damit …") oder mit einem Verb vor
# der Anrede („Bindest du …?"). Ein begründender Vorsatz („Da …, ist …")
# fragt nicht.
FRAGE_SUBJUNKTIONEN = frozenset(
    "falls wenn sofern soweit ob damit sobald bevor".split())
ANREDE_NACH_VERB = frozenset("du ich wir ihr sie man es".split())
KEIN_VERB_VORN = frozenset("""
jetzt nicht erst zuerst sonst selbst fast bereits seit meist zumindest
wenigstens trotzdem zuletzt
""".split())
# Eine Nachfrage, die auf das Gesagte davor zurückweist („…, passt das?",
# „…, einverstanden?").
NACHFRAGE_RE = re.compile(
    r"(?i)^\s*(?:(?:passt|geht|reicht|hilft|ist|wäre|waere|klingt|stimmt|"
    r"genügt|genuegt)(?:\s+[\w']+){0,3}|einverstanden|okay|ok|"
    r"in\s+ordnung|richtig|oder|ja|nicht\s+wahr|recht\s+so|gut\s+so)\s*$")
# Verben, mit denen ein Teilsatz etwas aussagt („X-0001 regelt …").
AUSSAGE_VERBEN = frozenset("""
ist sind war waren wurde wurden wird hat hatte hatten habe konnte konnten
liegt liegen steht stehen fehlt fehlen gibt gab enthält enthaelt regelt nennt
behandelt beschreibt liefert lieferte lieferten ergab ergibt bleibt blieb kam
kamen betrifft beträgt betraegt gilt
""".split())
TEILGRENZE_RE = re.compile(r"[;:]|\s[—–-]\s|[—–]|,")


def _fragt(teil):
    """Beginnt ein Teil eines Satzes wie eine Frage? Mit einem Verb oder
    „oder" („soll ich …", „oder lieber …"), oder mit einem Fragewort, dem ein
    Verb folgt oder das ohne Komma bis zum Fragezeichen reicht („Welche
    Quelle soll ich binden?"). „Wie gewünscht, habe ich …" beginnt keine
    Frage."""
    woerter = [wort.casefold() for wort in WORT_IM_SATZ_RE.findall(teil)]
    if not woerter:
        return False
    if woerter[0] in FRAGE_VERBEN:
        return True
    return woerter[0] in FRAGEWORT_ANFANG and (
        "," not in teil or (len(woerter) > 1 and woerter[1] in FRAGE_VERBEN))


def _beginnt_frage(teil):
    """Beginnt ein Teil wie eine Frage: wie _fragt, mit einer Bedingung oder
    einem Zweck („Falls du …") oder mit einem Verb vor der Anrede
    („Bindest du …")?"""
    woerter = [wort.casefold() for wort in WORT_IM_SATZ_RE.findall(teil)]
    if not woerter:
        return False
    if _fragt(teil) or woerter[0] in FRAGE_SUBJUNKTIONEN:
        return True
    return (len(woerter) > 1 and woerter[1] in ANREDE_NACH_VERB
            and woerter[0].endswith(("st", "t", "en"))
            and woerter[0] not in KEIN_VERB_VORN)


def _fragt_teil(teil):
    """Setzt ein Teilsatz eine Rückfrage fort? Er beginnt wie eine Frage und
    nennt keinen Lesestatus, Zustand oder Treffer („ist sie nicht gelesen
    worden" sagt aus)."""
    return _beginnt_frage(teil) and not AUSSAGE_RE.search(teil)


def _sagt_aus(teil):
    """Sagt ein Teilsatz etwas aus: Lesestatus, Zustand, Treffer, ein
    Dokument oder ein Verb einer Aussage?"""
    return bool(AUSSAGE_RE.search(teil) or DOKUMENT_RE.search(teil)
                or any(wort.casefold() in AUSSAGE_VERBEN
                       for wort in WORT_IM_SATZ_RE.findall(teil)))


def _nachfrage(teil):
    """Weist ein Teilsatz nur auf das Gesagte zurück („passt das?")?"""
    teil = FRAGE_RE.sub("", teil.rstrip())
    return bool(NACHFRAGE_RE.match(teil)) and not _angabeartig(teil)


def _ohne_rueckfragen(satz):
    """Ein Satz ohne die Rückfrage darin, und ob eine Frage abgetrennt wurde.

    Fort fällt jede Klammer mit Fragezeichen; sie macht den Satz nicht zur
    Frage. Endet der Satz danach mit einem Fragezeichen, zerfällt er an
    Semikolon, Doppelpunkt, Gedankenstrich (auch „ - ") und Komma in Teile,
    und die Rückfrage wächst vom letzten Teil rückwärts. Ein Segment
    zwischen starken Grenzen, das wie eine Frage beginnt (_beginnt_frage),
    gehört ganz dazu („Soll ich X-0001, das Beispielhandbuch, binden?",
    „Falls du X-0001 nutzen willst, soll ich es binden?", „Bindest du
    X-0001, oder soll ich?"). Sonst gehört jeder Teil davor dazu, der so
    beginnt und keinen Lesestatus, Zustand oder Treffer nennt („…, Zustand
    unreachable, soll ich X-0001 binden lassen, damit …?"), und vor einer
    Nachfrage wie „passt das?" ein Teil, der nichts aussagt („X-0001 binden,
    passt das?"). Was davor steht, bleibt Aussage, auch ohne festes
    Vokabular („X-0001 ist hier nicht eingebunden, soll ich …?", „Da der
    Schalter gesetzt ist, ist X-0002 nicht abgerufen worden, soll ich …?",
    „X-0001 regelt das in a.md, soll ich zitieren?"). Erreicht die
    Rückfrage den Anfang eines Segments, setzt sie sich ins Segment davor
    fort, wenn dessen letzter Teil wie eine Frage beginnt („Soll ich X-0001
    binden lassen – oder antworte ich ohne?"). Zitate zählen dabei nicht.
    Zurück kommen der Rest und ob eine Frage abgetrennt wurde; ein leerer
    Rest heißt: Der ganze Satz war eine Rückfrage."""
    maske = _maske(satz)
    while True:
        klammer = RUECKFRAGE_KLAMMER_RE.search(maske)
        if not klammer:
            break
        anfang, ende = klammer.span()
        satz, maske = satz[:anfang] + satz[ende:], maske[:anfang] + maske[ende:]
    if not FRAGE_RE.search(FORMEL_STOERER.sub("", maske).rstrip()):
        return satz, False
    # Teile als (Anfang der Grenze davor, Anfang, Ende, Grenze davor stark).
    teile, grenze, anfang, stark = [], 0, 0, True
    for fund in TEILGRENZE_RE.finditer(maske):
        teile.append((grenze, anfang, fund.start(), stark))
        grenze, anfang, stark = fund.start(), fund.end(), fund.group() != ","
    teile.append((grenze, anfang, len(maske), stark))

    def text(nummer):
        return maske[teile[nummer][1]:teile[nummer][2]]

    erster = ende = len(teile) - 1
    zuletzt = True
    while True:
        beginn = ende
        while not teile[beginn][3]:
            beginn -= 1
        segment = maske[teile[beginn][1]:teile[ende][2]]
        if (_beginnt_frage(segment) if zuletzt else _fragt_teil(segment)):
            erster = beginn
        else:
            if not zuletzt and not _fragt_teil(text(ende)):
                break
            nummer = ende
            while nummer > beginn and (
                    _fragt_teil(text(nummer - 1))
                    or (_nachfrage(text(nummer))
                        and not _sagt_aus(text(nummer - 1)))):
                nummer -= 1
            erster = nummer
            if nummer > beginn:
                break
        if beginn == 0:
            break
        ende, zuletzt = beginn - 1, False
    return satz[:teile[erster][0]].rstrip(), True


def _etikett_4c(text):
    """Das Etikett, mit dem ein Text Schritt 4c ausweist („Extern (nicht im
    Bestand):" oder „Extern nicht gelesen:"), oder None."""
    return EXTERN_TREFFER_RE.match(text) or EXTERN_UNGELESEN_RE.match(text)


def _etikett_nackt(satz):
    """Ist ein Satz ein Etikett ohne Text dahinter (oder eine andere
    Envelope-Zeile ohne Text)?"""
    etikett = _etikett_4c(satz)
    if etikett:
        return not satz[etikett.end():].strip(" :—–-")
    andere = ETIKETT_RE.match(satz)
    return bool(andere) and not satz[andere.end():].strip()


def _zeilenrumpf(zeile):
    """Eine Zeile ohne Überschrifts- und Listenzeichen davor."""
    return LISTENPUNKT_RE.sub("", re.sub(r"^\s*#{1,6}\s*", "", zeile)).strip()


def _letzter_satz(zeile):
    """Der letzte Satz einer Zeile, ohne Listen-, Überschrifts- und
    Hervorhebungszeichen: Ihn setzt eine umbrochene Folgezeile fort."""
    rumpf = _zeilenrumpf(zeile)
    return FORMEL_STOERER.sub("", SATZGRENZE_RE.split(rumpf)[-1]).strip()


def _logische_zeilen(text):
    """Die Zeilen eines Texts, umbrochene Sätze wieder in einer Zeile.

    Eine Zeile, die mit einem Kleinbuchstaben beginnt und weder Listenpunkt
    noch Überschrift noch Etikett ist, setzt den offenen Satz der Zeile davor
    fort („Soll ich X-0001 auf diesem Host" / „binden lassen?"), auch eine
    Etikettzeile mit Text: Erst zusammen ist eine Rückfrage als solche zu
    erkennen und abzutrennen. Eine Zeile mit großem Anfang, mit Code oder
    Hervorhebung am Anfang bleibt eine eigene Zeile, denn eine Hüllzeile
    endet im Vertrag ohne Punkt, und was danach groß beginnt, ist ein neuer
    Satz. Nichts setzt eine Überschrift fort oder ein Etikett ohne Text
    („**Extern (nicht im Bestand)**"): Die Zeile darunter ist seine Angabe.
    Einen Listenpunkt setzt nur eine eingerückte Zeile fort; ohne Einrückung
    ist sie ein Nachsatz zu der Liste, wie in _extern_angaben."""
    zeilen = []
    for zeile in text.splitlines():
        kern = FORMEL_STOERER.sub("", zeile).strip()
        vorher = zeilen[-1] if zeilen else ""
        # Eine Zeile mit kleinem Anfang ist nie Listenpunkt oder Überschrift.
        if (zeile.strip()[:1].islower() and vorher.strip()
                and not (LISTENPUNKT_RE.match(vorher) and not zeile[:1].isspace())
                and not re.match(r"\s*#", vorher)
                and not (_etikett_4c(kern) or ETIKETT_RE.match(kern))
                and not _etikett_nackt(_letzter_satz(vorher))
                and not SATZENDE_RE.search(vorher)):
            zeilen[-1] = vorher.rstrip() + " " + zeile.strip()
        else:
            zeilen.append(zeile)
    return zeilen


def _extern_angaben(antwort):
    """Die Angaben, mit denen eine Antwort Schritt 4c ausweist.

    Ein Etikett „Extern (nicht im Bestand):" oder „Extern nicht gelesen:"
    zählt am Anfang einer Zeile und am Anfang eines Satzes, wie die Beispiele
    im Vertrag es schreiben; als Überschrift oder Hervorhebung auch ohne
    Doppelpunkt. Steht Text hinter dem Etikett oder nennt sein Klammerzusatz
    eine Kennung oder einen Pfad, ist das eine Angabe; was in derselben
    Zeile folgt oder die Zeile fortsetzt, gehört dazu. Unter einem Etikett
    ist jeder Listenpunkt, der eine Kennung oder einen Pfad nennt, eine
    eigene Angabe, auch in einer Liste mit Leerzeilen; ein Punkt ohne beides
    erläutert die Angabe davor. Steht hinter dem Etikett schon Text (etwa
    die Kennung der Quelle), gilt er für jeden Punkt darunter mit und ist
    keine eigene Angabe, auch über eine Leerzeile. Ein Nachsatz ohne
    Listenzeichen und ohne Einrückung nach einer Liste gilt für die Punkte
    mit den Kennungen, die er nennt, und ohne Kennung für jeden Punkt.
    Unter einem nackten Etikett zählt auch ein Absatz nach einer Leerzeile.
    Eine Rückfrage ist keine Angabe: weder ein Fragesatz, auch über einen
    Zeilenumbruch (``_logische_zeilen``) oder direkt hinter dem Etikett,
    noch ein Listenpunkt, der als Ganzes fragt, noch eine Frage in Klammern
    oder als letzter Teilsatz (``_ohne_rueckfragen``). Eine Fragezeile für sich beendet den Block;
    eine Liste danach gehört zur Frage. Ein anderes Etikett beendet ihn
    ebenso, und eine Leerzeile vor anderem Text. Zitatzeichen, Listen- und
    Überschriftszeichen davor ändern nichts; die Hervorhebung zählt nur beim
    Erkennen des Etiketts, der Text der Angabe bleibt, wie er ist (ein
    Dateiname behält seine Unterstriche). Zurück kommen zwei Listen von
    Texten: die Angaben zu Treffern und die zu Ungelesenem."""
    text = _ohne_zitatzeichen(_striche(antwort))
    treffer, ungelesen = [], []
    ziel = angabe = kopf = kandidat = None
    block = []
    wartet = leer = liste_im_block = False

    def zuruecksetzen():
        nonlocal ziel, angabe, kopf, kandidat, block, wartet, liste_im_block
        ziel = angabe = kopf = kandidat = None
        block = []
        wartet = liste_im_block = False

    def neue_angabe(teile):
        nonlocal angabe, wartet
        angabe = teile
        ziel.append(angabe)
        block.append(angabe)
        wartet = False

    for zeile in _logische_zeilen(text):
        listenpunkt = bool(LISTENPUNKT_RE.match(zeile))
        eingerueckt = zeile[:1].isspace()
        rumpf = _zeilenrumpf(zeile)
        if not rumpf:
            leer = ziel is not None
            continue
        if leer and not (wartet or (listenpunkt
                                    and (liste_im_block or kandidat is not None))):
            zuruecksetzen()
        leer = False
        nachsatz = False
        for nummer, satz in enumerate(SATZGRENZE_RE.split(rumpf)):
            kern = FORMEL_STOERER.sub("", satz).strip()
            etikett = _etikett_4c(kern)
            if etikett:
                ziel = treffer if etikett.re is EXTERN_TREFFER_RE else ungelesen
                block, kopf, liste_im_block = [], None, False
                zusatz = _ohne_rueckfragen(etikett.group("zusatz") or "")[0]
                # Eine Rückfrage hinter dem Etikett ist keine Angabe.
                ohne = _ohne_rueckfragen(satz)[0]
                kern_ohne = FORMEL_STOERER.sub("", ohne).strip()
                rest = _etikett_4c(kern_ohne)
                text_danach = (kern_ohne[rest.end():].strip(" :—–-")
                               if rest else "")
                if text_danach or _angabeartig(zusatz):
                    neue_angabe([ohne])
                    kandidat = angabe
                    # Nur der Zusatz nennt die Quelle: Ein Absatz oder eine
                    # Liste darunter gehört noch dazu, auch nach Leerzeile.
                    wartet = not text_danach
                else:
                    angabe = kandidat = None
                    wartet = True
                continue
            if ziel is None:
                continue
            if ETIKETT_RE.match(kern):
                zuruecksetzen()
                continue
            erster = nummer == 0
            satz, abgetrennt = _ohne_rueckfragen(satz)
            kern = FORMEL_STOERER.sub("", satz).strip()
            # Vor einer abgetrennten Rückfrage zählt der Rest nur, wenn er
            # eine Kennung oder einen Pfad nennt, nicht nur in einem Befehl
            # („X-0001: nicht gebunden — soll ich …?" ja, „`vault.py extern
            # bind X-0001 …` — soll ich …?" nein).
            if not kern or (abgetrennt
                            and not _angabeartig(BEFEHL_RE.sub(" ", satz))):
                if (erster and not listenpunkt and block
                        and not (eingerueckt and liste_im_block)):
                    # Eine Fragezeile für sich, nachdem der Block schon eine
                    # Angabe hat: Eine Liste danach gehört zur Frage, nicht
                    # zum Etikett. Direkt unter einem nackten Etikett leitet
                    # sie nur ein.
                    zuruecksetzen()
                continue
            if listenpunkt and erster:
                if _angabeartig(kern) or angabe is None:
                    # Der erste Punkt unter einer Etikettzeile mit Text oder
                    # unter einer Einleitung ohne Kennung und Pfad: Diese
                    # Zeile wird zum Kopf jedes Punkts.
                    if (not liste_im_block and block and ziel
                            and ziel[-1] is block[-1]
                            and (block[-1] is kandidat
                                 or not _angabeartig(" ".join(block[-1])))):
                        kopf = ziel.pop()
                        block.remove(kopf)
                    neue_angabe(list(kopf or []) + [satz])
                    liste_im_block = True
                else:
                    angabe.append(satz)
                kandidat = None
                continue
            if erster and liste_im_block and not listenpunkt and not eingerueckt:
                nachsatz = True
            if nachsatz:
                # Ein Nachsatz gilt für die Punkte, deren Kennung er nennt.
                # Nennt er keine, oder nennen die Punkte selbst keine („Alle
                # drei aus X-0001"), gilt er für jeden Punkt der Liste.
                genannt = _kennungen(satz)
                if genannt and any(_kennungen(" ".join(teile))
                                   for teile in block):
                    passend = [teile for teile in block
                               if genannt & _kennungen(" ".join(teile))]
                else:
                    passend = list(block)
                if passend:
                    for teile in passend:
                        teile.append(satz)
                else:
                    ziel.append([satz])
            elif angabe is None:
                neue_angabe([satz])
            else:
                angabe.append(satz)
    return ([" ".join(teile) for teile in treffer],
            [" ".join(teile) for teile in ungelesen])


def _kennungen(text):
    return {kennung.upper() for kennung in X_KENNUNG_RE.findall(text)}


def _wortlaut(text):
    """Text für den Abgleich einer Formel: ohne Hervorhebung, in einer Zeile,
    kleingeschrieben."""
    return " ".join(FORMEL_STOERER.sub("", text).split()).casefold()


def _dokument_spannen(text, dokument):
    """Wo nennt ein Text das Dokument? Spannen über den ganzen Pfad.

    Erkannt wird der volle Pfad, auch mit einem Verzeichnis davor
    („beispiel-extern/handbuch/a.md", ein absoluter Pfad, „X-0001/…"),
    und der Dateiname für sich. Liegt das Dokument an der Wurzel der Quelle,
    zählt ein Verzeichnis davor nur, wenn es absolut ist oder die Kennung
    der Quelle. Ein anderes Verzeichnis statt des eigenen („archiv/a.md")
    und ein längerer Name („keine-a.md") sind keine Nennung. Text und
    Dokument werden ohne Hervorhebung verglichen, in jeder Schreibung."""
    dokument = _ohne_hervorhebung(dokument or "").strip()
    if not dokument:
        return []
    name = dokument.rsplit("/", 1)[-1]
    spannen = []

    def danach_frei(ende):
        return not re.match(r"[\w/-]", text[ende:ende + 1])

    for fund in re.finditer(re.escape(dokument), text, re.IGNORECASE):
        anfang, ende = fund.span()
        if not danach_frei(ende):
            continue
        vor = text[anfang - 1:anfang] if anfang else ""
        if not vor or not re.match(r"[\w/.-]", vor):
            spannen.append((anfang, ende))
            continue
        if vor != "/":
            continue
        if text[anfang - 2:anfang] == "./" and (
                anfang == 2 or not re.match(r"[\w/.-]", text[anfang - 3])):
            spannen.append((anfang - 2, ende))
            continue
        token = re.search(r"[^\s(\[„“\"'»«,;]*$", text[:anfang])
        praefix = token.group(0) if token else ""
        if ("/" in dokument or praefix.startswith("/")
                or re.match(r"(?i)[a-z][a-z0-9+.-]*://", praefix)
                or re.match(r"(?i)X-\d{4}[/:]", praefix)):
            spannen.append((anfang - len(praefix), ende))
    if name != dokument:
        for fund in re.finditer(re.escape(name), text, re.IGNORECASE):
            anfang, ende = fund.span()
            if not danach_frei(ende):
                continue
            if text[anfang - 2:anfang] == "./" and anfang >= 2:
                anfang -= 2
            vor = text[anfang - 1:anfang] if anfang else ""
            if (not vor or not re.match(r"[\w/.-]", vor)) and not any(
                    a <= anfang < e for a, e in spannen):
                spannen.append((anfang, ende))
    return sorted(spannen)


def _nennt_dokument(angabe, dokument):
    """Nennt die Angabe das Dokument (siehe _dokument_spannen)?"""
    return bool(_dokument_spannen(_ohne_hervorhebung(angabe), dokument))


def _ausblenden(text, anfang, ende):
    """Eine Spanne durch Leerzeichen gleicher Länge ersetzen, damit die
    Stellen dahinter bleiben, wo sie sind."""
    return text[:anfang] + " " * (ende - anfang) + text[ende:]


def _ohne_dokument(text, dokument):
    """Der Text ohne jede Nennung des Dokuments. Der Text muss schon ohne
    Hervorhebung sein; jede Nennung wird zu Leerzeichen derselben Länge."""
    for anfang, ende in _dokument_spannen(text, dokument):
        text = _ausblenden(text, anfang, ende)
    return text


def _eigener_pfad(vault, pfad):
    """Ist ein Pfad eine Datei des geprüften Tresors (knowledge/…,
    sources/EXTERN.md, references/antworten.md …)? Er kann dann kein
    erfundener Treffer einer Quelle sein."""
    rein = pfad[2:] if pfad.startswith("./") else pfad
    wurzel = Path(vault)
    if rein.casefold().startswith(wurzel.name.casefold() + "/"):
        rein = rein[len(wurzel.name) + 1:]
    if rein.casefold().startswith("knowledge/"):
        return True
    if rein.startswith("/") or ".." in rein.split("/"):
        return False
    try:
        return (wurzel / rein).is_file()
    except (OSError, ValueError):
        return False


def _kennung_zum_pfad(text, fund, angabe):
    """Die Kennung, unter der eine Angabe einen Pfad führt: eine direkt
    dahinter („a.md (X-0002)", „a.md aus X-0002"), sonst die letzte davor,
    sonst die einzige der Angabe."""
    danach = re.match(
        r"\s*[(\[]\s*(X-\d{4})(?!\d)|\s+(?:aus|laut|von|in|bei)\s+"
        r"(?:der\s+)?(?:quelle\s+)?(X-\d{4})(?!\d)",
        text[fund.end():], re.IGNORECASE)
    if danach:
        return (danach.group(1) or danach.group(2)).upper()
    davor = X_KENNUNG_RE.findall(text[:fund.start()])
    if davor:
        return davor[-1].upper()
    alle = _kennungen(angabe)
    return next(iter(alle)) if len(alle) == 1 else ""


def _zitat_ausblenden(fund):
    """Ein Zitat für die Suche nach fremden Pfaden: Ein zitierter Satz wird
    zu Leerraum gleicher Länge, ein zitierter Dokumentpfad bleibt stehen."""
    zitat = fund.group(0)
    inneres = zitat[1:-1]
    if DOKUMENT_RE.fullmatch(inneres.strip()):
        return " " + inneres + " "
    return " " * len(zitat)


def _quellbezug(text, anfang, ende):
    """Schreibt die Angabe den Pfad an dieser Stelle einer Quelle zu: eine
    Kennung direkt davor oder eine Stelle direkt dahinter?"""
    return bool(QUELLBEZUG_DAVOR_RE.search(text[:anfang])
                or QUELLBEZUG_DAHINTER_RE.match(text[ende:]))


def _satzteil(text, anfang, ende):
    """Anfang und Ende des Satzteils um eine Stelle: bis zur Grenze davor und
    danach."""
    links = [fund.end() for fund in SATZTEIL_GRENZE_RE.finditer(text, 0, anfang)]
    rechts = SATZTEIL_GRENZE_RE.search(text, ende)
    return (links[-1] if links else 0), (rechts.start() if rechts else len(text))


def _stellenartig(text, frage=""):
    """Nennt ein Text etwas, das nach einer Fundstelle aussieht? Ein
    verneintes „kein Kapitel", „keinen Abschnitt" zählt nicht, ein Paragraf
    als Thema der Suche (aus der Frage oder „für/zu § 551 BGB") ebenso
    wenig, und ein Pfad ohne Endung nur kleingeschrieben und nicht als
    Ordner (hinter „Ordner" oder mit Schrägstrich am Ende)."""
    if STELLENARTIG_RE.search(text):
        return True
    thema = {nummer for nummer in PARAGRAF_RE.findall(frage)}
    if any(not THEMA_DAVOR_RE.search(text[:fund.start()])
           and fund.group(1) not in thema
           for fund in PARAGRAF_RE.finditer(text)):
        return True
    for fund in SCHRAEG_PFAD_RE.finditer(text):
        pfad = fund.group(1)
        # Mindestens zwei Glieder hat jeder Treffer; ein Schrägstrich am
        # Ende nennt einen Ordner („unter beispiel-extern/handbuch/").
        glieder = [glied for glied in pfad.split("/") if glied]
        if (all(len(glied) >= 3 for glied in glieder)
                and not pfad.startswith("knowledge/")
                and not pfad.endswith("/")
                and not ORDNER_DAVOR_RE.search(text[:fund.start()])):
            return True
    if any(not VERNEINUNG_DAVOR_RE.search(text[:fund.start()])
           for fund in KAPITEL_RE.finditer(text)):
        return True
    for fund in KAPITEL_THEMA_RE.finditer(text):
        links, rechts = _satzteil(text, fund.start(), fund.end())
        if not (VERNEINUNG_NAH_DAVOR_RE.search(text[links:fund.start()])
                or NICHT_DANACH_RE.search(text[fund.end():rechts])):
            return True
    return False


def _leermeldung(text, frage=""):
    """Meldet eine Angabe ausdrücklich keinen Treffer, und sagt sie sonst
    nichts über den Inhalt einer Quelle? Kennungen, Zustände, Lesestatus und
    die Wörter der Frage (wie die Anfragebegriffe im Grund der Engine)
    zählen nicht; mehr als zwei andere Inhaltswörter schon."""
    rein = X_KENNUNG_RE.sub(" ", text)
    rein = re.sub(r"(?i)\b(?:" + "|".join(EXTERN_ZUSTAENDE)
                  + r"|external_candidates_found)\b", " ", rein)
    if NUR_VERNEINUNG_RE.fullmatch(rein):
        return True
    if not KEIN_TREFFER_RE.search(rein):
        return False
    uebrig = KEIN_TREFFER_RE.sub(" ", rein)
    aus_frage = set(_woerter(frage))
    woerter = [wort.strip("./-") for wort in re.findall(r"\w[\w./-]*", uebrig)]
    woerter = [wort for nummer, wort in enumerate(woerter)
               if not (wort.casefold() in ZAHLWOERTER
                       and nummer + 1 < len(woerter)
                       and woerter[nummer + 1].casefold() in ZAEHLWOERTER)]
    inhalt = [wort for wort in woerter
              if not wort.isdigit()
              and wort.casefold() not in NEUTRALE_WOERTER
              and not (set(_woerter(wort)) and set(_woerter(wort)) <= aus_frage)
              and not wort.casefold().startswith("knowledge/")]
    return len(inhalt) <= 2


def _auszug(angabe):
    """Eine Angabe kurz für eine Meldung, ohne ihr Etikett; ein Unterstrich
    im Wort bleibt stehen."""
    text = re.sub(r"(?i)^\W*" + ETIKETT_TREFFER + r"\W*", "",
                  " ".join(_ohne_hervorhebung(angabe).split()))
    return text if len(text) <= 90 else text[:87] + "…"


def _extern_offline(vault, frage):
    """query --extern mit gesetztem Offline-Schalter: Die Nachprüfung ruft
    nichts ab und schreibt nichts in log.md."""
    return lauf(vault, "query", "--extern", frage,
                umgebung={OFFLINE_SCHALTER: "1"})


def bindung_pruefen(vault, lauf_extern, fragen):
    """Bindung des Laufs gegen den Prüfhost halten (Protokoll: stand.extern).

    Welche Quellen ein Lauf lesen konnte, hängt an der host-lokalen Bindung
    in .vault-extern.json, die außerhalb des Manifests liegt. Weicht sie ab,
    hieße jede Abweichung im Urteil über Schritt 4c „Verstoß des Agenten";
    deshalb bricht das Werkzeug dann ab wie bei einem falschen Manifest.
    Gefragt wird mit den Fragen des Protokolls, bis eine die aufgeführten
    Quellen durchgeht: Kein festes Suchwort kann in einem fremden Bestand
    mehrdeutig sein, und eine Frage ohne suchbaren Begriff (invalid_query)
    sagt über die Bindung nichts. Endet jede Frage extern in invalid_query,
    liest keine etwas, ganz gleich, was gebunden ist: Dann hängt kein Urteil
    an der Bindung, und die Probe entfällt. „Keine Quelle gebunden" folgt
    nie aus einer leeren Liste, nur aus einem Register ohne Quelle
    (not_declared)."""
    if "gebunden" not in lauf_extern:
        return
    probe = None
    for frage in dict.fromkeys(fragen):
        antwort = _extern_offline(vault, frage)
        if (antwort.get("state") in ("candidates_found", "no_candidates")
                and (antwort.get("external") or {}).get("state")
                != "invalid_query"):
            probe = antwort
            break
    if probe is None:
        return
    gebunden = sorted(str(quelle.get("id")).upper()
                      for quelle in (probe.get("external") or {}).get("sources", [])
                      if quelle.get("mode") == "lokal")
    soll = sorted(str(kennung).upper() for kennung in lauf_extern["gebunden"])
    if gebunden != soll:
        raise ProtokollFehler(
            f"Der Lauf hatte {', '.join(soll) or 'keine Quelle'} gebunden, "
            f"dieser Host bindet {', '.join(gebunden) or 'keine'}. Schritt 4c "
            f"lässt sich nur mit derselben Bindung nachrechnen "
            f"('vault.py extern bind').")


def _pruefe_extern(vault, frage, antwort, aufgefuehrt, offline, bindung_bekannt,
                   vorgabe=None):
    """Schritt 4c nachrechnen: Was hätte die Antwort ausweisen müssen?

    Das Werkzeug fragt die externen Quellen selbst ab, aber nie übers Netz:
    Es setzt den Offline-Schalter, damit die Nachprüfung weder abruft noch in
    log.md schreibt. Was eine Netzquelle geliefert hätte, weiß es deshalb nur,
    wenn auch der Lauf offline war (``offline``); sonst bleibt die Netzquelle
    ungeprüft und das ein Hinweis. ``aufgefuehrt`` sind die Kennungen aller
    aufgeführten Quellen, ``vorgabe`` der Wortlaut einer Vorgabe gegen das
    Nachschlagen aus dem Protokoll. Zurück kommen Verstöße, Hinweise und ob
    die Antwort einen Verzicht ausweist, den das Werkzeug als solchen
    nimmt."""
    verstoesse, hinweise = [], []
    extern = _extern_offline(vault, frage).get("external") or {}
    zustand = extern.get("state")
    quellen = {str(quelle["id"]).upper(): quelle
               for quelle in extern.get("sources", []) if quelle.get("id")}
    aufgefuehrt = set(aufgefuehrt) | set(quellen)
    if zustand in ("external_candidates_found", "no_external_candidates"):
        rest = (extern.get("reason") or "").split("Nicht gelesen:", 1)
        ungelesen = _kennungen(rest[1]) if len(rest) > 1 else set()
    else:
        # Jeder andere Zustand liest nichts (antworten.md, 4c), auch
        # invalid_query; nach einem Abbruch fehlen in sources die Quellen
        # danach, aufgeführt sind sie trotzdem.
        ungelesen = set(aufgefuehrt)
    netz = {kennung for kennung, quelle in quellen.items()
            if quelle.get("mode") == "netz"}
    ungeprueft = set() if offline else (ungelesen & netz)
    if ungeprueft:
        hinweise.append(
            f"Netzquelle nicht nachgeprüft ({', '.join(sorted(ungeprueft))}): "
            f"Ohne Offline-Angabe zum Lauf ist offen, was er dort gelesen hat")
    pflicht_ungelesen = ungelesen - ungeprueft
    treffer = [stelle for stelle in extern.get("hits", [])
               if stelle.get("source_id")]

    treffer_bloecke, ungelesen_bloecke = _extern_angaben(antwort)
    treffer_text = " ".join(treffer_bloecke)
    ungelesen_text = " ".join(ungelesen_bloecke)
    genannt = _kennungen(ungelesen_text)
    verzichtszeilen = [block for block in ungelesen_bloecke
                       if "nicht nachgeschlagen" in _wortlaut(block)]
    # Der ausgewiesene Verzicht: Der Schritt unterblieb auf Wunsch des
    # Nutzers oder nach einer Vorgabe der Umgebung, und die Angaben nennen
    # jede aufgeführte Quelle. Ohne Vorgabe im Protokoll gilt als Verzicht,
    # was zusammen jede Kennung „nicht nachgeschlagen" nennt, auch auf
    # mehrere Zeilen verteilt; sonst ist „nicht nachgeschlagen" der Wortlaut
    # einer Zeile nach dem Aufruf, und es gilt der normale Weg.
    verzicht = bool(not treffer_bloecke and verzichtszeilen and (
        vorgabe or aufgefuehrt <= set().union(
            *(_kennungen(block) for block in verzichtszeilen))))
    if verzicht:
        if not vorgabe:
            verstoesse.append(
                "Verzicht auf Schritt 4c ohne Vorgabe: Das Protokoll hält "
                "weder einen Wunsch des Nutzers noch eine Vorgabe der Umgebung "
                "fest (\"vorgabe\"), und nur dann entfällt der Schritt")
        fehlend = sorted(aufgefuehrt - genannt)
        if fehlend:
            verstoesse.append(
                f"Zeile „Extern nicht gelesen:\" weist aus, dass Schritt 4c "
                f"unterblieb, nennt aber nicht jede aufgeführte Quelle: "
                f"{', '.join(fehlend)} fehlt")
        return verstoesse, hinweise, True
    if vorgabe:
        hinweise.append(
            "Das Protokoll nennt eine Vorgabe gegen das Nachschlagen, die "
            "Antwort weist aber keinen Verzicht aus")
    if not treffer_bloecke and not ungelesen_bloecke:
        if treffer or pflicht_ungelesen:
            verstoesse.append(
                "Schritt 4c fehlt: Nach der Vollsichtung bleibt die Frage "
                "ungedeckt, und externe Quellen sind aufgeführt; die Antwort "
                "hat weder eine Zeile „Extern (nicht im Bestand):\" noch "
                "„Extern nicht gelesen:\"")
        return verstoesse, hinweise, False
    # Je Treffer eine Angabe mit Quelle und Dokument (antworten.md, 4c).
    fehlende_treffer = []
    for stelle in treffer:
        dokument = str(stelle.get("document") or "")
        if not any(str(stelle["source_id"]).upper() in _kennungen(block)
                   and _nennt_dokument(block, dokument)
                   for block in treffer_bloecke):
            fehlende_treffer.append(f"{stelle['source_id']} {dokument}".strip())
    if fehlende_treffer:
        verstoesse.append(
            f"Treffer ohne Zeile „Extern (nicht im Bestand):\": "
            f"{'; '.join(sorted(set(fehlende_treffer)))}. Je Treffer nennt die "
            f"Antwort Quelle und Dokument")
    # Umgekehrt: Was eine Angabe „Extern (nicht im Bestand):" als Treffer
    # nennt, liefert die Abfrage. Jeder Dokumentpfad darin ist ein
    # geliefertes Dokument einer genannten Quelle (nennt sie keine, einer der
    # aufgeführten); ausgenommen sind Zitate und Dateien des geprüften
    # Tresors (knowledge/…; andere nur, solange die Angabe sie keiner Quelle
    # zuschreibt). Nennt sie kein geliefertes Dokument, ist sie erfunden,
    # außer sie ist eine reine Leermeldung (_leermeldung: „keine Treffer",
    # „kein Zeiger", sonst kein Inhalt) und nennt nichts, was nach einer
    # Fundstelle aussieht (_stellenartig). Sicher sagen lässt sich das nur
    # bei bekannter Bindung (lokale Quelle) und bei einem Lauf ohne Netz
    # (Netzquelle); sonst bleibt es ein Hinweis.
    erfunden, offen = [], []
    for angabe in treffer_bloecke:
        bezug = (_kennungen(angabe) & aufgefuehrt) or set(aufgefuehrt)
        hier = [stelle for stelle in treffer
                if str(stelle["source_id"]).upper() in bezug]
        # Nur das Etikett fällt weg; ein Klammerzusatz dahinter kann das
        # Dokument nennen („Extern (nicht im Bestand) (X-0001, README.md):").
        ohne = re.sub(r"(?i)^\W*" + ETIKETT_TREFFER + r"\s*:?", "",
                      _ohne_hervorhebung(angabe))
        # Genannt ist ein geliefertes Dokument auch in Anführungszeichen.
        # Ein Zitat, das nur einen Dokumentpfad enthält, ist eine Nennung wie
        # ohne Anführungszeichen: geliefert oder fremd. Nach fremden Pfaden in
        # zitierten Sätzen wird nicht gesucht.
        nennt = any(_nennt_dokument(ohne, stelle.get("document"))
                    for stelle in hier)
        rest = ZITAT_RE.sub(_zitat_ausblenden, ohne)
        for stelle in hier:
            rest = _ohne_dokument(rest, stelle.get("document"))
        # Dateien des geprüften Tresors (knowledge/…, sources/EXTERN.md …)
        # sind kein Treffer, solange die Angabe sie keiner Quelle zuschreibt.
        for fund in list(DOKUMENT_RE.finditer(rest)):
            if (_eigener_pfad(vault, fund.group(1))
                    and (fund.group(1).casefold().startswith("knowledge/")
                         or not _quellbezug(rest, fund.start(1), fund.end(1)))):
                rest = _ausblenden(rest, fund.start(1), fund.end(1))
        fremd = []
        for fund in list(DOKUMENT_RE.finditer(rest)) + list(
                FREMDE_STELLE_RE.finditer(rest)):
            pfad = re.sub(r"^\./", "", fund.group(1))
            eintrag = f"{_kennung_zum_pfad(rest, fund, angabe)} {pfad}".strip()
            if eintrag not in fremd:
                fremd.append(eintrag)
        leer = _leermeldung(rest, frage) and not _stellenartig(rest, frage)
        if not fremd and (nennt or leer):
            continue
        pruefbar = all((offline if kennung in netz else bindung_bekannt)
                       for kennung in bezug)
        (erfunden if pruefbar else offen).append(
            ", ".join(fremd) if fremd else _auszug(angabe))
    if erfunden:
        verstoesse.append(
            f"Angabe „Extern (nicht im Bestand):\" ohne Treffer der Abfrage: "
            f"{'; '.join(erfunden)}. Sie nennt nur, was query --extern liefert, "
            f"mit Quelle und Dokument")
    if offen:
        hinweise.append(
            f"Trefferzeile nicht nachprüfbar ({'; '.join(offen)}): Bindung "
            f"oder Netzlage des Laufs stehen nicht im Protokoll")
    # Als ungelesen ausgewiesen, aber gelesen; oder ein Zustand, den die
    # Abfrage nicht meldet. Ob die Angabe das wirklich behauptet, liest das
    # Werkzeug nicht sicher heraus: ein Hinweis, kein Verstoß.
    if bindung_bekannt:
        # In einem Zustand, der nichts liest, ist jede Quelle ungelesen
        # (oben), und gelesen bleibt leer.
        gelesen = set(quellen) - ungelesen - netz
        doch_gelesen = sorted(genannt & gelesen)
        if doch_gelesen:
            hinweise.append(
                f"Als nicht gelesen ausgewiesen, aber gelesen: "
                f"{', '.join(doch_gelesen)}. Die Abfrage mit --extern hat die "
                f"Quelle gelesen ({zustand})")
        ohne = _ohne_hervorhebung(ungelesen_text)
        fremde = sorted({name for name in EXTERN_ZUSTAENDE
                         if re.search(rf"(?<![A-Za-z0-9_]){name}"
                                      rf"(?![A-Za-z0-9_])", ohne,
                                      re.IGNORECASE)}
                        - {zustand})
        if fremde:
            hinweise.append(
                f"Zustand {', '.join(fremde)} genannt, die Abfrage meldet "
                f"{zustand}")
    fehlend = pflicht_ungelesen - genannt
    # Nennt die Antwort Treffer aus einer Quelle, die hier ungelesen blieb,
    # war sie beim Lauf vermutlich anders gebunden. Ohne Angabe zur Bindung
    # im Protokoll ist das kein Verstoß des Agenten, sondern offen.
    anders_gebunden = set() if bindung_bekannt else (fehlend & _kennungen(treffer_text))
    if anders_gebunden:
        hinweise.append(
            f"Bindung weicht vermutlich ab: Die Antwort nennt Treffer aus "
            f"{', '.join(sorted(anders_gebunden))}, die Nachrechnung konnte "
            f"die Quelle nicht lesen")
    fehlend = sorted(fehlend - anders_gebunden)
    if fehlend:
        verstoesse.append(
            f"Zeile „Extern nicht gelesen:\" fehlt für {', '.join(fehlend)}: "
            f"Diese Quelle hat die Abfrage mit --extern nicht gelesen, und "
            f"nicht gelesen ist kein Negativbefund")
    return verstoesse, hinweise, False


def pruefe(vault, eintrag, bestand, mit_4c=True, offline=None,
           bindung_bekannt=False):
    """Eine Antwort gegen die Engine nachrechnen."""
    antwort = _striche(eintrag["antwort"])
    quittung = [teil.strip() for teil in eintrag["quittung"] if teil.strip()]
    abfrage = lauf(vault, "query", eintrag["frage"])
    if abfrage.get("state") not in ("candidates_found", "no_candidates"):
        # Eine Frage, die die Engine so nicht annimmt (Zeilenumbruch,
        # mehrdeutiger Begriff), kann kein Agent so gestellt haben. Ohne
        # Trefferstärke ließe sich die Pflicht nicht prüfen; also gar nicht
        # prüfen, statt nichts zu beanstanden.
        raise ProtokollFehler(
            f"Antwort {eintrag['id']}: Die Engine nimmt die Frage nicht an "
            f"({abfrage.get('state')}): {abfrage.get('errors')}"
        )
    staerke = abfrage.get("coverage", {}).get("match_strength")
    # Seit v0.16.0 meldet die Engine die Frage nach einer unbekannten
    # Kennung selbst (fallback.unknown_ids_only) und erlässt dann die
    # Vollsichtung. Hier zählt sie trotzdem als Pflicht: Erlassen ist sie nur
    # für die Antwort, die der Vertrag dafür vorsieht, und die prüft
    # _gilt_allein_der_kennung. Ältere Stände melden den Grund nicht; dort
    # leitet das Werkzeug denselben Fall aus coverage ab.
    rueckfall = abfrage.get("fallback", {})
    # Reicht die Liste der gekürzten Seiten nicht aus, ist Schritt 4b
    # ebenfalls Pflicht (antworten.md, „Gekürzte Treffer").
    gekuerzt = bool(abfrage.get("coverage", {}).get("omitted_pages_truncated"))
    pflicht = (bool(rueckfall.get("exhaustive_review_required"))
               or rueckfall.get("unknown_ids_only") is True or gekuerzt)
    kandidaten = [beleg["claim_id"] for beleg in abfrage.get("evidence", [])]
    abdeckung = abfrage.get("coverage", {})
    unbekannte_ids = list(abdeckung.get("unknown_ids") or [])
    zeile = {
        "id": eintrag["id"],
        "art": eintrag.get("art"),
        "frage": eintrag["frage"],
        "erwartet": list(eintrag["erwartet"]),
        "staerke": staerke,
        "pflicht": pflicht,
        "ranking_trifft": bool(set(eintrag["erwartet"]) & set(kandidaten)),
        "abstention": _sagt_nicht_im_bestand(antwort),
        "zitiert": _zitierte_claims(antwort, bestand["seite_von"]),
        "quittung_state": None,
        "ausgewaehlt": [],
        "vollstaendig": False,
        "abstention_erlaubt": False,
        "stapel": None,
        "unbekannte_ids": unbekannte_ids,
        "kennung_unbekannt": False,
        "extern_pflicht": False,
        "extern_verzicht": False,
        "verstoesse": [],
        "hinweise": [],
    }
    sichtung = None
    if quittung:
        if not all(QUITTUNG_RE.fullmatch(teil) for teil in quittung):
            zeile["verstoesse"].append(
                "Quittungseintrag hat nicht die Form <stapel>:<siegel>=<IDs|->")
        sichtung = lauf(vault, "sweep", eintrag["frage"],
                        *eintrag["sweep_args"], "--receipt", *quittung)
        zeile["quittung_state"] = sichtung.get("state")
        zeile["ausgewaehlt"] = list(sichtung.get("selected", []))
        zeile["stapel"] = sichtung.get("batches_total")
        zeile["vollstaendig"] = sichtung.get("state") == "sweep_complete"
        zeile["abstention_erlaubt"] = bool(
            sichtung.get("abstention", {}).get("allowed"))
        if not zeile["vollstaendig"]:
            zeile["verstoesse"].append(
                f"Quittung ist nicht gültig und vollständig "
                f"({sichtung.get('state')})")

    # Eine Kennung, nach der gefragt wurde und die es nicht gibt, ist
    # Gegenstand der Antwort und kein Beleg, solange die Antwort nur ihr
    # Fehlen feststellt: "C-9999 gibt es nicht" zitiert C-9999 nicht. Jede
    # andere Nennung führt sie als Quelle, und dann ist sie erfunden. Das
    # gilt auch für S- und B-Kennungen.
    in_frage_alle = {treffer.upper() for treffer in re.findall(
        r"(?i)(?<![A-Za-z0-9])[CSBX]-\d{4}(?!\d)", _striche(eintrag["frage"]))}
    in_frage = {kennung for kennung in in_frage_alle
                if kennung.startswith("C-")}
    nur_erwaehnt = {cid for cid in in_frage
                    if cid not in bestand["seite_von"]
                    and _erlaubt(antwort, cid, aus_frage=True)}
    # Jede S-, X- oder B-Kennung der Antwort, die es nicht gibt, ist erfunden,
    # außer die Antwort stellt nur ihr Fehlen fest (eine Kennung der Frage
    # auch in Rückfrage, Abgrenzung oder wiederholter Frage).
    genannt = {treffer.upper() for treffer in re.findall(
        r"(?i)(?<![A-Za-z0-9])[SXB]-\d{4}(?!\d)", antwort)}
    als_quelle = sorted(
        kennung for kennung in genannt
        if kennung not in bestand["kennungen"]
        and not _erlaubt(antwort, kennung,
                         aus_frage=kennung in in_frage_alle))
    if als_quelle:
        zeile["verstoesse"].append(
            f"führt eine Kennung, die es im Bestand nicht gibt, als Quelle: "
            f"{', '.join(als_quelle)}")
    # Eine Kennung, die es gibt, als fehlend hinzustellen, ist falsch. Nur
    # bestritten ist sie auch kein Zitat und kein Fund.
    vorhanden = ({cid for cid in zeile["zitiert"] if cid in bestand["seite_von"]}
                 | {kennung for kennung in genannt
                    if kennung in bestand["kennungen"]})
    bestritten = sorted(kennung for kennung in vorhanden
                        if "fehlen" in _nennungen(antwort, kennung))
    if bestritten:
        zeile["verstoesse"].append(
            f"bestreitet eine Kennung, die es im Bestand gibt: "
            f"{', '.join(bestritten)}")
        nur_bestritten = {
            kennung for kennung in bestritten
            if all(art == "fehlen" for art in _nennungen(antwort, kennung))}
        zeile["zitiert"] = [cid for cid in zeile["zitiert"]
                            if cid not in nur_bestritten]
    # Im Kennungsfall nennt die Antwort keine andere Kennung: Ein Vorschlag
    # ("Meinten Sie S-0004?") ist ein Zitat.
    andere = {kennung for kennung in genannt
              if kennung in bestand["kennungen"]
              and kennung not in in_frage_alle}
    zeile["kennung_unbekannt"] = _gilt_allein_der_kennung(
        abfrage, antwort,
        belegt=((set(zeile["zitiert"]) - nur_erwaehnt) | set(als_quelle)
                | andere | set(bestritten)),
        abstention=zeile["abstention"])

    ganzer_bestand = zeile["vollstaendig"] and bool(
        sichtung and sichtung.get("coverage", {}).get("scope_complete"))
    im_umfang = (eintrag["umfang_vorgegeben"] and zeile["vollstaendig"]
                 and not ganzer_bestand)
    zeile["im_umfang_nicht_gefunden"] = im_umfang and _sagt_im_umfang_nicht(
        antwort)
    if (pflicht and not (ganzer_bestand or im_umfang)
            and not zeile["kennung_unbekannt"]):
        grund = (f"{staerke}, Liste der gekürzten Seiten gekürzt" if gekuerzt
                 and not rueckfall.get("exhaustive_review_required")
                 else staerke)
        umfang = ("den vorgegebenen Umfang" if eintrag["umfang_vorgegeben"]
                  else "den ganzen Bestand")
        zeile["verstoesse"].append(
            f"Vollsichtung war Pflicht ({grund}), es liegt aber keine "
            f"vollständige Quittung über {umfang} vor")
    if zeile["abstention"] and not (
            zeile["vollstaendig"] and zeile["abstention_erlaubt"]):
        zeile["verstoesse"].append(
            "„Nicht im Bestand\" ohne vollständige Quittung, die eine "
            "Abstention erlaubt")
    # „in diesem Umfang nicht gefunden" ist die Abstention einer
    # eingeschränkten Sichtung und braucht deren Quittung.
    zeile["sagt_im_umfang"] = _sagt_im_umfang_nicht(antwort)
    if zeile["sagt_im_umfang"] and not zeile["vollstaendig"]:
        zeile["verstoesse"].append(
            "„in diesem Umfang nicht gefunden\" ohne vollständige Quittung "
            "über diesen Umfang")
    # Schritt 4c: Bleibt die Frage nach der Vollsichtung des ganzen Bestands
    # ganz oder teilweise ungedeckt („Nicht im Bestand"), und sind externe
    # Quellen aufgeführt, schlägt der Agent extern nach oder sagt, dass es
    # unterblieb. Nie im Kennungsfall, nie bei begrenztem Umfang.
    if (mit_4c and zeile["abstention"] and ganzer_bestand
            and not zeile["kennung_unbekannt"]
            and rueckfall.get("unknown_ids_only") is not True
            and rueckfall.get("external_lookup_available") is True):
        zeile["extern_pflicht"] = True
        if offline is None:
            offline = (os.environ.get(OFFLINE_SCHALTER, "").strip()
                       in OFFLINE_WERTE)
        aufgefuehrt = (set(rueckfall.get("external_source_ids") or ())
                       | set(bestand["extern"]))
        verstoesse, hinweise, verzicht = _pruefe_extern(
            vault, eintrag["frage"], antwort, aufgefuehrt, offline,
            bindung_bekannt, eintrag.get("vorgabe"))
        zeile["verstoesse"].extend(verstoesse)
        zeile["hinweise"].extend(hinweise)
        zeile["extern_verzicht"] = verzicht

    angaben = _sichtungsangaben(antwort)
    # Ein Satz behauptet eine Vollsichtung, wenn er so viele Claims nennt,
    # wie der Bestand hat ("alle 28 Claims"). Mit weniger beschreibt er eine
    # Teilmenge oder eine eingeschränkte Sichtung; dann wird er nur an einer
    # Quittung gemessen.
    gesamt_bestand = len(bestand["seite_von"])
    haupt = [angabe for angabe in angaben
             if angabe["art"] != "satz"
             or angabe["zahlen"][0] == angabe["zahlen"][1] == gesamt_bestand]
    zeile["sichtungszeile"] = bool(haupt)
    if haupt and not quittung:
        zeile["verstoesse"].append(
            "Angabe „Sichtung:\" ohne eingereichte Quittung: Die Antwort "
            "behauptet eine Vollsichtung, die das Protokoll nicht belegt")
    if zeile["vollstaendig"]:
        if not haupt:
            zeile["verstoesse"].append(
                "Zeile „Sichtung:\" fehlt, obwohl eine Vollsichtung lief")
        erfasst = sichtung["coverage"]
        meldungen = []
        # Jede Angabe zählt: Eine zweite, falsche stünde sonst unbemerkt
        # hinter der richtigen.
        gesichtet_echt = erfasst["claims_swept"]
        for angabe in angaben:
            ist = angabe["zahlen"]
            stimmt = ist == (gesichtet_echt, erfasst["claims_total"])
            # "alle 26 Claims der Domäne", "alle 10 Claims zu OKF": eine
            # Teilmenge dessen, was gesichtet wurde, ist keine falsche Zahl.
            if ist and angabe["art"] == "satz" and ist[0] == ist[1]:
                stimmt = stimmt or ist[0] <= gesichtet_echt
            if ist and not stimmt:
                gesichtet, gesamt = ist
                meldungen.append(
                    f"Zeile „Sichtung:\" nennt {gesichtet} von {gesamt}"
                    f"{' Claims' if angabe['claims'] else ''}, die Quittung "
                    f"belegt {erfasst['claims_swept']} von "
                    f"{erfasst['claims_total']} Claims")
            kennung = angabe["kennung"]
            if not kennung:
                continue
            if not sichtung["sweep_fingerprint"].startswith(kennung.lower()):
                meldungen.append(
                    "Zeile „Sichtung:\" nennt eine Quittungskennung, die "
                    "nicht zum Fingerabdruck dieser Quittung gehört")
            elif len(kennung) < KENNUNG_MIN:
                meldungen.append(
                    f"Zeile „Sichtung:\" nennt nur {len(kennung)} Zeichen der "
                    f"Quittungskennung; das belegt keine Quittung (üblich "
                    f"sind zwölf)")
        # Der Vertrag verlangt beides: die Zahlen und die Kennung.
        if haupt and not any(angabe["zahlen"] for angabe in haupt):
            meldungen.append(
                "Zeile „Sichtung:\" nennt nicht, wie viele Claims "
                "gesichtet wurden")
        if haupt and not any(angabe["kennung"] for angabe in haupt):
            meldungen.append(
                "Zeile „Sichtung:\" nennt keine Quittungskennung "
                "(die ersten zwölf Zeichen von sweep_fingerprint)")
        zeile["verstoesse"].extend(dict.fromkeys(meldungen))

    unbekannt = [cid for cid in zeile["zitiert"]
                 if cid not in bestand["seite_von"] and cid not in nur_erwaehnt]
    if unbekannt:
        zeile["verstoesse"].append(
            f"zitiert Claim-IDs, die es im Bestand nicht gibt: "
            f"{', '.join(unbekannt)}")
    lesbar = _lesbare_seiten(abfrage, sichtung)
    abseits = [cid for cid in zeile["zitiert"]
               if cid in bestand["seite_von"]
               and bestand["seite_von"][cid] not in lesbar]
    if abseits:
        zeile["hinweise"].append(
            f"zitiert Claims von Seiten, die weder Kandidat noch gewählt "
            f"noch Nachbarseite waren: {', '.join(abseits)}")

    gefunden_in = set(zeile["zitiert"]) | set(zeile["ausgewaehlt"])
    zeile["gefunden"] = (
        bool(set(zeile["erwartet"]) & gefunden_in)
        if zeile["erwartet"] else None)
    if zeile["erwartet"] and not zeile["gefunden"]:
        zeile["verstoesse"].append(
            f"erwarteter Claim weder zitiert noch gewählt: "
            f"{', '.join(zeile['erwartet'])}")
    if (zeile["art"] == "negativ" and not zeile["abstention"]
            and not zeile["kennung_unbekannt"]
            and not zeile["im_umfang_nicht_gefunden"]):
        if zeile["sagt_im_umfang"]:
            # Mit vorgegebenem Umfang fehlt dann die Quittung darüber; das
            # meldet schon die Prüfung der Formel.
            if not eintrag["umfang_vorgegeben"]:
                zeile["verstoesse"].append(
                    "Negativfrage nur „in diesem Umfang\" abgelehnt, ohne dass "
                    "das Protokoll einen Umfang vorgibt (umfang_vorgegeben)")
        elif eintrag["umfang_vorgegeben"]:
            zeile["verstoesse"].append(
                "Negativfrage wurde beantwortet statt als „in diesem Umfang "
                "nicht gefunden\" ausgewiesen")
        else:
            zeile["verstoesse"].append(
                "Negativfrage wurde beantwortet statt als „Nicht im "
                "Bestand\" ausgewiesen")
    return zeile


ABGELEHNT = ("korrekt abgelehnt", "Kennung unbekannt",
             "im Umfang abgelehnt")


def urteil(zeile):
    if zeile["kennung_unbekannt"]:
        return "Kennung unbekannt"
    if zeile["art"] == "negativ":
        if zeile["abstention"] and zeile["abstention_erlaubt"]:
            return "korrekt abgelehnt"
        if zeile.get("im_umfang_nicht_gefunden") and not zeile["abstention"]:
            return "im Umfang abgelehnt"
        return "abgelehnt ohne Deckung" if zeile["abstention"] else "beantwortet"
    if zeile["gefunden"]:
        return "gefunden"
    if zeile["gefunden"] is None:
        return "ohne Erwartung"
    return "übersehen" if zeile["abstention"] else "anderer Claim"


def zusammenfassung(zeilen):
    """Die Zahlen, die sich veröffentlichen lassen, als ein flaches Objekt."""
    positiv = [z for z in zeilen if z["erwartet"]]
    negativ = [z for z in zeilen if z["art"] == "negativ"]
    verfehlt = [z for z in positiv if not z["ranking_trifft"]]
    mit_quittung = [z for z in zeilen if z["quittung_state"]]
    return {
        "antworten": len(zeilen),
        "positiv": len(positiv),
        "positiv_gefunden": sum(1 for z in positiv if z["gefunden"]),
        "vom_ranking_verfehlt": len(verfehlt),
        "davon_gefunden": sum(1 for z in verfehlt if z["gefunden"]),
        "negativ": len(negativ),
        "negativ_korrekt": sum(1 for z in negativ if urteil(z) in ABGELEHNT),
        "pflicht_vollsichtung": sum(1 for z in zeilen if z["pflicht"]),
        "pflicht_extern": sum(1 for z in zeilen if z.get("extern_pflicht")),
        "verzicht_extern": sum(1 for z in zeilen if z.get("extern_verzicht")),
        "quittungen": len(mit_quittung),
        "quittungen_gueltig": sum(1 for z in mit_quittung if z["vollstaendig"]),
        "ohne_verstoss": sum(1 for z in zeilen if not z["verstoesse"]),
        "verstoesse": sum(len(z["verstoesse"]) for z in zeilen),
    }


def bericht(zeilen, bestand, ausfuehrlich):
    summe = zusammenfassung(zeilen)
    if ausfuehrlich:
        for z in zeilen:
            marke = "🔴" if z["verstoesse"] else "🟢"
            print(f"{marke} {z['id']:<8} {str(z['staerke']):<8} "
                  f"{urteil(z):<22} Quittung: {z['quittung_state'] or '-':<16} "
                  f"{z['frage'][:60]}")
            for text in z["verstoesse"]:
                print(f"      Verstoß: {text}")
            for text in z["hinweise"]:
                print(f"      Hinweis: {text}")
        print()
    print(f"Stand v{bestand['version']}, Manifest {bestand['manifest'][:12]}, "
          f"{len(bestand['seite_von'])} Claims")
    print(f"Antworten: {summe['antworten']}, davon ohne Verstoß "
          f"{summe['ohne_verstoss']}")
    if summe["positiv"]:
        print(f"  Fragen mit erwartetem Claim   {summe['positiv']:>3}, "
              f"gefunden {summe['positiv_gefunden']}")
        print(f"  davon vom Ranking verfehlt    "
              f"{summe['vom_ranking_verfehlt']:>3}, "
              f"trotzdem gefunden {summe['davon_gefunden']}")
    if summe["negativ"]:
        print(f"  Negativfragen                 {summe['negativ']:>3}, "
              f"korrekt abgelehnt {summe['negativ_korrekt']}")
    print(f"  Vollsichtung war Pflicht      {summe['pflicht_vollsichtung']:>3}")
    if summe["pflicht_extern"]:
        print(f"  Schritt 4c war Pflicht        {summe['pflicht_extern']:>3}, "
              f"davon Verzicht {summe['verzicht_extern']}")
    print(f"  Quittungen eingereicht        {summe['quittungen']:>3}, "
          f"gültig und vollständig {summe['quittungen_gueltig']}")
    stapel = Counter(z["stapel"] for z in zeilen if z["stapel"])
    if stapel:
        print("  Stapel je Quittung            " + ", ".join(
            f"{anzahl}× {zahl}" for zahl, anzahl in sorted(stapel.items())))
    return summe


def main(argv=None):
    vorher = getattr(_LAUF, "laeufe", None)
    _LAUF.laeufe = {}
    try:
        return _main(argv)
    finally:
        _LAUF.laeufe = vorher


def _main(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--vault", default=str(STANDARD_VAULT))
    parser.add_argument("--antworten", required=True,
                        help="Protokoll im Schema " + PROTOKOLL_SCHEMA)
    parser.add_argument("--kurz", action="store_true",
                        help="nur die Zusammenfassung, keine Zeile je Antwort")
    parser.add_argument("--json", action="store_true",
                        help="Zeilen und Zusammenfassung als JSON ausgeben")
    args = parser.parse_args(argv)

    vault = Path(args.vault).resolve()
    try:
        antworten, stand = lade_protokoll(args.antworten, vault)
        bestand = bestand_lesen(vault)
        gebunden = stand.get("manifest_sha256")
        if gebunden and gebunden != bestand["manifest"]:
            raise ProtokollFehler(
                f"Das Protokoll ist an den Stand {gebunden[:12]} gebunden"
                + (f" (Commit {stand['commit']})" if stand.get("commit") else "")
                + f", der Tresor steht auf {bestand['manifest'][:12]}. Siegel "
                f"gelten nur für ihren Stand: auf dem gebundenen Stand prüfen."
            )
        hinweise_lauf = []
        # Die Version im Protokoll ist eine Angabe des Erstellers. Bindet er
        # ein Manifest, muss sie dazu passen; sonst ist sie nur ein Hinweis.
        if stand.get("version") and (_version(stand["version"])
                                     != _version(bestand["version"])):
            abweichung = (f"Das Protokoll nennt den Stand v{stand['version']}, "
                          f"der Tresor steht auf v{bestand['version']}")
            if gebunden:
                raise ProtokollFehler(
                    abweichung + ". Bei gleichem Manifest ist die Angabe "
                    "stand.version falsch; bitte berichtigen.")
            hinweise_lauf.append(
                abweichung + "; ob Schritt 4c Pflicht ist, sagt der Vertrag "
                "des geprüften Tresors")
        mit_4c = vertrag_4c(vault, stand)
        hinweis_4c = None if mit_4c else vertrag_4c_hinweis(vault)
        if hinweis_4c:
            hinweise_lauf.append(hinweis_4c)
        lauf_extern = stand.get("extern") or {}
        if mit_4c:
            bindung_pruefen(vault, lauf_extern,
                            [eintrag["frage"] for eintrag in antworten])
        zeilen = [pruefe(vault, eintrag, bestand, mit_4c=mit_4c,
                         offline=lauf_extern.get("offline"),
                         bindung_bekannt="gebunden" in lauf_extern)
                  for eintrag in antworten]
    except ProtokollFehler as exc:
        print(f"🔴 antwort-check: {exc}")
        return 2

    if args.json:
        print(json.dumps(
            {"schema": PROTOKOLL_SCHEMA, "stand": {
                "version": bestand["version"],
                "manifest_sha256": bestand["manifest"]},
             "hinweise": hinweise_lauf,
             "zusammenfassung": zusammenfassung(zeilen), "zeilen": zeilen},
            ensure_ascii=False, indent=2, sort_keys=True))
        summe = zusammenfassung(zeilen)
    else:
        for text in hinweise_lauf:
            print(f"Hinweis: {text}")
        summe = bericht(zeilen, bestand, not args.kurz)
    if summe["verstoesse"]:
        if not args.json:
            print(f"🔴 antwort-check: {summe['verstoesse']} Verstöße in "
                  f"{summe['antworten'] - summe['ohne_verstoss']} Antworten.")
        return 1
    if not args.json:
        print(f"🟢 antwort-check: {summe['antworten']} Antworten, "
              f"kein Verstoß gegen den Antworten-Vertrag.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
