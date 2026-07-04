#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""vault.py — deterministische Engine des Wissenstresors (Profil: oksv-lite/1.0).

Arbeitsteilung: Dieses Script erledigt ALLES, was deterministisch geht
(Prüfen, Indizieren, Graph ableiten, Suchen, Hashen, Loggen, Zählen).
Das Sprachmodell kuratiert und urteilt nur — es rechnet nie Prüfsummen,
verifiziert nie Links "im Kopf" und baut nie Indizes von Hand.

Determinismus-Garantie: gleiche Eingaben ⇒ byte-identische Ausgaben.
Erzeugte Artefakte (INDEX.md, graph.json, MANIFEST.sha256) enthalten
darum bewusst KEINE Zeitstempel. Nur Standardbibliothek, keine Abhängigkeiten.

Kommandos:
  validate           Schema-, Referenz- und Integritätsprüfung (fail-closed)
  index              INDEX.md aus den Frontmatter-Daten neu erzeugen
  graph              graph/graph.json (Wissensgraph) ableiten
  search <begriff>   Deterministische Volltextsuche (Plan B des Routers)
  checksum           MANIFEST.sha256 schreiben   |  checksum --verify: prüfen
  log <aktion> <txt> Log-Eintrag mit grep-barem Präfix anhängen
  stats              Bestandszahlen (Domänen, Typen, Claims, Kanten)
  source <datei>     Hash + nächste freie S-ID + fertige Registerzeile
  doctor             Gesamtdiagnose mit Ampel-Report (validate + Drift + Orphans)
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE = ROOT / "knowledge"
SOURCES = ROOT / "sources"
REGISTER = SOURCES / "REGISTER.md"
TYPES = ROOT / "schema" / "types.yaml"
ROUTER = ROOT / "ROUTER.md"
INDEX = ROOT / "INDEX.md"
GRAPH = ROOT / "graph" / "graph.json"
MANIFEST = ROOT / "MANIFEST.sha256"
LOG = ROOT / "log.md"
VERSION = ROOT / "VERSION"

PROFIL = "oksv-lite/1.0"
REQUIRED_FIELDS = ["type", "title", "domain", "status", "confidence",
                   "version", "stand", "sources", "tags"]
STATUS_WERTE = {"aktiv", "veraltet", "in-pruefung"}
CONF_WERTE = {"hoch", "mittel", "niedrig"}
LOG_AKTIONEN = {"ingest", "update", "lint", "release", "note", "onboarding"}
TRUST_WERTE = {"T1", "T2", "T3"}

# Split-Kandidaten (doctor, nur Hinweis): keine harte Obergrenze, kein
# automatisches Zerschneiden — Schwellen markieren nur, wann ein Mensch/
# das Modell die Kompressions- bzw. Beförderungsregel prüfen sollte.
SPLIT_CLAIMS_SCHWELLE = 20
SPLIT_ZEILEN_SCHWELLE = 400

CLAIM_START = "- **C-"
CLAIM_RE = re.compile(
    r"^- \*\*(C-\d{4})\*\* \[(S-\d{4}) \| ([^\]|]+?) \| (Wortlaut|Auslegung)\] (.+)$")
REL_RE = re.compile(r"^([a-z_]+) -> (.+)$")
LINK_RE = re.compile(r"\]\(([^)\s]+)\)")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
SID_RE = re.compile(r"^S-\d{4}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")


# ---------------------------------------------------------------- Hilfen

def rel(p: Path) -> str:
    return p.resolve().relative_to(ROOT).as_posix()


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def iter_pages():
    if not KNOWLEDGE.is_dir():
        return []
    return sorted(KNOWLEDGE.rglob("*.md"), key=lambda p: rel(p))


# ------------------------------------------- Parser (Profil-Untermenge)

