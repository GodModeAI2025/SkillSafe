#!/usr/bin/env python3
"""Misst, ob die Suche findet, was im Bestand steht — und ob sie es sagt, wenn nicht.

Zwei Zahlen zählen, und nur eine davon ist ein Gate:

* Trefferquote: Wie oft liefert ``query`` den Claim, der eine Frage
  beantwortet, unter den ausgegebenen Kandidaten? Das ist eine Gütezahl. Sie
  darf unter 100 % liegen, denn das Ranking erkennt nur Wörter, Wortformen und
  kuratierte Begriffe, keine Bedeutung. Daneben steht die mildere Zahl, wie
  oft wenigstens die Seite des Claims unter ``pages`` steht: der
  Antworten-Workflow liest genannte Seiten ganz.
* Stille Verfehlungen: Wie oft fehlt der Claim, OHNE dass das Ergebnis das
  zugibt? Das ist das Gate, und es steht hart auf null. Eine Verfehlung ist
  nur dann harmlos, wenn ``match_strength`` unter ``strong`` liegt: Dann
  nennt die Ausgabe die unverstandenen Begriffe, und bei ``weak`` oder
  ``none`` ist die Vollsichtung (``sweep``) Pflicht.

Dazu drei Wächter, die nichts mit Güte zu tun haben: Die Vollsichtung muss
jeden Claim genau einmal vorlegen, das Gold darf nicht im Skill liegen, und
keine Goldfrage darf im Skill-Ordner stehen. Ein Gold, das der Bestand
kennt, misst nur noch, ob er sich selbst wiederfindet. Verglichen wird Wort
für Wort in der Form, in der die Engine Wörter vergleicht: ohne Satzzeichen,
ohne Groß- und Kleinschreibung, Umlaute in Umschrift, jedes Wort auf seine
Wortform-Familie gebracht (wortform/v1). So fällt eine Goldfrage auch dann
auf, wenn sie als Alias in anderer Beugung dasteht, und eine lange Benennung,
die fast die ganze Frage deckt, ebenso: Die Engine trifft eine Benennung als
Wortfolge in der Frage. Eine freie Umschreibung erkennt kein Textvergleich.

Read-only, nur Standardbibliothek. Aus der Repository-Wurzel:

    python3 tools/recall_check.py
    python3 tools/recall_check.py --vault <tresor> --gold <gold.json>

Exit 0, wenn kein Gate verletzt ist, sonst 1.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
STANDARD_VAULT = REPOSITORY / "wissenstresor"
STANDARD_GOLD = REPOSITORY / "tests" / "gold" / "recall-demo.json"
GOLD_SCHEMA = "skillsafe.recall-gold/v1"
CLAIM_RE = re.compile(r"^C-\d{4}$")
# Größere Dateien sind Medien oder Rohquellen und werden nicht durchsucht,
# außer die Engine liest sie als Text (TEXT_ENDUNGEN, knowledge/, schema/).
LECK_MAX_BYTES = 5 * 1024 * 1024
TEXT_ENDUNGEN = {".md", ".markdown", ".json", ".yaml", ".yml", ".txt", ".csv"}
TEXT_ORDNER = {"knowledge", "schema"}
# Wortform wie wortform/v1 der Engine (_wortstamm in scripts/vault.py). Dass
# beide Fassungen dasselbe liefern, hält ein Test fest.
WORTFORM_ENDUNGEN = (("en", 3), ("em", 4), ("er", 4), ("es", 3),
                     ("e", 3), ("n", 3), ("s", 3))
WORTFORM_S_VORGAENGER = frozenset("bcdfghklmnprtvw")


class GoldFehler(ValueError):
    """Das Gold ist kaputt oder liegt am falschen Ort."""


class MessFehler(RuntimeError):
    """Der Tresor lässt sich gerade nicht messen.

    Bewusst kein SystemExit: Wer die Funktionen hier aus einem Test ruft,
    bekommt einen gewöhnlichen Fehlschlag statt eines abgebrochenen Laufs
    ohne Bericht.
    """


def lade_gold(pfad, vault):
    pfad = Path(pfad).resolve()
    vault = Path(vault).resolve()
    if pfad == vault or vault in pfad.parents:
        raise GoldFehler(
            f"{pfad} liegt im Skill-Ordner. Gold gehört nie in den Skill: "
            f"dort würde es mit ausgeliefert und vom Modell mitgelesen."
        )
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GoldFehler(f"{pfad} ist nicht lesbar: {exc}") from exc
    if not isinstance(daten, dict) or daten.get("schema") != GOLD_SCHEMA:
        raise GoldFehler(f"{pfad}: Schema {GOLD_SCHEMA!r} erwartet")
    fragen = daten.get("fragen")
    negativ = daten.get("negativ", [])
    if not isinstance(fragen, list) or not fragen:
        raise GoldFehler(f"{pfad}: 'fragen' fehlt oder ist leer")
    gesehen = set()
    for nummer, eintrag in enumerate(fragen, 1):
        if not isinstance(eintrag, dict):
            raise GoldFehler(f"{pfad}: Frage {nummer} ist kein Objekt")
        frage = eintrag.get("frage")
        erwartet = eintrag.get("erwartet")
        if not isinstance(frage, str) or not frage.strip():
            raise GoldFehler(f"{pfad}: Frage {nummer} hat keinen Text")
        if (not isinstance(erwartet, list) or not erwartet
                or not all(isinstance(c, str) and CLAIM_RE.fullmatch(c)
                           for c in erwartet)):
            raise GoldFehler(
                f"{pfad}: Frage {nummer} braucht 'erwartet' als Liste von C-nnnn"
            )
        # Verglichen wird, wie die Engine vergleicht: dieselbe Frage in
        # anderer Schreibung zählte sonst doppelt und schönte die Quote.
        if _norm(frage) in gesehen:
            raise GoldFehler(f"{pfad}: Frage {nummer} ist doppelt: {frage!r}")
        gesehen.add(_norm(frage))
    if (not isinstance(negativ, list)
            or not all(isinstance(f, str) and f.strip() for f in negativ)):
        raise GoldFehler(f"{pfad}: 'negativ' muss eine Liste von Fragen sein")
    for nummer, frage in enumerate(negativ, 1):
        if _norm(frage) in gesehen:
            raise GoldFehler(
                f"{pfad}: Negativfrage {nummer} steht doppelt im Gold oder "
                f"zugleich unter 'fragen': {frage!r}"
            )
        gesehen.add(_norm(frage))
    return fragen, negativ


def lauf(vault, *argv):
    """Die Engine so aufrufen, wie ein Agent es täte: als Prozess, über JSON."""
    # Einmal auflösen: mit einem relativen Pfad hieße das Script sonst
    # relativ zu einem Arbeitsverzeichnis, das selbst schon der Tresor ist.
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
        raise MessFehler(
            f"vault.py {' '.join(argv[:2])} lieferte kein JSON "
            f"(Exit {ergebnis.returncode}): {exc}\n"
            f"{(ergebnis.stdout + ergebnis.stderr)[-800:]}"
        ) from exc


def _norm(text):
    """Dieselbe Normalisierung wie ``_retrieval_norm`` der Engine.

    Bewusst nachgebaut und nicht importiert: Das Werkzeug ruft die Engine nur
    als Prozess. Dass beide Fassungen dasselbe liefern, hält ein Test fest.
    """
    text = unicodedata.normalize("NFKC", str(text)).casefold()
    text = (text.replace("ä", "ae").replace("ö", "oe")
            .replace("ü", "ue").replace("ß", "ss"))
    text = "".join(zeichen if zeichen.isalnum() else " " for zeichen in text)
    return re.sub(r"\s+", " ", text).strip()


def _wortform_flexion(stamm):
    for _ in range(3):
        for endung, minimum in WORTFORM_ENDUNGEN:
            if (not stamm.endswith(endung)
                    or len(stamm) - len(endung) < minimum):
                continue
            if endung == "s" and stamm[-2] not in WORTFORM_S_VORGAENGER:
                continue
            stamm = stamm[:-len(endung)]
            break
        else:
            break
    return stamm


def _wortstamm(token):
    """Der Schlüssel der Wortform-Familie eines normalisierten Tokens.

    Nachgebaut wie ``_norm``: 'Einträgen' und 'Einträge' landen beim selben
    Schlüssel, wie in der Engine.
    """
    if len(token) < 4 or any(zeichen.isdigit() for zeichen in token):
        return token
    stamm = _wortform_flexion(
        token.replace("ae", "a").replace("oe", "o").replace("ue", "u"))
    if stamm.endswith("ung") and len(stamm) - 3 >= 4:
        stamm = _wortform_flexion(stamm[:-3])
    return stamm


def _stammform(text):
    """Normalisierter Text, jedes Wort auf seine Wortform-Familie gebracht.

    Anders als im Ranking der Engine auch die Funktionswörter: Der Wächter
    soll eher zu viel melden als zu wenig.
    """
    return " ".join(_wortstamm(wort) for wort in _norm(text).split())


def _zeichenketten(wert):
    """Jede Zeichenkette eines JSON-Dokuments, Schlüssel eingeschlossen."""
    if isinstance(wert, str):
        yield wert
    elif isinstance(wert, dict):
        for schluessel, inhalt in wert.items():
            yield str(schluessel)
            yield from _zeichenketten(inhalt)
    elif isinstance(wert, list):
        for inhalt in wert:
            yield from _zeichenketten(inhalt)


def _lesbarer_text(pfad, vault=None):
    """Was an einer Datei Text ist; leer bei Binär- und Riesendateien.

    Ohne Blick auf die Endung: ``FRAGEN.MD`` oder eine Datei ohne Endung
    enthält eine Goldfrage genauso wie ``notes/fragen.md``. JSON wird
    zusätzlich geparst, sonst versteckte ``\\u00e4`` einen Umlaut.
    """
    # Was die Engine als Text liest, liest der Wächter ganz: Ein NUL-Byte in
    # einer Kommentarzeile oder viel Füllstoff versteckte sonst eine Seite.
    # Der Ordner zählt relativ zum Tresor, nicht am absoluten Pfad: Ein
    # Tresor unter ~/knowledge/ machte sonst jede Datei zur Textdatei.
    ordner = ""
    if vault is not None:
        try:
            ordner = Path(pfad).relative_to(vault).parts[0]
        except (ValueError, IndexError):
            ordner = ""
    textdatei = pfad.suffix.lower() in TEXT_ENDUNGEN or ordner in TEXT_ORDNER
    try:
        if not textdatei and pfad.stat().st_size > LECK_MAX_BYTES:
            return ""
        roh = pfad.read_bytes()
    except OSError:
        return ""
    if not textdatei and b"\x00" in roh[:8192]:
        return ""
    text = roh.decode("utf-8", errors="ignore")
    if pfad.suffix.lower() == ".json":
        try:
            text += "\n" + "\n".join(_zeichenketten(json.loads(text)))
        except ValueError:
            pass
    return text


def _benennungen(vault):
    """Vorzugsbenennungen und Aliase aus schema/begriffswelten.json."""
    try:
        daten = json.loads((Path(vault) / "schema" / "begriffswelten.json")
                           .read_text(encoding="utf-8"))
        return [str(benennung) for begriff in daten.get("concepts", [])
                for benennung in [begriff.get("preferred", ""),
                                  *begriff.get("aliases", [])]
                if str(benennung).strip()]
    except (OSError, UnicodeError, ValueError, AttributeError, TypeError):
        return []


def leck_suche(vault, fragen):
    """Goldfragen, die im Skill-Ordner stehen, Wort für Wort in Wortform.

    Zwei Richtungen: Steht die ganze Frage in einer Datei? Und steht eine
    lange Benennung in der Frage? Die Engine trifft eine Benennung, sobald
    sie als Wortfolge in der Frage steht; eine Goldfrage ohne ihr erstes Wort
    als Alias wirkt deshalb wie die ganze Frage. Als Leck zählt eine
    Benennung ab vier Wörtern, oder ab drei, wenn sie drei Viertel der Frage
    deckt; kürzere Benennungen sind Begriffe, und dass eine Frage einen
    Begriff nennt, ist kein Leck.
    """
    vault = Path(vault)
    korpus = []
    for pfad in sorted(vault.rglob("*")):
        if pfad.is_file():
            text = _stammform(_lesbarer_text(pfad, vault))
            if text:
                korpus.append((pfad, f" {text} "))
    benennungen = [_stammform(benennung) for benennung in _benennungen(vault)]
    lecks = []
    for frage in fragen:
        nadel = _stammform(frage)
        if not nadel:
            continue
        for pfad, text in korpus:
            if f" {nadel} " in text:
                lecks.append((frage, str(pfad.relative_to(vault))))
        woerter = len(nadel.split())
        for form in benennungen:
            laenge = len(form.split())
            if (laenge >= 4 or (laenge >= 3 and laenge >= 0.75 * woerter)) \
                    and f" {form} " in f" {nadel} ":
                ort = "schema/begriffswelten.json"
                if (frage, ort) not in lecks:
                    lecks.append((frage, ort))
    return lecks


def sichtung_pruefen(vault, frage):
    """Legt die Vollsichtung jeden Claim genau einmal vor?"""
    plan = lauf(vault, "sweep", frage)
    if plan.get("state") == "invalid_query":
        raise MessFehler(
            f"Die Engine nimmt eine Frage des Golds nicht an "
            f"(invalid_query): {plan.get('errors')}\nFrage: {frage[:120]!r}"
        )
    if plan.get("state") != "plan":
        raise MessFehler(
            f"sweep ist nicht bereit ({plan.get('state')}): "
            f"{plan.get('errors')}\nErst 'vault.py doctor' grün bekommen."
        )
    geliefert, seite_von = [], {}
    for eintrag in plan["batches"]:
        stapel = lauf(vault, "sweep", frage, "--batch", str(eintrag["batch"]))
        for seite in stapel["pages"]:
            for claim in seite["claims"]:
                geliefert.append(claim["claim_id"])
                seite_von[claim["claim_id"]] = seite["path"]
    return {
        "claims_total": plan["scope"]["claims_total"],
        "geliefert": geliefert,
        "seite_von": seite_von,
        "stapel": plan["batches_total"],
        "vollstaendig": plan["scope"]["complete"],
    }


def _parallel(funktion, eintraege):
    """Abfragen nebeneinander fahren; die Reihenfolge der Ergebnisse bleibt.

    Jede Abfrage ist ein eigener, nur lesender Prozess gegen denselben
    manifestierten Stand. Sie beeinflussen einander nicht, und das Ergebnis
    hängt nicht davon ab, welche zuerst fertig wird.
    """
    arbeiter = max(1, min(4, os.cpu_count() or 1))
    with ThreadPoolExecutor(max_workers=arbeiter) as pool:
        return list(pool.map(funktion, eintraege))


def messe(vault, fragen, negativ, limit=8, seite_von=None):
    """Jede Goldfrage einmal abfragen und nach ihrem Ausgang einordnen.

    ``seite_von`` ordnet jedem Claim seine Seite zu. Damit lässt sich neben
    dem strengen Claim-Treffer auch der Seitentreffer ausweisen: der
    Antworten-Workflow liest jede Seite aus ``pages`` ganz, ein Claim auf
    einer genannten Seite wird also gelesen, auch wenn er nicht selbst unter
    den Kandidaten steht.
    """
    seite_von = seite_von or {}

    def abfrage(frage):
        antwort = lauf(vault, "query", frage, "--limit", str(limit))
        if antwort["state"] in {"invalid_query", "ambiguous"}:
            # Nicht der Tresor ist kaputt, sondern die Frage unbrauchbar:
            # zu lang, mit Zeilenumbruch, oder mehrdeutig über Begriffswelten.
            raise MessFehler(
                f"Die Engine nimmt eine Frage des Golds nicht an "
                f"({antwort['state']}): {antwort.get('errors')}\n"
                f"Frage: {frage[:120]!r}"
            )
        if antwort["state"] not in {"candidates_found", "no_candidates"}:
            raise MessFehler(
                f"query ist nicht bereit ({antwort['state']}): "
                f"{antwort.get('errors')}\nErst 'vault.py doctor' grün bekommen."
            )
        return antwort

    def eine_frage(eintrag):
        antwort = abfrage(eintrag["frage"])
        coverage = antwort["coverage"]
        ids = [item["claim_id"] for item in antwort["evidence"]]
        rang = next(
            (n for n, cid in enumerate(ids, 1) if cid in eintrag["erwartet"]),
            None,
        )
        staerke = coverage["match_strength"]
        gezeigte_seiten = {seite["path"] for seite in antwort["pages"]}
        seite_gefunden = any(
            seite_von.get(claim_id) in gezeigte_seiten
            for claim_id in eintrag["erwartet"]
        )
        if rang is not None:
            ausgang = "treffer"
        elif antwort["fallback"]["exhaustive_review_required"]:
            ausgang = "pflicht"
        elif staerke == "strong":
            ausgang = "still"
        else:
            ausgang = "hinweis"
        return {
            "frage": eintrag["frage"],
            "erwartet": eintrag["erwartet"],
            "gruppe": eintrag.get("gruppe", "-"),
            "ausgang": ausgang,
            "rang": rang,
            "seite_gefunden": seite_gefunden,
            "staerke": staerke,
            "abdeckung": coverage["term_coverage_percent"],
            "ungetroffen": coverage["query_terms"]["unmatched"],
        }

    def eine_negativfrage(frage):
        antwort = abfrage(frage)
        return {
            "frage": frage,
            "staerke": antwort["coverage"]["match_strength"],
            "pflicht": antwort["fallback"]["exhaustive_review_required"],
        }

    return _parallel(eine_frage, fragen), _parallel(eine_negativfrage, negativ)


def zusammenfassung(zeilen):
    zahl = {name: 0 for name in ("treffer", "pflicht", "hinweis", "still")}
    for zeile in zeilen:
        zahl[zeile["ausgang"]] += 1
    gesamt = len(zeilen)
    zahl["gesamt"] = gesamt
    zahl["recall_prozent"] = (100 * zahl["treffer"] // gesamt) if gesamt else 0
    zahl["seite"] = sum(1 for zeile in zeilen if zeile.get("seite_gefunden"))
    zahl["seite_prozent"] = (100 * zahl["seite"] // gesamt) if gesamt else 0
    return zahl


AUSGANG_TEXT = {
    "treffer": "gefunden",
    "pflicht": "verfehlt, Vollsichtung Pflicht",
    "hinweis": "verfehlt, mit Hinweis",
    "still": "VERFEHLT, STILL",
}


def bericht(zeilen, negativ_zeilen, sichtung, lecks, limit, ausfuehrlich):
    if ausfuehrlich:
        for zeile in zeilen:
            rang = zeile["rang"] if zeile["rang"] is not None else "-"
            print(f"  {AUSGANG_TEXT[zeile['ausgang']]:<31} {zeile['staerke']:<7} "
                  f"Rang {rang!s:<2} {zeile['erwartet'][0]}  {zeile['frage']}")
        print()
    gruppen = sorted({zeile["gruppe"] for zeile in zeilen})
    for gruppe in gruppen:
        teil = [zeile for zeile in zeilen if zeile["gruppe"] == gruppe]
        zahl = zusammenfassung(teil)
        print(f"Gruppe {gruppe!r}: {zahl['gesamt']} Fragen, Limit {limit}")
        print(f"  gefunden                        {zahl['treffer']:>3}  "
              f"({zahl['recall_prozent']} %)")
        print(f"  Seite des Claims wird gelesen   {zahl['seite']:>3}  "
              f"({zahl['seite_prozent']} %)")
        print(f"  verfehlt, Vollsichtung Pflicht  {zahl['pflicht']:>3}")
        print(f"  verfehlt, mit Hinweis           {zahl['hinweis']:>3}")
        print(f"  verfehlt, still                 {zahl['still']:>3}")
    if negativ_zeilen:
        stark = sum(1 for zeile in negativ_zeilen if zeile["staerke"] == "strong")
        pflicht = sum(1 for zeile in negativ_zeilen if zeile["pflicht"])
        print(f"Negativfragen: {len(negativ_zeilen)}, davon Vollsichtung "
              f"Pflicht {pflicht}, als 'strong' eingestuft {stark}")
        # Gemessen ist hier nur das Signal. Dass auch die übrigen in der
        # Vollsichtung enden, ist eine Regel des Antworten-Vertrags und
        # lässt sich nur am Agenten messen (tools/antwort_check.py).
        print(f"  Bei {len(negativ_zeilen) - pflicht} verlangt kein Signal "
              f"die Vollsichtung; dort trägt allein die Vertragsregel: ohne "
              f"Quittung kein 'Nicht im Bestand'.")
    fehlend = sichtung["claims_total"] - len(set(sichtung["geliefert"]))
    doppelt = len(sichtung["geliefert"]) - len(set(sichtung["geliefert"]))
    print(f"Vollsichtung: {len(set(sichtung['geliefert']))} von "
          f"{sichtung['claims_total']} Claims vorgelegt (Stapel: "
          f"{sichtung['stapel']}), {doppelt} doppelt, {fehlend} fehlend")
    for frage, datei in lecks:
        print(f"Leck: {frage!r} steht in {datei}")


def gates(zeilen, sichtung, lecks, min_recall, max_hinweis):
    verletzt = []
    zahl = zusammenfassung(zeilen)
    if zahl["still"]:
        verletzt.append(
            f"{zahl['still']} stille Verfehlung(en): Claim fehlt, Ergebnis "
            f"behauptet trotzdem 'strong'"
        )
    if zahl["recall_prozent"] < min_recall:
        verletzt.append(
            f"Trefferquote {zahl['recall_prozent']} % liegt unter der "
            f"Untergrenze {min_recall} %"
        )
    if max_hinweis is not None and zahl["hinweis"] > max_hinweis:
        verletzt.append(
            f"{zahl['hinweis']} Verfehlungen nur mit Hinweis, erlaubt sind "
            f"{max_hinweis}"
        )
    erwartet = {cid for zeile in zeilen for cid in zeile["erwartet"]}
    nicht_vorgelegt = sorted(erwartet - set(sichtung["geliefert"]))
    if nicht_vorgelegt:
        verletzt.append(
            f"Die Vollsichtung legt {', '.join(nicht_vorgelegt)} nicht vor — "
            f"oder das Gold nennt Claims, die es im Bestand nicht gibt"
        )
    if (len(set(sichtung["geliefert"])) != sichtung["claims_total"]
            or len(sichtung["geliefert"]) != len(set(sichtung["geliefert"]))):
        verletzt.append("Die Vollsichtung legt nicht jeden Claim genau einmal vor")
    if lecks:
        verletzt.append(
            f"{len(lecks)} Goldfrage(n) stehen im Skill-Ordner"
        )
    return verletzt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--vault", default=str(STANDARD_VAULT))
    parser.add_argument("--gold", default=str(STANDARD_GOLD))
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--min-recall", type=int, default=0,
                        help="Untergrenze der Trefferquote in Prozent")
    parser.add_argument("--max-hinweis", type=int, default=None,
                        help="höchstens so viele Verfehlungen nur mit Hinweis")
    parser.add_argument("--kurz", action="store_true",
                        help="nur die Zusammenfassung ausgeben")
    args = parser.parse_args(argv)
    vault = Path(args.vault).resolve()
    try:
        fragen, negativ = lade_gold(args.gold, vault)
        sichtung = sichtung_pruefen(vault, fragen[0]["frage"])
        zeilen, negativ_zeilen = messe(
            vault, fragen, negativ, args.limit, sichtung["seite_von"])
    except (GoldFehler, MessFehler) as exc:
        print(f"🔴 recall-check: {exc}")
        return 1
    lecks = leck_suche(vault, [e["frage"] for e in fragen] + list(negativ))
    bericht(zeilen, negativ_zeilen, sichtung, lecks, args.limit, not args.kurz)
    verletzt = gates(zeilen, sichtung, lecks, args.min_recall, args.max_hinweis)
    if verletzt:
        print("🔴 recall-check: Gate verletzt.")
        for eintrag in verletzt:
            print(f"   {eintrag}")
        return 1
    zahl = zusammenfassung(zeilen)
    print(f"🟢 recall-check: {zahl['gesamt']} Fragen, {zahl['recall_prozent']} % "
          f"direkt gefunden, 0 stille Verfehlungen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
