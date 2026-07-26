#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""vault.py — deterministische Engine des Wissenstresors (Profil: oksv-lite/1.1).

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
  query <frage>      Lokales Hybrid-Retrieval als stabiler JSON-Vertrag
  media-template ID  JSON-Gerüst für eine registrierte Bild-/PDF-Quelle
  checksum           MANIFEST.sha256 schreiben   |  checksum --verify: prüfen
  log <aktion> <txt> Log-Eintrag mit grep-barem Präfix anhängen
  stats              Bestandszahlen (Domänen, Typen, Claims, Kanten)
  source <datei>     Hash + nächste freie S-ID + fertige Registerzeile
  doctor             Gesamtdiagnose mit Ampel-Report (validate + Drift + Orphans)
  release [stufe]    Transaktionaler Release mit Lock und Rollback
"""

import argparse
import hashlib
import heapq
import json
import os
import re
import stat
import sys
import tempfile
import unicodedata
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE = ROOT / "knowledge"
SOURCES = ROOT / "sources"
QUARANTINE = SOURCES / "quarantine"
RAW = SOURCES / "raw"
REGISTER = SOURCES / "REGISTER.md"
TYPES = ROOT / "schema" / "types.yaml"
CONCEPTS = ROOT / "schema" / "begriffswelten.json"
ROUTER = ROOT / "ROUTER.md"
INDEX = ROOT / "INDEX.md"
GRAPH = ROOT / "graph" / "graph.json"
DERIVED = SOURCES / "derived"
MANIFEST = ROOT / "MANIFEST.sha256"
LOG = ROOT / "log.md"
VERSION = ROOT / "VERSION"
RELEASE_LOCK = ROOT / ".vault-release.lock"

PROFIL = "oksv-lite/1.1"
REQUIRED_FIELDS = ["type", "title", "domain", "status", "confidence",
                   "version", "stand", "sources", "tags"]
OPTIONAL_FIELDS = {"relations", "concepts"}
LIST_FIELDS = {"sources", "tags", "relations", "concepts"}
STATUS_WERTE = {"aktiv", "veraltet", "in-pruefung"}
CONF_WERTE = {"hoch", "mittel", "niedrig"}
LOG_AKTIONEN = {"ingest", "update", "lint", "release", "note", "onboarding"}
TRUST_WERTE = {"T1", "T2", "T3"}
TYPE_REQUIRED_FIELDS = {
    "beschreibung", "kriterien", "besonderheiten", "pflicht_extra", "graph_rolle"
}

# Split-Kandidaten (doctor, nur Hinweis): keine harte Obergrenze, kein
# automatisches Zerschneiden — Schwellen markieren nur, wann ein Mensch/
# das Modell die Kompressions- bzw. Beförderungsregel prüfen sollte.
SPLIT_CLAIMS_SCHWELLE = 20
SPLIT_ZEILEN_SCHWELLE = 400

CLAIM_START = "- **C-"
CLAIM_RE = re.compile(
    r"^- \*\*(C-\d{4})\*\* \[(S-\d{4}) \| ([^\]|]+?) \| "
    r"(Wortlaut|Beobachtung|Auslegung)\] (.+)$")
REL_RE = re.compile(r"^([a-z_]+) -> (.+)$")
LINK_RE = re.compile(r"\]\(([^)]*)\)")
REFERENCE_LINK_RE = re.compile(
    r"(?m)^[ \t]{0,3}\[[^\]\r\n]+\]:[ \t]*(\S.*)$"
)
HTML_LINK_RE = re.compile(r"<(?:a|img)\b", re.IGNORECASE)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
SID_RE = re.compile(r"^S-\d{4}$")
CID_RE = re.compile(r"^C-\d{4}$")
WORLD_ID_RE = re.compile(r"^BW-\d{4}$")
CONCEPT_ID_RE = re.compile(r"^B-\d{4}$")
REGION_ID_RE = re.compile(r"^R-\d{4}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")

CONCEPT_SCHEMA = "skillsafe.begriffswelten/v1"
MEDIA_SCHEMA = "skillsafe.media/v1"
QUERY_SCHEMA = "skillsafe.query/v1"
RETRIEVAL_PROFILE = "hybrid-local/v1"
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_QUERY_LENGTH = 1000
MAX_QUERY_LIMIT = 20
MAX_CONCEPT_EXPANSIONS = 32
MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".pdf": "application/pdf",
}
ACTIVE_MEDIA_SUFFIXES = {".svg"}
REGION_KINDS = {"text", "diagram", "table", "photo", "chart", "other"}
EXTRACTOR_KINDS = {"human", "model", "ocr", "hybrid"}
PROMPT_INJECTION_RE = re.compile(
    r"(?:ignore\s+(?:(?:all|any)\s+)?(?:(?:previous|prior)\s+)?instructions|"
    r"system\s+prompt|developer\s+message|<\s*system\s*>)",
    re.IGNORECASE,
)
RETRIEVAL_STOPWORDS = {
    "aber", "als", "auch", "auf", "aus", "bei", "das", "dem", "den", "der",
    "des", "die", "ein", "eine", "einer", "eines", "für", "hat", "ich", "im",
    "in", "ist", "mit", "nach", "oder", "sich", "sind", "und", "von", "vor",
    "was", "welche", "welcher", "wie", "wo", "zu", "zum", "zur",
    "a", "an", "and", "are", "for", "from", "how", "in", "is", "of", "on",
    "or", "the", "to", "what", "which", "with",
}


class RollbackIncompleteError(RuntimeError):
    """Mindestens ein Release-Ziel konnte nicht wiederhergestellt werden."""


# ---------------------------------------------------------------- Hilfen

def rel(p: Path) -> str:
    """Lexikalischer, portabler Pfad innerhalb des Tresors."""
    return Path(os.path.abspath(p)).relative_to(ROOT).as_posix()


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _plain_text(value, field, errors, *, maximum=500, allow_empty=False):
    """Kompakten, einzeiligen Metadatenwert validieren."""
    if not isinstance(value, str):
        errors.append(f"{field}: Text erwartet")
        return False
    if (not allow_empty and not value.strip()) or value != value.strip():
        errors.append(f"{field}: leer oder mit Rand-Leerzeichen")
        return False
    if len(value) > maximum:
        errors.append(f"{field}: länger als {maximum} Zeichen")
        return False
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        errors.append(f"{field}: Steuerzeichen/Zeilenumbrüche sind verboten")
        return False
    return True


def _strict_json_pairs(pairs):
    """JSON-Objekte mit doppelten Schlüsseln fail-closed ablehnen."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"doppelter JSON-Schlüssel {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value):
    raise ValueError(f"nicht standardkonstante JSON-Zahl {value!r}")