def parse_frontmatter(text, quelle):
    """Flaches Frontmatter der Profil-Untermenge parsen.

    Erlaubt: 'key: skalar', 'key: [a, b]' und mehrzeilige Listen
    ('key:' gefolgt von '  - wert'). Nichts Verschachteltes — bewusst,
    damit genau EIN einfacher, prüfbarer Parser genügt.
    Rückgabe: (dict, body, fehlerliste, body_offset in Dateizeilen)
    """
    fehler = []
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, text, [f"{quelle}: kein Frontmatter (Datei muss mit '---' beginnen)"], 0
    fm, i, ende = {}, 1, None
    while i < len(lines):
        line = lines[i]
        if line.strip() == "---":
            ende = i
            break
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        if line.startswith("  - "):
            fehler.append(f"{quelle}: Listenzeile ohne zugehörigen Schlüssel: {line.strip()!r}")
            i += 1
            continue
        if ":" not in line:
            fehler.append(f"{quelle}: Frontmatter-Zeile ohne ':' — {line.strip()!r}")
            i += 1
            continue
        key, _, val = line.partition(":")
        key, val = key.strip(), val.strip()
        if val == "":
            werte, j = [], i + 1
            while j < len(lines) and lines[j].startswith("  - "):
                werte.append(lines[j][4:].strip().strip('"').strip("'"))
                j += 1
            fm[key] = werte
            i = j
            continue
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            fm[key] = ([] if not inner else
                       [x.strip().strip('"').strip("'") for x in inner.split(",")])
        else:
            fm[key] = val.strip('"').strip("'")
        i += 1
    if ende is None:
        return fm, "", [f"{quelle}: Frontmatter nicht geschlossen (zweites '---' fehlt)"], 0
    return fm, "\n".join(lines[ende + 1:]), fehler, ende + 1


def parse_types():
    """schema/types.yaml (zweistufig, Profil-Untermenge) lesen.

    Rückgabe: (typen: dict[name -> felder], relationstypen: liste, fehler)
    """
    fehler = []
    if not TYPES.exists():
        return {}, [], [f"{rel(TYPES)}: fehlt — Typ-Registry ist Pflicht"]
    typen, reltypen, aktuell = {}, [], None
    for n, line in enumerate(read(TYPES).split("\n"), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" "):
            key, _, val = line.partition(":")
            key, val = key.strip(), val.strip()
            if key == "_relationstypen":
                inner = val.strip()[1:-1] if val.startswith("[") else val
                reltypen = [x.strip() for x in inner.split(",") if x.strip()]
                aktuell = None
            elif val == "":
                aktuell = key
                typen[aktuell] = {}
            else:
                fehler.append(f"{rel(TYPES)}:{n}: Top-Level braucht 'typname:' ohne Wert")
        elif line.startswith("  ") and aktuell:
            key, _, val = line.strip().partition(":")
            typen[aktuell][key.strip()] = val.strip().strip('"')
        else:
            fehler.append(f"{rel(TYPES)}:{n}: Einrückung außerhalb der Profil-Untermenge")
    return typen, reltypen, fehler


def parse_register():
    """sources/REGISTER.md-Tabelle lesen.

    Spalten: | ID | Titel | Stand/Version | SHA-256 | Trust | Rechte | Ablage |
    Rückgabe: (dict sid -> zeile, fehler)
    """
    fehler, reg = [], {}
    if not REGISTER.exists():
        return {}, [f"{rel(REGISTER)}: fehlt — Quellenregister ist Pflicht"]
    for n, line in enumerate(read(REGISTER).split("\n"), 1):
        if not line.strip().startswith("| S-"):
            continue
        teile = [t.strip() for t in line.strip().strip("|").split("|")]
        if len(teile) != 7:
            fehler.append(f"{rel(REGISTER)}:{n}: erwartet 7 Spalten, gefunden {len(teile)}")
            continue
        sid, titel, stand, h, trust, rechte, ablage = teile
        if not SID_RE.match(sid):
            fehler.append(f"{rel(REGISTER)}:{n}: ungültige Quellen-ID {sid!r}")
            continue
        if sid in reg:
            fehler.append(f"{rel(REGISTER)}:{n}: doppelte Quellen-ID {sid}")
        reg[sid] = {"titel": titel, "stand": stand, "hash": h,
                    "trust": trust, "rechte": rechte, "ablage": ablage, "zeile": n}
    return reg, fehler


def parse_router():
    """ROUTER.md lesen. Rückgabe: (dict domain -> {schlagworte, seiten}, fehler)"""
    fehler, router, dom = [], {}, None
    if not ROUTER.exists():
        return {}, [f"{rel(ROUTER)}: fehlt — Schlagwort-Router ist Pflicht"]
    for n, line in enumerate(read(ROUTER).split("\n"), 1):
        s = line.strip()
        if s.startswith("## "):
            dom = s[3:].strip()
            router[dom] = {"schlagworte": [], "seiten": [], "zeile": n}
        elif dom and s.startswith("schlagworte:"):
            router[dom]["schlagworte"] = [
                w.strip().lower() for w in s.split(":", 1)[1].split(",") if w.strip()]
        elif dom and s.startswith("- knowledge/"):
            router[dom]["seiten"].append(s[2:].strip())
    return router, fehler


