#!/usr/bin/env python3
"""Misst, ob die Suche ehrlich bleibt, wenn der Bestand wächst.

Das Gold (tests/gold/recall-demo.json) misst gegen einen Demo-Bestand mit 28
Claims. Wie sich ``query`` in einem großen Bestand verhält, sagt es nicht:
Dort konkurrieren tausende Claims um dieselben Wörter. Dieses Werkzeug baut
Kopien des Tresors mit N Ablenkerseiten und misst das Gold darin, mit den
Zählungen von tools/recall_check.py:

* direkt gefunden: der erwartete Claim steht unter den Kandidaten;
* verfehlt, Vollsichtung Pflicht: ``weak`` oder ``none``, oder die Liste
  ausgelassener Seiten ist gekürzt;
* verfehlt, mit Hinweis: ``partial``, und die Ausgabe nennt den Grund;
* verfehlt, still: der Claim fehlt, und das Ergebnis nennt keinen Grund
  (``strong``, oder ``partial`` ohne benannten Grund).

Die Spalte ``still`` ist das Gate und steht hart auf null, bei jeder Größe
und in jeder Reihenfolge. ``Claims`` zählt den ganzen gemessenen Bestand:
die 28 Demo-Claims und die Ablenker. ``strong`` zählt die Goldfragen mit
'strong', ``o. Claim`` davon die, deren Claim fehlt: Dann behauptet das
Etikett mehr, als die Ausgabe hält, auch wenn der Vertrag den Fall über
die gekürzte Liste ausgelassener Seiten noch in die Vollsichtung schickt.

Die Ablenker kommen aus deutschem Fachtext dieses Repositorys, eingefroren
in tests/skalierung/korpus.txt (Fließtext der Doku im Stand 6d32ae3), damit
eine spätere Doku-Änderung die Messung nicht verschiebt. Zwei Arten:

* ``nah``: Markov-Text (Ordnung 2) über den Sätzen des Korpus. Wortschatz und
  Wortfolgen wie im Korpus, also dieselben Fachwörter wie die Fragen, aber
  keine zusammenhängenden Aussagen. Das sind harte Ablenker.
* ``echt``: echte Sätze des Korpus, ohne Zurücklegen. Jede Seite braucht
  vier bis sieben Sätze, bei 1.720 Sätzen reicht das für gut 300 Seiten.

Kein Ablenker enthält eine Goldfrage (Leck), eine Instruktionssignatur oder
fast den Wortlaut eines Demo-Claims. Jede Seite hat drei bis sechs Claims.
Alles ist deterministisch: gleiche Größe, Art, Saat und Reihenfolge ergeben
denselben Bestand.

Bei Punktgleichstand zeigt die Engine die kleinere Kennung zuerst. Die
Reihenfolge ``alt`` lässt die Demo-Claims bei ihren Kennungen (C-0001 bis
C-0402, Ablenker ab C-1000): Ein Gleichstand geht an das Gold, wie bei einem
Bestand, in dem das Gesuchte älter ist als das Rauschen. ``neu`` nummeriert
die Demo-Claims in der Kopie ans obere Ende (bis C-9999, das Gold wird
mitgenommen): Ein Gleichstand geht an den Ablenker. Standard ist beides; das
Gate gilt für jede Reihenfolge.

``--kurzfragen`` zählt zusätzlich, ohne Gate, wie oft eine Stichwortfrage
aus einem oder zwei Wörtern einer Goldfrage 'strong' heißt, ohne den Claim
der ganzen Frage zu zeigen, und davon, wie oft auch nichts anderes in der
Ausgabe auf ihn führt (seine Seite steht weder unter ``pages`` noch unter
``omitted_pages``, ``omitted_pages_truncated`` ist falsch). Das ist die
Grenze eines lexikalischen Rankings: Steht die Antwort in anderen Wörtern,
erkennt es sie nicht, auch im Demo-Bestand. Gerechnet wird im Prozess.

Read-only gegenüber dem Repository, nur Standardbibliothek; die Kopien liegen
in einem Temporärverzeichnis. Aus der Repository-Wurzel:

    python3 tools/skalierung_check.py
    python3 tools/skalierung_check.py --seiten 0,200,500,1000 --art nah --saat 1
    python3 tools/skalierung_check.py --seiten 500 --reihenfolge neu --kurzfragen

Exit 0, wenn bei keiner Größe still verfehlt wird, sonst 1; Exit 2, wenn
``--seiten`` keine Liste nicht negativer Zahlen ist.
"""

