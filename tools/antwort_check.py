#!/usr/bin/env python3
"""Prüft nach, ob Antworten eines Agenten dem Antworten-Vertrag gefolgt sind.

``recall_check.py`` misst das Ranking. Ob ein Modell die Vollsichtung
tatsächlich fährt, bevor es „Nicht im Bestand" sagt, misst es nicht: Das zeigt
nur ein Lauf mit einem Agenten, der nichts kennt als den Skill-Ordner. Dieses
Werkzeug wertet so einen Lauf aus, und zwar ohne dem Agenten etwas zu glauben.
Aus seinem Protokoll werden nur drei Dinge gelesen: die Frage, der Wortlaut
der Antwort und die Quittungseinträge, die er an ``sweep --receipt`` übergeben
hat. Alles andere rechnet die Engine hier neu:

* die Trefferstärke der Frage, also ob die Vollsichtung Pflicht war;
* die Quittung: gültig, vollständig, Abstention erlaubt, ausgewählte Claims,
  Fingerabdruck;
* ob jede zitierte Claim-ID existiert und zu einer Seite gehört, die der
  Vertrag zu lesen gab.

Ein Verstoß ist, was der Vertrag verbietet: „Nicht im Bestand" ohne
vollständige Quittung, eine ausgelassene Pflicht-Vollsichtung, eine ungültige
Quittung, eine Zeile „Sichtung:", die andere Zahlen oder eine andere Kennung
nennt als die Quittung, eine erfundene Claim-ID. Trägt ein Eintrag
``erwartet``, kommt die Messfrage dazu: Wurde der erwartete Claim gefunden?

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
from collections import Counter
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
STANDARD_VAULT = REPOSITORY / "wissenstresor"
PROTOKOLL_SCHEMA = "skillsafe.antwort-protokoll/v1"
CLAIM_RE = re.compile(r"(?<![A-Z0-9-])C-\d{4}(?![0-9])")
QUITTUNG_RE = re.compile(r"^\d{1,6}:[0-9a-f]{16}=(-|C-\d{4}(,C-\d{4})*)$")
SICHTUNG_RE = re.compile(r"(?m)^[ \t>*_-]*Sichtung:(.*)$")
ZAHLEN_RE = re.compile(r"(\d+)\s+von\s+(\d+)\s+Claims")
KENNUNG_RE = re.compile(r"Quittung\s+`?([0-9a-f]{8,64})")
ABSTENTION = "nicht im bestand"
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
        for feld in ("quittung", "sweep_args", "erwartet"):
            wert = eintrag.setdefault(feld, [])
            if not isinstance(wert, list) or not all(
                    isinstance(teil, str) for teil in wert):
                raise ProtokollFehler(f"{wo}: '{feld}' muss eine Textliste sein")
        if eintrag.get("art") not in (None, "positiv", "negativ"):
            raise ProtokollFehler(f"{wo}: 'art' ist positiv, negativ oder fehlt")
        if eintrag.get("art") == "negativ" and eintrag["erwartet"]:
            raise ProtokollFehler(f"{wo}: eine Negativfrage erwartet keinen Claim")
        kennung = eintrag.setdefault("id", str(nummer))
        if kennung in gesehen:
            raise ProtokollFehler(f"{wo}: Kennung {kennung!r} ist doppelt")
        gesehen.add(kennung)
    stand = daten.get("stand") or {}
    if not isinstance(stand, dict):
        raise ProtokollFehler(f"{pfad}: 'stand' muss ein Objekt sein")
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
    seite_von = {}
    for eintrag in plan["batches"]:
        stapel = lauf(vault, "sweep", frage, "--size", "200",
                      "--batch", str(eintrag["batch"]))
        for seite in stapel["pages"]:
            for claim in seite["claims"]:
                seite_von[claim["claim_id"]] = seite["path"]
    return {
        "seite_von": seite_von,
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


def pruefe(vault, eintrag, bestand):
    """Eine Antwort gegen die Engine nachrechnen."""
    antwort = eintrag["antwort"]
    quittung = [teil.strip() for teil in eintrag["quittung"] if teil.strip()]
    abfrage = lauf(vault, "query", eintrag["frage"])
    staerke = abfrage.get("coverage", {}).get("match_strength")
    pflicht = bool(abfrage.get("fallback", {}).get("exhaustive_review_required"))
    kandidaten = [beleg["claim_id"] for beleg in abfrage.get("evidence", [])]
    zeile = {
        "id": eintrag["id"],
        "art": eintrag.get("art"),
        "frage": eintrag["frage"],
        "erwartet": list(eintrag["erwartet"]),
        "staerke": staerke,
        "pflicht": pflicht,
        "ranking_trifft": bool(set(eintrag["erwartet"]) & set(kandidaten)),
        "abstention": ABSTENTION in antwort.casefold(),
        "zitiert": sorted(set(CLAIM_RE.findall(antwort))),
        "quittung_state": None,
        "ausgewaehlt": [],
        "vollstaendig": False,
        "abstention_erlaubt": False,
        "stapel": None,
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

    ganzer_bestand = zeile["vollstaendig"] and bool(
        sichtung and sichtung.get("coverage", {}).get("scope_complete"))
    if pflicht and not ganzer_bestand:
        zeile["verstoesse"].append(
            f"Vollsichtung war Pflicht ({staerke}), es liegt aber keine "
            f"vollständige Quittung über den ganzen Bestand vor")
    if zeile["abstention"] and not (
            zeile["vollstaendig"] and zeile["abstention_erlaubt"]):
        zeile["verstoesse"].append(
            "„Nicht im Bestand\" ohne vollständige Quittung, die eine "
            "Abstention erlaubt")

    angabe = SICHTUNG_RE.search(antwort)
    zeile["sichtungszeile"] = bool(angabe)
    if zeile["vollstaendig"]:
        if not angabe:
            zeile["verstoesse"].append(
                "Zeile „Sichtung:\" fehlt, obwohl eine Vollsichtung lief")
        else:
            zahlen = ZAHLEN_RE.search(angabe.group(1))
            abdeckung = sichtung["coverage"]
            if zahlen and (int(zahlen.group(1)), int(zahlen.group(2))) != (
                    abdeckung["claims_swept"], abdeckung["claims_total"]):
                zeile["verstoesse"].append(
                    f"Zeile „Sichtung:\" nennt {zahlen.group(1)} von "
                    f"{zahlen.group(2)} Claims, die Quittung belegt "
                    f"{abdeckung['claims_swept']} von "
                    f"{abdeckung['claims_total']}")
            kennung = KENNUNG_RE.search(angabe.group(1))
            if kennung and not sichtung["sweep_fingerprint"].startswith(
                    kennung.group(1)):
                zeile["verstoesse"].append(
                    "Zeile „Sichtung:\" nennt eine Quittungskennung, die "
                    "nicht zum Fingerabdruck dieser Quittung gehört")

    unbekannt = [cid for cid in zeile["zitiert"]
                 if cid not in bestand["seite_von"]]
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
    if zeile["art"] == "negativ" and not zeile["abstention"]:
        zeile["verstoesse"].append(
            "Negativfrage wurde beantwortet statt als „Nicht im Bestand\" "
            "ausgewiesen")
    return zeile


def urteil(zeile):
    if zeile["art"] == "negativ":
        if zeile["abstention"] and zeile["abstention_erlaubt"]:
            return "korrekt abgelehnt"
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
        "negativ_korrekt": sum(
            1 for z in negativ if urteil(z) == "korrekt abgelehnt"),
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