# ---------------------------------------------------------------- Seiten

def lade_seiten(register, typen, reltypen):
    """Alle Wissensseiten laden und prüfen. Rückgabe: (seiten, claims, fehler, warnungen)."""
    fehler, warnungen, seiten, alle_claims = [], [], {}, {}
    for p in iter_pages():
        rp = rel(p)
        fm, body, fm_fehler, offset = parse_frontmatter(read(p), rp)
        fehler.extend(fm_fehler)

        for feld in REQUIRED_FIELDS:
            if feld not in fm or fm[feld] in ("", []):
                fehler.append(f"{rp}: Pflichtfeld {feld!r} fehlt oder ist leer")
        typ = fm.get("type", "")
        if typen and typ and typ not in typen:
            fehler.append(f"{rp}: Typ {typ!r} nicht in schema/types.yaml — "
                          f"Type-Onboarding durchführen, bevor eingelesen wird (fail-closed)")
        if p.parent.parent != KNOWLEDGE:
            fehler.append(f"{rp}: Seiten liegen genau eine Ebene tief: knowledge/<domäne>/<seite>.md")
        elif fm.get("domain") != p.parent.name:
            fehler.append(f"{rp}: domain={fm.get('domain')!r} ≠ Ordner {p.parent.name!r} "
                          f"(Quellentrennung ist baulich)")
        if fm.get("status") not in STATUS_WERTE:
            fehler.append(f"{rp}: status muss eins sein von {sorted(STATUS_WERTE)}")
        if fm.get("confidence") not in CONF_WERTE:
            fehler.append(f"{rp}: confidence muss eins sein von {sorted(CONF_WERTE)}")
        if not DATE_RE.match(str(fm.get("stand", ""))):
            fehler.append(f"{rp}: stand muss JJJJ-MM-TT sein")
        if not VERSION_RE.match(str(fm.get("version", ""))):
            fehler.append(f"{rp}: version muss SemVer sein (z. B. 1.0.0)")

        quellen = fm.get("sources", [])
        if isinstance(quellen, str):
            quellen = [quellen]
        for sid in quellen:
            if sid not in register:
                fehler.append(f"{rp}: Quelle {sid} steht nicht im Register")

        # Claims (Grammatik siehe schema/profil.md)
        claims = []
        for bn, line in enumerate(body.split("\n"), 1):
            n = offset + bn
            if not line.startswith(CLAIM_START):
                continue
            m = CLAIM_RE.match(line)
            if not m:
                fehler.append(f"{rp}:{n}: Claim-Zeile verletzt die Grammatik "
                              f"'- **C-nnnn** [S-nnnn | Fundstelle | Wortlaut|Auslegung] Text'")
                continue
            cid, sid, fundstelle, art, text = m.groups()
            if cid in alle_claims:
                fehler.append(f"{rp}:{n}: Claim-ID {cid} bereits vergeben "
                              f"in {alle_claims[cid]['seite']}")
            if sid not in register:
                fehler.append(f"{rp}:{n}: {cid} verweist auf unregistrierte Quelle {sid}")
            elif sid not in quellen:
                fehler.append(f"{rp}:{n}: {cid} nutzt {sid}, aber {sid} fehlt in "
                              f"'sources:' des Frontmatters")
            eintrag = {"id": cid, "quelle": sid, "fundstelle": fundstelle.strip(),
                       "art": art, "text": text.strip(), "seite": rp}
            claims.append(eintrag)
            alle_claims[cid] = eintrag
        if not claims:
            warnungen.append(f"{rp}: keine Claims — Kurzfassung wäre unbelegt")

        # Relationen (typisierte Kanten; dürfen Domänen überschreiten)
        relationen = []
        rels = fm.get("relations", [])
        if isinstance(rels, str):
            rels = [rels]
        for r in rels:
            m = REL_RE.match(r)
            if not m:
                fehler.append(f"{rp}: relation {r!r} verletzt das Format 'typ -> domäne/seite.md'")
                continue
            rtyp, ziel = m.group(1), m.group(2).strip()
            if reltypen and rtyp not in reltypen:
                fehler.append(f"{rp}: Relationstyp {rtyp!r} nicht in _relationstypen "
                              f"(types.yaml) — erst dort deklarieren")
            zielpfad = KNOWLEDGE / ziel
            if not zielpfad.is_file():
                fehler.append(f"{rp}: Relationsziel knowledge/{ziel} existiert nicht")
            relationen.append({"typ": rtyp, "ziel": "knowledge/" + ziel})

        # Links im Fließtext: relativ, auflösbar, innerhalb der Domäne
        for m in LINK_RE.finditer(body):
            ziel = m.group(1)
            if ziel.startswith(("http://", "https://", "mailto:", "#")):
                continue
            if ziel.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:[\\/]", ziel):
                fehler.append(f"{rp}: absoluter Pfad im Link {ziel!r} — Portabilität "
                              f"verlangt relative Pfade")
                continue
            aufgeloest = (p.parent / ziel.split("#")[0]).resolve()
            if ROOT not in aufgeloest.parents and aufgeloest != ROOT:
                fehler.append(f"{rp}: Link {ziel!r} zeigt aus dem Tresor hinaus")
                continue
            if not aufgeloest.exists():
                fehler.append(f"{rp}: toter Link {ziel!r}")
                continue
            if KNOWLEDGE in aufgeloest.parents and aufgeloest.parent != p.parent:
                fehler.append(f"{rp}: Cross-Domain-Link im Fließtext auf "
                              f"{rel(aufgeloest)} — domänenübergreifend nur als "
                              f"typisierte relation im Frontmatter")

        seiten[rp] = {"fm": fm, "claims": claims, "relationen": relationen, "pfad": p,
                      "zeilen": len(body.split("\n"))}
    return seiten, alle_claims, fehler, warnungen