import argparse
import collections
import importlib.util
import itertools
import json
import random
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import unicodedata
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
STANDARD_VAULT = REPOSITORY / "wissenstresor"
STANDARD_GOLD = REPOSITORY / "tests" / "gold" / "recall-demo.json"
KORPUS = REPOSITORY / "tests" / "skalierung" / "korpus.txt"
# Woraus tests/skalierung/korpus.txt entstand (--korpus-neu schreibt sie neu).
KORPUS_DATEIEN = (
    "README.md", "BETRIEB.md", "PLAN-okf-v0.2.md", "tests/e2e/LIESMICH.md",
    "wissenstresor/KONZEPT.md", "wissenstresor/SKILL.md",
    "wissenstresor/schema/profil.md", "wissenstresor/notes/dead-ends.md",
    "wissenstresor/references/antworten.md",
    "wissenstresor/references/befuellen.md",
    "wissenstresor/references/begriffswelten.md",
    "wissenstresor/references/export-okf.md",
    "wissenstresor/references/externe-quellen.md",
    "wissenstresor/references/lint.md",
    "wissenstresor/references/mehrere-tresore.md",
    "wissenstresor/references/multimodal.md",
)
ERSTE_ID, LETZTE_ID = 1000, 9999
STANDARD_SEITEN = (0, 200, 500)
REIHENFOLGEN = ("alt", "neu")
KENNUNG_RE = re.compile(r"\bC-\d{4}\b")


def _laden(name, pfad):
    spec = importlib.util.spec_from_file_location(name, pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


RC = _laden("skalierung_recall", REPOSITORY / "tools" / "recall_check.py")


# ---- Korpus -----------------------------------------------------------------

ID_RE = re.compile(r"\b[A-Z]-\d{4}\b")
LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
URL_RE = re.compile(r"https?://\S+")
CODE_RE = re.compile(r"`[^`]*`")
SATZENDE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ„\"])")
LISTENMARKE_RE = re.compile(r"^([-*+]|\d+[.)])\s+")
VERBOTEN = set("|[]{}<>`*#_\\")


def _absaetze(text):
    """Fließtext eines Markdown-Dokuments als Absätze; Überschriften extra."""
    if text.startswith("---\n"):
        ende = text.find("\n---\n", 4)
        if ende > 0:
            text = text[ende + 5:]
    absaetze, ueberschriften, zeilen, im_code = [], [], [], False
    for zeile in text.split("\n"):
        roh = zeile.strip()
        if roh.startswith(("```", "~~~")):
            im_code = not im_code
            zeilen = []
            continue
        if im_code:
            continue
        if roh.startswith("#"):
            ueberschriften.append(roh.lstrip("#").strip())
            absaetze.append(" ".join(zeilen))
            zeilen = []
            continue
        if not roh or roh.startswith(("|", "<", ">")):
            absaetze.append(" ".join(zeilen))
            zeilen = []
            continue
        if LISTENMARKE_RE.match(roh):
            absaetze.append(" ".join(zeilen))
            zeilen = [LISTENMARKE_RE.sub("", roh)]
            continue
        zeilen.append(roh)
    absaetze.append(" ".join(zeilen))
    return [a for a in absaetze if a.strip()], ueberschriften


def _saeubern(text):
    text = LINK_RE.sub(r"\1", text)
    text = URL_RE.sub("", text)
    text = CODE_RE.sub("", text)
    text = ID_RE.sub("", text)
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return re.sub(r"\(\s*\)", "", text)


