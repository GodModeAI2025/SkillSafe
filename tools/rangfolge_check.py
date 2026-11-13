#!/usr/bin/env python3
"""Hält fest, was das Ranking für einen festen Fragensatz ausgibt.

``recall_check.py`` misst, ob die Suche findet. Dieses Werkzeug misst nichts,
es vergleicht: Für jede Frage des Golds und eine Handvoll fester Abfragen
steht in ``tests/gold/rangfolge-demo.json``, was ``query`` zuletzt ausgab —
Zustand, Trefferstärke, Abdeckung, die Evidenz mit Punktzahl und je ein
Prüfwert über die Blöcke ``coverage``, ``concepts``, ``pages``, ``evidence``
und ``fallback``.

Wozu: Gewichte, Schwellen, die Nachrück-Regel und die Kürzungszähler lassen
sich an Dutzenden Stellen verschieben, ohne dass die Trefferquote es zeigt.
Der Schnappschuss zeigt es. Weicht die Ausgabe ab, ist das entweder ein
Versehen oder eine Entscheidung. Ein Versehen wird behoben. Eine Entscheidung
am Ranking bekommt eine neue Profilnummer, eine neue Messung und einen neuen
Schnappschuss (``--schreiben``); dasselbe gilt, wenn sich der Bestand ändert,
an dem gemessen wird.

Die Engine wird hier ausnahmsweise im Prozess geladen statt aufgerufen: ein
paar hundert Abfragen wären als Prozesse eine Minute, so sind es Sekunden.
Geladen wird ohne Bytecode, der Skill-Ordner bleibt unangetastet.

Read-only bis auf ``--schreiben``, nur Standardbibliothek. Aus der
Repository-Wurzel:

    python3 tools/rangfolge_check.py
    python3 tools/rangfolge_check.py --schreiben

Exit 0 ohne Abweichung, 1 mit Abweichung, 2 bei unbrauchbaren Eingaben:
Tresor nicht bereit, Gold oder Schnappschuss unlesbar oder falsch gebaut.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
STANDARD_VAULT = REPOSITORY / "wissenstresor"
STANDARD_GOLD = REPOSITORY / "tests" / "gold" / "recall-demo.json"
STANDARD_STAND = REPOSITORY / "tests" / "gold" / "rangfolge-demo.json"
SCHEMA = "skillsafe.rangfolge/v1"
GOLD_SCHEMA = "skillsafe.recall-gold/v1"
# Je Goldfrage mit erwartetem Claim: knapp, mittel und Standard. Bei knappem
# Limit entscheidet die Nachrück-Regel, wer bleibt.
LIMITS = (1, 3, 8)
# Negativfragen nur mit dem Standardlimit: an ihnen hängt die Trefferstärke.
LIMIT_NEGATIV = 8
# Abfragen, die das Gold nicht stellt: Begriffe, Kennungen, Grenzfälle der
# Schwellen. (Frage, Limit, Begriffswelt)
FESTE_ABFRAGEN = (
    ("Was ist OKF?", 1, None),
    ("Was ist OKF?", 8, None),
    ("Was ist OKF?", 20, None),
    ("Was ist OKF?", 8, "BW-0001"),
    ("Welche Vertrauensstufen gibt es?", 8, None),
    ("Was sind attestierte Berechnungen?", 8, None),
    ("Trust-Tier und Provenienz", 2, None),
    ("Ontologie und Wissensgraph", 2, None),
    # Nachrück-Regel: der Definitions-Claim des zweiten Begriffs rückt nach
    # (C-0002), und eine Seite behält ihren letzten gezeigten Claim (C-0290).
    ("Wissensgraph und Trust-Tier", 8, None),
    ("Wissensgraph und Provenienz", 4, None),
    ("Wissenstresor 10", 10, None),
    ("Was steht in C-0401?", 8, None),
    ("Was steht in C-9999?", 8, None),
    ("Was sagen C-0401 und C-9999?", 8, None),
    # Seit v0.16.0 entscheidet die Engine, ob eine Frage nichts als
    # unbekannte Kennungen nennt: ein einleitendes Wort ja, ein Sachwort nein.
    ("Erkläre C-9999", 8, None),
    ("Mietminderung C-9999", 8, None),
    ("B-0001", 8, None),
    ("S-0004", 8, None),
    # Seit hybrid-local/v4 nie 'strong': ein per ID genannter Begriff ohne
    # Platz in der Ausgabe, eine unbekannte Kennung mit getroffenen Ziffern,
    # eine Abkürzung, die nur als Funktionswort einer Fundstelle vorkommt.
    ("S-0004 OKF B-0004", 8, None),
    ("C-0401 B-0004", 1, None),
    ("S-0007", 8, None),
    ("Was steht in S-0007?", 8, None),
    ("IT", 8, None),
    ("Kann ich bei nassen Wänden die Miete kürzen?", 8, None),
    ("Wie hoch ist der Urlaubsanspruch in Teilzeit?", 8, None),
    ("Was macht man mit dem?", 8, None),
    # Schwellen der Trefferstärke, ohne kuratierten Begriff als Anker:
    # 2 von 4 Begriffen (50 %, weak), 3 von 5 (60 %, partial), 3 von 4
    # (75 %, partial), 3 von 3 (strong), 4 von 7 (57 %, abgerundet, weak)
    # und 2 von 3 mit einem Wortteil-Treffer (66 %, abgerundet).
    ("Kernoperationen Chunking Urlaubsanspruch Zahnarzt", 8, None),
    ("Kernoperationen Chunking Vermieter Urlaubsanspruch Zahnarzt", 8, None),
    ("Kernoperationen Chunking Vermieter Urlaubsanspruch", 8, None),
    ("Kernoperationen Chunking Vermieter", 8, None),
    ("Kernoperationen Chunking Vermieter Dateipfad Urlaubsanspruch Zahnarzt "
     "Fahrradhelm", 8, None),
    ("Kernoperationen Chunking Paragraphen", 8, None),
)
BLOECKE = ("coverage", "concepts", "pages", "evidence", "fallback")
# Aus 'fallback' zählt, was das Ranking entscheidet. Die Felder zum externen
# Nachschlagen beschreiben eine andere Baustelle und bleiben draußen.
FALLBACK_FELDER = ("exhaustive_review_required", "unknown_ids_only", "reason",
                   "page_paths", "page_paths_total", "sweep")


class RangfolgeFehler(ValueError):
    """Eingaben unbrauchbar: Tresor gesperrt, Gold oder Schnappschuss kaputt."""


def lade_engine(vault):
    """Die Engine als Modul, ohne dass im Skill-Ordner Bytecode entsteht."""
    pfad = Path(vault).resolve() / "scripts" / "vault.py"
    spec = importlib.util.spec_from_file_location("skillsafe_rangfolge_engine", pfad)
    if spec is None or spec.loader is None or not pfad.is_file():
        raise RangfolgeFehler(f"{pfad} ist keine ladbare Engine")
    modul = importlib.util.module_from_spec(spec)
    vorher = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(modul)
    finally:
        sys.dont_write_bytecode = vorher
    return modul


def _ist_frage(wert):
    return isinstance(wert, str) and bool(wert.strip())


def lade_gold(pfad):
    try:
        daten = json.loads(Path(pfad).read_text(encoding="utf-8"))
        fragen = [eintrag["frage"] for eintrag in daten["fragen"]]
        negativ = daten.get("negativ", [])
    except (OSError, UnicodeError, ValueError, KeyError, TypeError,
            AttributeError, RecursionError) as exc:
        raise RangfolgeFehler(f"{pfad} ist kein lesbares Gold: {exc}") from exc
    if daten.get("schema") != GOLD_SCHEMA or not fragen:
        raise RangfolgeFehler(
            f"{pfad} ist kein lesbares Gold: Schema {GOLD_SCHEMA!r} und "
            f"mindestens eine Frage erwartet")
    # Ein Text statt einer Liste zerfiele sonst in einzelne Zeichen, jedes
    # eine "Frage".
    if (not isinstance(daten["fragen"], list)
            or not all(_ist_frage(frage) for frage in fragen)
            or not isinstance(negativ, list)
            or not all(_ist_frage(frage) for frage in negativ)):
        raise RangfolgeFehler(
            f"{pfad} ist kein lesbares Gold: 'fragen' braucht eine Liste von "
            f"Einträgen mit 'frage' als Text, 'negativ' eine Liste von Fragen")
    return fragen, list(negativ)


def abfragen_liste(fragen, negativ):
    """Der Fragensatz des Schnappschusses, in fester Reihenfolge."""
    liste = [(frage, limit, None) for frage in fragen for limit in LIMITS]
    liste += [(frage, LIMIT_NEGATIV, None) for frage in negativ]
    liste += list(FESTE_ABFRAGEN)
    # Eine feste Abfrage darf auch im Gold stehen; gezählt wird sie einmal.
    return list(dict.fromkeys(liste))


def _pruefwert(block):
    kanonisch = json.dumps(block, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"))
    return hashlib.sha256(kanonisch.encode("utf-8")).hexdigest()[:10]


def zeile(engine, bestand, frage, limit, welt):
    """Eine Abfrage so festhalten, dass ein Unterschied lesbar bleibt."""
    ergebnis = engine.build_query_result(
        dict(bestand, query=frage), world=welt, limit=limit)
    abdeckung = ergebnis.get("coverage") or {}
    bloecke = {}
    for name in BLOECKE:
        block = ergebnis.get(name)
        if name == "fallback" and isinstance(block, dict):
            block = {feld: block.get(feld) for feld in FALLBACK_FELDER}
        bloecke[name] = _pruefwert(block)
    return {
        "frage": frage,
        "limit": limit,
        "welt": welt,
        "state": ergebnis.get("state"),
        "staerke": abdeckung.get("match_strength"),
        "abdeckung": abdeckung.get("term_coverage_percent"),
        "evidenz": [f"{beleg['claim_id']}:{beleg['score']}"
                    for beleg in ergebnis.get("evidence", [])],
        "bloecke": bloecke,
    }


def _frage_fehler(engine, frage):
    """Warum die Engine diese Frage nicht annähme, sonst None.

    Der Schnappschuss ruft build_query_result direkt; die Prüfung der Frage,
    die query vorher macht, steht deshalb hier.
    """
    if not frage.strip():
        return "sie ist leer"
    if len(frage) > engine.MAX_QUERY_LENGTH:
        return f"sie ist länger als {engine.MAX_QUERY_LENGTH} Zeichen"
    if any(ord(zeichen) < 32 or ord(zeichen) == 127 for zeichen in frage):
        return "sie enthält ein Steuerzeichen oder einen Zeilenumbruch"
    try:
        frage.encode("utf-8")
    except UnicodeEncodeError:
        return "sie enthält ein Zeichen, das sich nicht als UTF-8 schreiben lässt"
    return None


def schreibe_stand(ziel, text):
    """Den Schnappschuss ersetzen, ganz oder gar nicht.

    Erst ganz kodieren, dann in eine Datei daneben schreiben und umbenennen:
    Ein Fehler lässt den alten Schnappschuss stehen, statt ihn zu leeren.
    """
    try:
        daten = text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise RangfolgeFehler(
            f"Der Schnappschuss lässt sich nicht als UTF-8 schreiben: {exc}"
        ) from exc
    ziel = Path(ziel)
    try:
        griff, temp = tempfile.mkstemp(
            prefix=f".{ziel.name}.", suffix=".neu", dir=str(ziel.parent))
    except OSError as exc:
        raise RangfolgeFehler(f"{ziel} lässt sich nicht schreiben: {exc}") from exc
    try:
        with os.fdopen(griff, "wb") as datei:
            datei.write(daten)
        os.replace(temp, str(ziel))
    except OSError as exc:
        try:
            os.unlink(temp)
        except OSError:
            pass
        raise RangfolgeFehler(f"{ziel} lässt sich nicht schreiben: {exc}") from exc


def aufnehmen(vault, abfragen):
    """Den heutigen Stand für diese Abfragen berechnen."""
    engine = lade_engine(vault)
    for frage, _limit, _welt in abfragen:
        fehler = _frage_fehler(engine, frage)
        if fehler:
            raise RangfolgeFehler(
                f"Die Engine nimmt die Frage {frage!r} nicht an: {fehler}")
    bestand, fehler = engine._load_released_query_snapshot("Schnappschuss")
    if fehler is not None:
        raise RangfolgeFehler(
            f"Der Tresor ist nicht bereit ({fehler.get('state')}): "
            f"{fehler.get('errors')}. Erst 'vault.py doctor' grün bekommen."
        )
    return {
        "schema": SCHEMA,
        "hinweis": (
            "Erzeugt von tools/rangfolge_check.py --schreiben; nicht von Hand "
            "ändern. Hält fest, was query für jede Goldfrage und die festen "
            "Abfragen des Werkzeugs ausgibt. Eine Abweichung ist ein Versehen "
            "oder eine Entscheidung; eine Entscheidung am Ranking bekommt "
            "eine neue Profilnummer und einen neuen Schnappschuss. Liegt wie "
            "das Gold bewusst unter tests/ und nie im Skill-Ordner."
        ),
        "retrieval": engine.RETRIEVAL_PROFILE,
        "wortform": engine.WORTFORM_PROFILE,
        "claims": len(bestand["claims"]),
        "abfragen": [zeile(engine, bestand, frage, limit, welt)
                     for frage, limit, welt in abfragen],
    }


def _als_text(stand):
    """Eine Abfrage je Zeile: so bleibt ein Unterschied im Diff lesbar."""
    kopf = {name: wert for name, wert in stand.items() if name != "abfragen"}
    zeilen = json.dumps(kopf, ensure_ascii=False, indent=1)[:-2] + ',\n "abfragen": [\n'
    zeilen += ",\n".join(
        "  " + json.dumps(eintrag, ensure_ascii=False)
        for eintrag in stand["abfragen"])
    return zeilen + "\n ]\n}\n"


def lade_stand(pfad, vault):
    pfad = Path(pfad).resolve()
    vault = Path(vault).resolve()
    if pfad == vault or vault in pfad.parents:
        raise RangfolgeFehler(
            f"{pfad} liegt im Skill-Ordner. Der Schnappschuss enthält die "
            f"Goldfragen und gehört wie sie nie in den Skill."
        )
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise RangfolgeFehler(f"{pfad} ist nicht lesbar: {exc}") from exc
    if (not isinstance(daten, dict) or daten.get("schema") != SCHEMA
            or not isinstance(daten.get("abfragen"), list)):
        raise RangfolgeFehler(f"{pfad}: Schema {SCHEMA!r} erwartet")
    for feld, typ in (("retrieval", str), ("wortform", str), ("claims", int)):
        wert = daten.get(feld)
        if isinstance(wert, bool) or not isinstance(wert, typ):
            raise RangfolgeFehler(
                f"{pfad}: Kopffeld {feld!r} fehlt oder hat den falschen Typ")
    for nummer, eintrag in enumerate(daten["abfragen"], 1):
        fehler = _eintrag_fehler(eintrag)
        if fehler:
            raise RangfolgeFehler(f"{pfad}: Abfrage {nummer}: {fehler}")
    return daten


# Was zeile() schreibt, mit den Typen, die vergleiche() erwartet.
EINTRAG_FELDER = {
    "frage": (str,), "limit": (int,), "welt": (str, type(None)),
    "state": (str, type(None)), "staerke": (str, type(None)),
    "abdeckung": (int, float, type(None)), "evidenz": (list,),
    "bloecke": (dict,),
}


def _eintrag_fehler(eintrag):
    """Warum ein Eintrag des Schnappschusses unbrauchbar ist, sonst None."""
    if not isinstance(eintrag, dict):
        return "ist kein Objekt"
    for feld, typen in EINTRAG_FELDER.items():
        if feld not in eintrag:
            return f"Feld {feld!r} fehlt"
        wert = eintrag[feld]
        if isinstance(wert, bool) or not isinstance(wert, typen):
            return f"Feld {feld!r} hat den Typ {type(wert).__name__}"
    if not all(isinstance(beleg, str) for beleg in eintrag["evidenz"]):
        return "evidenz braucht Einträge als Text"
    if set(eintrag["bloecke"]) != set(BLOECKE):
        return f"bloecke braucht genau die Blöcke {', '.join(BLOECKE)}"
    if not all(isinstance(wert, str) for wert in eintrag["bloecke"].values()):
        return "bloecke braucht Prüfwerte als Text"
    return None


def vergleiche(alt, neu, erwartete_abfragen):
    """Abweichungen als lesbare Zeilen; leer heißt: nichts hat sich bewegt."""
    abweichungen = []
    for feld in ("retrieval", "wortform", "claims"):
        if alt.get(feld) != neu.get(feld):
            abweichungen.append(
                f"{feld}: festgehalten {alt.get(feld)!r}, heute {neu.get(feld)!r}")

    def schluessel(eintrag):
        return (eintrag["frage"], eintrag["limit"], eintrag["welt"])

    festgehalten = [schluessel(eintrag) for eintrag in alt["abfragen"]]
    if len(set(festgehalten)) != len(festgehalten):
        abweichungen.append("Der Schnappschuss führt eine Abfrage doppelt")
    fehlend = [abfrage for abfrage in erwartete_abfragen
               if abfrage not in set(festgehalten)]
    fremd = [abfrage for abfrage in festgehalten
             if abfrage not in set(erwartete_abfragen)]
    for frage, limit, welt in fehlend:
        abweichungen.append(
            f"fehlt im Schnappschuss: {frage!r} (Limit {limit}, Welt {welt})")
    for frage, limit, welt in fremd:
        abweichungen.append(
            f"steht im Schnappschuss, aber weder im Gold noch unter den "
            f"festen Abfragen: {frage!r} (Limit {limit}, Welt {welt})")

    heute = {schluessel(eintrag): eintrag for eintrag in neu["abfragen"]}
    for eintrag in alt["abfragen"]:
        aktuell = heute.get(schluessel(eintrag))
        if aktuell is None:
            continue
        wo = f"{eintrag['frage']!r} (Limit {eintrag['limit']}"
        wo += f", Welt {eintrag['welt']})" if eintrag["welt"] else ")"
        for feld in ("state", "staerke", "abdeckung", "evidenz"):
            if eintrag.get(feld) != aktuell[feld]:
                abweichungen.append(
                    f"{wo}: {feld} festgehalten {eintrag.get(feld)!r}, "
                    f"heute {aktuell[feld]!r}")
        alte_bloecke = eintrag.get("bloecke") or {}
        andere = [name for name in BLOECKE
                  if alte_bloecke.get(name) != aktuell["bloecke"][name]]
        if andere:
            abweichungen.append(f"{wo}: Block {', '.join(andere)} weicht ab")
    return abweichungen


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--vault", default=str(STANDARD_VAULT))
    parser.add_argument("--gold", default=str(STANDARD_GOLD))
    parser.add_argument("--stand", default=str(STANDARD_STAND),
                        help="der Schnappschuss, Schema " + SCHEMA)
    parser.add_argument("--schreiben", action="store_true",
                        help="den heutigen Stand festhalten statt vergleichen")
    args = parser.parse_args(argv)
    vault = Path(args.vault).resolve()
    stand = Path(args.stand).resolve()
    try:
        if stand == vault or vault in stand.parents:
            raise RangfolgeFehler(
                f"{stand} liegt im Skill-Ordner. Der Schnappschuss enthält "
                f"die Goldfragen und gehört wie sie nie in den Skill."
            )
        fragen, negativ = lade_gold(args.gold)
        abfragen = abfragen_liste(fragen, negativ)
        if args.schreiben:
            neu = aufnehmen(vault, abfragen)
            schreibe_stand(stand, _als_text(neu))
            print(f"🟢 rangfolge-check: {len(neu['abfragen'])} Abfragen unter "
                  f"{neu['retrieval']} festgehalten in {stand}.")
            return 0
        alt = lade_stand(stand, vault)
        neu = aufnehmen(
            vault,
            [(eintrag["frage"], eintrag["limit"], eintrag["welt"])
             for eintrag in alt["abfragen"]])
    except RangfolgeFehler as exc:
        print(f"🔴 rangfolge-check: {exc}")
        return 2

    abweichungen = vergleiche(alt, neu, abfragen)
    if abweichungen:
        print(f"🔴 rangfolge-check: {len(abweichungen)} Abweichung(en) vom "
              f"festgehaltenen Stand.")
        for eintrag in abweichungen[:40]:
            print(f"   {eintrag}")
        if len(abweichungen) > 40:
            print(f"   … und {len(abweichungen) - 40} weitere")
        if alt.get("retrieval") != neu.get("retrieval"):
            print("   Neues Profil: neu messen, dann --schreiben (BETRIEB.md).")
        elif all(eintrag.endswith(": Block fallback weicht ab")
                 for eintrag in abweichungen):
            # Rangfolge, Punktzahlen und Stärke sind gleich geblieben; nur
            # ein Feld darüber, wann die Vollsichtung Pflicht ist, oder wie
            # ihr Aufwand lautet.
            print("   Nur der Block fallback weicht ab, die Rangfolge ist "
                  "dieselbe. War das ein Versehen: beheben. War es Absicht: "
                  "keine neue Profilnummer, aber ein Release-Eintrag, dann "
                  "--schreiben (BETRIEB.md).")
        else:
            print(f"   Das Profil heißt weiter {neu['retrieval']}. War das ein "
                  f"Versehen: beheben. War es Absicht: Profilnummer heben, neu "
                  f"messen, dann --schreiben (BETRIEB.md).")
        return 1
    print(f"🟢 rangfolge-check: {len(alt['abfragen'])} Abfragen, "
          f"{neu['retrieval']} gibt aus, was festgehalten ist.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