# ------------------------------------------------------------- Kommandos

def cmd_validate(still=False):
    typen, reltypen, fehler = parse_types()
    register, f2 = parse_register()
    fehler += f2

    # Registerzeilen materiell prüfen: Ablage existiert, Hash stimmt
    for sid, r in sorted(register.items()):
        if r["trust"] not in TRUST_WERTE:
            fehler.append(f"REGISTER {sid}: Trust muss T1/T2/T3 sein")
        if not HASH_RE.match(r["hash"]):
            fehler.append(f"REGISTER {sid}: SHA-256 hat kein gültiges Format")
        ablage = ROOT / r["ablage"]
        if not ablage.is_file():
            fehler.append(f"REGISTER {sid}: Ablage {r['ablage']} existiert nicht")
        elif HASH_RE.match(r["hash"]) and sha256_file(ablage) != r["hash"]:
            fehler.append(f"REGISTER {sid}: Hash der Ablage weicht vom Register ab "
                          f"— Quelle wurde nach Registrierung verändert")

    seiten, claims, f3, warnungen = lade_seiten(register, typen, reltypen)
    fehler += f3

    # Router: jede Domäne hat Abschnitt, jede gelistete Seite existiert und passt
    router, f4 = parse_router()
    fehler += f4
    domaenen = sorted({d.name for d in KNOWLEDGE.iterdir() if d.is_dir()}) if KNOWLEDGE.is_dir() else []
    for d in domaenen:
        if d not in router:
            fehler.append(f"ROUTER.md: Domäne {d!r} hat keinen Abschnitt — jede Domäne "
                          f"braucht Schlagworte und Seitenliste")
    for d, sec in sorted(router.items()):
        if d not in domaenen:
            fehler.append(f"ROUTER.md: Abschnitt {d!r} ohne Domänen-Ordner knowledge/{d}/")
        if not sec["schlagworte"]:
            fehler.append(f"ROUTER.md [{d}]: keine Schlagworte")
        for s in sec["seiten"]:
            if not (ROOT / s).is_file():
                fehler.append(f"ROUTER.md [{d}]: gelistete Seite {s} existiert nicht")
            elif not s.startswith(f"knowledge/{d}/"):
                fehler.append(f"ROUTER.md [{d}]: {s} gehört nicht zur Domäne {d}")

    if not still:
        for w in warnungen:
            print(f"🟡 WARNUNG  {w}")
        for f in fehler:
            print(f"🔴 FEHLER   {f}")
        if fehler:
            print(f"\nvalidate: {len(fehler)} Fehler, {len(warnungen)} Warnungen — "
                  f"FAIL-CLOSED: erst beheben, dann weiterarbeiten.")
        else:
            print(f"🟢 validate: 0 Fehler, {len(warnungen)} Warnungen — "
                  f"{len(seiten)} Seiten, {len(claims)} Claims, {len(register)} Quellen.")
    return fehler, warnungen, seiten, claims, register, router