def korpus_aus_texten(texte):
    """Sätze und Überschriften aus Markdown-Texten, gesäubert, ohne Dubletten."""
    saetze, titel = [], []
    for text in texte:
        absaetze, ueberschriften = _absaetze(text)
        for absatz in absaetze:
            for satz in SATZENDE_RE.split(_saeubern(absatz)):
                satz = satz.strip()
                if (6 <= len(satz.split()) <= 35 and satz[-1:] in ".!?"
                        and not VERBOTEN & set(satz) and satz[0].isupper()):
                    saetze.append(satz)
        for ueberschrift in ueberschriften:
            ueberschrift = _saeubern(ueberschrift)
            if (1 <= len(ueberschrift.split()) <= 6
                    and not VERBOTEN & set(ueberschrift)):
                titel.append(ueberschrift)
    return list(dict.fromkeys(saetze)), list(dict.fromkeys(titel))


def korpus_lesen(pfad=KORPUS):
    saetze, titel, teil = [], [], None
    for zeile in Path(pfad).read_text(encoding="utf-8").split("\n"):
        if not zeile or zeile.startswith("#"):
            continue
        if zeile in ("[saetze]", "[titel]"):
            teil = saetze if zeile == "[saetze]" else titel
            continue
        teil.append(zeile)
    return saetze, titel


def korpus_schreiben(saetze, titel, pfad=KORPUS, stand="Arbeitsbaum"):
    kopf = (
        "# Ablenker-Korpus für tools/skalierung_check.py. Nicht von Hand ändern.\n"
        f"# Fließtext der Doku im Stand {stand} ({len(KORPUS_DATEIEN)} Dateien,\n"
        "# siehe KORPUS_DATEIEN), gesäubert wie in korpus_aus_texten().\n"
        "# Neu erzeugen: python3 tools/skalierung_check.py --korpus-neu\n")
    Path(pfad).parent.mkdir(parents=True, exist_ok=True)
    Path(pfad).write_text(
        kopf + "[saetze]\n" + "\n".join(saetze) + "\n[titel]\n"
        + "\n".join(titel) + "\n", encoding="utf-8")


# ---- Ablenker ---------------------------------------------------------------

class Filter:
    """Was ein Ablenker nicht enthalten darf: eine Goldfrage (Leck), eine
    Instruktionssignatur oder fast den Wortlaut eines Demo-Claims."""

    def __init__(self, vault, gold):
        self.engine = _laden("skalierung_vault", Path(vault) / "scripts" / "vault.py")
        daten = json.loads(Path(gold).read_text(encoding="utf-8"))
        fragen = [e["frage"] for e in daten["fragen"]] + list(daten.get("negativ", []))
        self.nadeln = [f" {RC._stammform(f)} " for f in fragen if RC._stammform(f)]
        self.claims = []
        for seite in sorted((Path(vault) / "knowledge").rglob("*.md")):
            for zeile in seite.read_text(encoding="utf-8").split("\n"):
                treffer = self.engine.CLAIM_RE.match(zeile)
                if treffer:
                    self.claims.append(set(RC._stammform(treffer.group(5)).split()))

    def erlaubt(self, text):
        if self.engine._hat_signatur(text):
            return False
        form = f" {RC._stammform(text)} "
        if any(nadel in form for nadel in self.nadeln):
            return False
        woerter = set(form.split())
        return not any(
            claim and len(woerter & claim) / len(woerter | claim) > 0.5
            for claim in self.claims)


def _markov(saetze, rng):
    uebergang = collections.defaultdict(list)
    for satz in saetze:
        kette = ["\x02", "\x02"] + satz.split() + ["\x03"]
        for i in range(len(kette) - 2):
            uebergang[(kette[i], kette[i + 1])].append(kette[i + 2])
    bekannt = set(saetze)

    def satz():
        while True:
            a, b, aus = "\x02", "\x02", []
            while len(aus) <= 32:
                c = rng.choice(uebergang[(a, b)])
                if c == "\x03":
                    break
                aus.append(c)
                a, b = b, c
            text = " ".join(aus)
            if 8 <= len(aus) <= 32 and c == "\x03" and text not in bekannt:
                return text
    return satz


