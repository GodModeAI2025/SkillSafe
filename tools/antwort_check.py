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
nennt als die Quittung, eine erfundene Claim-ID. Trägt ein Eintrag
``erwartet``, kommt die Messfrage dazu: Wurde der erwartete Claim gefunden?

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
Fund. Im Kennungsfall nennt die Antwort keine andere Kennung: Ein Vorschlag
(„Meinten Sie S-0004?") ist ein Zitat.

Gibt der Mensch einen Umfang vor, oder nennt die Frage selbst eine Domäne
oder Seite als Umfang, erfüllt die Sichtung dieses Umfangs die Pflicht, und
„in diesem Umfang nicht gefunden" ist eine korrekte Ablehnung. Das weiß nur,
wer die Messung baut: Der Eintrag trägt dann ``umfang_vorgegeben: true`` und
den Umfang in ``sweep_args``.

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
import re
import subprocess
import sys
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


class ProtokollFehler(ValueError):
    """Das Protokoll ist kaputt oder passt nicht zum Stand des Tresors."""


def lauf(vault, *argv):
    """Die Engine so aufrufen, wie ein Agent es täte: als Prozess, über JSON."""
    vault = Path(vault).resolve()
    ergebnis = subprocess.run(
        [sys.executable, "-B", str(vault / "scripts" / "vault.py"), *argv],
        cwd=str(vault),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=120,
    )
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
    for name in ("sources/REGISTER.md", "sources/EXTERN.md",
                 "schema/begriffswelten.json"):
        try:
            text = (Path(vault) / name).read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        kennungen.update(kennung.upper() for kennung in re.findall(
            r"(?i)(?<![A-Za-z0-9])[SXB]-\d{4}(?!\d)", text))
    return {
        "seite_von": seite_von,
        "kennungen": kennungen | set(seite_von),
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
    text = FORMEL_STOERER.sub("", _ohne_zitatzeichen(antwort))
    return "in diesem umfang nicht gefunden" in " ".join(text.split()).casefold()


def _sagt_nicht_im_bestand(antwort):
    """Steht die Formel da, auch umbrochen, zitiert oder hervorgehoben?"""
    text = FORMEL_STOERER.sub("", _ohne_zitatzeichen(antwort))
    return ABSTENTION in " ".join(text.split()).casefold()


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
        roh = _ohne_typklammern(muster.sub(f" {ZIEL} ", satz))
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


def pruefe(vault, eintrag, bestand):
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
    print(f"  Quittungen eingereicht        {summe['quittungen']:>3}, "
          f"gültig und vollständig {summe['quittungen_gueltig']}")
    stapel = Counter(z["stapel"] for z in zeilen if z["stapel"])
    if stapel:
        print("  Stapel je Quittung            " + ", ".join(
            f"{anzahl}× {zahl}" for zahl, anzahl in sorted(stapel.items())))
    return summe


def main(argv=None):
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
        zeilen = [pruefe(vault, eintrag, bestand) for eintrag in antworten]
    except ProtokollFehler as exc:
        print(f"🔴 antwort-check: {exc}")
        return 2

    if args.json:
        print(json.dumps(
            {"schema": PROTOKOLL_SCHEMA, "stand": {
                "version": bestand["version"],
                "manifest_sha256": bestand["manifest"]},
             "zusammenfassung": zusammenfassung(zeilen), "zeilen": zeilen},
            ensure_ascii=False, indent=2, sort_keys=True))
        summe = zusammenfassung(zeilen)
    else:
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