def build_index(seiten):
    zeilen = ["# INDEX — Navigations-Map des Wissenstresors",
              "",
              "<!-- Generiert durch scripts/vault.py index — NICHT von Hand editieren. -->",
              "<!-- Map-first-Regel: Relevanz wird HIER entschieden, nie durch Lesen von Seitenkörpern. -->",
              ""]
    nach_dom = {}
    for rp, s in sorted(seiten.items()):
        nach_dom.setdefault(s["fm"].get("domain", "?"), []).append((rp, s))
    for dom in sorted(nach_dom):
        zeilen.append(f"## {dom}")
        zeilen.append("")
        zeilen.append("| Seite | Typ | Status | Konfidenz | Stand | Titel |")
        zeilen.append("|---|---|---|---|---|---|")
        for rp, s in nach_dom[dom]:
            fm = s["fm"]
            name = Path(rp).name
            zeilen.append(f"| [{name}]({rp}) | {fm.get('type','')} | {fm.get('status','')} "
                          f"| {fm.get('confidence','')} | {fm.get('stand','')} "
                          f"| {fm.get('title','')} |")
        zeilen.append("")
    return "\n".join(zeilen)


def cmd_index():
    fehler, _, seiten, *_ = cmd_validate(still=True)
    if fehler:
        print("🔴 index: abgebrochen — validate meldet Fehler (fail-closed). "
              "Erst 'vault.py validate' grün bekommen.")
        return 1
    INDEX.write_text(build_index(seiten), encoding="utf-8")
    print(f"🟢 index: {rel(INDEX)} neu erzeugt ({len(seiten)} Seiten).")
    return 0


def build_graph(seiten):
    knoten, kanten = [], []
    for rp, s in sorted(seiten.items()):
        fm = s["fm"]
        knoten.append({"id": rp, "titel": fm.get("title", ""), "typ": fm.get("type", ""),
                       "domaene": fm.get("domain", ""), "status": fm.get("status", ""),
                       "konfidenz": fm.get("confidence", ""), "stand": fm.get("stand", ""),
                       "claims": sorted(c["id"] for c in s["claims"])})
        for r in s["relationen"]:
            kanten.append({"von": rp, "nach": r["ziel"], "typ": r["typ"]})
    kanten.sort(key=lambda k: (k["von"], k["nach"], k["typ"]))
    return {"profil": PROFIL, "knoten": knoten, "kanten": kanten}


def cmd_graph():
    fehler, _, seiten, *_ = cmd_validate(still=True)
    if fehler:
        print("🔴 graph: abgebrochen — validate meldet Fehler (fail-closed).")
        return 1
    GRAPH.parent.mkdir(exist_ok=True)
    GRAPH.write_text(json.dumps(build_graph(seiten), ensure_ascii=False,
                                indent=2, sort_keys=True) + "\n", encoding="utf-8")
    g = build_graph(seiten)
    print(f"🟢 graph: {rel(GRAPH)} abgeleitet — {len(g['knoten'])} Knoten, "
          f"{len(g['kanten'])} Kanten. Kanten stammen nur aus validierten Seiten.")
    return 0


def cmd_search(begriffe, mit_quellen=True):
    """Plan B: erschöpfende, deterministische Volltextsuche.
    Ein Nicht-Treffer ist damit ein belastbarer Negativbefund."""
    muster = re.compile("|".join(re.escape(b) for b in begriffe), re.IGNORECASE)
    dateien = list(iter_pages())
    if mit_quellen:
        for extra in (REGISTER, ROUTER):
            if extra.exists():
                dateien.append(extra)
    treffer = 0
    for p in dateien:
        for n, line in enumerate(read(p).split("\n"), 1):
            if muster.search(line):
                treffer += 1
                print(f"{rel(p)}:{n}: {line.strip()[:160]}")
    print(f"\nsearch: {treffer} Treffer für {begriffe} "
          f"(erschöpfend über {len(dateien)} Dateien).")
    if treffer == 0:
        print("Negativbefund ist belastbar: 'steht nicht im Bestand'.")
    return 0 if treffer else 1


def _tracked_files():
    # log.md ist bewusst NICHT im Manifest: das Journal wächst append-only
    # weiter (auch der Release-Eintrag selbst) und würde jedes Manifest
    # sofort wieder invalidieren. Historie ist Nachweis, nicht Inhalt.
    # evals/ (nur auf oberster Ebene) ist ebenfalls ausgenommen: Werkstatt-
    # material des Skill-Creators, das beim Packaging nicht mitgeliefert
    # wird — stünde es im Manifest, schlüge verify nach Installation fehl.
    aus = {MANIFEST.name, LOG.name}
    ergebnis = []
    for p in sorted(ROOT.rglob("*"), key=lambda x: rel(x)):
        if not p.is_file():
            continue
        teile = p.relative_to(ROOT).parts
        if p.name in aus or "__pycache__" in teile or p.suffix == ".pyc":
            continue
        if teile[0] == "evals":
            continue
        ergebnis.append(p)
    return ergebnis