def _echt(saetze, rng):
    vorrat = list(saetze)
    rng.shuffle(vorrat)

    def satz():
        if not vorrat:
            raise MessFehler("Korpus erschöpft: zu viele Seiten für 'echt'")
        return vorrat.pop()
    return satz


def _tag(wort):
    wort = unicodedata.normalize("NFKD", wort.lower().replace("ß", "ss"))
    wort = "".join(zeichen for zeichen in wort if zeichen.isascii())
    return re.sub(r"[^a-z0-9-]", "", wort)


class MessFehler(Exception):
    pass


def _umnummerieren(ziel):
    """Die Claims der Kopie ans obere Ende des Kennungsraums, in alter
    Reihenfolge. Zurück kommt die Abbildung alt → neu."""
    seiten = sorted((ziel / "knowledge").rglob("*.md"))
    alte = sorted({treffer for seite in seiten for treffer in re.findall(
        r"^- \*\*(C-\d{4})\*\*", seite.read_text(encoding="utf-8"),
        flags=re.MULTILINE)})
    abbildung = {alt: f"C-{LETZTE_ID - len(alte) + 1 + nummer:04d}"
                 for nummer, alt in enumerate(alte)}
    for pfad in seiten + [ziel / "schema" / "begriffswelten.json"]:
        text = pfad.read_text(encoding="utf-8")
        neu = KENNUNG_RE.sub(lambda m: abbildung.get(m.group(0), m.group(0)), text)
        if neu != text:
            pfad.write_text(neu, encoding="utf-8")
    return abbildung


def bauen(ziel, seiten, art, saat, quelle=STANDARD_VAULT, gold=STANDARD_GOLD,
          korpus=KORPUS, reihenfolge="alt"):
    """Kopie des Tresors mit ``seiten`` Ablenkerseiten, freigegeben.

    Zurück kommen die Zahl der Ablenker-Claims und die Abbildung der
    Demo-Kennungen (leer bei Reihenfolge ``alt``)."""
    ziel = Path(ziel)
    shutil.copytree(quelle, ziel, symlinks=True, ignore=shutil.ignore_patterns(
        "__pycache__", ".vault-extern.json", ".vault-release.lock"))
    if reihenfolge not in REIHENFOLGEN:
        raise MessFehler(f"Unbekannte Reihenfolge {reihenfolge!r}: 'alt' oder 'neu'")
    abbildung = _umnummerieren(ziel) if reihenfolge == "neu" else {}
    letzte = min(abbildung.values(), default=f"C-{LETZTE_ID + 1}")
    letzte = int(letzte[2:]) - 1
    rng = random.Random(f"{art}:{saat}")
    saetze, titel = korpus_lesen(korpus)
    filt = Filter(ziel, gold)
    if art == "nah":
        roh = _markov(saetze, rng)
    elif art == "echt":
        roh = _echt(saetze, rng)
    else:
        raise MessFehler(f"Unbekannte Art {art!r}: 'nah' oder 'echt'")

    def naechster():
        while True:
            text = roh()
            if filt.erlaubt(text):
                return text

    domaene = ziel / "knowledge" / "demo-okf"
    cid, neu, gezaehlt = ERSTE_ID, [], collections.Counter()
    for nummer in range(seiten):
        anzahl = rng.randint(3, 6)
        if cid + anzahl - 1 > letzte:
            raise MessFehler(f"Kennungsraum erschöpft nach {nummer} Seiten")
        claims = []
        for _ in range(anzahl):
            claims.append(f"- **C-{cid:04d}** [S-0001 | Abschnitt "
                          f"{rng.randint(1, 40)} | Wortlaut] {naechster()}")
            cid += 1
        while True:
            name = rng.choice(titel)
            if filt.erlaubt(name):
                break
        gezaehlt[name] += 1
        if gezaehlt[name] > 1:
            name = f"{name} ({gezaehlt[name]})"
        woerter = [wort.strip(".,;:!?()„“\"'") for claim in claims
                   for wort in claim.split("] ", 1)[1].split()]
        kandidaten = sorted({_tag(w) for w in woerter
                             if len(w) >= 7 and w[:1].isalpha()} - {""})
        tags = rng.sample(kandidaten, min(3, len(kandidaten))) if kandidaten else []
        tags = [tag for tag in tags if not filt.engine._hat_signatur(tag)] or ["ablenker"]
        datei = f"abl-{nummer:05d}.md"
        (domaene / datei).write_text(
            f"---\ntype: konzept\ntitle: {name}\ndomain: demo-okf\nstatus: aktiv\n"
            f"confidence: mittel\nversion: 1.0.0\nstand: 2026-07-04\n"
            f"sources: [S-0001]\ntags: [{', '.join(tags)}]\n---\n\n# {name}\n\n"
            f"## Kurzfassung\n{naechster()}\n\n## Claims\n" + "\n".join(claims) + "\n",
            encoding="utf-8")
        neu.append(f"- knowledge/demo-okf/{datei}")
    router = (ziel / "ROUTER.md").read_text(encoding="utf-8")
    anker = "- knowledge/demo-okf/fakten.md"
    if router.count(anker) != 1:
        raise MessFehler("ROUTER.md: Eintrag für fakten.md fehlt")
    if neu:
        router = router.replace(anker, anker + "\n" + "\n".join(neu))
    (ziel / "ROUTER.md").write_text(router, encoding="utf-8")
    ergebnis = subprocess.run(
        [sys.executable, "-B", str(ziel / "scripts" / "vault.py"), "release", "patch"],
        cwd=str(ziel), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False, timeout=1800)
    if ergebnis.returncode != 0:
        raise MessFehler(f"release scheiterte:\n{(ergebnis.stdout + ergebnis.stderr)[-1500:]}")
    return cid - ERSTE_ID, abbildung