def _load_strict_json(path: Path, label: str, errors):
    """Kleine JSON-Datei sicher, größenbegrenzt und ohne Duplicate Keys lesen."""
    if not _safe_regular_file(path):
        errors.append(f"{label}: fehlt oder ist keine sichere reguläre Datei")
        return None
    try:
        flags = (
            os.O_RDONLY | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        fd = os.open(str(path), flags)
        try:
            status = os.fstat(fd)
            if not stat.S_ISREG(status.st_mode) or status.st_nlink != 1:
                raise OSError("keine einfach verlinkte reguläre Datei")
            chunks, total = [], 0
            while True:
                chunk = os.read(fd, min(65536, MAX_JSON_BYTES + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > MAX_JSON_BYTES:
                    raise ValueError(f"größer als {MAX_JSON_BYTES} Bytes")
            source = b"".join(chunks).decode("utf-8")
        finally:
            os.close(fd)
        return json.loads(
            source,
            object_pairs_hook=_strict_json_pairs,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        errors.append(f"{label}: ungültiges JSON — {exc}")
        return None


def _exact_keys(value, required, optional, field, errors):
    if not isinstance(value, dict):
        errors.append(f"{field}: JSON-Objekt erwartet")
        return False
    missing = sorted(set(required) - set(value))
    unknown = sorted(set(value) - set(required) - set(optional))
    if missing:
        errors.append(f"{field}: Pflichtfelder fehlen {missing}")
    if unknown:
        errors.append(f"{field}: unbekannte Felder {unknown}")
    return not missing and not unknown


def _read_prefix(path: Path, size=16):
    """Dateisignatur ohne Link-Folgen lesen."""
    if _is_path_alias(path):
        raise OSError(f"{path}: Link statt regulärer Datei")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(str(path), flags)
    try:
        status = os.fstat(fd)
        if not stat.S_ISREG(status.st_mode) or status.st_nlink != 1:
            raise OSError(f"{path}: keine einfach verlinkte reguläre Datei")
        return os.read(fd, size)
    finally:
        os.close(fd)


def _detected_media_type(path: Path):
    try:
        prefix = _read_prefix(path, 64 * 1024)
    except OSError:
        return None
    if prefix.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if prefix.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if prefix.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(prefix) >= 12 and prefix[:4] == b"RIFF" and prefix[8:12] == b"WEBP":
        return "image/webp"
    if prefix.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff"
    if prefix.startswith(b"%PDF-"):
        return "application/pdf"
    if prefix.startswith(b"BM"):
        return "image/bmp"
    if prefix.startswith(b"\x00\x00\x01\x00"):
        return "image/x-icon"
    if len(prefix) >= 12 and prefix[4:8] == b"ftyp":
        brand = prefix[8:12]
        if brand in {b"avif", b"avis"}:
            return "image/avif"
        if brand in {b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1"}:
            return "image/heif"
    text_prefix = prefix.lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    # Ein SVG darf sich nicht durch XML-Prolog oder führende Kommentare als
    # Textquelle tarnen. Der Parser bleibt bewusst klein und fail-closed:
    # ein innerhalb von 64 KiB nicht abgeschlossenes Markup-Preamble wird
    # ebenfalls als aktive XML-/SVG-Signatur behandelt.
    while text_prefix.startswith((b"<!--", b"<?")):
        if text_prefix.startswith(b"<!--"):
            end = text_prefix.find(b"-->")
            marker_size = 3
        else:
            end = text_prefix.find(b"?>")
            marker_size = 2
        if end < 0:
            return "image/svg+xml"
        text_prefix = text_prefix[end + marker_size:].lstrip(b" \t\r\n")
    if text_prefix.startswith(b"<!doctype") and b"svg" in text_prefix[:512]:
        return "image/svg+xml"
    if text_prefix.startswith(b"<svg"):
        return "image/svg+xml"
    return None


def _media_signature_matches(path: Path, media_type: str) -> bool:
    return _detected_media_type(path) == media_type


def _is_path_alias(p: Path) -> bool:
    """Symlink oder Windows-Reparse-Point/Junction erkennen, ohne zu folgen."""
    try:
        status = os.lstat(str(p))
    except OSError:
        return False
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    attributes = getattr(status, "st_file_attributes", 0)
    return stat.S_ISLNK(status.st_mode) or bool(attributes & reparse_flag)


def sha256_file(p: Path) -> str:
    """Reguläre Datei hashen, ohne einem Symlink zu folgen."""
    if _is_path_alias(p):
        raise OSError(f"{p}: Symlinks/Reparse-Points werden nicht gehasht")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(str(p), flags)
    h = hashlib.sha256()
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError(f"{p}: keine reguläre Datei")
        with os.fdopen(fd, "rb", closefd=False) as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
    finally:
        os.close(fd)
    return h.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _resolved_within(p: Path, basis: Path) -> bool:
    """Auch über Symlinks nur Pfade innerhalb von ``basis`` zulassen."""
    try:
        p.resolve(strict=False).relative_to(basis.resolve(strict=True))
        return True
    except (OSError, RuntimeError, ValueError):
        return False


def _first_symlink_component(p: Path):
    """Ersten Symlink/Reparse-Point zwischen Tresorwurzel und ``p`` liefern."""
    try:
        teile = Path(os.path.abspath(p)).relative_to(ROOT).parts
    except ValueError:
        return p
    aktuell = ROOT
    for teil in teile:
        aktuell = aktuell / teil
        if _is_path_alias(aktuell):
            return aktuell
    return None


def _safe_regular_file(p: Path) -> bool:
    """Nur echte, einfach verlinkte Dateien innerhalb des Tresors akzeptieren."""
    if _first_symlink_component(p) is not None or not _resolved_within(p, ROOT):
        return False
    try:
        status = os.lstat(str(p))
    except OSError:
        return False
    return stat.S_ISREG(status.st_mode) and status.st_nlink == 1


def _safe_directory(p: Path) -> bool:
    """Nur echte Verzeichnisse ohne Symlink-Komponente akzeptieren."""
    if _first_symlink_component(p) is not None or not _resolved_within(p, ROOT):
        return False
    try:
        return stat.S_ISDIR(os.lstat(str(p)).st_mode)
    except OSError:
        return False


def _safe_relative_path(basis: Path, raw: str):
    """Portablen relativen Pfad unter ``basis`` auflösen.

    Rückgabe: ``(pfad, None)`` oder ``(None, fehlergrund)``.
    """
    original = str(raw)
    wert = original.strip()
    if not wert:
        return None, "Pfad ist leer"
    if wert != original:
        return None, "führende oder abschließende Leerzeichen sind verboten"
    if any(ord(zeichen) < 32 or ord(zeichen) == 127 for zeichen in wert):
        return None, "Steuerzeichen sind in portablen Pfaden verboten"
    if "\\" in wert:
        return None, "Backslashes sind nicht portabel; '/' verwenden"
    raw_pfad = Path(wert)
    if (raw_pfad.is_absolute() or wert.startswith(("/", "\\"))
            or re.match(r"^[A-Za-z]:[\\/]", wert)):
        return None, "absolute Pfade sind verboten"
    if ".." in raw_pfad.parts:
        return None, "'..' ist in Tresor-Pfaden verboten"
    kandidat = basis / raw_pfad
    if not _resolved_within(kandidat, basis):
        return None, "Pfad oder Symlink zeigt aus dem erlaubten Bereich hinaus"
    return kandidat, None


def _safe_output_target(p: Path):
    """Schreibziel und alle Eltern müssen echte Pfade im Tresor sein."""
    try:
        relativ = Path(os.path.abspath(p)).relative_to(ROOT)
    except ValueError:
        return False, "Schreibziel liegt außerhalb des Tresors"
    symlink = _first_symlink_component(p)
    if symlink is not None:
        return False, f"Symlink im Schreibpfad {rel(symlink)!r}"
    if not _resolved_within(p.parent, ROOT):
        return False, "Elternpfad des Schreibziels zeigt aus dem Tresor hinaus"
    if p.exists():
        try:
            status = os.lstat(str(p))
        except OSError as exc:
            return False, f"Schreibziel kann nicht geprüft werden: {exc}"
        if not stat.S_ISREG(status.st_mode):
            return False, "bestehendes Schreibziel ist keine reguläre Datei"
        if status.st_nlink != 1:
            return False, "Schreibziel ist mehrfach hart verlinkt"
    return True, None


def _markdown_link_target(raw: str):
    """Ziel aus der unterstützten Markdown-Link-Untermenge lesen."""
    wert = raw.strip()
    if not wert:
        return None, "leeres Linkziel"
    rest = ""
    if wert.startswith("<"):
        ende = wert.find(">")
        if ende < 0:
            return None, "nicht geschlossenes '<...>'-Linkziel"
        ziel, rest = wert[1:ende], wert[ende + 1:].strip()
    else:
        teile = wert.split(maxsplit=1)
        ziel = teile[0]
        rest = teile[1].strip() if len(teile) == 2 else ""
    if rest:
        gueltiger_titel = (
            len(rest) >= 2
            and ((rest[0] == rest[-1] and rest[0] in "\"'")
                 or (rest[0] == "(" and rest[-1] == ")"))
        )
        if not gueltiger_titel:
            return None, "nicht unterstützte Linksyntax nach dem Ziel"
    return ziel, None


def _quarantine_payloads():
    """Nicht freigegebene Dateien/Ordner in der Quarantäne."""
    if not _safe_directory(QUARANTINE):
        return [QUARANTINE]
    return sorted(
        (p for p in QUARANTINE.iterdir()
         if not (p.name == "README.md" and _safe_regular_file(p))),
        key=lambda p: p.name,
    )


def _walk_tree_no_links(start: Path):
    """Deterministischer Baumlauf, der Symlinks/Junctions nie rekursiv folgt."""
    if not _safe_directory(start):
        return []
    ergebnis, stapel = [], [start]
    while stapel:
        ordner = stapel.pop()
        try:
            with os.scandir(str(ordner)) as scan:
                eintraege = sorted(scan, key=lambda e: e.name, reverse=True)
        except OSError as exc:
            raise OSError(f"{rel(ordner)}: Verzeichnis kann nicht gelesen werden — {exc}") from exc
        for eintrag in eintraege:
            p = Path(eintrag.path)
            ergebnis.append(p)
            try:
                status = eintrag.stat(follow_symlinks=False)
            except OSError as exc:
                raise OSError(
                    f"{rel(p)}: Verzeichniseintrag kann nicht geprüft werden — {exc}"
                ) from exc
            reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
            attributes = getattr(status, "st_file_attributes", 0)
            alias = stat.S_ISLNK(status.st_mode) or bool(attributes & reparse_flag)
            if stat.S_ISDIR(status.st_mode) and not alias:
                stapel.append(p)
    return sorted(ergebnis, key=lambda p: rel(p))


def _skill_symlinks():
    """Symlinks/Junctions sind im portablen Skill-Artefakt verboten."""
    return [p for p in _walk_tree_no_links(ROOT) if _is_path_alias(p)]


def _skill_hardlinks():
    """Mehrfach hart verlinkte Dateien umgehen die Ordnergrenze."""
    ergebnis = []
    for p in _walk_tree_no_links(ROOT):
        if _is_path_alias(p):
            continue
        try:
            status = os.lstat(str(p))
            if stat.S_ISREG(status.st_mode) and status.st_nlink != 1:
                ergebnis.append(p)
        except OSError:
            continue
    return sorted(ergebnis, key=lambda p: rel(p))


def iter_pages():
    if not _safe_directory(KNOWLEDGE):
        return []
    return sorted(
        (p for p in _walk_tree_no_links(KNOWLEDGE)
         if p.suffix == ".md" and _safe_regular_file(p)),
        key=lambda p: rel(p),
    )


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
        if key in fm:
            fehler.append(f"{quelle}:{i + 1}: Frontmatter-Schlüssel {key!r} ist doppelt")
            i += 1
            continue
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
    if not _safe_regular_file(TYPES):
        return {}, [], [f"{rel(TYPES)}: fehlt oder ist keine reguläre Datei "
                        f"— Typ-Registry ist Pflicht"]
    typen, reltypen, aktuell = {}, [], None
    reltypen_gesehen = False
    for n, line in enumerate(read(TYPES).split("\n"), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" "):
            if ":" not in line:
                fehler.append(f"{rel(TYPES)}:{n}: Top-Level-Zeile ohne ':'")
                aktuell = None
                continue
            key, _, val = line.partition(":")
            key, val = key.strip(), val.strip()
            if key == "_relationstypen":
                if reltypen_gesehen:
                    fehler.append(f"{rel(TYPES)}:{n}: _relationstypen ist doppelt definiert")
                reltypen_gesehen = True
                if not (val.startswith("[") and val.endswith("]")):
                    fehler.append(f"{rel(TYPES)}:{n}: _relationstypen muss "
                                  f"eine Inline-Liste '[a, b]' sein")
                    inner = ""
                else:
                    inner = val[1:-1].strip()
                reltypen = [x.strip() for x in inner.split(",") if x.strip()]
                if len(reltypen) != len(set(reltypen)):
                    fehler.append(f"{rel(TYPES)}:{n}: doppelte Relationstypen")
                for rtyp in reltypen:
                    if not re.match(r"^[a-z][a-z0-9_]*$", rtyp):
                        fehler.append(f"{rel(TYPES)}:{n}: ungültiger Relationstyp {rtyp!r}")
                aktuell = None
            elif val == "":
                if not re.match(r"^[a-z][a-z0-9_-]*$", key):
                    fehler.append(f"{rel(TYPES)}:{n}: ungültiger Typname {key!r}")
                    aktuell = None
                    continue
                if key in typen:
                    fehler.append(f"{rel(TYPES)}:{n}: Typ {key!r} ist doppelt definiert")
                    aktuell = None
                    continue
                aktuell = key
                typen[aktuell] = {}
            else:
                fehler.append(f"{rel(TYPES)}:{n}: Top-Level braucht 'typname:' ohne Wert")
        elif line.startswith("  ") and aktuell:
            if ":" not in line.strip():
                fehler.append(f"{rel(TYPES)}:{n}: Typfeld ohne ':'")
                continue
            key, _, val = line.strip().partition(":")
            key = key.strip()
            if key in typen[aktuell]:
                fehler.append(f"{rel(TYPES)}:{n}: Feld {key!r} in Typ {aktuell!r} ist doppelt")
                continue
            typen[aktuell][key] = val.strip().strip('"')
        else:
            fehler.append(f"{rel(TYPES)}:{n}: Einrückung außerhalb der Profil-Untermenge")

    if not typen:
        fehler.append(f"{rel(TYPES)}: keine Typen registriert — fail-closed")
    if not reltypen_gesehen or not reltypen:
        fehler.append(f"{rel(TYPES)}: _relationstypen fehlt oder ist leer — fail-closed")
    for typ, felder in sorted(typen.items()):
        fehlend = sorted(TYPE_REQUIRED_FIELDS - set(felder))
        unbekannt = sorted(set(felder) - TYPE_REQUIRED_FIELDS)
        leer = sorted(k for k in TYPE_REQUIRED_FIELDS & set(felder) if not felder[k].strip())
        if fehlend:
            fehler.append(f"{rel(TYPES)}: Typ {typ!r} ohne Pflichtfelder {fehlend}")
        if unbekannt:
            fehler.append(f"{rel(TYPES)}: Typ {typ!r} mit unbekannten Feldern {unbekannt}")
        if leer:
            fehler.append(f"{rel(TYPES)}: Typ {typ!r} mit leeren Pflichtfeldern {leer}")
    return typen, reltypen, fehler


def _retrieval_norm(value):
    """Versionierte Unicode-Normalisierung nur für Hybrid-Retrieval."""
    text = unicodedata.normalize("NFKC", str(value)).casefold()
    text = (text.replace("ä", "ae").replace("ö", "oe")
            .replace("ü", "ue").replace("ß", "ss"))
    text = "".join(char if char.isalnum() else " " for char in text)
    return re.sub(r"\s+", " ", text).strip()


def _retrieval_tokens(value):
    return tuple(
        token for token in _retrieval_norm(value).split()
        if token not in RETRIEVAL_STOPWORDS and (len(token) >= 2 or token.isdigit())
    )


def _phrase_present(haystack, needle):
    """Normalisierte Phrase nur an Token-Grenzen finden."""
    return bool(needle) and f" {needle} " in f" {haystack} "


def parse_concepts():
    """Strikte, beleggebundene Begriffswelten-Registry lesen."""
    errors = []
    data = _load_strict_json(CONCEPTS, rel(CONCEPTS), errors)
    if data is None:
        return {}, {}, errors
    if not _exact_keys(
            data, {"schema", "worlds", "concepts"}, set(),
            rel(CONCEPTS), errors):
        return {}, {}, errors
    if data.get("schema") != CONCEPT_SCHEMA:
        errors.append(
            f"{rel(CONCEPTS)}: schema muss {CONCEPT_SCHEMA!r} sein"
        )
    worlds_raw = data.get("worlds")
    concepts_raw = data.get("concepts")
    if not isinstance(worlds_raw, list):
        errors.append(f"{rel(CONCEPTS)}.worlds: Liste erwartet")
        worlds_raw = []
    if not isinstance(concepts_raw, list):
        errors.append(f"{rel(CONCEPTS)}.concepts: Liste erwartet")
        concepts_raw = []
    if len(worlds_raw) > 128:
        errors.append(f"{rel(CONCEPTS)}.worlds: höchstens 128 Einträge")
    if len(concepts_raw) > 10000:
        errors.append(f"{rel(CONCEPTS)}.concepts: höchstens 10000 Einträge")

    worlds = {}
    for index, item in enumerate(worlds_raw, 1):
        field = f"{rel(CONCEPTS)}.worlds[{index}]"
        if not _exact_keys(
                item, {"id", "name", "description"}, set(), field, errors):
            continue
        wid = item.get("id")
        if not isinstance(wid, str) or not WORLD_ID_RE.fullmatch(wid):
            errors.append(f"{field}.id: erwartet BW-nnnn")
            continue
        if wid in worlds:
            errors.append(f"{field}.id: Begriffswelt-ID {wid} ist doppelt")
            continue
        _plain_text(item.get("name"), f"{field}.name", errors, maximum=120)
        _plain_text(
            item.get("description"), f"{field}.description", errors, maximum=500
        )
        worlds[wid] = item

    concepts = {}
    required = {
        "id", "world", "preferred", "aliases", "broader", "related",
        "definition_claim",
    }
    for index, item in enumerate(concepts_raw, 1):
        field = f"{rel(CONCEPTS)}.concepts[{index}]"
        if not _exact_keys(item, required, set(), field, errors):
            continue
        cid = item.get("id")
        if not isinstance(cid, str) or not CONCEPT_ID_RE.fullmatch(cid):
            errors.append(f"{field}.id: erwartet B-nnnn")
            continue
        if cid in concepts:
            errors.append(f"{field}.id: Begriff-ID {cid} ist doppelt")
            continue
        world = item.get("world")
        if (not isinstance(world, str)
                or not WORLD_ID_RE.fullmatch(world)
                or world not in worlds):
            errors.append(f"{field}.world: unbekannte Begriffswelt {world!r}")
        _plain_text(
            item.get("preferred"), f"{field}.preferred", errors, maximum=160
        )
        definition_claim = item.get("definition_claim")
        if (not isinstance(definition_claim, str)
                or not CID_RE.fullmatch(definition_claim)):
            errors.append(f"{field}.definition_claim: erwartet C-nnnn")
        for list_name in ("aliases", "broader", "related"):
            values = item.get(list_name)
            if not isinstance(values, list):
                errors.append(f"{field}.{list_name}: Liste erwartet")
                item[list_name] = []
                continue
            if len(values) > 32:
                errors.append(f"{field}.{list_name}: höchstens 32 Einträge")
            if len(values) != len(set(
                    value for value in values if isinstance(value, str))):
                errors.append(f"{field}.{list_name}: doppelte Einträge")
            for number, value in enumerate(values, 1):
                value_field = f"{field}.{list_name}[{number}]"
                if list_name == "aliases":
                    _plain_text(value, value_field, errors, maximum=160)
                elif not isinstance(value, str) or not CONCEPT_ID_RE.fullmatch(value):
                    errors.append(f"{value_field}: erwartet B-nnnn")
        concepts[cid] = item

    labels_by_world = {}
    for cid, concept in sorted(concepts.items()):
        world = concept.get("world")
        for target_type in ("broader", "related"):
            for target in concept.get(target_type, []):
                if not isinstance(target, str):
                    continue
                if target == cid:
                    errors.append(
                        f"{rel(CONCEPTS)}: {cid} hat eine {target_type}-Selbstkante"
                    )
                elif target not in concepts:
                    errors.append(
                        f"{rel(CONCEPTS)}: {cid}.{target_type} verweist auf "
                        f"unbekannten Begriff {target}"
                    )
                elif concepts[target].get("world") != world:
                    errors.append(
                        f"{rel(CONCEPTS)}: {cid}.{target_type} darf die "
                        f"Begriffswelt nicht verlassen ({target})"
                    )
        seen_here = set()
        labels = [concept.get("preferred", "")] + concept.get("aliases", [])
        for label in labels:
            if not isinstance(label, str):
                continue
            normalized = _retrieval_norm(label)
            if not normalized:
                errors.append(f"{rel(CONCEPTS)}: {cid} enthält einen leeren Suchbegriff")
                continue
            if normalized in seen_here:
                errors.append(
                    f"{rel(CONCEPTS)}: {cid} enthält den Suchbegriff "
                    f"{normalized!r} mehrfach"
                )
                continue
            seen_here.add(normalized)
            key = (
                world if isinstance(world, str) else "<invalid-world>",
                normalized,
            )
            previous = labels_by_world.get(key)
            if previous and previous != cid:
                errors.append(
                    f"{rel(CONCEPTS)}: Suchbegriff {normalized!r} kollidiert "
                    f"in {world} zwischen {previous} und {cid}"
                )
            else:
                labels_by_world[key] = cid

    # ``broader`` ist gerichtet und muss azyklisch bleiben. Kahn statt
    # rekursiver DFS: auch die maximal erlaubte Registry kann nicht am
    # Python-Recursionlimit vorbeilaufen.
    outgoing = {cid: [] for cid in concepts}
    indegree = {cid: 0 for cid in concepts}
    for cid, concept in sorted(concepts.items()):
        for target in concept.get("broader", []):
            if isinstance(target, str) and target in concepts and target != cid:
                outgoing[cid].append(target)
                indegree[target] += 1
    ready = [cid for cid, degree in indegree.items() if degree == 0]
    heapq.heapify(ready)
    processed = 0
    while ready:
        cid = heapq.heappop(ready)
        processed += 1
        for target in sorted(outgoing[cid]):
            indegree[target] -= 1
            if indegree[target] == 0:
                heapq.heappush(ready, target)
    if processed != len(concepts):
        cycle_nodes = sorted(
            cid for cid, degree in indegree.items() if degree > 0
        )
        preview = ", ".join(cycle_nodes[:20])
        suffix = " …" if len(cycle_nodes) > 20 else ""
        errors.append(
            f"{rel(CONCEPTS)}: broader-Zyklus in {preview}{suffix}"
        )
    return worlds, concepts, errors


def parse_register():
    """sources/REGISTER.md-Tabelle lesen.

    Spalten: | ID | Titel | Stand/Version | SHA-256 | Trust | Rechte | Ablage |
    Rückgabe: (dict sid -> zeile, fehler)
    """
    fehler, reg = [], {}
    if not _safe_regular_file(REGISTER):
        return {}, [f"{rel(REGISTER)}: fehlt oder ist keine reguläre Datei "
                    f"— Quellenregister ist Pflicht"]
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
            continue
        for feldname, wert in (("Titel", titel), ("Stand/Version", stand),
                               ("Trust", trust), ("Rechte", rechte), ("Ablage", ablage)):
            if not wert:
                fehler.append(f"{rel(REGISTER)}:{n}: Feld {feldname} ist leer")
        reg[sid] = {"titel": titel, "stand": stand, "hash": h,
                    "trust": trust, "rechte": rechte, "ablage": ablage, "zeile": n}
    return reg, fehler


def parse_media_representations(register):
    """Manifestierbare Bild-/PDF-Repräsentationen streng validieren.

    Die Repräsentationen sind nur Fundstellen-Metadaten. Ihr ``text`` wird
    niemals direkt vom Query-Pfad als Evidenz ausgegeben.
    """
    errors, representations = [], {}
    if not _safe_directory(DERIVED):
        return {}, [
            f"{rel(DERIVED)}: fehlt oder enthält eine unsichere "
            f"Symlink-Komponente"
        ]
    try:
        entries = sorted(DERIVED.iterdir(), key=lambda path: path.name)
    except OSError as exc:
        return {}, [f"{rel(DERIVED)}: kann nicht gelesen werden — {exc}"]

    for path in entries:
        if path.name == "README.md" and _safe_regular_file(path):
            continue
        rp = rel(path)
        if not _safe_regular_file(path):
            errors.append(f"{rp}: nur einfach verlinkte reguläre Dateien erlaubt")
            continue
        match = re.fullmatch(r"(S-\d{4})__media\.json", path.name)
        if not match:
            errors.append(
                f"{rp}: erwartet Dateiname S-nnnn__media.json "
                f"(README.md ist die einzige Ausnahme)"
            )
            continue
        filename_sid = match.group(1)
        data = _load_strict_json(path, rp, errors)
        if data is None:
            continue
        required = {
            "schema", "source_id", "source_sha256", "media_type", "language",
            "extractor", "verified", "alt_text", "regions",
        }
        if not _exact_keys(data, required, set(), rp, errors):
            continue
        if data.get("schema") != MEDIA_SCHEMA:
            errors.append(f"{rp}.schema: erwartet {MEDIA_SCHEMA!r}")
        sid = data.get("source_id")
        if not isinstance(sid, str) or not SID_RE.fullmatch(sid):
            errors.append(f"{rp}.source_id: erwartet S-nnnn")
            continue
        if sid != filename_sid:
            errors.append(
                f"{rp}.source_id: {sid!r} passt nicht zu {filename_sid}"
            )
            continue
        if sid in representations:
            errors.append(f"{rp}: Repräsentation für {sid} ist doppelt")
            continue
        if sid not in register:
            errors.append(f"{rp}.source_id: Quelle {sid!r} fehlt im REGISTER")
            continue
        source_hash = data.get("source_sha256")
        if source_hash != register[sid].get("hash"):
            errors.append(
                f"{rp}.source_sha256: stimmt nicht mit REGISTER {sid} überein"
            )
        source_path, path_error = _safe_relative_path(
            ROOT, register[sid].get("ablage", "")
        )
        if path_error:
            errors.append(f"{rp}: Quellenpfad ist unzulässig — {path_error}")
            continue
        expected_type = MEDIA_TYPES.get(source_path.suffix.lower())
        media_type = data.get("media_type")
        if expected_type is None:
            errors.append(
                f"{rp}: {source_path.suffix or '(ohne Endung)'} ist kein "
                f"unterstütztes Bild-/PDF-Format"
            )
        elif media_type != expected_type:
            errors.append(
                f"{rp}.media_type: erwartet {expected_type!r} für "
                f"{source_path.name}"
            )
        elif source_path.is_file() and not _media_signature_matches(
                source_path, expected_type):
            errors.append(
                f"{rp}: Dateisignatur von {source_path.name} passt nicht zu "
                f"{expected_type}"
            )
        language = data.get("language")
        if (not isinstance(language, str)
                or not re.fullmatch(r"(?:und|[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*)",
                                    language)):
            errors.append(f"{rp}.language: BCP-47-Kurzform oder 'und' erwartet")
        _plain_text(data.get("alt_text"), f"{rp}.alt_text", errors, maximum=1000)
        if (isinstance(data.get("alt_text"), str)
                and PROMPT_INJECTION_RE.search(data["alt_text"])):
            errors.append(
                f"{rp}.alt_text: offensichtliche Instruktionssignatur ist "
                f"als Alttext verboten"
            )

        extractor = data.get("extractor")
        if _exact_keys(
                extractor, {"kind", "name", "version"}, set(),
                f"{rp}.extractor", errors):
            if (not isinstance(extractor.get("kind"), str)
                    or extractor.get("kind") not in EXTRACTOR_KINDS):
                errors.append(
                    f"{rp}.extractor.kind: erwartet "
                    f"{sorted(EXTRACTOR_KINDS)}"
                )
            _plain_text(
                extractor.get("name"), f"{rp}.extractor.name", errors, maximum=120
            )
            _plain_text(
                extractor.get("version"), f"{rp}.extractor.version",
                errors, maximum=80
            )
        if data.get("verified") is not True:
            errors.append(
                f"{rp}.verified: muss nach Sicht-/Qualitätsprüfung true sein"
            )

        regions_raw = data.get("regions")
        if not isinstance(regions_raw, list) or not regions_raw:
            errors.append(f"{rp}.regions: nicht leere Liste erwartet")
            regions_raw = []
        if len(regions_raw) > 1000:
            errors.append(f"{rp}.regions: höchstens 1000 Regionen")
        regions = {}
        region_required = {
            "id", "kind", "locator", "text", "confidence", "bbox",
            "suspicious_instruction",
        }
        for index, region in enumerate(regions_raw, 1):
            field = f"{rp}.regions[{index}]"
            if not _exact_keys(region, region_required, set(), field, errors):
                continue
            rid = region.get("id")
            if not isinstance(rid, str) or not REGION_ID_RE.fullmatch(rid):
                errors.append(f"{field}.id: erwartet R-nnnn")
                continue
            if rid in regions:
                errors.append(f"{field}.id: Region {rid} ist doppelt")
                continue
            if (not isinstance(region.get("kind"), str)
                    or region.get("kind") not in REGION_KINDS):
                errors.append(f"{field}.kind: erwartet {sorted(REGION_KINDS)}")
            _plain_text(
                region.get("locator"), f"{field}.locator", errors, maximum=500
            )
            _plain_text(
                region.get("text"), f"{field}.text", errors, maximum=20000
            )
            confidence = region.get("confidence")
            if (isinstance(confidence, bool)
                    or not isinstance(confidence, (int, float))
                    or not 0 <= confidence <= 1):
                errors.append(f"{field}.confidence: Zahl zwischen 0 und 1 erwartet")
            suspicious = region.get("suspicious_instruction")
            if not isinstance(suspicious, bool):
                errors.append(f"{field}.suspicious_instruction: Boolean erwartet")
            elif (
                    any(
                        isinstance(region.get(key), str)
                        and PROMPT_INJECTION_RE.search(region[key])
                        for key in ("text", "locator")
                    )
                    and suspicious is not True):
                errors.append(
                    f"{field}: offensichtliche Instruktionssignatur muss "
                    f"als suspicious_instruction=true markiert sein"
                )
            bbox = region.get("bbox")
            if bbox is not None:
                valid_bbox = (
                    isinstance(bbox, list) and len(bbox) == 4
                    and all(
                        not isinstance(value, bool)
                        and isinstance(value, (int, float))
                        for value in bbox
                    )
                )
                if valid_bbox:
                    x, y, width, height = bbox
                    valid_bbox = (
                        0 <= x <= 1 and 0 <= y <= 1
                        and 0 < width <= 1 and 0 < height <= 1
                        and x + width <= 1.000000001
                        and y + height <= 1.000000001
                    )
                if not valid_bbox:
                    errors.append(
                        f"{field}.bbox: null oder normalisierte "
                        f"[x,y,breite,höhe] innerhalb 0..1 erwartet"
                    )
            regions[rid] = region
        representations[sid] = {
            "path": rp,
            "source_id": sid,
            "source_sha256": source_hash,
            "media_type": media_type,
            "language": language,
            "alt_text": data.get("alt_text"),
            "regions": regions,
        }

    for sid, entry in sorted(register.items()):
        source_path, path_error = _safe_relative_path(ROOT, entry.get("ablage", ""))
        if path_error:
            continue
        suffix = source_path.suffix.lower()
        if suffix in ACTIVE_MEDIA_SUFFIXES:
            errors.append(
                f"REGISTER {sid}: aktive Bildformate wie SVG sind nicht erlaubt; "
                f"lokal in PNG/JPEG rasterisieren und neu registrieren"
            )
        elif suffix in MEDIA_TYPES and sid not in representations:
            errors.append(
                f"REGISTER {sid}: Bild-/PDF-Quelle braucht "
                f"sources/derived/{sid}__media.json"
            )
    return representations, errors


def parse_router():
    """ROUTER.md lesen. Rückgabe: (dict domain -> {schlagworte, seiten}, fehler)"""
    fehler, router, dom = [], {}, None
    if not _safe_regular_file(ROUTER):
        return {}, [f"{rel(ROUTER)}: fehlt oder ist keine reguläre Datei "
                    f"— Schlagwort-Router ist Pflicht"]
    for n, line in enumerate(read(ROUTER).split("\n"), 1):
        s = line.strip()
        if s.startswith("## "):
            dom = s[3:].strip()
            if dom in router:
                fehler.append(f"{rel(ROUTER)}:{n}: Domäne {dom!r} ist doppelt definiert")
                dom = None
                continue
            router[dom] = {"schlagworte": [], "seiten": [], "zeile": n}
        elif dom and s.startswith("schlagworte:"):
            router[dom]["schlagworte"] = [
                w.strip().lower() for w in s.split(":", 1)[1].split(",") if w.strip()]
        elif dom and s.startswith("- knowledge/"):
            router[dom]["seiten"].append(s[2:].strip())
    return router, fehler


# ---------------------------------------------------------------- Seiten

def lade_seiten(register, typen, reltypen, concepts=None, media=None):
    """Alle Wissensseiten laden und prüfen. Rückgabe: (seiten, claims, fehler, warnungen)."""
    concepts = concepts or {}
    media = media or {}
    fehler, warnungen, seiten, alle_claims = [], [], {}, {}
    for p in iter_pages():
        rp = rel(p)
        if not _resolved_within(p, KNOWLEDGE):
            fehler.append(f"{rp}: Datei oder Symlink zeigt aus knowledge/ hinaus")
            continue
        fm, body, fm_fehler, offset = parse_frontmatter(read(p), rp)
        fehler.extend(fm_fehler)

        unbekannt = sorted(
            set(fm) - set(REQUIRED_FIELDS) - OPTIONAL_FIELDS
        )
        if unbekannt:
            fehler.append(f"{rp}: unbekannte Frontmatter-Felder {unbekannt}")
        for feld in REQUIRED_FIELDS:
            if feld not in fm or fm[feld] in ("", []):
                fehler.append(f"{rp}: Pflichtfeld {feld!r} fehlt oder ist leer")
        for feld in LIST_FIELDS:
            if feld in fm and not isinstance(fm[feld], list):
                fehler.append(f"{rp}: Frontmatter-Feld {feld!r} muss eine Liste sein")
        for feld in set(REQUIRED_FIELDS) - LIST_FIELDS:
            if feld in fm and not isinstance(fm[feld], str):
                fehler.append(f"{rp}: Frontmatter-Feld {feld!r} muss Text sein")
        typ = fm.get("type", "")
        if typ and typ not in typen:
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
        if not isinstance(quellen, list):
            quellen = []
        for sid in quellen:
            if not isinstance(sid, str) or not SID_RE.fullmatch(sid):
                fehler.append(f"{rp}: ungültige Quellen-ID {sid!r}")
            elif sid not in register:
                fehler.append(f"{rp}: Quelle {sid} steht nicht im Register")
        tags = fm.get("tags", [])
        if isinstance(tags, list):
            for tag in tags:
                if not isinstance(tag, str) or not _retrieval_norm(tag):
                    fehler.append(f"{rp}: ungültiger oder leerer Tag {tag!r}")
        concept_ids = fm.get("concepts", [])
        if not isinstance(concept_ids, list):
            concept_ids = []
        if len(concept_ids) != len(set(
                item for item in concept_ids if isinstance(item, str))):
            fehler.append(f"{rp}: doppelte IDs in concepts")
        for concept_id in concept_ids:
            if (not isinstance(concept_id, str)
                    or not CONCEPT_ID_RE.fullmatch(concept_id)):
                fehler.append(f"{rp}: concepts enthält ungültige ID {concept_id!r}")
            elif concept_id not in concepts:
                fehler.append(f"{rp}: Begriff {concept_id} fehlt in schema/begriffswelten.json")

        # Claims (Grammatik siehe schema/profil.md)
        claims = []
        for bn, line in enumerate(body.split("\n"), 1):
            n = offset + bn
            if not line.startswith(CLAIM_START):
                continue
            m = CLAIM_RE.match(line)
            if not m:
                fehler.append(f"{rp}:{n}: Claim-Zeile verletzt die Grammatik "
                              f"'- **C-nnnn** [S-nnnn | Fundstelle | "
                              f"Wortlaut|Beobachtung|Auslegung] Text'")
                continue
            cid, sid, fundstelle, art, text = m.groups()
            fundstelle = fundstelle.strip()
            text = text.strip()
            _plain_text(
                fundstelle, f"{rp}:{n}: {cid} Fundstelle", fehler, maximum=1000
            )
            _plain_text(
                text, f"{rp}:{n}: {cid} Aussagetext", fehler, maximum=20000
            )
            for feld, wert in (("Fundstelle", fundstelle), ("Aussagetext", text)):
                if PROMPT_INJECTION_RE.search(wert):
                    fehler.append(
                        f"{rp}:{n}: {cid} {feld} enthält eine offensichtliche "
                        "Instruktionssignatur und darf nicht als Claim "
                        "freigegeben werden"
                    )
            if cid in alle_claims:
                fehler.append(f"{rp}:{n}: Claim-ID {cid} bereits vergeben "
                              f"in {alle_claims[cid]['seite']}")
            if sid not in register:
                fehler.append(f"{rp}:{n}: {cid} verweist auf unregistrierte Quelle {sid}")
            elif sid not in quellen:
                fehler.append(f"{rp}:{n}: {cid} nutzt {sid}, aber {sid} fehlt in "
                              f"'sources:' des Frontmatters")
            region_id = None
            region_ids = re.findall(r"(?<![A-Za-z0-9])R-\d{4}(?![A-Za-z0-9])",
                                    fundstelle)
            if sid in media:
                if len(region_ids) != 1:
                    fehler.append(
                        f"{rp}:{n}: {cid} auf Bild/PDF {sid} braucht genau "
                        f"eine Region R-nnnn in der Fundstelle"
                    )
                else:
                    region_id = region_ids[0]
                    region = media[sid]["regions"].get(region_id)
                    if region is None:
                        fehler.append(
                            f"{rp}:{n}: {cid} verweist auf unbekannte Region "
                            f"{region_id} in {sid}"
                        )
                    elif region.get("suspicious_instruction") is True:
                        fehler.append(
                            f"{rp}:{n}: {cid} darf verdächtige Region "
                            f"{region_id} nicht als Evidenz nutzen"
                        )
            elif region_ids:
                fehler.append(
                    f"{rp}:{n}: {cid} nennt eine Region, aber {sid} ist "
                    f"keine registrierte Bild-/PDF-Repräsentation"
                )
            if art == "Beobachtung" and sid not in media:
                fehler.append(
                    f"{rp}:{n}: {cid} nutzt Beobachtung ohne Bild-/PDF-Quelle"
                )
            eintrag = {"id": cid, "quelle": sid, "fundstelle": fundstelle,
                       "art": art, "text": text, "seite": rp,
                       "region": region_id}
            claims.append(eintrag)
            alle_claims[cid] = eintrag
        if not claims:
            warnungen.append(f"{rp}: keine Claims — Kurzfassung wäre unbelegt")

        # Relationen (typisierte Kanten; dürfen Domänen überschreiten)
        relationen = []
        rels = fm.get("relations", [])
        if not isinstance(rels, list):
            rels = []
        for r in rels:
            m = REL_RE.match(r)
            if not m:
                fehler.append(f"{rp}: relation {r!r} verletzt das Format 'typ -> domäne/seite.md'")
                continue
            rtyp, ziel = m.group(1), m.group(2).strip()
            if rtyp not in reltypen:
                fehler.append(f"{rp}: Relationstyp {rtyp!r} nicht in _relationstypen "
                              f"(types.yaml) — erst dort deklarieren")
            ziel_rel = Path(ziel)
            if len(ziel_rel.parts) != 2 or ziel_rel.suffix != ".md":
                fehler.append(f"{rp}: Relationsziel {ziel!r} muss "
                              f"'domäne/seite.md' entsprechen")
                continue
            zielpfad, pfadfehler = _safe_relative_path(KNOWLEDGE, ziel)
            if pfadfehler:
                fehler.append(f"{rp}: Relationsziel {ziel!r} unzulässig — {pfadfehler}")
                continue
            if not zielpfad.is_file():
                fehler.append(f"{rp}: Relationsziel knowledge/{ziel} existiert nicht")
                continue
            relationen.append({"typ": rtyp, "ziel": "knowledge/" + ziel})

        # Links im Fließtext: Inline- und Referenzziele werden geprüft;
        # HTML-Links bleiben außerhalb der bewusst kleinen Markdown-Untermenge.
        if HTML_LINK_RE.search(body):
            fehler.append(f"{rp}: HTML-Links/-Bilder sind nicht unterstützt — "
                          f"portable Markdown-Linksyntax verwenden")
        link_kandidaten = [m.group(1) for m in LINK_RE.finditer(body)]
        link_kandidaten += [m.group(1) for m in REFERENCE_LINK_RE.finditer(body)]
        for link_raw in link_kandidaten:
            ziel, linkfehler = _markdown_link_target(link_raw)
            if linkfehler:
                fehler.append(f"{rp}: Markdown-Link unzulässig — {linkfehler}")
                continue
            if ziel.startswith(("http://", "https://", "mailto:", "#")):
                continue
            dateiziel = ziel.split("#", 1)[0]
            aufgeloest, pfadfehler = _safe_relative_path(p.parent, dateiziel)
            if pfadfehler:
                fehler.append(f"{rp}: Markdown-Link {ziel!r} unzulässig — {pfadfehler}")
                continue
            if aufgeloest.is_symlink():
                fehler.append(f"{rp}: Markdown-Link {ziel!r} zeigt auf einen Symlink")
                continue
            if not aufgeloest.is_file():
                fehler.append(f"{rp}: toter Link {ziel!r}")
                continue

        seiten[rp] = {
            "fm": fm, "claims": claims, "relationen": relationen, "pfad": p,
            "zeilen": len(body.split("\n")), "body": body,
        }

    for rp, seite in sorted(seiten.items()):
        for relation in seite["relationen"]:
            if relation["ziel"] not in seiten:
                fehler.append(f"{rp}: Relationsziel {relation['ziel']} ist keine "
                              f"validierte Wissensseite")
    return seiten, alle_claims, fehler, warnungen


# ------------------------------------------------------------- Kommandos

def cmd_validate(still=False):
    typen, reltypen, fehler = parse_types()
    register, f2 = parse_register()
    fehler += f2
    _, concepts, concept_errors = parse_concepts()
    fehler += concept_errors
    media, media_errors = parse_media_representations(register)
    fehler += media_errors

    try:
        for p in _skill_symlinks():
            fehler.append(f"{rel(p)}: Symlink im Tresor verboten — "
                          f"portable Releases enthalten nur echte Dateien/Ordner")
        for p in _skill_hardlinks():
            fehler.append(f"{rel(p)}: mehrfach hart verlinkte Datei im Tresor verboten "
                          f"— Inhalt könnte außerhalb der Ordnergrenze verändert werden")
    except OSError as exc:
        fehler.append(f"Tresorbaum kann nicht vollständig geprüft werden — {exc}")
    for p in _quarantine_payloads():
        fehler.append(f"{rel(p)}: Quarantäne fehlt, ist unsicher oder nicht leer — "
                      f"ungeprüfte Inhalte vor Validierung freigeben oder entfernen")

    # Registerzeilen materiell prüfen: Ablage existiert, ist eindeutig und Hash stimmt
    registrierte_ablagen = {}
    for sid, r in sorted(register.items()):
        if r["trust"] not in TRUST_WERTE:
            fehler.append(f"REGISTER {sid}: Trust muss T1/T2/T3 sein")
        if r["rechte"].strip().upper() in {
                "", "-", "?", "N/A", "NA", "RECHTE", "TODO", "TBD",
                "OFFEN", "UNKLAR", "UNGEKLÄRT", "UNKNOWN"}:
            fehler.append(f"REGISTER {sid}: Rechte müssen vor Ingest eindeutig geklärt sein")
        if not HASH_RE.match(r["hash"]):
            fehler.append(f"REGISTER {sid}: SHA-256 hat kein gültiges Format")
        ablage, pfadfehler = _safe_relative_path(ROOT, r["ablage"])
        if pfadfehler:
            fehler.append(f"REGISTER {sid}: Ablage {r['ablage']!r} unzulässig — "
                          f"{pfadfehler}")
            continue
        if ablage.parent != RAW or not ablage.name.startswith(f"{sid}__"):
            fehler.append(f"REGISTER {sid}: Ablage muss direkt unter sources/raw/ liegen "
                          f"und mit '{sid}__' beginnen")
            continue
        if ablage.is_symlink():
            fehler.append(f"REGISTER {sid}: Ablage darf kein Symlink sein")
            continue
        if ablage in registrierte_ablagen:
            fehler.append(f"REGISTER {sid}: Ablage wird bereits von "
                          f"{registrierte_ablagen[ablage]} verwendet")
            continue
        registrierte_ablagen[ablage] = sid
        if not ablage.is_file():
            fehler.append(f"REGISTER {sid}: Ablage {r['ablage']} existiert nicht")
        else:
            if HASH_RE.match(r["hash"]) and sha256_file(ablage) != r["hash"]:
                fehler.append(f"REGISTER {sid}: Hash der Ablage weicht vom Register ab "
                              f"— Quelle wurde nach Registrierung verändert")
            expected_media = MEDIA_TYPES.get(ablage.suffix.lower())
            detected_media = _detected_media_type(ablage)
            if detected_media and expected_media != detected_media:
                fehler.append(
                    f"REGISTER {sid}: Dateisignatur ist {detected_media}, aber "
                    f"Endung {ablage.suffix or '(keine)'} ist dafür nicht erlaubt "
                    f"— Quelle nicht als Text tarnen"
                )
            elif expected_media and detected_media != expected_media:
                fehler.append(
                    f"REGISTER {sid}: Endung {ablage.suffix} erwartet "
                    f"{expected_media}, Dateisignatur passt nicht"
                )

    if _safe_directory(RAW):
        try:
            raw_baum = _walk_tree_no_links(RAW)
            raw_eintraege = sorted(
                (p for p in raw_baum if _safe_regular_file(p) or _is_path_alias(p)),
                key=lambda p: rel(p),
            )
            for p in raw_eintraege:
                if p not in registrierte_ablagen:
                    fehler.append(f"{rel(p)}: Rohquelle ist nicht eindeutig im REGISTER erfasst")
            for p in sorted(
                    (p for p in raw_baum if _safe_directory(p)),
                    key=lambda p: rel(p)):
                if p != RAW:
                    fehler.append(f"{rel(p)}: Unterordner in sources/raw/ sind nicht erlaubt")
        except OSError as exc:
            fehler.append(f"sources/raw: Baum kann nicht vollständig geprüft werden — {exc}")
    else:
        fehler.append("sources/raw: fehlt oder enthält eine unsichere Symlink-Komponente")

    if _safe_directory(KNOWLEDGE):
        try:
            for p in _walk_tree_no_links(KNOWLEDGE):
                if (_safe_regular_file(p) or _is_path_alias(p)) and p.suffix != ".md":
                    fehler.append(f"{rel(p)}: knowledge/ enthält nur validierte Markdown-Seiten")
        except OSError as exc:
            fehler.append(f"knowledge: Baum kann nicht vollständig geprüft werden — {exc}")
    else:
        fehler.append("knowledge: fehlt oder enthält eine unsichere Symlink-Komponente")

    try:
        seiten, claims, f3, warnungen = lade_seiten(
            register, typen, reltypen, concepts=concepts, media=media
        )
        fehler += f3
    except (OSError, UnicodeError) as exc:
        seiten, claims, warnungen = {}, {}, []
        fehler.append(f"knowledge: Seiten können nicht vollständig gelesen werden — {exc}")

    for concept_id, concept in sorted(concepts.items()):
        claim_id = concept.get("definition_claim")
        if not isinstance(claim_id, str) or claim_id not in claims:
            fehler.append(
                f"{rel(CONCEPTS)}: {concept_id}.definition_claim {claim_id!r} "
                f"existiert nicht"
            )
            continue
        page = seiten.get(claims[claim_id]["seite"])
        page_concepts = page["fm"].get("concepts", []) if page else []
        if concept_id not in page_concepts:
            fehler.append(
                f"{rel(CONCEPTS)}: Definition {claim_id} liegt auf einer Seite, "
                f"die {concept_id} nicht in concepts führt"
            )
    referenced_media = {
        claim["quelle"] for claim in claims.values() if claim.get("region")
    }
    for sid in sorted(set(media) - referenced_media):
        warnungen.append(
            f"{media[sid]['path']}: freigegebene Medienrepräsentation ohne Claim"
        )

    # Router: jede Domäne hat Abschnitt, jede gelistete Seite existiert und passt
    router, f4 = parse_router()
    fehler += f4
    try:
        domaenen = (
            sorted({d.name for d in KNOWLEDGE.iterdir()
                    if _safe_directory(d) and d.parent == KNOWLEDGE})
            if _safe_directory(KNOWLEDGE) else []
        )
    except OSError as exc:
        domaenen = []
        fehler.append(f"knowledge: Domänen können nicht aufgelistet werden — {exc}")
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
            seitenpfad, pfadfehler = _safe_relative_path(ROOT, s)
            if pfadfehler or not _resolved_within(seitenpfad, KNOWLEDGE):
                grund = pfadfehler or "Pfad zeigt aus knowledge/ hinaus"
                fehler.append(f"ROUTER.md [{d}]: Seite {s!r} unzulässig — {grund}")
            elif not seitenpfad.is_file():
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
              "<!-- Manuelle Audit-Map; für Abfragen zuerst vault.py query, dann Kandidatenseiten lesen. -->",
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
    def arbeit():
        fehler, _, seiten, *_ = cmd_validate(still=True)
        if fehler:
            print("🔴 index: abgebrochen — validate meldet Fehler (fail-closed). "
                  "Erst 'vault.py validate' grün bekommen.")
            return 1
        try:
            _replace_files_transactionally({INDEX: build_index(seiten).encode("utf-8")})
        except RollbackIncompleteError:
            raise
        except (OSError, RuntimeError, TypeError) as exc:
            print(f"🔴 index: Schreiben fehlgeschlagen — {exc}")
            return 1
        print(f"🟢 index: {rel(INDEX)} neu erzeugt ({len(seiten)} Seiten).")
        return 0

    return _run_locked_mutation("index", arbeit)


def build_graph(seiten):
    knoten, kanten = [], []
    for rp, s in sorted(seiten.items()):
        fm = s["fm"]
        knoten.append({"id": rp, "titel": fm.get("title", ""), "typ": fm.get("type", ""),
                       "domaene": fm.get("domain", ""), "status": fm.get("status", ""),
                       "konfidenz": fm.get("confidence", ""), "stand": fm.get("stand", ""),
                       "begriffe": sorted(fm.get("concepts", [])),
                       "claims": sorted(c["id"] for c in s["claims"])})
        for r in s["relationen"]:
            kanten.append({"von": rp, "nach": r["ziel"], "typ": r["typ"]})
    kanten.sort(key=lambda k: (k["von"], k["nach"], k["typ"]))
    return {"profil": PROFIL, "knoten": knoten, "kanten": kanten}


def cmd_graph():
    def arbeit():
        fehler, _, seiten, *_ = cmd_validate(still=True)
        if fehler:
            print("🔴 graph: abgebrochen — validate meldet Fehler (fail-closed).")
            return 1
        g = build_graph(seiten)
        inhalt = json.dumps(g, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        try:
            _replace_files_transactionally({GRAPH: inhalt.encode("utf-8")})
        except RollbackIncompleteError:
            raise
        except (OSError, RuntimeError, TypeError) as exc:
            print(f"🔴 graph: Schreiben fehlgeschlagen — {exc}")
            return 1
        print(f"🟢 graph: {rel(GRAPH)} abgeleitet — {len(g['knoten'])} Knoten, "
              f"{len(g['kanten'])} Kanten. Kanten stammen nur aus validierten Seiten.")
        return 0

    return _run_locked_mutation("graph", arbeit)


def cmd_search(begriffe, mit_quellen=True):
    """Plan B: erschöpfende, deterministische Volltextsuche.
    Ein Nicht-Treffer beweist nur lexikalische, nie semantische Abwesenheit."""
    try:
        unsichere = _skill_symlinks() + _skill_hardlinks()
    except OSError as exc:
        print(f"🔴 search: Tresorbaum kann nicht vollständig geprüft werden — {exc}")
        return 1
    if unsichere or not _safe_directory(KNOWLEDGE):
        print("🔴 search: unsichere Symlinks/Hardlinks oder knowledge-Grenze "
              "— Suche fail-closed abgebrochen.")
        return 1
    if mit_quellen and (
            not _safe_regular_file(REGISTER) or not _safe_regular_file(ROUTER)):
        print("🔴 search: REGISTER.md/ROUTER.md fehlt oder ist kein sicheres "
              "reguläres Tresor-Dokument.")
        return 1
    muster = re.compile("|".join(re.escape(b) for b in begriffe), re.IGNORECASE)
    try:
        dateien = list(iter_pages())
    except OSError as exc:
        print(f"🔴 search: Wissensseiten können nicht vollständig gelesen werden — {exc}")
        return 1
    if mit_quellen:
        for extra in (REGISTER, ROUTER):
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
        print("Kein Lexiktreffer: semantische Abwesenheit ist damit nicht "
              "bewiesen — relevante Seiten/Claims vollständig prüfen.")
    return 0 if treffer else 1


def _query_base(query, state, *, manifest_digest=None, version=None,
                errors=None, warnings=None):
    return {
        "schema": QUERY_SCHEMA,
        "profile": PROFIL,
        "retrieval": RETRIEVAL_PROFILE,
        "state": state,
        "query": query,
        "vault": {
            "version": version,
            "manifest_sha256": manifest_digest,
        },
        "coverage": {
            "retrieval_complete": False,
            "semantic_coverage": "not_assessed",
            "mode": "exhaustive_validated_claim_ranking",
            "claims_scanned": 0,
        },
        "fallback": {
            "exhaustive_review_required": False,
            "reason": None,
            "page_paths": [],
        },
        "concepts": {"matched": [], "expanded": []},
        "pages": [],
        "evidence": [],
        "warnings": sorted(set(warnings or [])),
        "errors": list(errors or []),
        "retrieval_fingerprint": None,
    }


def _emit_query_json(result):
    print(json.dumps(
        result, ensure_ascii=False, indent=2, sort_keys=True
    ))


def _load_released_query_snapshot(query):
    """Validierten, manifestgebundenen Query-Snapshot fail-closed puffern."""
    if not isinstance(query, str) or not query.strip():
        return None, _query_base(
            query if isinstance(query, str) else "",
            "invalid_query",
            errors=["Frage darf nicht leer sein"],
        )
    if len(query) > MAX_QUERY_LENGTH:
        return None, _query_base(
            query, "invalid_query",
            errors=[f"Frage ist länger als {MAX_QUERY_LENGTH} Zeichen"],
        )
    if any(ord(char) < 32 or ord(char) == 127 for char in query):
        return None, _query_base(
            query, "invalid_query",
            errors=["Steuerzeichen/Zeilenumbrüche sind in Fragen verboten"],
        )
    if os.path.lexists(str(RELEASE_LOCK)):
        return None, _query_base(
            query, "vault_busy",
            errors=["Release-/Recovery-Lock vorhanden; kein konsistenter Snapshot"],
        )
    if not _safe_regular_file(MANIFEST):
        return None, _query_base(
            query, "invalid_vault",
            errors=["MANIFEST.sha256 fehlt oder ist nicht sicher lesbar"],
        )
    try:
        manifest_digest = sha256_file(MANIFEST)
    except OSError as exc:
        return None, _query_base(
            query, "invalid_vault",
            errors=[f"Manifest kann nicht sicher gehasht werden: {exc}"],
        )
    manifest_errors, _ = _manifest_status()
    if manifest_errors:
        return None, _query_base(
            query, "invalid_vault", manifest_digest=manifest_digest,
            errors=manifest_errors,
        )

    errors, warnings, pages, claims, register, _ = cmd_validate(still=True)
    if errors:
        return None, _query_base(
            query, "invalid_vault", manifest_digest=manifest_digest,
            errors=errors, warnings=warnings,
        )
    derived_errors = []
    try:
        if not _safe_regular_file(INDEX) or read(INDEX) != build_index(pages):
            derived_errors.append("INDEX.md ist nicht konsistent mit dem Bestand")
        expected_graph = (
            json.dumps(build_graph(pages), ensure_ascii=False, indent=2,
                       sort_keys=True) + "\n"
        )
        if not _safe_regular_file(GRAPH) or read(GRAPH) != expected_graph:
            derived_errors.append(
                "graph/graph.json ist nicht konsistent mit dem Bestand"
            )
    except (OSError, UnicodeError) as exc:
        derived_errors.append(f"Abgeleitete Artefakte sind nicht sicher lesbar: {exc}")
    if derived_errors:
        return None, _query_base(
            query, "invalid_vault", manifest_digest=manifest_digest,
            errors=derived_errors, warnings=warnings,
        )
    worlds, concepts, concept_errors = parse_concepts()
    media, media_errors = parse_media_representations(register)
    auxiliary_errors = concept_errors + media_errors
    if auxiliary_errors:
        return None, _query_base(
            query, "invalid_vault", manifest_digest=manifest_digest,
            errors=auxiliary_errors, warnings=warnings,
        )
    try:
        version = read(VERSION).strip() if _safe_regular_file(VERSION) else None
    except (OSError, UnicodeError):
        version = None
    if version is None or not VERSION_RE.fullmatch(version):
        return None, _query_base(
            query, "invalid_vault", manifest_digest=manifest_digest,
            errors=["VERSION fehlt, ist unsicher oder kein SemVer"],
            warnings=warnings,
        )

    # Nach dem vollständigen Parsen erneut gegen genau denselben Release prüfen.
    manifest_errors_after, _ = _manifest_status()
    try:
        digest_after = sha256_file(MANIFEST)
    except OSError as exc:
        return None, _query_base(
            query, "snapshot_changed", manifest_digest=manifest_digest,
            version=version, errors=[f"Manifest änderte sich beim Lesen: {exc}"],
        )
    if (os.path.lexists(str(RELEASE_LOCK))
            or digest_after != manifest_digest or manifest_errors_after):
        reasons = manifest_errors_after or [
            "Release-/Manifeststand änderte sich während der Abfrage"
        ]
        return None, _query_base(
            query, "snapshot_changed", manifest_digest=manifest_digest,
            version=version, errors=reasons,
        )
    return {
        "query": query,
        "manifest_digest": manifest_digest,
        "version": version,
        "warnings": warnings,
        "pages": pages,
        "claims": claims,
        "register": register,
        "worlds": worlds,
        "concepts": concepts,
        "media": media,
    }, None


def _match_concepts(query_norm, concepts, world=None):
    phrase_matches = {}
    matched_labels = {}
    for concept_id, concept in sorted(concepts.items()):
        if world is not None and concept.get("world") != world:
            continue
        labels = [concept.get("preferred", "")] + concept.get("aliases", [])
        for label in labels:
            normalized = _retrieval_norm(label)
            if _phrase_present(query_norm, normalized):
                phrase_matches.setdefault(normalized, []).append(concept_id)
                matched_labels.setdefault(concept_id, []).append(label)
    ambiguous = {
        phrase: sorted(ids)
        for phrase, ids in sorted(phrase_matches.items())
        if len(set(ids)) > 1
    }
    direct = sorted(matched_labels)
    return direct, {
        cid: sorted(set(labels), key=lambda value: (_retrieval_norm(value), value))
        for cid, labels in matched_labels.items()
    }, ambiguous


def _concept_expansion(concepts, direct):
    """Genau einen belegbaren Ontologie-Hop, hart begrenzt, ableiten."""
    narrower = {}
    for cid, concept in concepts.items():
        for broader in concept.get("broader", []):
            narrower.setdefault(broader, []).append(cid)
    expansion = {}
    for cid in direct:
        concept = concepts[cid]
        candidates = (
            [(target, "broader", 55) for target in concept.get("broader", [])]
            + [(target, "narrower", 55) for target in narrower.get(cid, [])]
            + [(target, "related", 35) for target in concept.get("related", [])]
        )
        for target, relation, weight in sorted(candidates):
            if target in direct or target not in concepts:
                continue
            previous = expansion.get(target)
            proposal = {"id": target, "via": cid, "relation": relation, "weight": weight}
            if previous is None or (
                    weight, cid, relation
            ) > (
                    previous["weight"], previous["via"], previous["relation"]
            ):
                expansion[target] = proposal
    return [
        expansion[cid] for cid in sorted(expansion)[:MAX_CONCEPT_EXPANSIONS]
    ]


def build_query_result(snapshot, world=None, limit=8):
    """Reines, ganzzahlig geranktes Hybrid-Retrieval über validierte Claims."""
    query = snapshot["query"]
    query_norm = _retrieval_norm(query)
    query_tokens = set(_retrieval_tokens(query))
    query_claim_ids = set(re.findall(r"(?i)(?<![A-Z0-9])C-\d{4}(?![A-Z0-9])",
                                     query))
    query_claim_ids = {value.upper() for value in query_claim_ids}
    query_source_ids = set(re.findall(r"(?i)(?<![A-Z0-9])S-\d{4}(?![A-Z0-9])",
                                      query))
    query_source_ids = {value.upper() for value in query_source_ids}
    query_concept_ids = set(re.findall(r"(?i)(?<![A-Z0-9])B-\d{4}(?![A-Z0-9])",
                                       query))
    query_concept_ids = {value.upper() for value in query_concept_ids}
    concepts = snapshot["concepts"]
    worlds = snapshot["worlds"]
    if world is not None and world not in worlds:
        return _query_base(
            query, "invalid_query",
            manifest_digest=snapshot["manifest_digest"],
            version=snapshot["version"],
            errors=[f"Unbekannte Begriffswelt {world!r}"],
            warnings=snapshot["warnings"],
        )

    direct, matched_labels, ambiguous = _match_concepts(
        query_norm, concepts, world=world
    )
    for concept_id in sorted(query_concept_ids):
        if (concept_id in concepts
                and (world is None or concepts[concept_id]["world"] == world)
                and concept_id not in direct):
            direct.append(concept_id)
            matched_labels[concept_id] = [concept_id]
    direct.sort()
    if ambiguous:
        details = [
            f"{phrase!r} ist mehrdeutig: {', '.join(ids)}"
            for phrase, ids in ambiguous.items()
        ]
        return _query_base(
            query, "ambiguous",
            manifest_digest=snapshot["manifest_digest"],
            version=snapshot["version"], errors=details,
            warnings=snapshot["warnings"],
        )
    expansion = _concept_expansion(concepts, direct)
    expanded_weights = {item["id"]: item["weight"] for item in expansion}

    page_scores, page_reasons = {}, {}
    pages = snapshot["pages"]
    for path, page in sorted(pages.items()):
        fm = page["fm"]
        score, reasons = 0, []
        page_concepts = set(fm.get("concepts", []))
        for cid in sorted(page_concepts & set(direct)):
            score += 120
            reasons.append(f"concept:{cid}:direct")
        for cid in sorted(page_concepts & set(expanded_weights)):
            weight = expanded_weights[cid]
            score += weight
            reasons.append(f"concept:{cid}:expanded:{weight}")

        title_norm = _retrieval_norm(fm.get("title", ""))
        title_tokens = set(_retrieval_tokens(fm.get("title", "")))
        tag_tokens = set()
        for tag in fm.get("tags", []):
            tag_tokens.update(_retrieval_tokens(tag))
        claim_text = " ".join(
            f"{claim['text']} {claim['fundstelle']}" for claim in page["claims"]
        )
        page_claim_ids = {claim["id"] for claim in page["claims"]}
        page_source_ids = {claim["quelle"] for claim in page["claims"]}
        for claim_id in sorted(query_claim_ids & page_claim_ids):
            score += 180
            reasons.append(f"id:{claim_id}")
        for source_id in sorted(query_source_ids & page_source_ids):
            score += 100
            reasons.append(f"id:{source_id}")
        claim_norm = _retrieval_norm(claim_text)
        claim_tokens = set(_retrieval_tokens(claim_text))
        if query_norm and _phrase_present(title_norm, query_norm):
            score += 80
            reasons.append("exact:title")
        if query_norm and _phrase_present(claim_norm, query_norm):
            score += 60
            reasons.append("exact:claim")
        for token in sorted(query_tokens):
            if token in title_tokens:
                score += 30
                reasons.append(f"token:{token}:title")
            if token in tag_tokens:
                score += 24
                reasons.append(f"token:{token}:tag")
            if token in claim_tokens:
                score += 12
                reasons.append(f"token:{token}:claim")
        if score:
            page_scores[path] = score
            page_reasons[path] = reasons

    # Ein Graph-Hop ergänzt Kontext, bleibt aber niedriger gewichtet als
    # jeder direkte Begriffs-/Lexikaltreffer.
    graph_boost = {}
    for source in sorted(page_scores):
        for relation in pages[source]["relationen"]:
            target = relation["ziel"]
            graph_boost[target] = max(graph_boost.get(target, 0), 10)
        for candidate, page in sorted(pages.items()):
            if any(relation["ziel"] == source for relation in page["relationen"]):
                graph_boost[candidate] = max(graph_boost.get(candidate, 0), 10)
    for path, boost in sorted(graph_boost.items()):
        if path not in pages:
            continue
        page_scores[path] = page_scores.get(path, 0) + boost
        page_reasons.setdefault(path, []).append("graph:one-hop")

    evidence = []
    for path, page in sorted(pages.items()):
        if path not in page_scores:
            continue
        fm = page["fm"]
        page_concepts = set(fm.get("concepts", []))
        concept_base = (
            100 * len(page_concepts & set(direct))
            + sum(
                expanded_weights[cid]
                for cid in page_concepts & set(expanded_weights)
            )
        )
        for claim in page["claims"]:
            claim_norm = _retrieval_norm(
                f"{claim['text']} {claim['fundstelle']}"
            )
            claim_tokens = set(_retrieval_tokens(claim_norm))
            score = concept_base
            reasons = []
            if concept_base:
                reasons.append("concept-page")
            if claim["id"] in query_claim_ids:
                score += 240
                reasons.append(f"id:{claim['id']}")
            if claim["quelle"] in query_source_ids:
                score += 140
                reasons.append(f"id:{claim['quelle']}")
            if query_norm and _phrase_present(claim_norm, query_norm):
                score += 80
                reasons.append("exact:claim")
            matched_tokens = sorted(query_tokens & claim_tokens)
            if matched_tokens:
                score += 20 * len(matched_tokens)
                reasons.extend(f"token:{token}" for token in matched_tokens)
            if not score and path in graph_boost:
                score = 5
                reasons.append("graph:one-hop")
            elif not score and page_scores[path]:
                score = 10
                reasons.append("page-metadata")
            if score <= 0:
                continue
            source = snapshot["register"].get(claim["quelle"], {})
            item = {
                "claim_id": claim["id"],
                "role": "retrieval_candidate",
                "page": path,
                "page_status": fm.get("status"),
                "page_confidence": fm.get("confidence"),
                "score": int(score),
                "reasons": sorted(set(reasons)),
                "kind": claim["art"],
                "text": claim["text"],
                "source": {
                    "id": claim["quelle"],
                    "title": source.get("titel"),
                    "stand": source.get("stand"),
                    "trust": source.get("trust"),
                    "rights": source.get("rechte"),
                    "locator": claim["fundstelle"],
                },
                "signals": [],
                "media": None,
            }
            if claim["art"] == "Auslegung":
                item["signals"].append("interpretation")
            if fm.get("status") != "aktiv":
                item["signals"].append(f"page_status:{fm.get('status')}")
            if fm.get("confidence") == "niedrig":
                item["signals"].append("low_confidence")
            if source.get("trust") == "T3":
                item["signals"].append("source_trust:T3")
            region_id = claim.get("region")
            representation = snapshot["media"].get(claim["quelle"])
            if region_id and representation:
                region = representation["regions"].get(region_id, {})
                item["media"] = {
                    "representation": representation["path"],
                    "media_type": representation["media_type"],
                    "region_id": region_id,
                    "region_kind": region.get("kind"),
                    "confidence": region.get("confidence"),
                }
            evidence.append(item)
    evidence.sort(key=lambda item: (-item["score"], item["claim_id"], item["page"]))
    evidence = evidence[:limit]

    page_paths = sorted(
        {item["page"] for item in evidence},
        key=lambda path: (-page_scores.get(path, 0), path),
    )
    page_results = []
    for path in page_paths:
        fm = pages[path]["fm"]
        page_results.append({
            "path": path,
            "title": fm.get("title"),
            "domain": fm.get("domain"),
            "status": fm.get("status"),
            "confidence": fm.get("confidence"),
            "stand": fm.get("stand"),
            "score": int(page_scores[path]),
            "reasons": sorted(set(page_reasons[path])),
            "concepts": sorted(fm.get("concepts", [])),
        })

    state = "candidates_found" if evidence else "no_candidates"
    matched_output = [
        {
            "id": cid,
            "world": concepts[cid]["world"],
            "preferred": concepts[cid]["preferred"],
            "matched_labels": matched_labels[cid],
        }
        for cid in direct
    ]
    expanded_output = [
        {
            **item,
            "world": concepts[item["id"]]["world"],
            "preferred": concepts[item["id"]]["preferred"],
        }
        for item in expansion
    ]
    fingerprint_data = {
        "algorithm": RETRIEVAL_PROFILE,
        "manifest": snapshot["manifest_digest"],
        "query": query_norm,
        "world": world,
        "evidence": [
            [item["claim_id"], item["score"]] for item in evidence
        ],
    }
    fingerprint = _sha256_bytes(json.dumps(
        fingerprint_data, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8"))
    result = _query_base(
        query, state, manifest_digest=snapshot["manifest_digest"],
        version=snapshot["version"], warnings=snapshot["warnings"],
    )
    result.update({
        "coverage": {
            "retrieval_complete": True,
            "semantic_coverage": "not_assessed",
            "mode": "exhaustive_validated_claim_ranking",
            "claims_scanned": len(snapshot["claims"]),
        },
        "fallback": {
            "exhaustive_review_required": not evidence,
            "reason": None if evidence else "no_retrieval_candidates",
            "page_paths": sorted(snapshot["pages"]),
        },
        "concepts": {
            "matched": matched_output,
            "expanded": expanded_output,
        },
        "pages": page_results,
        "evidence": evidence,
        "retrieval_fingerprint": fingerprint,
    })
    return result


def cmd_query(question_words, world=None, limit=8):
    query = " ".join(question_words)
    snapshot, error = _load_released_query_snapshot(query)
    if error is not None:
        _emit_query_json(error)
        return 1
    result = build_query_result(snapshot, world=world, limit=limit)
    _emit_query_json(result)
    if result["state"] in {"candidates_found", "no_candidates"}:
        return 0
    return 2


def cmd_media_template(source_id):
    """Nicht schreibendes JSON-Gerüst für eine registrierte Medienquelle."""
    register, errors = parse_register()
    if errors or source_id not in register:
        result = {
            "schema": MEDIA_SCHEMA,
            "state": "invalid_source",
            "errors": errors or [f"Quelle {source_id!r} fehlt im REGISTER"],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 1
    entry = register[source_id]
    source_path, path_error = _safe_relative_path(ROOT, entry["ablage"])
    expected_type = (
        MEDIA_TYPES.get(source_path.suffix.lower()) if source_path else None
    )
    if (path_error or not expected_type or not _safe_regular_file(source_path)
            or sha256_file(source_path) != entry["hash"]
            or not _media_signature_matches(source_path, expected_type)):
        result = {
            "schema": MEDIA_SCHEMA,
            "state": "invalid_source",
            "errors": [
                path_error or
                "Quelle fehlt, Hash/Signatur weicht ab oder Format ist nicht erlaubt"
            ],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 1
    template = {
        "schema": MEDIA_SCHEMA,
        "source_id": source_id,
        "source_sha256": entry["hash"],
        "media_type": expected_type,
        "language": "und",
        "extractor": {
            "kind": "human",
            "name": "AUSFÜLLEN",
            "version": "AUSFÜLLEN",
        },
        "verified": False,
        "alt_text": "AUSFÜLLEN",
        "regions": [{
            "id": "R-0001",
            "kind": "other",
            "locator": "AUSFÜLLEN",
            "text": "AUSFÜLLEN",
            "confidence": 0,
            "bbox": None,
            "suspicious_instruction": False,
        }],
    }
    print(json.dumps(template, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _tracked_path(p: Path) -> bool:
    """Ob ein Tresorpfad Bestandteil des Integritätsmanifests ist."""
    rp = Path(rel(p))
    teile = rp.parts
    if not teile:
        return False
    if p in {MANIFEST, LOG, RELEASE_LOCK}:
        return False
    if "__pycache__" in teile or p.suffix == ".pyc" or teile[0] == "evals":
        return False
    if teile[:2] == ("sources", "quarantine"):
        return p == QUARANTINE / "README.md"
    return True


def _open_parent_dir_fd(ziel: Path):
    """Elternordner komponentenweise und ohne Link-Folgen verankern."""
    if os.open not in os.supports_dir_fd or os.rename not in os.supports_dir_fd:
        raise OSError(
            "sichere dir_fd-Dateiersetzung wird auf dieser Plattform nicht unterstützt"
        )
    try:
        teile = ziel.parent.relative_to(ROOT).parts
    except ValueError as exc:
        raise OSError("Schreibziel liegt außerhalb des Tresors") from exc
    flags = (os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
             | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
    fd = os.open(str(ROOT), flags)
    try:
        for teil in teile:
            naechster = os.open(teil, flags, dir_fd=fd)
            os.close(fd)
            fd = naechster
        return fd
    except BaseException:
        os.close(fd)
        raise


def _assert_parent_fd(fd, ordner: Path):
    """Prüfen, dass der gehaltene Verzeichnis-FD noch zum Tresorpfad gehört."""
    if _first_symlink_component(ordner) is not None:
        raise OSError(f"{rel(ordner)}: Elternpfad wurde durch einen Link ersetzt")
    gehalten = os.fstat(fd)
    aktuell = os.lstat(str(ordner))
    if (gehalten.st_dev, gehalten.st_ino) != (aktuell.st_dev, aktuell.st_ino):
        raise OSError(f"{rel(ordner)}: Elternverzeichnis wurde während des Schreibens ersetzt")


def _read_regular_at(fd, name, fehlt_erlaubt=False, mit_modus=False):
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        datei_fd = os.open(name, flags, dir_fd=fd)
    except FileNotFoundError:
        if fehlt_erlaubt:
            return None
        raise
    try:
        status = os.fstat(datei_fd)
        if not stat.S_ISREG(status.st_mode) or status.st_nlink != 1:
            raise OSError(f"{name}: Ziel ist keine einfach verlinkte reguläre Datei")
        teile = []
        while True:
            chunk = os.read(datei_fd, 65536)
            if not chunk:
                break
            teile.append(chunk)
        daten = b"".join(teile)
        if mit_modus:
            return daten, stat.S_IMODE(status.st_mode)
        return daten
    finally:
        os.close(datei_fd)


def _replace_files_transactionally(outputs, precommit=None, postcheck=None):
    """Mehrere kleine Release-Dateien vorbereiten, ersetzen und ggf. zurückrollen.

    ``outputs`` behält seine Einfügereihenfolge; das Manifest wird vom
    Release bewusst zuletzt übergeben und dient damit als Commit-Marker.
    """
    if not outputs:
        return
    originals, parent_fds = {}, {}
    try:
        for ziel, daten in outputs.items():
            sicher, grund = _safe_output_target(ziel)
            if not sicher:
                raise OSError(f"{rel(ziel)}: unsicheres Schreibziel — {grund}")
            if not isinstance(daten, bytes):
                raise TypeError(f"{rel(ziel)}: Transaktionsinhalt muss bytes sein")
            if ziel.parent not in parent_fds:
                parent_fds[ziel.parent] = _open_parent_dir_fd(ziel)
            parent_fd = parent_fds[ziel.parent]
            _assert_parent_fd(parent_fd, ziel.parent)
            originals[ziel] = _read_regular_at(
                parent_fd, ziel.name, fehlt_erlaubt=True, mit_modus=True
            )

        with tempfile.TemporaryDirectory(prefix=f".{ROOT.name}-release-",
                                         dir=str(ROOT.parent)) as tmp:
            tmpdir = Path(tmp)
            staged = {}
            for n, (ziel, daten) in enumerate(outputs.items()):
                stage = tmpdir / f"{n:02d}.stage"
                with open(stage, "wb") as f:
                    vorher = originals[ziel]
                    os.fchmod(f.fileno(), vorher[1] if vorher is not None else 0o600)
                    f.write(daten)
                    f.flush()
                    os.fsync(f.fileno())
                staged[ziel] = stage

            if precommit is not None:
                precommit()

            committed = []
            try:
                for ziel in outputs:
                    parent_fd = parent_fds[ziel.parent]
                    _assert_parent_fd(parent_fd, ziel.parent)
                    # Vor dem Replace vormerken: Auch eine Unterbrechung direkt
                    # nach erfolgreichem Replace wird so zurückgerollt.
                    committed.append(ziel)
                    os.replace(
                        str(staged[ziel]), ziel.name, dst_dir_fd=parent_fd
                    )
                    os.fsync(parent_fd)
                for ziel, daten in outputs.items():
                    parent_fd = parent_fds[ziel.parent]
                    _assert_parent_fd(parent_fd, ziel.parent)
                    if _read_regular_at(parent_fd, ziel.name) != daten:
                        raise OSError(
                            f"{rel(ziel)}: Nachprüfung nach Replace fehlgeschlagen"
                        )
                if postcheck is not None:
                    postcheck()
                    for ziel, daten in outputs.items():
                        parent_fd = parent_fds[ziel.parent]
                        _assert_parent_fd(parent_fd, ziel.parent)
                        if _read_regular_at(parent_fd, ziel.name) != daten:
                            raise OSError(
                                f"{rel(ziel)}: Nachprüfung nach Endkontrolle fehlgeschlagen"
                            )
            except BaseException as commit_fehler:
                rollback_fehler = []
                for n, ziel in enumerate(reversed(committed)):
                    parent_fd = parent_fds[ziel.parent]
                    try:
                        alt = originals[ziel]
                        if alt is None:
                            try:
                                os.unlink(ziel.name, dir_fd=parent_fd)
                            except FileNotFoundError:
                                pass
                        else:
                            alt_daten, alt_modus = alt
                            rollback = tmpdir / f"rollback-{n:02d}.stage"
                            with open(rollback, "wb") as f:
                                os.fchmod(f.fileno(), alt_modus)
                                f.write(alt_daten)
                                f.flush()
                                os.fsync(f.fileno())
                            os.replace(
                                str(rollback), ziel.name, dst_dir_fd=parent_fd
                            )
                        os.fsync(parent_fd)
                    except Exception as exc:
                        rollback_fehler.append(f"{rel(ziel)}: {exc}")
                for ordner, parent_fd in parent_fds.items():
                    try:
                        _assert_parent_fd(parent_fd, ordner)
                    except Exception as exc:
                        rollback_fehler.append(f"{rel(ordner)}: {exc}")
                if rollback_fehler:
                    raise RollbackIncompleteError(
                        f"Commit fehlgeschlagen ({commit_fehler}); "
                        f"Rollback unvollständig: " + "; ".join(rollback_fehler)
                    ) from commit_fehler
                raise
    finally:
        for fd in parent_fds.values():
            try:
                os.close(fd)
            except OSError:
                pass


def _acquire_release_lock():
    try:
        fd = os.open(str(RELEASE_LOCK), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise OSError(
            f"{rel(RELEASE_LOCK)} existiert — anderer oder abgebrochener Release; "
            f"Zustand prüfen, Lock danach bewusst entfernen"
        ) from exc
    try:
        os.write(fd, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(fd)
    except Exception:
        try:
            _release_lock_freigeben(fd)
        except OSError:
            pass
        raise
    return fd


def _release_lock_freigeben(fd):
    gehalten = os.fstat(fd)
    try:
        aktuell = os.lstat(str(RELEASE_LOCK))
    except OSError:
        os.close(fd)
        raise OSError("Release-Lockpfad fehlt vor der Freigabe")
    if (gehalten.st_dev, gehalten.st_ino) != (aktuell.st_dev, aktuell.st_ino):
        os.close(fd)
        raise OSError("Release-Lock wurde ausgetauscht; fremden Lock nicht entfernt")
    os.unlink(str(RELEASE_LOCK))
    os.close(fd)


def _release_lock_behalten(fd, grund):
    """Recovery-Hinweis in den Lock schreiben und den Pfad bewusst behalten."""
    hinweis = re.sub(r"[\r\n\x00-\x1f\x7f]+", " ", str(grund)).strip()
    os.lseek(fd, 0, os.SEEK_END)
    os.write(fd, f"recovery_required={hinweis}\n".encode("utf-8"))
    os.fsync(fd)
    os.close(fd)


def _run_locked_mutation(name, operation):
    """Alle schreibenden Einzelkommandos mit demselben Lock serialisieren."""
    try:
        fd = _acquire_release_lock()
    except OSError as exc:
        print(f"🔴 {name}: Schreib-Lock nicht verfügbar — {exc}")
        return 1

    ergebnis, recovery = 1, None
    try:
        ergebnis = operation()
    except RollbackIncompleteError as exc:
        recovery = exc
        print(f"🔴 {name}: KRITISCH — Rollback unvollständig: {exc}")
    finally:
        try:
            if recovery is not None:
                _release_lock_behalten(fd, recovery)
            else:
                _release_lock_freigeben(fd)
        except OSError as exc:
            print(f"🔴 {name}: Lock konnte nicht sicher abgeschlossen werden — {exc}")
            ergebnis = 1
    return ergebnis


def _release_input_fingerprint():
    """Snapshot aller Release-Eingaben; abgeleitete Dateien bleiben außen vor."""
    ignorieren = {INDEX, GRAPH}
    h = hashlib.sha256()
    eingaben = [p for p in _tracked_files() if p not in ignorieren]
    if LOG.is_file() and not LOG.is_symlink():
        eingaben.append(LOG)
    for p in sorted(eingaben, key=lambda x: rel(x)):
        h.update(rel(p).encode("utf-8"))
        h.update(b"\0")
        h.update(sha256_file(p).encode("ascii"))
        h.update(b"\n")
    return h.hexdigest()


def _checksum_entries(overrides=None):
    """Prüfsummen des aktuellen oder eines vorbereiteten Endstands."""
    overrides = overrides or {}
    pfade = set(_tracked_files())
    for p in overrides:
        if _tracked_path(p):
            pfade.add(p)
    eintraege = {}
    for p in sorted(pfade, key=lambda x: rel(x)):
        if p in overrides:
            eintraege[rel(p)] = _sha256_bytes(overrides[p])
        else:
            eintraege[rel(p)] = sha256_file(p)
    return eintraege


def _manifest_bytes(overrides=None):
    eintraege = _checksum_entries(overrides=overrides)
    text = "".join(f"{h}  {rp}\n" for rp, h in sorted(eintraege.items()))
    return text.encode("utf-8"), len(eintraege)


def _tracked_files():
    # log.md ist bewusst NICHT im Manifest: das Journal wächst append-only
    # weiter (auch der Release-Eintrag selbst) und würde jedes Manifest
    # sofort wieder invalidieren. Historie ist Nachweis, nicht Inhalt.
    # evals/ (nur auf oberster Ebene) ist ebenfalls ausgenommen: Werkstatt-
    # material des Skill-Creators, das beim Packaging nicht mitgeliefert
    # wird — stünde es im Manifest, schlüge verify nach Installation fehl.
    ergebnis = []
    for p in _walk_tree_no_links(ROOT):
        if _is_path_alias(p):
            raise ValueError(f"{rel(p)}: Symlink/Reparse-Point im Tresor verboten")
        status = os.lstat(str(p))
        if stat.S_ISDIR(status.st_mode):
            continue
        if not stat.S_ISREG(status.st_mode):
            raise ValueError(f"{rel(p)}: nur reguläre Dateien/Ordner sind erlaubt")
        if status.st_nlink != 1:
            raise ValueError(f"{rel(p)}: mehrfach hart verlinkte Datei ist verboten")
        if not _tracked_path(p):
            continue
        rp = rel(p)
        kanonisch, pfadfehler = _safe_relative_path(ROOT, rp)
        if pfadfehler or kanonisch != p:
            raise ValueError(f"{rp!r}: nicht als portabler Manifestpfad darstellbar")
        ergebnis.append(p)
    return ergebnis


def _manifest_status():
    """Manifest ohne Ausgabe gegen den aktuellen Bestand prüfen."""
    try:
        aktuell = _checksum_entries()
    except (OSError, RuntimeError, ValueError) as exc:
        return [f"MANIFEST: aktueller Bestand kann nicht sicher gelesen werden — {exc}"], 0
    if not _safe_regular_file(MANIFEST):
        return ["MANIFEST.sha256 fehlt oder ist keine sichere reguläre Datei"], 0
    try:
        manifest_text = read(MANIFEST)
    except (OSError, UnicodeError) as exc:
        return [f"MANIFEST.sha256 ist nicht als UTF-8 lesbar — {exc}"], 0

    soll, manifest_fehler = {}, []
    for n, line in enumerate(manifest_text.split("\n"), 1):
        if not line.strip():
            continue
        m = re.match(r"^([0-9a-f]{64})  (\S.*)$", line)
        if not m:
            manifest_fehler.append(
                f"MANIFEST Zeile {n}: erwartet '<sha256>  <relativer-pfad>'"
            )
            continue
        h, rp = m.groups()
        pfad, pfadfehler = _safe_relative_path(ROOT, rp)
        if (pfadfehler or rel(pfad) != rp or not _tracked_path(pfad)):
            manifest_fehler.append(f"MANIFEST Zeile {n}: Pfad {rp!r} unzulässig")
            continue
        if rp in soll:
            manifest_fehler.append(f"MANIFEST Zeile {n}: Pfad {rp!r} doppelt")
            continue
        soll[rp] = h
    if manifest_fehler:
        return manifest_fehler, len(soll)
    neu = sorted(set(aktuell) - set(soll))
    weg = sorted(set(soll) - set(aktuell))
    anders = sorted(rp for rp in set(soll) & set(aktuell) if soll[rp] != aktuell[rp])
    probleme = (
        [f"NEU {rp}" for rp in neu]
        + [f"FEHLT {rp}" for rp in weg]
        + [f"GEÄNDERT {rp}" for rp in anders]
    )
    return probleme, len(soll)


def cmd_checksum(verify=False):
    if _quarantine_payloads():
        print("🔴 checksum: Quarantäne nicht leer — ungeprüfte Inhalte verhindern "
              "ein Integritätsmanifest.")
        return 1
    if verify:
        probleme, anzahl = _manifest_status()
        for problem in probleme:
            symbol = "🟡" if problem.startswith("NEU ") else "🔴"
            print(f"{symbol} {problem}")
        if probleme:
            print(f"\nverify: {len(probleme)} Abweichungen/Fehler — "
                  f"Stand entspricht NICHT dem Manifest.")
            return 1
        print(f"🟢 verify: {anzahl} Dateien unverändert — Stand = Manifest.")
        return 0

    def arbeit():
        if _quarantine_payloads():
            print("🔴 checksum: Quarantäne wurde während des Schreibens befüllt.")
            return 1
        try:
            inhalt, anzahl = _manifest_bytes()

            def endkontrolle():
                probleme, _ = _manifest_status()
                if probleme:
                    raise RuntimeError(
                        "geschriebenes Manifest ist nicht selbstkonsistent: "
                        + "; ".join(probleme)
                    )

            _replace_files_transactionally(
                {MANIFEST: inhalt}, postcheck=endkontrolle
            )
        except RollbackIncompleteError:
            raise
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            print(f"🔴 checksum: Schreiben fehlgeschlagen — {exc}")
            return 1
        print(f"🟢 checksum: {rel(MANIFEST)} geschrieben ({anzahl} Dateien). "
              f"Jede inhaltliche Änderung invalidiert dieses Manifest.")
        return 0

    return _run_locked_mutation("checksum", arbeit)


def cmd_log(aktion, text):
    if aktion not in LOG_AKTIONEN:
        print(f"🔴 log: Aktion muss eine sein von {sorted(LOG_AKTIONEN)}")
        return 1
    if any(ord(zeichen) < 32 or ord(zeichen) == 127 for zeichen in text):
        print("🔴 log: Steuerzeichen und Zeilenumbrüche im Logtext sind verboten")
        return 1

    def arbeit():
        sicher, grund = _safe_output_target(LOG)
        if not sicher:
            print(f"🔴 log: unsicheres Schreibziel — {grund}")
            return 1
        eintrag = f"## [{date.today().isoformat()}] {aktion} | {text}"
        bisher = read(LOG) if LOG.exists() else ""
        if bisher and not bisher.endswith("\n"):
            bisher += "\n"
        try:
            _replace_files_transactionally(
                {LOG: (bisher + eintrag + "\n").encode("utf-8")}
            )
        except RollbackIncompleteError:
            raise
        except (OSError, RuntimeError, TypeError) as exc:
            print(f"🔴 log: Schreiben fehlgeschlagen — {exc}")
            return 1
        print(f"🟢 log: angehängt — {eintrag}")
        return 0

    return _run_locked_mutation("log", arbeit)


def cmd_stats():
    fehler, warn, seiten, claims, register, _ = cmd_validate(still=True)
    worlds, concepts, _ = parse_concepts()
    media, _ = parse_media_representations(register)
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
    print(f"  Begriffswelten: {len(worlds)}, Begriffe: {len(concepts)}, "
          f"Medienrepräsentationen: {len(media)}")
    for name, d in (("Domänen", dom), ("Typen", typ), ("Status", status)):
        print(f"  {name}: " + ", ".join(f"{k}={v}" for k, v in sorted(d.items())))
    return 0


def cmd_source(pfad):
    p = Path(pfad)
    if _is_path_alias(p) or not p.is_file():
        print(f"🔴 source: {pfad} nicht gefunden oder ist ein Symlink/Reparse-Point")
        return 1
    register, _ = parse_register()
    naechste = max([int(s[2:]) for s in register] or [0]) + 1
    sid = f"S-{naechste:04d}"
    try:
        h = sha256_file(p)
    except OSError as exc:
        print(f"🔴 source: Datei kann nicht sicher gehasht werden — {exc}")
        return 1
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
    fehler, _, _, _, _, router = cmd_validate(still=True)
    if fehler:
        for f in fehler:
            print(f"🔴 {f}")
        print("🔴 route: Tresor ist nicht valide — Routing fail-closed abgebrochen.")
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
              "(lexikalisch erschöpfend; kein semantischer Negativbeweis).")
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
    """Transaktionale Release-Kette mit Gate, Lock und Rollback.

    Alle Ergebnisse werden erst im Speicher und in temporären Dateien
    vorbereitet. Danach werden Index, Graph, VERSION und Log ersetzt;
    das Manifest kommt als Commit-Marker zuletzt. Jeder behandelte
    Schreibfehler stellt den vorherigen Byte-Stand vollständig wieder her.
    """
    if stufe not in ("major", "minor", "patch"):
        print("🔴 release: Stufe muss major|minor|patch sein")
        return 1

    lock_fd, committed, lock_behalten = None, False, False
    ergebnis, status = 1, None
    try:
        lock_fd = _acquire_release_lock()
        fingerprint = _release_input_fingerprint()

        fehler, warnungen, seiten, claims, register, _ = cmd_validate(still=True)
        if fehler:
            for f in fehler:
                print(f"🔴 {f}")
            raise RuntimeError("validate schlägt fehl (fail-closed)")
        if _release_input_fingerprint() != fingerprint:
            raise RuntimeError("Eingabestand hat sich während der Validierung verändert")

        if not _safe_regular_file(VERSION):
            raise ValueError("VERSION fehlt oder ist keine sichere reguläre Datei")
        alt = read(VERSION).strip()
        if not VERSION_RE.fullmatch(alt):
            raise ValueError(f"VERSION '{alt}' ist kein SemVer x.y.z")
        ma, mi, pa = (int(x) for x in alt.split("."))
        ma, mi, pa = {"major": (ma + 1, 0, 0),
                      "minor": (ma, mi + 1, 0),
                      "patch": (ma, mi, pa + 1)}[stufe]
        neu = f"{ma}.{mi}.{pa}"

        if LOG.exists() and not _safe_regular_file(LOG):
            raise OSError("log.md ist kein sicheres reguläres Schreibziel")
        index_bytes = build_index(seiten).encode("utf-8")
        graph = build_graph(seiten)
        graph_bytes = (json.dumps(graph, ensure_ascii=False, indent=2,
                                  sort_keys=True) + "\n").encode("utf-8")
        version_bytes = (neu + "\n").encode("utf-8")
        bisheriges_log = read(LOG) if LOG.exists() else ""
        if bisheriges_log and not bisheriges_log.endswith("\n"):
            bisheriges_log += "\n"
        log_eintrag = (
            f"## [{date.today().isoformat()}] release | v{neu} — "
            f"{len(seiten)} Seiten, {len(claims)} Claims, "
            f"{len(register)} Quellen ({stufe})\n"
        )
        log_bytes = (bisheriges_log + log_eintrag).encode("utf-8")

        vorbereitet = {
            INDEX: index_bytes,
            GRAPH: graph_bytes,
            VERSION: version_bytes,
            LOG: log_bytes,
        }
        manifest_bytes, manifest_anzahl = _manifest_bytes(overrides=vorbereitet)
        vorbereitet[MANIFEST] = manifest_bytes  # Commit-Marker bewusst zuletzt.

        if _quarantine_payloads():
            raise RuntimeError("Quarantäne wurde während des Release befüllt")
        if _release_input_fingerprint() != fingerprint:
            raise RuntimeError("Eingabestand hat sich während des Release verändert")

        def precommit():
            if _quarantine_payloads():
                raise RuntimeError("Quarantäne wurde vor dem Commit befüllt")
            if _release_input_fingerprint() != fingerprint:
                raise RuntimeError("Eingabestand hat sich vor dem Commit verändert")

        def endkontrolle():
            endfehler, _, endseiten, _, _, _ = cmd_validate(still=True)
            if endfehler:
                raise RuntimeError(
                    "Endzustand verletzt validate: " + "; ".join(endfehler)
                )
            if read(INDEX) != build_index(endseiten):
                raise RuntimeError("INDEX.md ist im Endzustand inkonsistent")
            graph_soll = (
                json.dumps(build_graph(endseiten), ensure_ascii=False,
                           indent=2, sort_keys=True) + "\n"
            )
            if read(GRAPH) != graph_soll:
                raise RuntimeError("graph/graph.json ist im Endzustand inkonsistent")
            manifest_fehler, _ = _manifest_status()
            if manifest_fehler:
                raise RuntimeError(
                    "Endmanifest ist inkonsistent: " + "; ".join(manifest_fehler)
                )

        _replace_files_transactionally(
            vorbereitet, precommit=precommit, postcheck=endkontrolle
        )
        committed = True
        ergebnis = 0
        status = (neu, warnungen, len(seiten), len(graph["knoten"]),
                  len(graph["kanten"]), manifest_anzahl)
    except RollbackIncompleteError as exc:
        lock_behalten = True
        print(f"🔴 release: KRITISCH — Rollback unvollständig: {exc}. "
              f"Recovery-Lock bleibt bestehen; nicht veröffentlichen.")
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"🔴 release: ABBRUCH — {exc}. "
              f"Release-Ziele wurden nicht veröffentlicht oder zurückgerollt.")
    finally:
        if lock_fd is not None:
            try:
                if lock_behalten:
                    _release_lock_behalten(lock_fd, "Rollback unvollständig")
                else:
                    _release_lock_freigeben(lock_fd)
            except OSError as exc:
                if committed:
                    print(f"🔴 release: Inhalt committed, aber Lock-Abschluss unsicher — {exc}")
                else:
                    print(f"🔴 release: Lock konnte nicht sicher abgeschlossen werden — {exc}")
                ergebnis = 1
    if committed and ergebnis == 0:
        neu, warnungen, seiten_anzahl, knoten, kanten, manifest_anzahl = status
        try:
            print(f"🟢 index: {seiten_anzahl} Seiten vorbereitet.")
            print(f"🟢 graph: {knoten} Knoten, {kanten} Kanten vorbereitet.")
            print(f"🟢 checksum: {manifest_anzahl} Dateien im Endstand gepinnt.")
            if warnungen:
                print(f"🟡 release: v{neu} mit {len(warnungen)} Warnungen "
                      f"(Details: vault.py doctor).")
            else:
                print(f"🟢 release: v{neu} transaktional veröffentlicht.")
        except OSError:
            # Ausgabeproblem ändert den bereits verifizierten Commit nicht.
            pass
    return ergebnis


def cmd_doctor():
    print("── doctor: Gesamtdiagnose ─────────────────────────────────────")
    fehler, warnungen, seiten, claims, register, router = cmd_validate(still=True)
    hinweise = []

    if not _safe_regular_file(VERSION):
        fehler.append("VERSION fehlt oder ist keine sichere reguläre Datei")
    else:
        try:
            version_text = read(VERSION).strip()
        except (OSError, UnicodeError) as exc:
            version_text = None
            fehler.append(f"VERSION ist nicht sicher als UTF-8 lesbar — {exc}")
        if version_text is not None and not VERSION_RE.fullmatch(version_text):
            fehler.append(f"VERSION {version_text!r} ist kein SemVer x.y.z")

    if _safe_regular_file(INDEX):
        try:
            index_text = read(INDEX)
        except (OSError, UnicodeError) as exc:
            index_text = None
            fehler.append(f"INDEX.md ist nicht sicher als UTF-8 lesbar — {exc}")
        if index_text is not None and index_text != build_index(seiten):
            fehler.append("INDEX.md weicht vom Bestand ab — 'vault.py index' ausführen (Drift)")
    else:
        fehler.append("INDEX.md fehlt oder ist keine reguläre Datei — 'vault.py index' ausführen")
    if _safe_regular_file(GRAPH):
        soll = json.dumps(build_graph(seiten), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        try:
            graph_text = read(GRAPH)
        except (OSError, UnicodeError) as exc:
            graph_text = None
            fehler.append(f"graph/graph.json ist nicht sicher als UTF-8 lesbar — {exc}")
        if graph_text is not None and graph_text != soll:
            fehler.append("graph/graph.json weicht vom Bestand ab — 'vault.py graph' ausführen (Drift)")
    else:
        fehler.append("graph/graph.json fehlt oder ist keine reguläre Datei "
                      "— 'vault.py graph' ausführen")
    if os.path.lexists(str(RELEASE_LOCK)):
        fehler.append(".vault-release.lock vorhanden — laufenden/abgebrochenen Release prüfen")

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

    print("── Prüfsummen ─────────────────────────────────────────────────")
    if cmd_checksum(verify=True) != 0:
        fehler.append("MANIFEST.sha256 fehlt, ist ungültig oder weicht vom Bestand ab")

    print("── Zusammenfassung ────────────────────────────────────────────")
    for f in fehler:
        print(f"🔴 FEHLER   {f}")
    for w in warnungen:
        print(f"🟡 WARNUNG  {w}")
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
    query_parser = sub.add_parser("query")
    query_parser.add_argument("frage", nargs="+")
    query_parser.add_argument("--world")
    query_parser.add_argument("--limit", type=int, default=8)
    media_parser = sub.add_parser("media-template")
    media_parser.add_argument("source_id")
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
    elif a.cmd == "query":
        if not 1 <= a.limit <= MAX_QUERY_LIMIT:
            result = _query_base(
                " ".join(a.frage), "invalid_query",
                errors=[f"--limit muss zwischen 1 und {MAX_QUERY_LIMIT} liegen"],
            )
            _emit_query_json(result)
            sys.exit(2)
        sys.exit(cmd_query(a.frage, world=a.world, limit=a.limit))
    elif a.cmd == "media-template":
        sys.exit(cmd_media_template(a.source_id))
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