def cmd_checksum(verify=False):
    aktuell = {rel(p): sha256_file(p) for p in _tracked_files()}
    if not verify:
        MANIFEST.write_text(
            "".join(f"{h}  {rp}\n" for rp, h in sorted(aktuell.items())),
            encoding="utf-8")
        print(f"🟢 checksum: {rel(MANIFEST)} geschrieben ({len(aktuell)} Dateien). "
              f"Jede inhaltliche Änderung invalidiert dieses Manifest.")
        return 0
    if not MANIFEST.exists():
        print("🔴 verify: MANIFEST.sha256 fehlt — erst 'checksum' ausführen.")
        return 1
    soll = {}
    for line in read(MANIFEST).split("\n"):
        if line.strip():
            h, _, rp = line.partition("  ")
            soll[rp.strip()] = h.strip()
    neu = sorted(set(aktuell) - set(soll))
    weg = sorted(set(soll) - set(aktuell))
    anders = sorted(rp for rp in set(soll) & set(aktuell) if soll[rp] != aktuell[rp])
    for rp in neu:
        print(f"🟡 NEU       {rp}")
    for rp in weg:
        print(f"🔴 FEHLT     {rp}")
    for rp in anders:
        print(f"🔴 GEÄNDERT  {rp}")
    if neu or weg or anders:
        print(f"\nverify: Abweichungen — Stand entspricht NICHT dem Manifest. "
              f"Nach bewusster Änderung: 'checksum' neu ausführen (neue Version).")
        return 1
    print(f"🟢 verify: {len(soll)} Dateien unverändert — Stand = Manifest.")
    return 0


def cmd_log(aktion, text):
    if aktion not in LOG_AKTIONEN:
        print(f"🔴 log: Aktion muss eine sein von {sorted(LOG_AKTIONEN)}")
        return 1
    eintrag = f"## [{date.today().isoformat()}] {aktion} | {text}"
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(eintrag + "\n")
    print(f"🟢 log: angehängt — {eintrag}")
    return 0


def cmd_stats():
    fehler, warn, seiten, claims, register, _ = cmd_validate(still=True)
    g = build_graph(seiten)
    dom, typ, status = {}, {}, {}
    for s in seiten.values():
        fm = s["fm"]
        dom[fm.get("domain", "?")] = dom.get(fm.get("domain", "?"), 0) + 1
        typ[fm.get("type", "?")] = typ.get(fm.get("type", "?"), 0) + 1
        status[fm.get("status", "?")] = status.get(fm.get("status", "?"), 0) + 1
    print(f"Profil {PROFIL} — {len(seiten)} Seiten, {len(claims)} Claims, "
          f"{len(register)} Quellen, {len(g['kanten'])} Kanten "
          f"({len(fehler)} Fehler, {len(warn)} Warnungen)")
    for name, d in (("Domänen", dom), ("Typen", typ), ("Status", status)):
        print(f"  {name}: " + ", ".join(f"{k}={v}" for k, v in sorted(d.items())))
    return 0


def cmd_source(pfad):
    p = Path(pfad)
    if not p.is_file():
        print(f"🔴 source: {pfad} nicht gefunden")
        return 1
    register, _ = parse_register()
    naechste = max([int(s[2:]) for s in register] or [0]) + 1
    sid = f"S-{naechste:04d}"
    h = sha256_file(p)
    print(f"Datei     : {p.name} ({p.stat().st_size} Bytes)")
    print(f"SHA-256   : {h}")
    print(f"Nächste ID: {sid}")
    print("Registerzeile (Titel/Stand/Trust/Rechte ausfüllen, Datei nach sources/raw/ verschieben):")
    print(f"| {sid} | TITEL | JJJJ-MM-TT | {h} | T? | RECHTE | sources/raw/{sid}__{p.name} |")
    return 0


UMLAUT = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue",
                        "Ä": "ae", "Ö": "oe", "Ü": "ue", "ß": "ss"})


def _norm(s):
    return re.sub(r"\s+", " ", s.lower().translate(UMLAUT)).strip()