def _seite_von(vault, engine):
    zuordnung = {}
    for seite in sorted((Path(vault) / "knowledge").rglob("*.md")):
        pfad = str(seite.relative_to(vault))
        for zeile in seite.read_text(encoding="utf-8").split("\n"):
            treffer = engine.CLAIM_RE.match(zeile)
            if treffer:
                zuordnung[treffer.group(1)] = pfad
    return zuordnung


def messen(vault, gold=STANDARD_GOLD, limit=8, abbildung=None):
    vault = Path(vault).resolve()
    fragen, negativ = RC.lade_gold(gold, vault)
    abbildung = abbildung or {}
    fragen = [dict(eintrag, erwartet=[abbildung.get(c, c) for c in eintrag["erwartet"]])
              for eintrag in fragen]
    engine = _laden("skalierung_messung", vault / "scripts" / "vault.py")
    seite_von = _seite_von(vault, engine)
    dauer = []
    echter_lauf = RC.lauf

    def gemessener_lauf(tresor, *argv):
        anfang = time.monotonic()
        try:
            return echter_lauf(tresor, *argv)
        finally:
            dauer.append(time.monotonic() - anfang)

    RC.lauf = gemessener_lauf
    try:
        zeilen, negativ_zeilen = RC.messe(vault, fragen, negativ, limit, seite_von)
    finally:
        RC.lauf = echter_lauf
    zahl = RC.zusammenfassung(zeilen)
    return {
        "claims": len(seite_von),
        "fragen": zahl["gesamt"], "treffer": zahl["treffer"],
        "seite": zahl["seite"], "pflicht": zahl["pflicht"],
        "hinweis": zahl["hinweis"], "still": zahl["still"],
        "strong": sum(1 for z in zeilen if z["staerke"] == "strong"),
        "strong_ohne_claim": sum(1 for z in zeilen
                                 if z["staerke"] == "strong" and z["rang"] is None),
        "negativ": len(negativ_zeilen),
        "negativ_strong": sum(1 for z in negativ_zeilen if z["staerke"] == "strong"),
        "negativ_pflicht": sum(1 for z in negativ_zeilen if z["pflicht"]),
        "query_median_s": round(statistics.median(dauer), 2) if dauer else 0,
        "still_fragen": [z["frage"] for z in zeilen if z["ausgang"] == "still"],
        "strong_ohne_claim_fragen": [z["frage"] for z in zeilen
                                     if z["staerke"] == "strong" and z["rang"] is None],
    }


