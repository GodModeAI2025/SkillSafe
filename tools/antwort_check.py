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

Eine einzige Antwort kommt ohne Vollsichtung aus, obwohl das Ranking nichts
verstanden hat: die auf eine Frage, die allein einer Kennung gilt, die es
nicht gibt (``coverage.unknown_ids``). Das weiß die Engine selbst. Die Antwort
muss die Kennung nennen, darf keinen Claim zitieren und nicht „Nicht im
Bestand" sagen; diese Formel bleibt der Quittung vorbehalten.

Was das Werkzeug nicht kann: Es erkennt die Formel „Nicht im Bestand", auch
über einen Zeilenumbruch oder eine Hervorhebung hinweg, aber keine Umschreibung
(„dazu schweigt der Bestand"). Bei einer als ``negativ`` gekennzeichneten
Frage fällt eine fehlende Formel auf, sonst nicht. Und es prüft, ob eine
Antwort dem Verfahren folgt, nicht ob sie inhaltlich stimmt.

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
# Eine Claim-ID im Antworttext, gleich in welcher Schreibung. Ein Bereich
# ("C-0001 bis C-0005") zitiert auch, was dazwischen liegt.
CLAIM_RE = re.compile(r"(?<![A-Za-z0-9])C-(\d{4})(?!\d)", re.IGNORECASE)
BEREICH_RE = re.compile(
    r"(?<![A-Za-z0-9])C-(\d{4})\s*(?:bis|–|—|-)\s*C-(\d{4})(?!\d)",
    re.IGNORECASE)
QUITTUNG_RE = re.compile(r"^\d{1,6}:[0-9a-f]{16}=(-|C-\d{4}(,C-\d{4})*)$")
# Die Angabe zur Sichtung: als eigene Zeile oder im Satz, auch hervorgehoben.
SICHTUNG_RE = re.compile(
    r"(?m)(?<![A-Za-zÄÖÜäöüß])Sichtung[*_`]{0,2}\s*:(.*)$")
ZAHLEN_RE = re.compile(r"(\d+)\s+von\s+(\d+)")
KENNUNG_RE = re.compile(r"Quittung\W{0,3}([0-9a-f]{4,64})\b")
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


def _sagt_nicht_im_bestand(antwort):
    """Steht die Formel da, auch umbrochen oder hervorgehoben?"""
    text = FORMEL_STOERER.sub("", antwort)
    return ABSTENTION in " ".join(text.split()).casefold()


def _zitierte_claims(text, bestand_ids):
    """Jede genannte Claim-ID, Bereiche aufgelöst, in fester Schreibung."""
    zitiert = {f"C-{ziffern}" for ziffern in CLAIM_RE.findall(text)}
    for von, bis in BEREICH_RE.findall(text):
        unten, oben = sorted((int(von), int(bis)))
        zitiert.update(
            cid for cid in bestand_ids if unten <= int(cid[2:]) <= oben)
    return sorted(zitiert)


def _gilt_allein_der_kennung(abdeckung, unbekannte_ids, antwort, belegt,
                             abstention):
    """Antwortet hier jemand nur „diese Kennung gibt es nicht"?

    Das ist der eine Fall, in dem der Vertrag die Vollsichtung erlässt
    (antworten.md, Schritt 2b). Er gilt, wenn die Ziffern der unbekannten
    Kennungen selbst ungetroffen sind, das Ranking sonst kein Wort der Frage
    unverstanden ließ und die Antwort nichts tut, wofür es eine Quittung
    bräuchte. Sind die Ziffern irgendwo getroffen, kann die Frage auch etwas
    anderes meinen als eine Kennung, und es gilt die gewöhnliche Regel.
    """
    if not unbekannte_ids or abstention or belegt:
        return False
    ziffern = {kennung.split("-", 1)[1] for kennung in unbekannte_ids}
    begriffe = abdeckung.get("query_terms") or {}
    ungetroffen = set(begriffe.get("unmatched") or [])
    offen = ungetroffen | set(begriffe.get("partial") or [])
    if not ziffern <= ungetroffen or offen - ziffern:
        return False
    gross = antwort.upper()
    return all(kennung in gross for kennung in unbekannte_ids)


def pruefe(vault, eintrag, bestand):
    """Eine Antwort gegen die Engine nachrechnen."""
    antwort = eintrag["antwort"]
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
    pflicht = bool(abfrage.get("fallback", {}).get("exhaustive_review_required"))
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

    # Eine Kennung, nach der gefragt wurde, ist Gegenstand der Antwort und
    # kein Beleg: "C-9999 gibt es nicht" zitiert C-9999 nicht.
    in_frage = set(_zitierte_claims(eintrag["frage"], ()))
    zeile["kennung_unbekannt"] = _gilt_allein_der_kennung(
        abdeckung, unbekannte_ids, antwort,
        belegt=set(zeile["zitiert"]) - in_frage,
        abstention=zeile["abstention"])

    ganzer_bestand = zeile["vollstaendig"] and bool(
        sichtung and sichtung.get("coverage", {}).get("scope_complete"))
    if pflicht and not ganzer_bestand and not zeile["kennung_unbekannt"]:
        zeile["verstoesse"].append(
            f"Vollsichtung war Pflicht ({staerke}), es liegt aber keine "
            f"vollständige Quittung über den ganzen Bestand vor")
    if zeile["abstention"] and not (
            zeile["vollstaendig"] and zeile["abstention_erlaubt"]):
        zeile["verstoesse"].append(
            "„Nicht im Bestand\" ohne vollständige Quittung, die eine "
            "Abstention erlaubt")

    angabe = SICHTUNG_RE.search(FORMEL_STOERER.sub("", antwort))
    zeile["sichtungszeile"] = bool(angabe)
    if angabe and not quittung:
        zeile["verstoesse"].append(
            "Angabe „Sichtung:\" ohne eingereichte Quittung: Die Antwort "
            "behauptet eine Vollsichtung, die das Protokoll nicht belegt")
    if zeile["vollstaendig"]:
        if not angabe:
            zeile["verstoesse"].append(
                "Zeile „Sichtung:\" fehlt, obwohl eine Vollsichtung lief")
        else:
            zahlen = ZAHLEN_RE.search(angabe.group(1))
            erfasst = sichtung["coverage"]
            if not zahlen:
                zeile["verstoesse"].append(
                    "Zeile „Sichtung:\" nennt nicht, wie viele Claims "
                    "gesichtet wurden")
            elif (int(zahlen.group(1)), int(zahlen.group(2))) != (
                    erfasst["claims_swept"], erfasst["claims_total"]):
                zeile["verstoesse"].append(
                    f"Zeile „Sichtung:\" nennt {zahlen.group(1)} von "
                    f"{zahlen.group(2)} Claims, die Quittung belegt "
                    f"{erfasst['claims_swept']} von "
                    f"{erfasst['claims_total']}")
            kennung = KENNUNG_RE.search(angabe.group(1))
            if kennung and not sichtung["sweep_fingerprint"].startswith(
                    kennung.group(1)):
                zeile["verstoesse"].append(
                    "Zeile „Sichtung:\" nennt eine Quittungskennung, die "
                    "nicht zum Fingerabdruck dieser Quittung gehört")
            elif kennung and len(kennung.group(1)) < KENNUNG_MIN:
                zeile["verstoesse"].append(
                    f"Zeile „Sichtung:\" nennt nur {len(kennung.group(1))} "
                    f"Zeichen der Quittungskennung; das belegt keine "
                    f"Quittung (üblich sind zwölf)")

    unbekannt = [cid for cid in zeile["zitiert"]
                 if cid not in bestand["seite_von"] and cid not in in_frage]
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
            and not zeile["kennung_unbekannt"]):
        zeile["verstoesse"].append(
            "Negativfrage wurde beantwortet statt als „Nicht im Bestand\" "
            "ausgewiesen")
    return zeile


ABGELEHNT = ("korrekt abgelehnt", "Kennung unbekannt")


def urteil(zeile):
    if zeile["kennung_unbekannt"]:
        return "Kennung unbekannt"
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