def cmd_route(frage_woerter):
    """Deterministisches Routing: Frage → Domäne(n) → Seiten.

    Kein Modell, keine Wahrscheinlichkeit — Schlagwort-Abgleich gegen
    ROUTER.md (Mehrwort-Schlagworte als Teilstring der normalisierten
    Frage). Treffer in mehreren Domänen ⇒ Mischfrage wird gemeldet und
    pro Domäne getrennt beantwortet. Das Ergebnis ist ein nachvollzieh-
    barer VORSCHLAG; die finale Einordnung trifft das Modell anhand von
    INDEX.md und benennt es, wenn es den Router überstimmt.
    """
    router, fehler = parse_router()
    if fehler:
        for f in fehler:
            print(f"🔴 {f}")
        return 1
    frage = _norm(" ".join(frage_woerter))
    treffer = {}
    for dom in sorted(router):
        worte = sorted({w for w in router[dom]["schlagworte"]
                        if _norm(w) and _norm(w) in frage})
        if worte:
            treffer[dom] = worte
    if not treffer:
        print("route: kein Schlagwort-Treffer.")
        print("Plan B: python3 scripts/vault.py search <begriff> "
              "(erschöpfend; Negativbefund belastbar).")
        return 1
    if len(treffer) > 1:
        print(f"🟡 MISCHFRAGE — berührt {len(treffer)} Domänen "
              f"({', '.join(sorted(treffer))}): pro Domäne getrennt "
              f"beantworten, Quellen nicht vermischen.")
    for dom in sorted(treffer):
        print(f"route: Domäne {dom}  (Schlagworte: {', '.join(treffer[dom])})")
        for seite in router[dom]["seiten"]:
            print(f"       → {seite}")
    print("Hinweis: Vorschlag, kein Urteil — finale Auswahl über INDEX.md; "
          "Überstimmen des Routers in der Antwort benennen.")
    return 0


def cmd_release(stufe):
    """Atomare Release-Kette mit Gate und Version.

    Gate: validate muss fehlerfrei sein (fail-closed). Dann in fester
    Reihenfolge: index → graph → VERSION anheben → log → checksum.
    Das neue Manifest pinnt exakt diesen Stand; alte Prüfsummen sind
    damit invalidiert. Zweimal hintereinander (ohne Änderung) gebaut
    ergibt bis auf VERSION/Manifest byte-identische Artefakte.
    """
    if stufe not in ("major", "minor", "patch"):
        print("🔴 release: Stufe muss major|minor|patch sein")
        return 1
    fehler, warnungen, seiten, claims, register, _ = cmd_validate(still=True)
    if fehler:
        for f in fehler:
            print(f"🔴 {f}")
        print("🔴 release: ABBRUCH — validate schlägt fehl (fail-closed).")
        return 1
    cmd_index()
    cmd_graph()
    alt = VERSION.read_text(encoding="utf-8").strip() if VERSION.exists() else "0.0.0"
    try:
        ma, mi, pa = (int(x) for x in alt.split("."))
    except ValueError:
        print(f"🔴 release: VERSION '{alt}' ist kein SemVer x.y.z")
        return 1
    ma, mi, pa = {"major": (ma + 1, 0, 0),
                  "minor": (ma, mi + 1, 0),
                  "patch": (ma, mi, pa + 1)}[stufe]
    neu = f"{ma}.{mi}.{pa}"
    VERSION.write_text(neu + "\n", encoding="utf-8")
    cmd_log("release", f"v{neu} — {len(seiten)} Seiten, {len(claims)} Claims, "
                       f"{len(register)} Quellen ({stufe})")
    rc = cmd_checksum(verify=False)
    if warnungen:
        print(f"🟡 release: v{neu} mit {len(warnungen)} Warnungen "
              f"(Details: vault.py doctor).")
    else:
        print(f"🟢 release: v{neu} — Stand gepinnt, alte Prüfsummen invalidiert.")
    return rc