def kurzfragen(vault, gold=STANDARD_GOLD, limit=8, abbildung=None):
    """Stichwortfragen aus einem oder zwei Inhaltswörtern jeder Goldfrage,
    im Prozess gegen den freigegebenen Stand gerechnet. Kein Gate."""
    vault = Path(vault).resolve()
    engine = _laden("skalierung_kurz", vault / "scripts" / "vault.py")
    stand, fehler = engine._load_released_query_snapshot("x")
    if fehler is not None:
        raise MessFehler(f"Kein freigegebener Stand: {fehler}")
    abbildung = abbildung or {}
    seite_von = {claim["id"]: pfad for pfad, seite in stand["pages"].items()
                 for claim in seite["claims"]}
    daten = json.loads(Path(gold).read_text(encoding="utf-8"))
    gesehen, zahl, strong_ohne, still = set(), 0, 0, 0
    for eintrag in daten["fragen"]:
        erwartet = {abbildung.get(c, c) for c in eintrag["erwartet"]}
        woerter = [wort for wort in re.findall(r"[^\W_]+(?:[-+][^\W_]+)*", eintrag["frage"])
                   if engine._inhaltstokens(wort)]
        for groesse in (1, 2):
            if groesse >= len(woerter):
                continue
            for auswahl in itertools.combinations(woerter, groesse):
                frage = " ".join(auswahl)
                if frage.casefold() in gesehen:
                    continue
                gesehen.add(frage.casefold())
                zahl += 1
                ergebnis = engine.build_query_result(dict(stand, query=frage),
                                                     world=None, limit=limit)
                if (ergebnis["state"] != "candidates_found"
                        or ergebnis["coverage"]["match_strength"] != "strong"
                        or {b["claim_id"] for b in ergebnis["evidence"]} & erwartet):
                    continue
                strong_ohne += 1
                abdeckung = ergebnis["coverage"]
                seiten = ({s["path"] for s in ergebnis["pages"]}
                          | {s["path"] for s in abdeckung["omitted_pages"]})
                if (not abdeckung["omitted_pages_truncated"]
                        and not {seite_von.get(c) for c in erwartet} & seiten):
                    still += 1
    return {"teilfragen": zahl, "strong_ohne_claim": strong_ohne, "davon_still": still}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--vault", default=str(STANDARD_VAULT))
    parser.add_argument("--gold", default=str(STANDARD_GOLD))
    parser.add_argument("--seiten", default=",".join(map(str, STANDARD_SEITEN)),
                        help="Größen als Liste, z. B. 0,200,500,1000")
    parser.add_argument("--art", choices=("nah", "echt"), default="nah")
    parser.add_argument("--saat", type=int, default=1)
    parser.add_argument("--reihenfolge", choices=("alt", "neu", "beide"), default="beide",
                        help="Kennungen der Demo-Claims: alt, ans obere Ende (neu) oder beides")
    parser.add_argument("--kurzfragen", action="store_true",
                        help="zusätzlich Stichwortfragen aus ein oder zwei Wörtern zählen (kein Gate)")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--json", help="Ergebnisse zusätzlich als JSON schreiben")
    parser.add_argument("--korpus-neu", action="store_true",
                        help="tests/skalierung/korpus.txt aus der Doku neu schreiben")
    args = parser.parse_args(argv)
    if args.korpus_neu:
        texte = [(REPOSITORY / name).read_text(encoding="utf-8") for name in KORPUS_DATEIEN]
        saetze, titel = korpus_aus_texten(texte)
        korpus_schreiben(saetze, titel)
        print(f"🟢 skalierung-check: {KORPUS.relative_to(REPOSITORY)} mit "
              f"{len(saetze)} Sätzen und {len(titel)} Überschriften geschrieben.")
        return 0
    try:
        groessen = [int(teil) for teil in args.seiten.split(",") if teil.strip()]
    except ValueError:
        groessen = []
    if not groessen or any(groesse < 0 for groesse in groessen):
        print(f"🔴 skalierung-check: --seiten {args.seiten!r} ist keine Liste "
              f"nicht negativer Zahlen")
        return 2
    reihenfolgen = REIHENFOLGEN if args.reihenfolge == "beide" else (args.reihenfolge,)
    ergebnisse = []
    print(f"Ablenker {args.art}, Saat {args.saat}, Limit {args.limit}; "
          f"Gold {Path(args.gold).name}")
    print(f"{'Reihe':>5} {'Seiten':>6} {'Claims':>6} {'direkt':>6} {'Seite':>5} "
          f"{'Pflicht':>7} {'Hinweis':>7} {'still':>5} {'strong':>6} {'o. Claim':>8} "
          f"{'neg. strong':>11} "
          f"{'Median s':>8}" + ("  Kurzfragen: strong ohne Claim / davon still"
                                if args.kurzfragen else ""))
    with tempfile.TemporaryDirectory(prefix="skillsafe-skalierung-") as temp:
        for reihenfolge in reihenfolgen:
            for groesse in groessen:
                ziel = Path(temp) / f"{args.art}-{reihenfolge}-{groesse}" / "wissenstresor"
                try:
                    claims, abbildung = bauen(ziel, groesse, args.art, args.saat,
                                              Path(args.vault), args.gold,
                                              reihenfolge=reihenfolge)
                    ergebnis = messen(ziel, args.gold, args.limit, abbildung)
                    if args.kurzfragen:
                        ergebnis["kurzfragen"] = kurzfragen(ziel, args.gold, args.limit,
                                                            abbildung)
                except (MessFehler, RC.MessFehler, RC.GoldFehler) as exc:
                    print(f"🔴 skalierung-check: {exc}")
                    return 1
                ergebnis.update({"reihenfolge": reihenfolge, "seiten": groesse,
                                 "claims_ablenker": claims})
                ergebnisse.append(ergebnis)
                kurz = ergebnis.get("kurzfragen")
                print(f"{reihenfolge:>5} {groesse:>6} {ergebnis['claims']:>6} "
                      f"{ergebnis['treffer']:>6} {ergebnis['seite']:>5} {ergebnis['pflicht']:>7} "
                      f"{ergebnis['hinweis']:>7} {ergebnis['still']:>5} {ergebnis['strong']:>6} "
                      f"{ergebnis['strong_ohne_claim']:>8} "
                      f"{ergebnis['negativ_strong']:>11} {ergebnis['query_median_s']:>8}"
                      + (f"  {kurz['teilfragen']} Teilfragen: {kurz['strong_ohne_claim']} / "
                         f"{kurz['davon_still']}" if kurz else ""), flush=True)
                shutil.rmtree(ziel.parent)
    if args.json:
        Path(args.json).write_text(json.dumps(
            {"art": args.art, "saat": args.saat, "limit": args.limit,
             "reihenfolge": args.reihenfolge, "ergebnisse": ergebnisse}, ensure_ascii=False, indent=1), encoding="utf-8")
    still = [(e["reihenfolge"], e["seiten"], frage)
             for e in ergebnisse for frage in e["still_fragen"]]
    if still:
        print("🔴 skalierung-check: stille Verfehlung(en): Claim fehlt, und das "
              "Ergebnis nennt keinen Grund.")
        for reihenfolge, groesse, frage in still:
            print(f"   {reihenfolge}, {groesse} Seiten: {frage}")
        return 1
    print(f"🟢 skalierung-check: {len(groessen)} Größe(n) in {len(reihenfolgen)} "
          f"Reihenfolge(n), 0 stille Verfehlungen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