def cmd_doctor():
    print("── doctor: Gesamtdiagnose ─────────────────────────────────────")
    fehler, warnungen, seiten, claims, register, router = cmd_validate(still=False)
    hinweise = []

    if INDEX.exists():
        if read(INDEX) != build_index(seiten):
            fehler.append("INDEX.md weicht vom Bestand ab — 'vault.py index' ausführen (Drift)")
    else:
        fehler.append("INDEX.md fehlt — 'vault.py index' ausführen")
    if GRAPH.exists():
        soll = json.dumps(build_graph(seiten), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if read(GRAPH) != soll:
            fehler.append("graph/graph.json weicht vom Bestand ab — 'vault.py graph' ausführen (Drift)")
    else:
        fehler.append("graph/graph.json fehlt — 'vault.py graph' ausführen")

    # Router-Abdeckung und Orphans
    gelistet = {s for sec in router.values() for s in sec["seiten"]}
    verlinkt = {r["ziel"] for s in seiten.values() for r in s["relationen"]}
    for rp in sorted(seiten):
        if rp not in gelistet:
            warnungen.append(f"{rp}: nicht im ROUTER gelistet — Seite ist unauffindbar per Map-first")
        if rp not in gelistet and rp not in verlinkt:
            warnungen.append(f"{rp}: Orphan — weder Router-Eintrag noch eingehende Relation")

    # Schlagwort-Überschneidungen zwischen Domänen = Mischfragen-Signal
    wo = {}
    for d, sec in router.items():
        for w in sec["schlagworte"]:
            wo.setdefault(w, []).append(d)
    for w, ds in sorted(wo.items()):
        if len(ds) > 1:
            hinweise.append(f"Schlagwort {w!r} in mehreren Domänen ({', '.join(sorted(ds))}) "
                            f"— Treffer in beiden ⇒ Mischfrage melden")

    # Split-Kandidaten: kein Fehler, keine Warnung — nur ein deterministisches
    # Signal, wann Kompressions- bzw. Beförderungsregel geprüft werden sollte.
    # Splitten selbst bleibt Modellarbeit (Befüllen-Workflow), nie automatisch.
    for rp, s in sorted(seiten.items()):
        n_claims = len(s["claims"])
        n_zeilen = s.get("zeilen", 0)
        if n_claims > SPLIT_CLAIMS_SCHWELLE:
            hinweise.append(f"{rp}: {n_claims} Claims (Schwelle {SPLIT_CLAIMS_SCHWELLE}) "
                            f"— Split-Kandidat: thematisch verwandte Claims ggf. in eigene "
                            f"Konzeptseite auslagern (Befüllen-Workflow, Beförderungsregel)")
        if n_zeilen > SPLIT_ZEILEN_SCHWELLE:
            hinweise.append(f"{rp}: Body {n_zeilen} Zeilen (Schwelle {SPLIT_ZEILEN_SCHWELLE}) "
                            f"— möglicher Verdichtungs-/Split-Kandidat, siehe Kompressionsregel")

    if MANIFEST.exists():
        print("── Prüfsummen ─────────────────────────────────────────────────")
        cmd_checksum(verify=True)

    print("── Zusammenfassung ────────────────────────────────────────────")
    for h in hinweise:
        print(f"ℹ️  {h}")
    ampel = "🔴" if fehler else ("🟡" if warnungen else "🟢")
    print(f"{ampel} doctor: {len(fehler)} Fehler, {len(warnungen)} Warnungen, "
          f"{len(hinweise)} Hinweise — {len(seiten)} Seiten / {len(claims)} Claims / "
          f"{len(register)} Quellen.")
    return 1 if fehler else 0


def main():
    ap = argparse.ArgumentParser(prog="vault.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate")
    sub.add_parser("index")
    sub.add_parser("graph")
    s = sub.add_parser("search")
    s.add_argument("begriffe", nargs="+")
    c = sub.add_parser("checksum")
    c.add_argument("--verify", action="store_true")
    l = sub.add_parser("log")
    l.add_argument("aktion")
    l.add_argument("text")
    sub.add_parser("stats")
    q = sub.add_parser("source")
    q.add_argument("datei")
    sub.add_parser("doctor")
    r = sub.add_parser("route")
    r.add_argument("frage", nargs="+")
    v = sub.add_parser("release")
    v.add_argument("stufe", nargs="?", default="patch",
                   choices=["major", "minor", "patch"])
    a = ap.parse_args()

    if a.cmd == "validate":
        fehler, *_ = cmd_validate()
        sys.exit(1 if fehler else 0)
    elif a.cmd == "index":
        sys.exit(cmd_index())
    elif a.cmd == "graph":
        sys.exit(cmd_graph())
    elif a.cmd == "search":
        sys.exit(cmd_search(a.begriffe))
    elif a.cmd == "checksum":
        sys.exit(cmd_checksum(verify=a.verify))
    elif a.cmd == "log":
        sys.exit(cmd_log(a.aktion, a.text))
    elif a.cmd == "stats":
        sys.exit(cmd_stats())
    elif a.cmd == "source":
        sys.exit(cmd_source(a.datei))
    elif a.cmd == "doctor":
        sys.exit(cmd_doctor())
    elif a.cmd == "route":
        sys.exit(cmd_route(a.frage))
    elif a.cmd == "release":
        sys.exit(cmd_release(a.stufe))


if __name__ == "__main__":
    main()
