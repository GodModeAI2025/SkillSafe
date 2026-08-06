#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""vault.py — deterministische Engine des Wissenstresors (Profil: oksv-lite/1.3).

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
                     (--extern: zusätzlich aufgeführte externe Quellen lesen)
  media-template ID  JSON-Gerüst für eine registrierte Bild-/PDF-Quelle
  extern             Aufgeführte externe Bezugsquellen: list/bind/unbind
  anchor-template    Sätze eines externen Dokuments mit Index und Digest
  orchestrator-template  Katalog-Gerüst für einen externen Markdown-Baum
  checksum           MANIFEST.sha256 schreiben   |  checksum --verify: prüfen
  log <aktion> <txt> Log-Eintrag mit grep-barem Präfix anhängen
  stats              Bestandszahlen (Domänen, Typen, Claims, Kanten)
  source <datei>     Hash + nächste freie S-ID + fertige Registerzeile
  route <frage>      Frage deterministisch auf Domäne und Seiten routen
  doctor             Gesamtdiagnose mit Ampel-Report (validate + Drift + Orphans)
  release [stufe]    Transaktionaler Release mit Lock und Rollback
  export --okf       Bestand als OKF-v0.2-Bundle außerhalb des Tresors ausgeben
"""

import argparse
import hashlib
import heapq
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import unicodedata
from datetime import date
from pathlib import Path

# Die Ausgabe ist UTF-8, auch wenn die Umgebung etwas anderes vorgibt. Auf
# einer cp1252-Konsole (Windows-Voreinstellung) starb sonst jedes Kommando mit
# UnicodeEncodeError an der Ampel, statt lesbar zu bleiben. Nicht darstellbare
# Zeichen werden ersetzt, nie verschluckt.
for _strom in (sys.stdout, sys.stderr):
    if hasattr(_strom, "reconfigure"):
        try:
            _strom.reconfigure(encoding="utf-8", errors="backslashreplace")
        except (AttributeError, OSError, ValueError):
            pass

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
EXTERN_REGISTER = SOURCES / "EXTERN.md"
# Maschinenlokale Bindung externer Wurzeln. Bewusst AUSSERHALB des Manifests
# (siehe _tracked_path), genau wie log.md: ein absoluter Pfad ist eine
# Eigenschaft dieses Hosts, nicht des Artefakts. Ohne Bindung antwortet der
# Tresor vollständig — externe Auflösung meldet dann fail-closed "not_bound".
BINDUNG = ROOT / ".vault-extern.json"

PROFIL = "oksv-lite/1.3"
REQUIRED_FIELDS = ["type", "title", "domain", "status", "confidence",
                   "version", "stand", "sources", "tags"]
OPTIONAL_FIELDS = {"relations", "concepts", "geprueft_von", "geprueft_am",
                   "externe_quellen"}
# Optionale Skalarfelder brauchen eine eigene Typprüfung: die Textschleife in
# lade_seiten deckt nur Pflichtfelder ab, die Listenschleife nur LIST_FIELDS.
# Ohne diesen Satz würde 'geprueft_von:' ohne Wert stillschweigend zur leeren
# Liste und eine Inline-Liste als Wert bis in die Regex-Prüfung durchrutschen.
OPTIONAL_SCALAR_FIELDS = {"geprueft_von", "geprueft_am"}
LIST_FIELDS = {"sources", "tags", "relations", "concepts", "externe_quellen"}
STATUS_WERTE = {"aktiv", "veraltet", "in-pruefung"}
CONF_WERTE = {"hoch", "mittel", "niedrig"}
LOG_AKTIONEN = {"ingest", "update", "lint", "release", "note", "onboarding",
                "extern"}
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
# Eine Zeilenform, Präfix-Dispatch: S- ist eine lokal gehashte Quelle, X- eine
# aufgeführte externe Bezugsquelle. Eine zweite Regex wäre schlechter — die
# eine lehrbare Zeilenform ist das, was die Grammatik trägt.
CLAIM_RE = re.compile(
    r"^- \*\*(C-\d{4})\*\* \[((?:S|X)-\d{4}) \| ([^\]|]+?) \| "
    r"(Wortlaut|Beobachtung|Auslegung)\] (.+)$")
REL_RE = re.compile(r"^([a-z_]+) -> (.+)$")
LINK_RE = re.compile(r"\]\(([^)]*)\)")
REFERENCE_LINK_RE = re.compile(
    r"(?m)^[ \t]{0,3}\[[^\]\r\n]+\]:[ \t]*(\S.*)$"
)
HTML_LINK_RE = re.compile(r"<(?:a|img)\b", re.IGNORECASE)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Aktorgrammatik für geprueft_von. Bewusst strenger als OKF v0.2 §7: die Spec
# fixiert nur das Präfix, nicht den Zeichenvorrat. Deutsche Präfixe, weil der
# ganze Vertrag deutsch ist; die Abbildung auf human:/process: gehört in einen
# späteren Export, nicht in den Bestand.
ACTOR_RE = re.compile(
    r"^(?:mensch:[a-z0-9][a-z0-9._-]{0,63}"
    r"|prozess:[a-z0-9][a-z0-9._-]{0,63}"
    r"|agent:[A-Za-z0-9][A-Za-z0-9._-]{0,63}/[A-Za-z0-9][A-Za-z0-9._-]{0,63})$"
)
# Trust-Tiers nach OKF v0.2 §5.3. Sie werden ausschließlich ABGELEITET, nie
# gespeichert, und gehen niemals in das Ranking ein: sonst würde aus einem
# reproduzierbaren Score ein Vertrauensurteil (AD-01).
TIER_UNVERIFIED = "unverified"
TIER_MACHINE = "machine-confirmed"
TIER_HUMAN = "human-reviewed"

# ---- OKF-Export (nur ausgehend; der Tresor konsumiert kein fremdes OKF) ----
OKF_VERSION = "0.2"
# Die einzige Stelle exakter semantischer Deckung zwischen beiden Welten.
STATUS_OKF = {"aktiv": "stable", "veraltet": "deprecated", "in-pruefung": "draft"}
# Aktorpräfixe nach OKF v0.2 §7. Die Rückrichtung ist bei Großbuchstaben in
# IDs nicht eindeutig; der Export ist bewusst eine Einbahnstraße.
ACTOR_OKF = {"mensch:": "human:", "prozess:": "process:", "agent:": ""}
# Ein exportiertes Bundle hat keine Engine, kein Manifest und keine Regeln.
# Landet es in einem Skill-Ladeort, lädt ein Agent es als Wissensquelle ohne
# jede Absicherung. Genau diese Vermischung verhindert AD-06.
EXPORT_VERBOTENE_SEGMENTE = {".claude", ".codex"}
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
SID_RE = re.compile(r"^S-\d{4}$")
CID_RE = re.compile(r"^C-\d{4}$")
WORLD_ID_RE = re.compile(r"^BW-\d{4}$")
CONCEPT_ID_RE = re.compile(r"^B-\d{4}$")
REGION_ID_RE = re.compile(r"^R-\d{4}$")
XID_RE = re.compile(r"^X-\d{4}$")
ANCHOR_ID_RE = re.compile(r"^A-\d{4}$")
BINDUNGSSCHLUESSEL_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")

CONCEPT_SCHEMA = "skillsafe.begriffswelten/v1"
MEDIA_SCHEMA = "skillsafe.media/v1"
QUERY_SCHEMA = "skillsafe.query/v1"
ANCHORS_SCHEMA = "skillsafe.anchors/v1"
ORCHESTRATOR_SCHEMA = "skillsafe.orchestrator/v1"
BINDING_SCHEMA = "skillsafe.bindung/v1"
RETRIEVAL_PROFILE = "hybrid-local/v1"
EXTERN_RETRIEVAL_PROFILE = "extern-zweistufig/v1"
SEGMENTATION_PROFILE = "satzsegmentierung/v1"
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_QUERY_LENGTH = 1000
MAX_QUERY_LIMIT = 20
MAX_CONCEPT_EXPANSIONS = 32

# ---- Externe Bezugsquellen -------------------------------------------------
# Eine aufgeführte Bezugsquelle ist KEINE Internetrecherche: Titel, Art, Ziel,
# Trust und Rechte stehen namentlich in sources/EXTERN.md und sind über
# MANIFEST.sha256 gepinnt. Es gibt keinen Codepfad, der ein Ziel aus einer
# Anfrage, einem Dokument oder einer Antwort übernimmt.
EXTERN_ARTEN = {"markdown-tree", "skillsafe-vault"}
EXTERN_SCOPES = {"organisation", "fachbereich", "projekt", "persoenlich"}
EXTERN_BLOCK_ARTEN = {"absatz", "listenpunkt", "tabellenzelle", "ueberschrift",
                      "zitat"}
# Budgets werden GEZÄHLT, nie über eine Uhr gestoppt: ein Wall-Clock-Limit
# würde die Determinismus-Garantie aus dem Modul-Docstring brechen. Nur der
# Netzpfad kennt ein Zeitlimit, und der ist ausdrücklich als nicht
# reproduzierbar gekennzeichnet.
MAX_EXTERN_TIEFE = 12
MAX_EXTERN_EINTRAEGE = 20000
MAX_EXTERN_DOKUMENTE = 5000
MAX_EXTERN_BYTES_JE_DATEI = 1 * 1024 * 1024
MAX_EXTERN_BYTES_GESAMT = 64 * 1024 * 1024
MAX_EXTERN_STUFE1 = 24
MAX_EXTERN_TREFFER = 8
MAX_EXTERN_TOP_TOKENS = 12
# Abdeckung 0 fliegt raus, egal wie gut der Katalogtext aussah. Der Katalogtext
# ist ein schwaches Signal, der tatsächliche Bestand das starke.
EXTERN_ABDECKUNG_MIN = 1
# Netzgrenzen. Nur https, nur unter dem registrierten Präfix, nie eine
# Suchmaschine, nie ein Link aus dem Inhalt.
EXTERN_NETZ_TIMEOUT = 10
EXTERN_NETZ_MAX_REDIRECTS = 3
EXTERN_NETZ_MAX_ABRUFE = 20
EXTERN_CACHE_TTL = 6 * 3600
EXTERN_OFFLINE_ENV = "SKILLSAFE_OFFLINE"
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
# Erlaubte Dateiarten im Tresorbaum: Wissen ist Text, Registry oder
# registriertes Medium, die Engine ist genau EIN Python-Script. Alles andere
# (Archive, Binaries, Shellskripte, ein zweites Script) bricht fail-closed ab,
# und kein Tresorinhalt darf ausführbar sein. Aktive Bildformate bleiben über
# ACTIVE_MEDIA_SUFFIXES draußen.
ARTEFAKT_SUFFIXE = {".md", ".json", ".yaml", ".sha256"} | set(MEDIA_TYPES)
ARTEFAKT_DATEINAMEN = {"LICENSE", "VERSION"}
ENGINE_SCRIPT = "scripts/vault.py"
# OKF v0.2 §3.1 belegt diese Namen; sie duerfen keine Wissensseite sein.
RESERVIERTE_DATEINAMEN = {"index.md", "log.md"}
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


def _iso_date(value):
    """Kalendergültiges JJJJ-MM-TT oder None.

    Das Format allein genügt nicht: '2026-02-31' passiert DATE_RE, ist aber
    kein Datum. Rückgabe ist das date-Objekt, damit Aufrufer vergleichen
    können, ohne ein zweites Mal zu parsen.
    """
    text = str(value)
    if not DATE_RE.match(text):
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _trust_tier(actor):
    """Trust-Tier nach OKF v0.2 §5.3 ableiten, nie speichern.

    Die isinstance-Wache ist nicht kosmetisch: cmd_stats läuft bewusst auch
    auf einem roten Bestand, und ein Frontmatter mit Liste statt Text hätte
    dort einen rohen Traceback erzeugt, also genau dann, wenn man die
    Diagnose braucht.
    """
    if not isinstance(actor, str) or not actor:
        return TIER_UNVERIFIED
    return TIER_HUMAN if actor.startswith("mensch:") else TIER_MACHINE


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


def _first_alias_component(p: Path, basis: Path):
    """Ersten Symlink/Reparse-Point zwischen ``basis`` und ``p`` liefern.

    Ein Pfad außerhalb von ``basis`` gilt als Alias — das ist die Sperre, die
    verhindert, dass Tresorhelfer versehentlich fremde Bäume akzeptieren.
    Externe Wurzeln bekommen deshalb eigene Aufrufe mit eigener Basis, statt
    dass diese Prüfung aufgeweicht wird.
    """
    try:
        teile = Path(os.path.abspath(p)).relative_to(basis).parts
    except ValueError:
        return p
    aktuell = basis
    for teil in teile:
        aktuell = aktuell / teil
        if _is_path_alias(aktuell):
            return aktuell
    return None


def _first_symlink_component(p: Path):
    """Ersten Symlink/Reparse-Point zwischen Tresorwurzel und ``p`` liefern."""
    return _first_alias_component(p, ROOT)


def _safe_regular_file_within(p: Path, basis: Path) -> bool:
    """Nur echte, einfach verlinkte Dateien unterhalb von ``basis``."""
    if _first_alias_component(p, basis) is not None or not _resolved_within(p, basis):
        return False
    try:
        status = os.lstat(str(p))
    except OSError:
        return False
    return stat.S_ISREG(status.st_mode) and status.st_nlink == 1


def _safe_regular_file(p: Path) -> bool:
    """Nur echte, einfach verlinkte Dateien innerhalb des Tresors akzeptieren."""
    return _safe_regular_file_within(p, ROOT)


def _safe_directory_within(p: Path, basis: Path) -> bool:
    """Nur echte Verzeichnisse ohne Alias-Komponente unterhalb von ``basis``."""
    if _first_alias_component(p, basis) is not None or not _resolved_within(p, basis):
        return False
    try:
        return stat.S_ISDIR(os.lstat(str(p)).st_mode)
    except OSError:
        return False


def _safe_directory(p: Path) -> bool:
    """Nur echte Verzeichnisse ohne Symlink-Komponente akzeptieren."""
    return _safe_directory_within(p, ROOT)


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


def _rel_zu(p: Path, basis: Path) -> str:
    """Lexikalischer, portabler Pfad relativ zu einer beliebigen Basis."""
    return Path(os.path.abspath(p)).relative_to(basis).as_posix()


def _walk_tree_no_links_within(start: Path, basis: Path, *, max_tiefe=None,
                               max_eintraege=None):
    """Deterministischer Baumlauf unterhalb von ``basis``, ohne Alias zu folgen.

    ``max_tiefe`` und ``max_eintraege`` sind gezählte Budgets, keine Zeitlimits:
    ein Wall-Clock-Limit würde die Determinismus-Garantie brechen. Wird ein
    Budget überschritten, bricht der Lauf fail-closed ab, statt ein
    Teilergebnis zu liefern, das wie ein vollständiges aussieht.
    """
    if not _safe_directory_within(start, basis):
        return []
    ergebnis, stapel, besucht = [], [(start, 0)], 0
    while stapel:
        ordner, tiefe = stapel.pop()
        if max_tiefe is not None and tiefe > max_tiefe:
            raise OSError(
                f"{_rel_zu(ordner, basis)}: Verzeichnistiefe über {max_tiefe}"
            )
        try:
            with os.scandir(str(ordner)) as scan:
                eintraege = sorted(scan, key=lambda e: e.name, reverse=True)
        except OSError as exc:
            raise OSError(
                f"{_rel_zu(ordner, basis)}: Verzeichnis kann nicht gelesen "
                f"werden — {exc}"
            ) from exc
        for eintrag in eintraege:
            p = Path(eintrag.path)
            besucht += 1
            if max_eintraege is not None and besucht > max_eintraege:
                raise OSError(
                    f"{_rel_zu(basis, basis) or '.'}: mehr als {max_eintraege} "
                    f"Verzeichniseinträge"
                )
            ergebnis.append(p)
            try:
                status = eintrag.stat(follow_symlinks=False)
            except OSError as exc:
                raise OSError(
                    f"{_rel_zu(p, basis)}: Verzeichniseintrag kann nicht "
                    f"geprüft werden — {exc}"
                ) from exc
            reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
            attributes = getattr(status, "st_file_attributes", 0)
            alias = stat.S_ISLNK(status.st_mode) or bool(attributes & reparse_flag)
            if stat.S_ISDIR(status.st_mode) and not alias:
                stapel.append((p, tiefe + 1))
    return sorted(ergebnis, key=lambda p: _rel_zu(p, basis))


def _walk_tree_no_links(start: Path):
    """Deterministischer Baumlauf, der Symlinks/Junctions nie rekursiv folgt."""
    return _walk_tree_no_links_within(start, ROOT)


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


def _skill_fremdartefakte():
    """Dateiarten, die nicht in ein portables Wissensartefakt gehören.

    Rückgabe: Liste (Pfad, Grund). Geprüft wird nur, was das Manifest
    ohnehin abdeckt; Quarantäne-Payloads, Lock und Cache haben eigene
    Prüfungen. Ein gesetztes Ausführungsbit ist immer ein Fehler: der Tresor
    liefert Wissen aus, keinen ausführbaren Inhalt.
    """
    ergebnis = []
    for p in _walk_tree_no_links(ROOT):
        if _is_path_alias(p) or not _tracked_path(p):
            continue
        try:
            status = os.lstat(str(p))
        except OSError:
            continue
        if not stat.S_ISREG(status.st_mode):
            continue
        suffix = p.suffix.lower()
        if rel(p) == ENGINE_SCRIPT:
            erlaubt, benennung = True, "Engine-Script"
        elif suffix:
            erlaubt = suffix in ARTEFAKT_SUFFIXE
            benennung = f"Endung {suffix}"
        else:
            erlaubt = p.name in ARTEFAKT_DATEINAMEN
            benennung = "Datei ohne Endung"
        if not erlaubt:
            ergebnis.append((p, f"{benennung} ist im Tresor nicht vorgesehen"))
        elif status.st_mode & 0o111:
            ergebnis.append((p, "Ausführungsbit ist gesetzt"))
    return sorted(ergebnis, key=lambda eintrag: rel(eintrag[0]))


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
    ('key:' gefolgt von '  - wert'). Nichts Verschachteltes, bewusst,
    damit genau EIN einfacher, prüfbarer Parser genügt.

    Verschachtelung wird fail-closed abgelehnt und nicht toleriert. Ohne diese
    Prüfung zog die Blockform ('key:' gefolgt von '  unter: wert') ihre
    Unterschlüssel still ins Top-Level-Dictionary und machte den Wert zur
    leeren Liste. Das war Strukturkorruption ohne Fehlermeldung.
    Rückgabe: (dict, body, fehlerliste, body_offset in Dateizeilen)
    """
    fehler = []
    lines = text.split("\n")
    if not lines or lines[0].rstrip("\r") != "---":
        return {}, text, [f"{quelle}: kein Frontmatter (Datei muss mit '---' beginnen)"], 0
    fm, i, ende = {}, 1, None
    while i < len(lines):
        line = lines[i]
        # Der Terminator wird strikt geprüft. Ein eingerücktes '---' beendete
        # den Block früher stillschweigend, weil strip() die Einrückung
        # entfernt: alles danach landete im Body, und fehlten dabei nur
        # optionale Felder, blieb validate grün und der Graph verlor Kanten.
        if line.rstrip("\r") == "---":
            ende = i
            break
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        if line != line.lstrip() and not line.startswith("  - "):
            fehler.append(
                f"{quelle}:{i + 1}: Einrückung außerhalb der Profil-Untermenge; "
                f"verschachteltes Frontmatter ist nicht erlaubt: "
                f"{line.strip()!r}")
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


# ------------------------------------------------- satzsegmentierung/v1
#
# Der Satzindex ist Teil eines Ankers, also braucht die Zerlegung einen
# versionierten, deterministischen Algorithmus. Abkürzungen, nach denen ein
# Punkt kein Satzende ist. Ohne diese Liste zerlegte 'Das Profil nutzt z. B.
# flache Listen. Danach folgt mehr.' zu 'Das Profil nutzt z.' — und diese
# Beschreibung landet gleich zweimal im Bundle, im Frontmatter und im
# Domänen-Index.
SATZ_ABKUERZUNGEN = {
    "z", "b", "u", "a", "d", "h", "vgl", "bzw", "ca", "etc", "ff", "abs",
    "nr", "bspw", "ggf", "evtl", "inkl", "exkl", "max", "min", "sog", "usw",
    "s", "vs", "dr", "prof", "ebd", "bzgl", "o",
    "art", "lit", "rn", "bd", "hrsg", "aufl", "approx", "resp", "no", "fig",
    "pp", "cf", "e", "i", "g",
}
SATZENDE_RE = re.compile(r"([.!?])\s")
CODE_FENCE_RE = re.compile(r"^\s{0,3}(?:```|~~~)")
ATX_RE = re.compile(r"^\s{0,3}#{1,6}\s")
LIST_RE = re.compile(r"^\s*(?:[-*+]\s|\d+[.)]\s)")
QUOTE_RE = re.compile(r"^\s{0,3}>")
TABLE_RE = re.compile(r"^\s*\|")


def _satz_norm(text):
    """Normalisierung zum Zitieren: NFC, Whitespace kollabiert, getrimmt.

    Bewusst NFC und nicht das NFKC aus ``_retrieval_norm``: NFKC faltet
    Ligaturen und Formatzeichen und verändert damit den *Wortlaut*. Für
    Matching ist das richtig, für ein Zitat ist es falsch. Zwei
    Normalisierungen, zwei Zwecke, beide versioniert.
    """
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(text))).strip()


def _satz_digest(text):
    """SHA-256 über den normalisierten Satz — macht den Anker selbstprüfend."""
    return _sha256_bytes(_satz_norm(text).encode("utf-8"))


def _ist_satzende(kopf):
    """Ob der Punkt am Ende von ``kopf`` wirklich einen Satz beendet."""
    letztes = re.split(r"[\s(]", kopf)[-1].strip("„»‚'\"")
    if letztes.lower() in SATZ_ABKUERZUNGEN or len(letztes) == 1:
        return False
    if letztes.isdigit() or re.fullmatch(r"[§]?\d+", letztes):
        return False
    # Dezimalzahlen und Versionsbezeichner: 'v0.2', '3.14', '1.2.0'
    return not re.search(r"\d$", letztes)


def _bloecke(text):
    """Markdown in Blöcke zerlegen; Frontmatter und Code-Fences fallen weg.

    Beides enthält keine Sätze und würde sonst die Indizes verschieben.
    """
    zeilen = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    start = 0
    if zeilen and zeilen[0].strip() == "---":
        for i in range(1, len(zeilen)):
            if zeilen[i].strip() == "---":
                start = i + 1
                break
    bloecke, puffer, art, im_code = [], [], "absatz", False

    def abschliessen():
        if puffer:
            inhalt = " ".join(teil.strip() for teil in puffer if teil.strip())
            if inhalt:
                bloecke.append((art, inhalt))
            puffer.clear()

    for zeile in zeilen[start:]:
        if CODE_FENCE_RE.match(zeile):
            abschliessen()
            im_code = not im_code
            continue
        if im_code:
            continue
        if not zeile.strip():
            abschliessen()
            art = "absatz"
            continue
        if ATX_RE.match(zeile):
            abschliessen()
            bloecke.append(("ueberschrift", zeile.lstrip("# \t").strip()))
            art = "absatz"
            continue
        if TABLE_RE.match(zeile):
            abschliessen()
            for zelle in zeile.strip().strip("|").split("|"):
                if zelle.strip() and not re.fullmatch(r"[\s:-]+", zelle):
                    bloecke.append(("tabellenzelle", zelle.strip()))
            art = "absatz"
            continue
        if LIST_RE.match(zeile):
            abschliessen()
            art = "listenpunkt"
            puffer.append(LIST_RE.sub("", zeile, count=1))
            continue
        if QUOTE_RE.match(zeile):
            abschliessen()
            art = "zitat"
            puffer.append(QUOTE_RE.sub("", zeile, count=1))
            continue
        puffer.append(zeile)
    abschliessen()
    return bloecke


def _saetze(text):
    """Sätze eines Markdown-Textes als ``(index, blockart, satz)``.

    Ein Satz überschreitet nie eine Blockgrenze: Absatz, Listenpunkt,
    Tabellenzelle, Überschrift und Zitat beenden ihn immer.
    """
    ergebnis, index = [], 0
    for art, inhalt in _bloecke(text):
        rest, pos = inhalt, 0
        for treffer in SATZENDE_RE.finditer(inhalt):
            kopf = inhalt[pos:treffer.start()]
            if not _ist_satzende(inhalt[pos:treffer.start()]):
                continue
            satz = _satz_norm(kopf + treffer.group(1))
            if satz:
                index += 1
                ergebnis.append((index, art, satz))
            pos = treffer.end()
        rest = _satz_norm(inhalt[pos:])
        if rest:
            index += 1
            ergebnis.append((index, art, rest))
    return ergebnis


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
        if _plain_text(
            item.get("preferred"), f"{field}.preferred", errors, maximum=160
        ):
            # Begriffslabels wandern in Query-Ausgabe und Export. Sie waren
            # bisher schwächer geprüft als Claim-Text, obwohl sie denselben Weg
            # nach außen nehmen.
            if PROMPT_INJECTION_RE.search(item["preferred"]):
                errors.append(
                    f"{field}.preferred: enthält eine offensichtliche "
                    f"Instruktionssignatur")
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
                    if (_plain_text(value, value_field, errors, maximum=160)
                            and PROMPT_INJECTION_RE.search(value)):
                        errors.append(
                            f"{value_field}: enthält eine offensichtliche "
                            f"Instruktionssignatur")
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


def parse_extern_register():
    """sources/EXTERN.md-Tabelle lesen — die Allowlist externer Bezugsquellen.

    Spalten: | ID | Titel | Art | Ziel | Stand/Version | Bindungsschlüssel |
             | Trust | Rechte |

    ``Ziel`` ist entweder ein festes https-Präfix oder ``-`` für eine lokale
    Quelle. Ein absoluter lokaler Pfad steht hier NIE: er ist eine Eigenschaft
    des Hosts und bräche die Portabilität des Artefakts. Die Datei ist die
    einzige Stelle, die festlegt, was überhaupt erreichbar ist — es gibt
    keinen Codepfad, der ein Ziel aus Anfrage oder Inhalt übernimmt.
    """
    fehler, reg = [], {}
    if not _safe_regular_file(EXTERN_REGISTER):
        # Kein Fehler: ein Tresor ohne externe Bezugsquellen ist der Normalfall.
        return {}, []
    schluessel = {}
    for n, line in enumerate(read(EXTERN_REGISTER).split("\n"), 1):
        if not line.strip().startswith("| X-"):
            continue
        teile = [t.strip() for t in line.strip().strip("|").split("|")]
        if len(teile) != 8:
            fehler.append(
                f"{rel(EXTERN_REGISTER)}:{n}: erwartet 8 Spalten, "
                f"gefunden {len(teile)}"
            )
            continue
        xid, titel, art, ziel, stand, key, trust, rechte = teile
        if not XID_RE.match(xid):
            fehler.append(f"{rel(EXTERN_REGISTER)}:{n}: ungültige Quellen-ID {xid!r}")
            continue
        if xid in reg:
            fehler.append(f"{rel(EXTERN_REGISTER)}:{n}: doppelte Quellen-ID {xid}")
            continue
        for feldname, wert in (("Titel", titel), ("Art", art), ("Ziel", ziel),
                               ("Stand/Version", stand),
                               ("Bindungsschlüssel", key),
                               ("Trust", trust), ("Rechte", rechte)):
            if not wert:
                fehler.append(f"{rel(EXTERN_REGISTER)}:{n}: Feld {feldname} ist leer")
        if art not in EXTERN_ARTEN:
            fehler.append(
                f"{rel(EXTERN_REGISTER)}:{n}: Art {art!r} ist keine von "
                f"{sorted(EXTERN_ARTEN)}"
            )
        if trust not in TRUST_WERTE:
            fehler.append(
                f"{rel(EXTERN_REGISTER)}:{n}: Trust {trust!r} ist keine von "
                f"{sorted(TRUST_WERTE)}"
            )
        if not BINDUNGSSCHLUESSEL_RE.match(key):
            fehler.append(
                f"{rel(EXTERN_REGISTER)}:{n}: Bindungsschlüssel {key!r} muss "
                f"[a-z0-9][a-z0-9-]{{0,63}} sein"
            )
        elif key in schluessel:
            fehler.append(
                f"{rel(EXTERN_REGISTER)}:{n}: Bindungsschlüssel {key!r} ist "
                f"schon in Zeile {schluessel[key]} vergeben"
            )
        else:
            schluessel[key] = n
        url, url_fehler = (None, None) if ziel == "-" else _https_praefix(ziel)
        if url_fehler:
            fehler.append(f"{rel(EXTERN_REGISTER)}:{n}: Ziel — {url_fehler}")
        scope = None
        if art == "skillsafe-vault":
            gefunden = [wert for wert in EXTERN_SCOPES if wert in stand.lower()]
            if len(gefunden) != 1:
                fehler.append(
                    f"{rel(EXTERN_REGISTER)}:{n}: Stand/Version muss bei "
                    f"skillsafe-vault genau einen Scope aus "
                    f"{sorted(EXTERN_SCOPES)} nennen"
                )
            else:
                scope = gefunden[0]
        reg[xid] = {"titel": titel, "art": art, "ziel": ziel, "url": url,
                    "stand": stand, "key": key, "trust": trust,
                    "rechte": rechte, "scope": scope, "zeile": n}
    return reg, fehler


def _https_praefix(roh):
    """Ein registriertes Ziel als striktes https-Präfix prüfen.

    Rückgabe: ``(praefix, None)`` oder ``(None, grund)``. Bewusst streng:
    kein http, kein Benutzer/Passwort im Host, keine Query, kein Fragment.
    Ein Präfix ist ein Ort, kein Suchaufruf.
    """
    wert = str(roh).strip()
    if wert != str(roh):
        return None, "führende oder abschließende Leerzeichen sind verboten"
    if any(ord(z) < 32 or ord(z) == 127 for z in wert):
        return None, "Steuerzeichen sind verboten"
    if not wert.startswith("https://"):
        return None, "nur https:// ist erlaubt"
    rest = wert[len("https://"):]
    if not rest or rest.startswith("/"):
        return None, "Host fehlt"
    if "?" in wert or "#" in wert:
        return None, "Query und Fragment sind in einem Präfix verboten"
    if "@" in rest.split("/", 1)[0]:
        return None, "Zugangsdaten im Host sind verboten"
    if ".." in wert:
        return None, "'..' ist verboten"
    host = rest.split("/", 1)[0].split(":", 1)[0]
    if not re.fullmatch(r"[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?", host):
        return None, f"Host {host!r} ist nicht wohlgeformt"
    return wert, None


def parse_anchors(extern_register):
    """Satzanker streng validieren — das textuelle Gegenstück zu Medienregionen.

    Der ``text`` eines Ankers bleibt untrusted Quelldatum und wird vom
    Query-Pfad nie als Evidenz ausgegeben; Evidenz ist immer nur der
    kuratierte lokale Claim.
    """
    errors, anchors = [], {}
    if not _safe_directory(DERIVED):
        return {}, []
    try:
        entries = sorted(DERIVED.iterdir(), key=lambda path: path.name)
    except OSError as exc:
        return {}, [f"{rel(DERIVED)}: kann nicht gelesen werden — {exc}"]

    gesehene_ids = set()
    for path in entries:
        match = re.fullmatch(r"(X-\d{4})__anchors\.json", path.name)
        if not match:
            continue
        rp = rel(path)
        if not _safe_regular_file(path):
            errors.append(f"{rp}: nur einfach verlinkte reguläre Dateien erlaubt")
            continue
        filename_xid = match.group(1)
        data = _load_strict_json(path, rp, errors)
        if data is None:
            continue
        required = {"schema", "source_id", "source_kind", "segmentation",
                    "language", "extractor", "verified", "anchors"}
        if not _exact_keys(data, required, set(), rp, errors):
            continue
        if data.get("schema") != ANCHORS_SCHEMA:
            errors.append(f"{rp}.schema: erwartet {ANCHORS_SCHEMA!r}")
        if data.get("segmentation") != SEGMENTATION_PROFILE:
            errors.append(f"{rp}.segmentation: erwartet {SEGMENTATION_PROFILE!r}")
        xid = data.get("source_id")
        if not isinstance(xid, str) or not XID_RE.fullmatch(xid):
            errors.append(f"{rp}.source_id: erwartet X-nnnn")
            continue
        if xid != filename_xid:
            errors.append(f"{rp}.source_id: {xid!r} passt nicht zu {filename_xid}")
            continue
        if xid in anchors:
            errors.append(f"{rp}: Ankerdatei für {xid} ist doppelt")
            continue
        if xid not in extern_register:
            errors.append(f"{rp}.source_id: Quelle {xid!r} fehlt in {rel(EXTERN_REGISTER)}")
            continue
        if data.get("source_kind") != extern_register[xid]["art"]:
            errors.append(
                f"{rp}.source_kind: erwartet "
                f"{extern_register[xid]['art']!r} aus {rel(EXTERN_REGISTER)}"
            )
        language = data.get("language")
        if (not isinstance(language, str)
                or not re.fullmatch(r"(?:und|[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*)",
                                    language)):
            errors.append(f"{rp}.language: BCP-47-Kurzform oder 'und' erwartet")
        extractor = data.get("extractor")
        if _exact_keys(extractor, {"kind", "name", "version"}, set(),
                       f"{rp}.extractor", errors):
            if extractor.get("kind") not in EXTRACTOR_KINDS:
                errors.append(
                    f"{rp}.extractor.kind: erwartet einen Wert aus "
                    f"{sorted(EXTRACTOR_KINDS)}"
                )
            _plain_text(extractor.get("name"), f"{rp}.extractor.name", errors,
                        maximum=200)
            _plain_text(extractor.get("version"), f"{rp}.extractor.version",
                        errors, maximum=50)
        if data.get("verified") is not True:
            errors.append(
                f"{rp}.verified: muss vor einem Release true sein — ein "
                f"ungeprüfter Anker belegt nichts"
            )
        liste = data.get("anchors")
        if not isinstance(liste, list) or not liste:
            errors.append(f"{rp}.anchors: nicht leere Liste erwartet")
            continue
        eintraege = {}
        for pos, anker in enumerate(liste, 1):
            label = f"{rp}.anchors[{pos}]"
            felder = {"id", "document", "document_sha256", "sentence_index",
                      "block", "locator", "text", "text_sha256",
                      "suspicious_instruction"}
            if not _exact_keys(anker, felder, set(), label, errors):
                continue
            aid = anker.get("id")
            if not isinstance(aid, str) or not ANCHOR_ID_RE.fullmatch(aid):
                errors.append(f"{label}.id: erwartet A-nnnn")
                continue
            if aid in gesehene_ids:
                errors.append(f"{label}.id: {aid} ist tresorweit doppelt")
                continue
            gesehene_ids.add(aid)
            dokument = anker.get("document")
            if not isinstance(dokument, str):
                errors.append(f"{label}.document: Text erwartet")
                continue
            # Rein lexikalische Prüfung gegen ROOT: sie wirkt auch dann, wenn
            # die Quelle gar nicht gebunden ist, und ist damit unabhängig von
            # der Erreichbarkeit der Wurzel.
            _, pfadfehler = _safe_relative_path(ROOT, dokument)
            if pfadfehler:
                errors.append(f"{label}.document: unzulässiger Pfad — {pfadfehler}")
                continue
            if not dokument.endswith(".md"):
                errors.append(f"{label}.document: nur .md-Dokumente sind zitierbar")
            for feld in ("document_sha256", "text_sha256"):
                wert = anker.get(feld)
                if not isinstance(wert, str) or not HASH_RE.fullmatch(wert):
                    errors.append(f"{label}.{feld}: 64-stelliger SHA-256 erwartet")
            index = anker.get("sentence_index")
            if not isinstance(index, int) or isinstance(index, bool) or index < 1:
                errors.append(f"{label}.sentence_index: positive Ganzzahl erwartet")
            if anker.get("block") not in EXTERN_BLOCK_ARTEN:
                errors.append(
                    f"{label}.block: erwartet einen Wert aus "
                    f"{sorted(EXTERN_BLOCK_ARTEN)}"
                )
            _plain_text(anker.get("locator"), f"{label}.locator", errors, maximum=200)
            _plain_text(anker.get("text"), f"{label}.text", errors, maximum=2000)
            if not isinstance(anker.get("suspicious_instruction"), bool):
                errors.append(f"{label}.suspicious_instruction: Boolean erwartet")
            text = anker.get("text")
            if isinstance(text, str):
                if _satz_norm(text) != text:
                    errors.append(
                        f"{label}.text: muss nach satzsegmentierung/v1 "
                        f"normalisiert sein (NFC, einfache Leerzeichen)"
                    )
                elif (isinstance(anker.get("text_sha256"), str)
                        and _satz_digest(text) != anker["text_sha256"]):
                    errors.append(
                        f"{label}.text_sha256: passt nicht zum hinterlegten Satz"
                    )
                verdaechtig = bool(PROMPT_INJECTION_RE.search(text))
                if isinstance(anker.get("locator"), str):
                    verdaechtig = verdaechtig or bool(
                        PROMPT_INJECTION_RE.search(anker["locator"])
                    )
                if verdaechtig and anker.get("suspicious_instruction") is not True:
                    errors.append(
                        f"{label}: Instruktionssignatur erkannt — "
                        f"suspicious_instruction muss true sein"
                    )
            eintraege[aid] = anker
        anchors[xid] = {"meta": data, "anchors": eintraege}
    return anchors, errors


def parse_orchestrators(extern_register):
    """Katalogdateien externer Markdown-Bäume validieren.

    Der Orchestrator ist DATEN, kein zweites Script (AD-09): eine .json, die
    dieses Script liest. Er dient als Prefilter, nie als Wahrheit — Stufe 2
    des Rankings rechnet immer gegen den tatsächlich gelesenen Text.
    """
    errors, kataloge = [], {}
    if not _safe_directory(DERIVED):
        return {}, []
    try:
        entries = sorted(DERIVED.iterdir(), key=lambda path: path.name)
    except OSError as exc:
        return {}, [f"{rel(DERIVED)}: kann nicht gelesen werden — {exc}"]

    for path in entries:
        match = re.fullmatch(r"(X-\d{4})__orchestrator\.json", path.name)
        if not match:
            continue
        rp = rel(path)
        if not _safe_regular_file(path):
            errors.append(f"{rp}: nur einfach verlinkte reguläre Dateien erlaubt")
            continue
        data = _load_strict_json(path, rp, errors)
        if data is None:
            continue
        required = {"schema", "source_id", "segmentation",
                    "generated_from_sha256", "document_count", "documents"}
        if not _exact_keys(data, required, set(), rp, errors):
            continue
        if data.get("schema") != ORCHESTRATOR_SCHEMA:
            errors.append(f"{rp}.schema: erwartet {ORCHESTRATOR_SCHEMA!r}")
        if data.get("segmentation") != SEGMENTATION_PROFILE:
            errors.append(f"{rp}.segmentation: erwartet {SEGMENTATION_PROFILE!r}")
        xid = data.get("source_id")
        if not isinstance(xid, str) or not XID_RE.fullmatch(xid):
            errors.append(f"{rp}.source_id: erwartet X-nnnn")
            continue
        if xid != match.group(1):
            errors.append(f"{rp}.source_id: {xid!r} passt nicht zu {match.group(1)}")
            continue
        if xid not in extern_register:
            errors.append(f"{rp}.source_id: Quelle {xid!r} fehlt in {rel(EXTERN_REGISTER)}")
            continue
        if extern_register[xid]["art"] != "markdown-tree":
            errors.append(
                f"{rp}: ein Katalog ist nur für Art 'markdown-tree' vorgesehen "
                f"— ein fremder Tresor bringt seine Claims schon mit"
            )
            continue
        # Ein Katalog behauptet nichts, was er nicht halten kann. Bei einer
        # Netzquelle zeigt das Ziel auf einen beweglichen Ref; ein dort
        # eingefrorener Hash ist nach dem naechsten fremden Commit unwahr und
        # nur noch endlos nachziehbar. Deshalb: bei Netzquellen MUSS er fehlen,
        # bei lokalen Quellen MUSS er da sein — der Baum ist dort greifbar.
        # Die Regel wirkt in beide Richtungen, sonst ist sie keine.
        ist_netzquelle = bool(extern_register[xid].get("url"))
        wurzel_hash = data.get("generated_from_sha256")
        if ist_netzquelle:
            if wurzel_hash is not None:
                errors.append(
                    f"{rp}.generated_from_sha256: muss bei einer Netzquelle "
                    f"null sein — ein beweglicher Ref laesst sich nicht pinnen"
                )
        elif not isinstance(wurzel_hash, str) or not HASH_RE.fullmatch(wurzel_hash):
            errors.append(f"{rp}.generated_from_sha256: 64-stelliger SHA-256 erwartet")
        dokumente = data.get("documents")
        if not isinstance(dokumente, list) or not dokumente:
            errors.append(f"{rp}.documents: nicht leere Liste erwartet")
            continue
        if data.get("document_count") != len(dokumente):
            # Bewusst redundant: eine abgeschnittene Datei fällt so auf.
            errors.append(
                f"{rp}.document_count: {data.get('document_count')!r} passt "
                f"nicht zu {len(dokumente)} Einträgen"
            )
        gesehen, eintraege = set(), []
        for pos, dok in enumerate(dokumente, 1):
            label = f"{rp}.documents[{pos}]"
            felder = {"path", "sha256", "title", "summary", "tags",
                      "sentence_count", "token_count", "top_tokens"}
            if not _exact_keys(dok, felder, set(), label, errors):
                continue
            pfad = dok.get("path")
            if not isinstance(pfad, str):
                errors.append(f"{label}.path: Text erwartet")
                continue
            _, pfadfehler = _safe_relative_path(ROOT, pfad)
            if pfadfehler:
                errors.append(f"{label}.path: unzulässiger Pfad — {pfadfehler}")
                continue
            if not pfad.endswith(".md"):
                errors.append(f"{label}.path: nur .md-Dokumente werden katalogisiert")
            if pfad in gesehen:
                errors.append(f"{label}.path: {pfad!r} ist doppelt")
                continue
            gesehen.add(pfad)
            dok_hash = dok.get("sha256")
            if ist_netzquelle:
                if dok_hash is not None:
                    errors.append(
                        f"{label}.sha256: muss bei einer Netzquelle null sein"
                    )
            elif not isinstance(dok_hash, str) or not HASH_RE.fullmatch(dok_hash):
                errors.append(f"{label}.sha256: 64-stelliger SHA-256 erwartet")
            _plain_text(dok.get("title"), f"{label}.title", errors, maximum=300)
            _plain_text(dok.get("summary"), f"{label}.summary", errors,
                        maximum=600, allow_empty=True)
            for feld in ("sentence_count", "token_count"):
                wert = dok.get(feld)
                if not isinstance(wert, int) or isinstance(wert, bool) or wert < 0:
                    errors.append(f"{label}.{feld}: nicht negative Ganzzahl erwartet")
            for feld in ("tags", "top_tokens"):
                wert = dok.get(feld)
                if not isinstance(wert, list) or not all(
                        isinstance(t, str) and t for t in wert):
                    errors.append(f"{label}.{feld}: Liste nicht leerer Texte erwartet")
            eintraege.append(dok)
        kataloge[xid] = {"meta": data, "documents": eintraege}
    return kataloge, errors


def parse_bindung():
    """Maschinenlokale Bindung lesen. Fehlt sie, ist das NIE ein Fehler.

    Ungebunden ist der Normalzustand eines frisch entpackten Pakets: der
    Tresor antwortet dann vollständig aus seinem eigenen Bestand, und externe
    Auflösung meldet fail-closed ``not_bound``. Netzquellen stehen hier nie —
    ihre URL ist auf jedem Host dieselbe und schon durch die Registrierung
    gebunden.
    """
    if not _safe_regular_file(BINDUNG):
        return {"bindings": {}, "cache_ttl_seconds": EXTERN_CACHE_TTL}, []
    errors = []
    rp = rel(BINDUNG)
    data = _load_strict_json(BINDUNG, rp, errors)
    if data is None:
        return {"bindings": {}, "cache_ttl_seconds": EXTERN_CACHE_TTL}, errors
    if not _exact_keys(data, {"schema", "bindings"}, {"cache_ttl_seconds"},
                       rp, errors):
        return {"bindings": {}, "cache_ttl_seconds": EXTERN_CACHE_TTL}, errors
    if data.get("schema") != BINDING_SCHEMA:
        errors.append(f"{rp}.schema: erwartet {BINDING_SCHEMA!r}")
    ttl = data.get("cache_ttl_seconds", EXTERN_CACHE_TTL)
    if not isinstance(ttl, int) or isinstance(ttl, bool) or ttl < 0:
        errors.append(f"{rp}.cache_ttl_seconds: nicht negative Ganzzahl erwartet")
        ttl = EXTERN_CACHE_TTL
    liste = data.get("bindings")
    if not isinstance(liste, list):
        errors.append(f"{rp}.bindings: Liste erwartet")
        return {"bindings": {}, "cache_ttl_seconds": ttl}, errors
    bindings = {}
    for pos, eintrag in enumerate(liste, 1):
        label = f"{rp}.bindings[{pos}]"
        if not _exact_keys(eintrag, {"key", "source_id", "root", "bound_at"},
                           set(), label, errors):
            continue
        key, xid = eintrag.get("key"), eintrag.get("source_id")
        if not isinstance(key, str) or not BINDUNGSSCHLUESSEL_RE.fullmatch(key):
            errors.append(f"{label}.key: [a-z0-9][a-z0-9-]{{0,63}} erwartet")
            continue
        if not isinstance(xid, str) or not XID_RE.fullmatch(xid):
            errors.append(f"{label}.source_id: erwartet X-nnnn")
            continue
        if not _iso_date(eintrag.get("bound_at")):
            errors.append(f"{label}.bound_at: Datum JJJJ-MM-TT erwartet")
        if xid in bindings:
            errors.append(f"{label}.source_id: {xid} ist doppelt gebunden")
            continue
        bindings[xid] = {"key": key, "root": eintrag.get("root"),
                         "bound_at": eintrag.get("bound_at")}
    return {"bindings": bindings, "cache_ttl_seconds": ttl}, errors


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
        if re.fullmatch(r"X-\d{4}__(?:anchors|orchestrator)\.json", path.name):
            # Externe Registries haben eigene Parser (parse_anchors,
            # parse_orchestrators) und werden hier nur durchgelassen.
            continue
        match = re.fullmatch(r"(S-\d{4})__media\.json", path.name)
        if not match:
            errors.append(
                f"{rp}: erwartet Dateiname S-nnnn__media.json, "
                f"X-nnnn__anchors.json oder X-nnnn__orchestrator.json "
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

def lade_seiten(register, typen, reltypen, concepts=None, media=None,
                extern=None, anchors=None):
    """Alle Wissensseiten laden und prüfen. Rückgabe: (seiten, claims, fehler, warnungen)."""
    concepts = concepts or {}
    media = media or {}
    extern = extern or {}
    anchors = anchors or {}
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
                # 'sources' darf genau dann leer sein, wenn die Seite
                # ausschließlich aus aufgeführten externen Bezugsquellen
                # belegt ist. Ganz ohne Beleg bleibt sie unzulässig.
                if feld == "sources" and fm.get("externe_quellen"):
                    continue
                fehler.append(f"{rp}: Pflichtfeld {feld!r} fehlt oder ist leer")
        for feld in LIST_FIELDS:
            if feld in fm and not isinstance(fm[feld], list):
                fehler.append(f"{rp}: Frontmatter-Feld {feld!r} muss eine Liste sein")
        for feld in (set(REQUIRED_FIELDS) - LIST_FIELDS) | OPTIONAL_SCALAR_FIELDS:
            if feld in fm and not isinstance(fm[feld], str):
                fehler.append(f"{rp}: Frontmatter-Feld {feld!r} muss Text sein")
        typ = fm.get("type", "")
        if typ and typ not in typen:
            fehler.append(f"{rp}: Typ {typ!r} nicht in schema/types.yaml — "
                          f"Type-Onboarding durchführen, bevor eingelesen wird (fail-closed)")
        if p.name.lower() in RESERVIERTE_DATEINAMEN:
            fehler.append(
                f"{rp}: {p.name} ist ein reservierter Dateiname (OKF v0.2 §3.1) "
                f"und darf keine Wissensseite sein; beim Export würde der "
                f"generierte Index sie überschreiben")
        if p.parent.parent != KNOWLEDGE:
            fehler.append(f"{rp}: Seiten liegen genau eine Ebene tief: knowledge/<domäne>/<seite>.md")
        elif fm.get("domain") != p.parent.name:
            fehler.append(f"{rp}: domain={fm.get('domain')!r} ≠ Ordner {p.parent.name!r} "
                          f"(Quellentrennung ist baulich)")
        if fm.get("status") not in STATUS_WERTE:
            fehler.append(f"{rp}: status muss eins sein von {sorted(STATUS_WERTE)}")
        if fm.get("confidence") not in CONF_WERTE:
            fehler.append(f"{rp}: confidence muss eins sein von {sorted(CONF_WERTE)}")
        stand = _iso_date(fm.get("stand", ""))
        if stand is None:
            fehler.append(f"{rp}: stand muss ein gültiges Datum JJJJ-MM-TT sein")
        if not VERSION_RE.match(str(fm.get("version", ""))):
            fehler.append(f"{rp}: version muss SemVer sein (z. B. 1.0.0)")

        # Optionale Prüfangabe (OKF v0.2 §5.2/§5.3, hier flach und deutsch).
        # Sie tritt als Paar auf oder gar nicht: ein Prüfer ohne Datum ist
        # nicht nachvollziehbar, ein Datum ohne Prüfer nicht zurechenbar.
        geprueft_von = fm.get("geprueft_von")
        geprueft_am = fm.get("geprueft_am")
        if isinstance(geprueft_von, str) or isinstance(geprueft_am, str):
            if not (isinstance(geprueft_von, str) and isinstance(geprueft_am, str)):
                fehler.append(
                    f"{rp}: geprueft_von und geprueft_am treten nur gemeinsam "
                    f"auf; eine Prüfung braucht Prüfer und Datum")
        if isinstance(geprueft_von, str):
            if _plain_text(geprueft_von, f"{rp}: geprueft_von", fehler, maximum=128):
                if PROMPT_INJECTION_RE.search(geprueft_von):
                    fehler.append(
                        f"{rp}: geprueft_von enthält eine offensichtliche "
                        f"Instruktionssignatur")
                elif not ACTOR_RE.match(geprueft_von):
                    fehler.append(
                        f"{rp}: geprueft_von muss 'mensch:<id>', "
                        f"'prozess:<id>' oder 'agent:<name>/<version>' sein, "
                        f"nicht {geprueft_von!r}")
        if isinstance(geprueft_am, str):
            geprueft_datum = _iso_date(geprueft_am)
            if geprueft_datum is None:
                fehler.append(
                    f"{rp}: geprueft_am muss ein gültiges Datum JJJJ-MM-TT sein")
            elif stand is not None and geprueft_datum < stand:
                # Kein Fehler: eine Prüfung DARF älter als die letzte
                # inhaltliche Änderung sein. Sie ist dann nur nicht mehr
                # aussagekräftig, und genau das soll sichtbar werden.
                warnungen.append(
                    f"{rp}: geprueft_am {geprueft_am} liegt vor stand "
                    f"{fm.get('stand')} — die Prüfung deckt den aktuellen "
                    f"Inhalt nicht mehr")

        quellen = fm.get("sources", [])
        if not isinstance(quellen, list):
            quellen = []
        for sid in quellen:
            if not isinstance(sid, str) or not SID_RE.fullmatch(sid):
                fehler.append(f"{rp}: ungültige Quellen-ID {sid!r}")
            elif sid not in register:
                fehler.append(f"{rp}: Quelle {sid} steht nicht im Register")
        # Externe Bezugsquellen stehen in einem eigenen Feld, nicht in
        # 'sources:'. Grund: 'sources' bildet beim OKF-Export auf §5.1 ab und
        # wird an mehreren Stellen als Registerschlüssel gelesen. Ein Feld
        # additiv hinzuzufügen ist rückwärtskompatibel, die Bedeutung eines
        # bestehenden zu ändern ist es nicht.
        externe = fm.get("externe_quellen", [])
        if not isinstance(externe, list):
            externe = []
        if len(externe) != len(set(x for x in externe if isinstance(x, str))):
            fehler.append(f"{rp}: doppelte IDs in externe_quellen")
        for xid in externe:
            if not isinstance(xid, str) or not XID_RE.fullmatch(xid):
                fehler.append(f"{rp}: ungültige externe Quellen-ID {xid!r}")
            elif xid not in extern:
                fehler.append(
                    f"{rp}: externe Quelle {xid} steht nicht in "
                    f"{rel(EXTERN_REGISTER)}"
                )
        tags = fm.get("tags", [])
        if isinstance(tags, list):
            for tag in tags:
                if not isinstance(tag, str) or not _retrieval_norm(tag):
                    fehler.append(f"{rp}: ungültiger oder leerer Tag {tag!r}")
                elif any(zeichen in tag for zeichen in ",[]"):
                    fehler.append(
                        f"{rp}: Tag {tag!r} enthält ',' '[' oder ']'; in der "
                        f"Inline-Listenform ist das nicht darstellbar und "
                        f"zerlegt den Wert")
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
                              f"'- **C-nnnn** [S-nnnn|X-nnnn | Fundstelle | "
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
            ist_extern = sid.startswith("X-")
            if ist_extern:
                if sid not in extern:
                    fehler.append(
                        f"{rp}:{n}: {cid} verweist auf nicht aufgeführte "
                        f"externe Quelle {sid}"
                    )
                elif sid not in externe:
                    fehler.append(
                        f"{rp}:{n}: {cid} nutzt {sid}, aber {sid} fehlt in "
                        f"'externe_quellen:' des Frontmatters"
                    )
            elif sid not in register:
                fehler.append(f"{rp}:{n}: {cid} verweist auf unregistrierte Quelle {sid}")
            elif sid not in quellen:
                fehler.append(f"{rp}:{n}: {cid} nutzt {sid}, aber {sid} fehlt in "
                              f"'sources:' des Frontmatters")

            # Satzanker sind das textuelle Gegenstück zu Medienregionen: bei
            # einer externen Quelle enthält die Fundstelle genau eine
            # existierende A-nnnn, und ein als verdächtig markierter Anker
            # darf nie einen Claim tragen.
            anchor_id = None
            anchor_ids = re.findall(r"(?<![A-Za-z0-9])A-\d{4}(?![A-Za-z0-9])",
                                    fundstelle)
            if ist_extern:
                if len(anchor_ids) != 1:
                    fehler.append(
                        f"{rp}:{n}: {cid} auf externe Quelle {sid} braucht "
                        f"genau einen Satzanker A-nnnn in der Fundstelle"
                    )
                else:
                    anchor_id = anchor_ids[0]
                    anker = anchors.get(sid, {}).get("anchors", {}).get(anchor_id)
                    if anker is None:
                        fehler.append(
                            f"{rp}:{n}: {cid} verweist auf unbekannten Anker "
                            f"{anchor_id} in {sid}"
                        )
                    elif anker.get("suspicious_instruction") is True:
                        fehler.append(
                            f"{rp}:{n}: {cid} darf verdächtigen Anker "
                            f"{anchor_id} nicht als Evidenz nutzen"
                        )
            elif anchor_ids:
                fehler.append(
                    f"{rp}:{n}: {cid} nennt einen Satzanker, aber {sid} ist "
                    f"keine aufgeführte externe Bezugsquelle"
                )
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
                       "region": region_id, "anker": anchor_id,
                       "extern": ist_extern}
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
    extern, extern_errors = parse_extern_register()
    fehler += extern_errors
    anchors, anchor_errors = parse_anchors(extern)
    fehler += anchor_errors
    orchestrators, orchestrator_errors = parse_orchestrators(extern)
    fehler += orchestrator_errors

    try:
        for p in _skill_symlinks():
            fehler.append(f"{rel(p)}: Symlink im Tresor verboten — "
                          f"portable Releases enthalten nur echte Dateien/Ordner")
        for p in _skill_hardlinks():
            fehler.append(f"{rel(p)}: mehrfach hart verlinkte Datei im Tresor verboten "
                          f"— Inhalt könnte außerhalb der Ordnergrenze verändert werden")
        for p, grund in _skill_fremdartefakte():
            fehler.append(f"{rel(p)}: {grund} — der Tresor liefert Wissen aus, "
                          f"keinen ausführbaren Inhalt")
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
            register, typen, reltypen, concepts=concepts, media=media,
            extern=extern, anchors=anchors
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
    # Jede aufgeführte externe Quelle braucht ihre Ankerdatei; verwaiste Anker
    # sind eine Warnung, kein Fehler — sie belegen nur nichts (mehr).
    referenced_anchors = {
        (claim["quelle"], claim["anker"]) for claim in claims.values()
        if claim.get("anker")
    }
    for xid in sorted(extern):
        # Kein Fehler: eine Quelle darf aufgeführt sein, ohne dass schon ein
        # Claim sie zitiert — sie steht dann für das Nachschlagen bereit, und
        # ihr Katalog belegt das. Erst eine Quelle ohne Anker UND ohne Katalog
        # ist für gar nichts aufgeführt. Ein Claim ohne existierenden Anker
        # fällt im Claim-Zweig von lade_seiten auf, nicht hier.
        if xid not in anchors and xid not in orchestrators:
            warnungen.append(
                f"{rel(EXTERN_REGISTER)}: {xid} ist aufgeführt, aber weder "
                f"satzweise belegt noch katalogisiert — die Quelle trägt nichts"
            )
    for xid in sorted(anchors):
        for aid in sorted(anchors[xid]["anchors"]):
            if (xid, aid) not in referenced_anchors:
                warnungen.append(
                    f"sources/derived/{xid}__anchors.json: Anker {aid} wird "
                    f"von keinem Claim genutzt"
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
            extern_zusatz = (
                f", {len(extern)} externe Quellen" if extern else ""
            )
            print(f"🟢 validate: 0 Fehler, {len(warnungen)} Warnungen — "
                  f"{len(seiten)} Seiten, {len(claims)} Claims, "
                  f"{len(register)} Quellen{extern_zusatz}.")
    extern_kontext = {"register": extern, "anchors": anchors,
                      "orchestrators": orchestrators}
    return fehler, warnungen, seiten, claims, register, router, extern_kontext


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
            # Gegenstück zu page_paths: was ein Mensch AUSSERHALB des Bestands
            # nachlesen müsste. Nur Hinweis, nie Ersatz für "Nicht im Bestand".
            #
            # Zwei getrennte Felder, weil sie zwei verschiedene Fragen
            # beantworten: '…_available' ist das ANGEBOT (gibt es überhaupt
            # aufgeführte Quellen?) und steht auch ohne --extern, weil der
            # Antwort-Workflow genau dann entscheiden muss, ob Schritt 4c
            # existiert. '…_used' ist das ERGEBNIS (wurde live gelesen?).
            "external_lookup_available": False,
            "external_live_lookup_used": False,
            "external_reason": None,
            "external_document_paths": [],
        },
        "concepts": {"matched": [], "expanded": []},
        # Externe Bezugsquellen stehen bewusst in einem eigenen Block und nie
        # in 'evidence': ein externer Satz ist ein Zeiger, kein kuratierter
        # Claim dieses Bestands. Der Top-Level-'state' bleibt eingefroren,
        # damit bestehende Konsumenten nicht an einem neuen Wert brechen.
        "external": {
            "state": "not_requested",
            "algorithm": EXTERN_RETRIEVAL_PROFILE,
            "live": False,
            "fetched_at": None,
            "sources": [],
            "hits": [],
            "reason": None,
            "notes": [],
            "external_fingerprint": None,
        },
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

    (errors, warnings, pages, claims, register, _,
     extern_kontext) = cmd_validate(still=True)
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
        "extern": extern_kontext,
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
            # Präfix-Dispatch: X- steht im Extern-Register, S- im Quellen-
            # register. Ohne diesen Zweig lieferte .get() still ein leeres
            # dict, und der Claim bekäme eine leere Quellenangabe — ein
            # Bug, der aussieht wie eine Antwort.
            if claim.get("extern"):
                extern_zeile = snapshot["extern"]["register"].get(
                    claim["quelle"], {})
                source = {
                    "titel": extern_zeile.get("titel"),
                    "stand": extern_zeile.get("stand"),
                    "trust": extern_zeile.get("trust"),
                    "rechte": extern_zeile.get("rechte"),
                    "kind": "extern",
                }
            else:
                source = dict(snapshot["register"].get(claim["quelle"], {}))
                source["kind"] = "lokal"
            item = {
                "claim_id": claim["id"],
                "role": "retrieval_candidate",
                "page": path,
                "page_status": fm.get("status"),
                "page_confidence": fm.get("confidence"),
                "page_reviewed_by": fm.get("geprueft_von"),
                "page_reviewed_at": fm.get("geprueft_am"),
                "page_trust_tier": _trust_tier(fm.get("geprueft_von")),
                "score": int(score),
                "reasons": sorted(set(reasons)),
                "kind": claim["art"],
                "text": claim["text"],
                "source": {
                    "id": claim["quelle"],
                    "kind": source.get("kind"),
                    "title": source.get("titel"),
                    "stand": source.get("stand"),
                    "trust": source.get("trust"),
                    "rights": source.get("rechte"),
                    "locator": claim["fundstelle"],
                },
                "signals": [],
                "media": None,
                "anchor": None,
            }
            if claim["art"] == "Auslegung":
                item["signals"].append("interpretation")
            if fm.get("status") != "aktiv":
                item["signals"].append(f"page_status:{fm.get('status')}")
            if fm.get("confidence") == "niedrig":
                item["signals"].append("low_confidence")
            if source.get("trust") == "T3":
                item["signals"].append("source_trust:T3")
            # Nur die unterste Stufe wird als Signal geführt, analog zu
            # source_trust:T3. Der Tier ist abgeleitet, geht nie in den Score
            # ein und ist keine Zugriffskontrolle (OKF v0.2 §5.3).
            if item["page_trust_tier"] == TIER_UNVERIFIED:
                item["signals"].append(f"trust_tier:{TIER_UNVERIFIED}")
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
            # Satzanker: wie bei Medienregionen wird nur die geprüfte
            # Fundstelle ausgegeben, nie der externe Satz selbst. Der Wortlaut
            # bleibt untrusted Quelldatum in der Ankerdatei.
            anchor_id = claim.get("anker")
            ankerdatei = snapshot["extern"]["anchors"].get(claim["quelle"])
            if anchor_id and ankerdatei:
                anker = ankerdatei["anchors"].get(anchor_id, {})
                item["anchor"] = {
                    "anchor_id": anchor_id,
                    "document": anker.get("document"),
                    "sentence_index": anker.get("sentence_index"),
                    "block": anker.get("block"),
                    "text_sha256": anker.get("text_sha256"),
                }
                item["signals"].append("external_source")
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
            "reviewed_by": fm.get("geprueft_von"),
            "reviewed_at": fm.get("geprueft_am"),
            "trust_tier": _trust_tier(fm.get("geprueft_von")),
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
            "external_lookup_available": bool(
                snapshot["extern"]["register"]),
            "external_live_lookup_used": False,
            "external_reason": None,
            "external_document_paths": [],
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


def cmd_query(question_words, world=None, limit=8, extern=False,
              quellen_filter=None):
    query = " ".join(question_words)
    snapshot, error = _load_released_query_snapshot(query)
    if error is not None:
        _emit_query_json(error)
        return 1
    result = build_query_result(snapshot, world=world, limit=limit)
    # Ohne --extern verlässt kein Byte den Skill-Ordner. Das Flag macht am
    # Aufruf sichtbar, dass hier bewusst eine Ausnahme von Regel 2
    # (Vertrauen zur Abfragezeit) gemacht wird.
    if extern:
        block = build_external_result(snapshot, query,
                                      quellen_filter=quellen_filter)
        gelesen = block.pop("documents_read", [])
        result["external"] = block
        result["fallback"]["external_live_lookup_used"] = True
        result["fallback"]["external_reason"] = block.get("reason")
        result["fallback"]["external_document_paths"] = gelesen
    _emit_query_json(result)
    if result["state"] in {"candidates_found", "no_candidates"}:
        return 0
    return 2


def cmd_extern(aktion, xid=None, pfad=None):
    """Aufgeführte externe Bezugsquellen anzeigen und maschinenlokal binden."""
    register, fehler = parse_extern_register()
    for eintrag in fehler:
        print(f"🔴 FEHLER   {eintrag}")
    if fehler:
        return 1
    bindung, bindungsfehler = parse_bindung()
    for eintrag in bindungsfehler:
        print(f"🔴 FEHLER   {eintrag}")
    if bindungsfehler:
        return 1

    if aktion == "list":
        if not register:
            print(f"🟡 extern: {rel(EXTERN_REGISTER)} führt keine Quelle. "
                  f"Erreichbar ist ausschließlich, was dort namentlich steht.")
            return 0
        print(f"extern: {len(register)} aufgeführte Bezugsquelle(n)")
        for kennung in sorted(register):
            zeile = register[kennung]
            status = _extern_quelle_status(kennung, zeile, bindung)
            if status["modus"] == "netz":
                ampel, wo = "🟢", f"Netz {zeile['ziel']}"
                if not _netz_erlaubt():
                    ampel, wo = "🟡", f"{wo} ({EXTERN_OFFLINE_ENV} gesetzt)"
            elif status["modus"] == "lokal":
                ampel, wo = "🟢", f"lokal {status['wurzel']}"
            else:
                ampel, wo = "🟡", f"ungebunden — {status['grund']}"
            print(f"  {ampel} {kennung}  {zeile['art']:<16} {zeile['titel']}")
            print(f"       {wo}")
        return 0

    if xid not in register:
        print(f"🔴 extern: {xid!r} steht nicht in {rel(EXTERN_REGISTER)} — "
              f"eine nicht aufgeführte Quelle wird nie erreicht")
        return 1
    if register[xid]["ziel"] != "-":
        print(f"🔴 extern: {xid} ist eine Netzquelle und schon durch ihre "
              f"Registrierung gebunden; eine Maschinenbindung gibt es dafür nicht")
        return 1

    if aktion == "bind":
        wurzel, _, grund = _resolve_external_root(pfad)
        if grund:
            print(f"🔴 extern: Bindungswurzel abgelehnt — {grund}")
            return 1
        eintraege = [
            {"key": bindung["bindings"][k]["key"], "source_id": k,
             "root": bindung["bindings"][k]["root"],
             "bound_at": bindung["bindings"][k]["bound_at"]}
            for k in sorted(bindung["bindings"]) if k != xid
        ]
        # Überlappungssperre: zwei Wurzeln dürfen einander nicht enthalten,
        # sonst wäre nicht mehr entscheidbar, welche Quelle ein Dokument trägt.
        for vorhanden in eintraege:
            andere, _, fehlgrund = _resolve_external_root(vorhanden["root"])
            if fehlgrund:
                continue
            if _resolved_within(wurzel, andere) or _resolved_within(andere, wurzel):
                print(f"🔴 extern: Wurzel überlappt mit {vorhanden['source_id']} "
                      f"({vorhanden['root']})")
                return 1
        eintraege.append({"key": register[xid]["key"], "source_id": xid,
                          "root": str(wurzel),
                          "bound_at": date.today().isoformat()})
        eintraege.sort(key=lambda e: e["source_id"])
    elif aktion == "unbind":
        eintraege = [
            {"key": bindung["bindings"][k]["key"], "source_id": k,
             "root": bindung["bindings"][k]["root"],
             "bound_at": bindung["bindings"][k]["bound_at"]}
            for k in sorted(bindung["bindings"]) if k != xid
        ]
    else:
        print(f"🔴 extern: unbekannte Aktion {aktion!r}")
        return 1

    inhalt = json.dumps(
        {"schema": BINDING_SCHEMA, "bindings": eintraege,
         "cache_ttl_seconds": bindung["cache_ttl_seconds"]},
        ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    sicher, grund = _safe_output_target(BINDUNG)
    if not sicher:
        print(f"🔴 extern: unsicheres Schreibziel — {grund}")
        return 1
    try:
        _replace_files_transactionally({BINDUNG: inhalt.encode("utf-8")})
    except (OSError, RuntimeError, TypeError) as exc:
        print(f"🔴 extern: Schreiben fehlgeschlagen — {exc}")
        return 1
    print(f"🟢 extern: {xid} {'gebunden an ' + str(pfad) if aktion == 'bind' else 'gelöst'} "
          f"— {rel(BINDUNG)} steht bewusst außerhalb des Manifests")
    return 0


def cmd_anchor_template(xid, dokument):
    """Sätze eines externen Dokuments mit Index und Digest ausgeben.

    Nicht schreibend. Das Modell WÄHLT einen Satz aus, statt Zeilen zu zählen —
    die Zerlegung und das Hashen sind deterministische Skriptarbeit.
    """
    register, fehler = parse_extern_register()
    if fehler or xid not in register:
        print(json.dumps({
            "schema": ANCHORS_SCHEMA, "state": "invalid_source",
            "errors": fehler or [f"{xid} steht nicht in {rel(EXTERN_REGISTER)}"],
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 1
    bindung, _ = parse_bindung()
    status = _extern_quelle_status(xid, register[xid], bindung)
    if status["modus"] == "unbound":
        print(json.dumps({
            "schema": ANCHORS_SCHEMA, "state": "not_bound",
            "errors": [status["grund"]],
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 1
    text, digest, grund = _extern_dokument_text(
        status, dokument, bindung["cache_ttl_seconds"], xid, [])
    if grund:
        print(json.dumps({
            "schema": ANCHORS_SCHEMA, "state": "unreachable",
            "errors": [f"{dokument}: {grund}"],
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 1
    anker = []
    for index, art, satz in _saetze(text):
        anker.append({
            "id": f"A-{index:04d}",
            "document": dokument,
            "document_sha256": digest,
            "sentence_index": index,
            "block": art,
            "locator": "AUSFÜLLEN",
            "text": satz,
            "text_sha256": _satz_digest(satz),
            "suspicious_instruction": bool(PROMPT_INJECTION_RE.search(satz)),
        })
    print(json.dumps({
        "schema": ANCHORS_SCHEMA,
        "source_id": xid,
        "source_kind": register[xid]["art"],
        "segmentation": SEGMENTATION_PROFILE,
        "language": "de",
        "extractor": {"kind": "human", "name": "AUSFÜLLEN", "version": "1"},
        "verified": False,
        "anchors": anker,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def cmd_orchestrator_template(xid):
    """Katalog-Gerüst für einen externen Markdown-Baum ausgeben.

    Alle Zahlenfelder sind nachrechenbar und kommen aus dem Script; ``title``,
    ``summary`` und ``tags`` bleiben leer und sind Modellarbeit. Genau diese
    Trennlinie ist später der Prüfpunkt.
    """
    register, fehler = parse_extern_register()
    if fehler or xid not in register:
        print(json.dumps({
            "schema": ORCHESTRATOR_SCHEMA, "state": "invalid_source",
            "errors": fehler or [f"{xid} steht nicht in {rel(EXTERN_REGISTER)}"],
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 1
    if register[xid]["art"] != "markdown-tree":
        print(json.dumps({
            "schema": ORCHESTRATOR_SCHEMA, "state": "invalid_source",
            "errors": [f"{xid} ist kein markdown-tree — ein fremder Tresor "
                       f"bringt seine Claims schon mit"],
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 1
    bindung, _ = parse_bindung()
    status = _extern_quelle_status(xid, register[xid], bindung)
    if status["modus"] != "lokal":
        print(json.dumps({
            "schema": ORCHESTRATOR_SCHEMA, "state": "not_bound",
            "errors": [status["grund"] or
                       "ein Katalog entsteht aus einem lokal gebundenen Baum"],
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 1
    dokumente, grund = _extern_dokumente(status["wurzel"], status["anker"])
    if grund:
        print(json.dumps({
            "schema": ORCHESTRATOR_SCHEMA, "state": "budget_exceeded",
            "errors": [grund],
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 1
    eintraege = []
    for dok in dokumente:
        saetze = _saetze(dok["text"])
        haeufigkeit = {}
        for _, _, satz in saetze:
            for token in _retrieval_tokens(satz):
                haeufigkeit[token] = haeufigkeit.get(token, 0) + 1
        top = sorted(haeufigkeit.items(), key=lambda e: (-e[1], e[0]))
        eintraege.append({
            "path": dok["path"],
            "sha256": dok["sha256"],
            "title": "AUSFÜLLEN",
            "summary": "",
            "tags": [],
            "sentence_count": len(saetze),
            "token_count": sum(haeufigkeit.values()),
            "top_tokens": [token for token, _ in top[:MAX_EXTERN_TOP_TOKENS]],
        })
    fingerprint = _sha256_bytes("".join(
        f"{dok['path']}\0{dok['sha256']}\n" for dok in dokumente
    ).encode("utf-8"))
    print(json.dumps({
        "schema": ORCHESTRATOR_SCHEMA,
        "source_id": xid,
        "segmentation": SEGMENTATION_PROFILE,
        "generated_from_sha256": fingerprint,
        "document_count": len(eintraege),
        "documents": eintraege,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


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


# ------------------------------------------- Externe Bezugsquellen
#
# Grundsatz: Eine aufgeführte Bezugsquelle ist KEINE Internetrecherche. Es gibt
# keine Suche, keinen Suchendpunkt und kein Folgen von Links aus Inhalten —
# erreichbar ist ausschließlich, was namentlich in sources/EXTERN.md steht und
# damit über MANIFEST.sha256 gepinnt ist. Deshalb wird eine aufgeführte
# Netzquelle behandelt wie eine interne Quelle, und deshalb ist jeder Abruf im
# Log nachlesbar.
#
# Zweite Grundregel: Auf dem Default-Query-Pfad passiert nichts davon. Ohne
# --extern verlässt kein Byte den Skill-Ordner, weder zur Platte noch ins Netz.

def _extern_cache_dir(xid):
    """TTL-Abzug außerhalb des Skill-Ordners.

    Innerhalb von ROOT liefe jeder Cache-Eintrag durch den Dateiart-Walk
    (_skill_fremdartefakte) und den Manifest-Walk (_tracked_files) und
    verunreinigte das Artefakt. Der Cache ist flüchtige Maschinensache.
    """
    basis = os.environ.get("XDG_CACHE_HOME") or os.path.join(
        os.path.expanduser("~"), ".cache")
    return Path(basis) / "skillsafe" / ROOT.name / xid


def _resolve_external_root(roh):
    """Gebundene externe Wurzel fail-closed auflösen.

    Rückgabe: ``(pfad, anker, None)`` oder ``(None, None, grund)``. ``anker``
    ist ``(st_dev, st_ino)`` und wird bei jeder Datei erneut geprüft, damit ein
    unter der Hand ausgetauschter Mount auffällt.

    Dies ist die einzige Stelle im System, an der ein absoluter Pfad zulässig
    ist. Die Tresorhelfer bleiben unverändert auf ROOT festgenagelt; hier
    entsteht ein zweites, gleich strenges Confinement.
    """
    if not isinstance(roh, str) or not roh.strip():
        return None, None, "Bindungswurzel fehlt"
    wert = roh.strip()
    if wert != roh:
        return None, None, "führende oder abschließende Leerzeichen sind verboten"
    if any(ord(z) < 32 or ord(z) == 127 for z in wert):
        return None, None, "Steuerzeichen sind in Pfaden verboten"
    kandidat = Path(wert)
    if not kandidat.is_absolute():
        return None, None, "Bindungswurzel muss ein absoluter Pfad sein"
    if ".." in kandidat.parts:
        return None, None, "'..' ist in der Bindungswurzel verboten"
    try:
        aufgeloest = kandidat.resolve(strict=True)
    except OSError as exc:
        return None, None, f"Bindungswurzel nicht lesbar — {exc}"
    # Bewusst AUFLÖSEN statt kanonische Eingabe zu verlangen. Eine frühere
    # Fassung lehnte jede nicht schon kanonische Wurzel ab; das machte den
    # Tresor auf macOS unbrauchbar, weil dort /var selbst ein Symlink auf
    # /private/var ist und das Betriebssystem Temporärpfade so ausliefert.
    # Die Prüfung war zu streng für das, was sie schützen sollte.
    #
    # Die tragende Zusage ist nicht „die Eingabe war kanonisch", sondern „wir
    # arbeiten auf einer vollständig aufgelösten Wurzel und folgen darunter
    # nie einem Link": _walk_tree_no_links_within folgt keinem Alias, jedes
    # Öffnen nutzt O_NOFOLLOW, und der (st_dev, st_ino)-Anker fällt auf, wenn
    # jemand die Wurzel unter der Hand austauscht. Gebunden und gespeichert
    # wird der aufgelöste Pfad, damit nichts still umgeleitet wird.
    try:
        status = os.lstat(str(aufgeloest))
    except OSError as exc:
        return None, None, f"Bindungswurzel nicht prüfbar — {exc}"
    if not stat.S_ISDIR(status.st_mode):
        return None, None, "Bindungswurzel ist kein Verzeichnis"
    # Beidseitige Rückverweis-Sperre: ein Tresor bindet sich nie selbst, und
    # eine Wurzel schließt den Tresor nie ein.
    tresor = ROOT.resolve(strict=False)
    if _resolved_within(tresor, aufgeloest) or _resolved_within(aufgeloest, tresor):
        return None, None, (
            "Bindungswurzel und Tresor dürfen einander nicht enthalten"
        )
    return aufgeloest, (status.st_dev, status.st_ino), None


def _lies_externes_dokument(wurzel, anker, relpfad):
    """Ein einzelnes externes Dokument eingesperrt lesen.

    Rückgabe: ``(text, sha256, None)`` oder ``(None, None, grund)``.
    """
    ziel, pfadfehler = _safe_relative_path(wurzel, relpfad)
    if pfadfehler:
        return None, None, pfadfehler
    flags = (os.O_RDONLY | getattr(os, "O_BINARY", 0)
             | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    try:
        fd = os.open(str(ziel), flags)
    except OSError as exc:
        return None, None, f"nicht lesbar — {exc}"
    try:
        status = os.fstat(fd)
        # Nur echte Dateien. O_NONBLOCK verhindert, dass ein untergeschobenes
        # FIFO den Prozess am Öffnen hängen lässt.
        if not stat.S_ISREG(status.st_mode):
            return None, None, "keine reguläre Datei"
        if anker is not None and status.st_dev != anker[0]:
            return None, None, (
                "liegt auf einem anderen Dateisystem als die Bindungswurzel"
            )
        if status.st_size > MAX_EXTERN_BYTES_JE_DATEI:
            return None, None, (
                f"größer als {MAX_EXTERN_BYTES_JE_DATEI} Byte"
            )
        # st_nlink wird bewusst NICHT geprüft, anders als in
        # _safe_regular_file: die Hardlink-Regel schützt die Portabilität des
        # Artefakts. Auf einem rein lesenden Pfad, dessen Bytes nie
        # manifestiert werden, schützt sie nichts.
        with os.fdopen(fd, "rb", closefd=False) as f:
            rohdaten = f.read(MAX_EXTERN_BYTES_JE_DATEI + 1)
    except OSError as exc:
        return None, None, f"nicht lesbar — {exc}"
    finally:
        os.close(fd)
    if len(rohdaten) > MAX_EXTERN_BYTES_JE_DATEI:
        return None, None, f"größer als {MAX_EXTERN_BYTES_JE_DATEI} Byte"
    try:
        text = rohdaten.decode("utf-8")
    except UnicodeError as exc:
        return None, None, f"kein gültiges UTF-8 — {exc}"
    return text, _sha256_bytes(rohdaten), None


def _extern_dokumente(wurzel, anker):
    """Alle Markdown-Dokumente einer externen Wurzel deterministisch sammeln.

    Rückgabe: ``(liste, None)`` oder ``(None, grund)``. Budgets werden gezählt,
    nie über eine Uhr gestoppt — sonst wäre das Ergebnis nicht reproduzierbar.
    """
    try:
        baum = _walk_tree_no_links_within(
            wurzel, wurzel, max_tiefe=MAX_EXTERN_TIEFE,
            max_eintraege=MAX_EXTERN_EINTRAEGE,
        )
    except OSError as exc:
        return None, str(exc)
    ergebnis, gesamt = [], 0
    for p in baum:
        relpfad = _rel_zu(p, wurzel)
        # Punkt-Verzeichnisse sind kein Wissen (.git und Konsorten).
        if any(teil.startswith(".") for teil in Path(relpfad).parts):
            continue
        if p.suffix.lower() != ".md":
            continue
        if not _safe_regular_file_within(p, wurzel):
            # Fail closed statt still überspringen: eine Datei, die wie ein
            # Dokument heißt, aber keines ist (FIFO, Symlink, Gerätedatei),
            # ist eine Auffälligkeit und kein Rauschen.
            return None, f"{relpfad}: keine reguläre Datei"
        if len(ergebnis) >= MAX_EXTERN_DOKUMENTE:
            return None, f"mehr als {MAX_EXTERN_DOKUMENTE} Markdown-Dokumente"
        text, digest, grund = _lies_externes_dokument(wurzel, anker, relpfad)
        if grund:
            return None, f"{relpfad}: {grund}"
        gesamt += len(text.encode("utf-8"))
        if gesamt > MAX_EXTERN_BYTES_GESAMT:
            return None, f"mehr als {MAX_EXTERN_BYTES_GESAMT} Byte insgesamt"
        ergebnis.append({"path": relpfad, "sha256": digest, "text": text})
    return ergebnis, None


def _https_ziel(praefix, relpfad):
    """Vollständige URL unter dem registrierten Präfix bilden."""
    _, pfadfehler = _safe_relative_path(ROOT, relpfad)
    if pfadfehler:
        return None, pfadfehler
    return praefix.rstrip("/") + "/" + relpfad, None


def _netz_erlaubt():
    """Harte Offline-Schaltung. CI setzt sie, damit kein Test ins Netz kann."""
    return os.environ.get(EXTERN_OFFLINE_ENV, "").strip() not in {"1", "true", "yes"}


def _hole_https(url, praefix, *, opener=None):
    """Ein Dokument unter dem registrierten Präfix abrufen.

    Rückgabe: ``(bytes, None)`` oder ``(None, grund)``. Bewusst eng: nur https,
    Zertifikatsprüfung zwingend, Redirects nur unterhalb desselben Präfix,
    keine Auth-Header, keine Cookies. Ein Redirect, das das Präfix verlässt,
    ist ein Abbruch und kein Umweg.
    """
    import ssl
    import urllib.error
    import urllib.request

    if not _netz_erlaubt():
        return None, f"{EXTERN_OFFLINE_ENV} ist gesetzt — kein Netzzugriff"
    if not url.startswith("https://") or not url.startswith(praefix):
        return None, "Ziel liegt nicht unter dem registrierten Präfix"
    kontext = ssl.create_default_context()
    aktuell, gesehen = url, 0
    while True:
        anfrage = urllib.request.Request(
            aktuell, method="GET",
            headers={"User-Agent": f"SkillSafe/{ROOT.name} (wissenstresor)",
                     "Accept": "text/markdown, text/plain"},
        )
        try:
            if opener is not None:
                antwort = opener(anfrage, timeout=EXTERN_NETZ_TIMEOUT)
            else:
                antwort = urllib.request.urlopen(
                    anfrage, timeout=EXTERN_NETZ_TIMEOUT, context=kontext)
        except urllib.error.HTTPError as exc:
            if exc.code in (301, 302, 303, 307, 308):
                ziel = exc.headers.get("Location", "")
                gesehen += 1
                if gesehen > EXTERN_NETZ_MAX_REDIRECTS:
                    return None, "zu viele Weiterleitungen"
                if not ziel.startswith(praefix):
                    return None, (
                        "Weiterleitung verlässt das registrierte Präfix"
                    )
                aktuell = ziel
                continue
            return None, f"HTTP {exc.code}"
        except (urllib.error.URLError, OSError, ValueError) as exc:
            return None, f"nicht erreichbar — {exc}"
        with antwort:
            endgueltig = getattr(antwort, "url", aktuell) or aktuell
            if not endgueltig.startswith(praefix):
                return None, "Weiterleitung verlässt das registrierte Präfix"
            rohdaten = antwort.read(MAX_EXTERN_BYTES_JE_DATEI + 1)
        if len(rohdaten) > MAX_EXTERN_BYTES_JE_DATEI:
            return None, f"größer als {MAX_EXTERN_BYTES_JE_DATEI} Byte"
        return rohdaten, None


def _katalog_score(dokument, query_norm, tokens):
    """Stufe 1: Katalogtext. Bewusst dieselben Gewichte wie die Seitenebene.

    Der Katalogtext ist ein SCHWACHES Signal — er entscheidet nur, welche
    Dokumente überhaupt geöffnet werden, nie welches gewinnt.
    """
    score = 0
    titel = _retrieval_norm(dokument.get("title", ""))
    if _phrase_present(titel, query_norm):
        score += 80
    titel_tokens = set(_retrieval_tokens(dokument.get("title", "")))
    tag_tokens = set()
    for tag in dokument.get("tags", []):
        tag_tokens |= set(_retrieval_tokens(tag))
    summary_tokens = set(_retrieval_tokens(dokument.get("summary", "")))
    top_tokens = set()
    for token in dokument.get("top_tokens", []):
        top_tokens |= set(_retrieval_tokens(token))
    for token in tokens:
        if token in titel_tokens:
            score += 30
        if token in tag_tokens:
            score += 24
        if token in summary_tokens:
            score += 12
        if token in top_tokens:
            score += 12
    return score


def _bestand_score(text, query_norm, tokens):
    """Stufe 2: der tatsächliche Satzbestand. Das starke Signal.

    Abgeglichen wird ausschließlich über ``_retrieval_tokens`` und
    ``_phrase_present`` — beide treffen nur an Tokengrenzen. Ein rohes ``in``
    auf ungeteilten Strings gibt es hier nicht, sonst fände „himmel" ein
    „schimmel". Der Fehler ist strukturell ausgeschlossen, nicht per
    Konvention vermieden.
    """
    saetze = _saetze(text)
    getroffen, bester, beste_zahl = set(), None, -1
    volltreffer, phrase = 0, False
    for index, art, satz in saetze:
        satz_tokens = set(_retrieval_tokens(satz))
        treffer = satz_tokens & set(tokens)
        getroffen |= treffer
        if tokens and treffer == set(tokens):
            volltreffer += 1
        if _phrase_present(_retrieval_norm(satz), query_norm):
            phrase = True
        if len(treffer) > beste_zahl:
            beste_zahl, bester = len(treffer), (index, art, satz)
    abdeckung = (100 * len(getroffen) // len(tokens)) if tokens else 0
    score = 4 * abdeckung + 40 * volltreffer + 20 * len(getroffen)
    if phrase:
        score += 80
    return {"score": score, "coverage": abdeckung, "satz": bester,
            "treffer": len(getroffen)}


def _extern_quelle_status(xid, zeile, bindung):
    """Bindungszustand einer aufgeführten Quelle bestimmen.

    Netzquellen sind schon durch ihre Registrierung gebunden: ihre URL ist auf
    jedem Host dieselbe. Lokale Quellen brauchen die maschinenlokale Bindung,
    weil ein absoluter Pfad nichts über das Artefakt aussagt.
    """
    if zeile.get("url"):
        return {"modus": "netz", "wurzel": None, "anker": None,
                "praefix": zeile["url"], "grund": None}
    eintrag = bindung["bindings"].get(xid)
    if not eintrag:
        return {"modus": "unbound", "wurzel": None, "anker": None,
                "praefix": None,
                "grund": f"{xid} ist auf diesem Host nicht gebunden — "
                         f"'vault.py extern bind {xid} <pfad>'"}
    wurzel, anker, grund = _resolve_external_root(eintrag.get("root"))
    if grund:
        return {"modus": "unbound", "wurzel": None, "anker": None,
                "praefix": None, "grund": f"{xid}: {grund}"}
    return {"modus": "lokal", "wurzel": wurzel, "anker": anker,
            "praefix": None, "grund": None}


def _extern_dokument_text(status, relpfad, ttl, xid, protokoll):
    """Ein externes Dokument JETZT lesen — Platte oder Netz.

    „Live" heißt hier wörtlich: der Katalog ist nur Prefilter, gerechnet wird
    gegen den Text, der in diesem Moment dort steht.
    """
    if status["modus"] == "lokal":
        return _lies_externes_dokument(status["wurzel"], status["anker"], relpfad)
    url, grund = _https_ziel(status["praefix"], relpfad)
    if grund:
        return None, None, grund
    cache = _extern_cache_dir(xid) / (_sha256_bytes(url.encode("utf-8")) + ".md")
    alter = None
    try:
        if cache.is_file() and not cache.is_symlink():
            alter = int(max(0.0, _jetzt() - cache.stat().st_mtime))
            if ttl and alter <= ttl:
                rohdaten = cache.read_bytes()
                protokoll.append({"url": url, "cache_age_seconds": alter,
                                  "bytes": len(rohdaten),
                                  "sha256": _sha256_bytes(rohdaten)})
                return (rohdaten.decode("utf-8", errors="replace"),
                        _sha256_bytes(rohdaten), None)
    except OSError:
        alter = None
    rohdaten, grund = _hole_https(url, status["praefix"])
    if grund:
        return None, None, grund
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(rohdaten)
    except OSError:
        pass
    protokoll.append({"url": url, "cache_age_seconds": 0,
                      "bytes": len(rohdaten), "sha256": _sha256_bytes(rohdaten)})
    try:
        text = rohdaten.decode("utf-8")
    except UnicodeError as exc:
        return None, None, f"kein gültiges UTF-8 — {exc}"
    return text, _sha256_bytes(rohdaten), None


def _jetzt():
    """Wanduhr, gekapselt: sie kommt ausschließlich im Netzpfad vor."""
    import time
    return time.time()


def _lese_fremden_tresor(wurzel, anker):
    """Einen fremden SkillSafe als DATEN lesen. Sein Script läuft nie.

    Wir rechnen sein MANIFEST.sha256 mit unserem eigenen ``sha256_file`` nach,
    bevor wir irgendetwas glauben. Sein ``scripts/vault.py`` ist an dieser
    Stelle eine Datei mit einer Prüfsumme — kein import, kein exec, kein
    subprocess (AD-09, eiserne Regel 5).
    """
    manifest, digest, grund = _lies_externes_dokument(
        wurzel, anker, "MANIFEST.sha256")
    if grund:
        return None, f"MANIFEST.sha256 — {grund}"
    geprueft = 0
    for zeile in manifest.split("\n"):
        if not zeile.strip():
            continue
        teile = zeile.split(maxsplit=1)
        if len(teile) != 2 or not HASH_RE.fullmatch(teile[0]):
            return None, "MANIFEST.sha256 ist nicht lesbar"
        soll, relpfad = teile[0], teile[1].strip().lstrip("*")
        ziel, pfadfehler = _safe_relative_path(wurzel, relpfad)
        if pfadfehler:
            return None, f"MANIFEST.sha256 nennt {relpfad!r} — {pfadfehler}"
        try:
            ist = sha256_file(ziel)
        except OSError as exc:
            return None, f"{relpfad} nicht prüfbar — {exc}"
        if ist != soll:
            return None, (
                f"{relpfad}: Prüfsumme weicht vom fremden Manifest ab — "
                f"der fremde Bestand ist nicht vertrauenswürdig"
            )
        geprueft += 1
    if not geprueft:
        return None, "MANIFEST.sha256 ist leer"

    dokumente = []
    for p in _walk_tree_no_links_within(
            wurzel / "knowledge", wurzel, max_tiefe=MAX_EXTERN_TIEFE,
            max_eintraege=MAX_EXTERN_EINTRAEGE):
        if p.suffix.lower() != ".md" or not _safe_regular_file_within(p, wurzel):
            continue
        relpfad = _rel_zu(p, wurzel)
        text, _, grund = _lies_externes_dokument(wurzel, anker, relpfad)
        if grund:
            return None, f"{relpfad}: {grund}"
        dokumente.append({"path": relpfad, "text": text})
    return {"documents": dokumente, "manifest_sha256": digest,
            "files": geprueft}, None


def build_external_result(snapshot, query, quellen_filter=None):
    """Externe Bezugsquellen zweistufig durchsuchen.

    Ergebnisse landen NIE in ``evidence`` und nie im lokalen
    ``retrieval_fingerprint``: ein externer Satz ist ein Zeiger auf fremdes
    Material, kein kuratierter Claim dieses Bestands.
    """
    bindung, bindungsfehler = parse_bindung()
    register = snapshot["extern"]["register"]
    kataloge = snapshot["extern"]["orchestrators"]
    query_norm = _retrieval_norm(query)
    tokens = _retrieval_tokens(query)

    block = {
        "state": "no_external_candidates",
        "algorithm": EXTERN_RETRIEVAL_PROFILE,
        "live": True,
        "fetched_at": None,
        "sources": [],
        "hits": [],
        "reason": None,
        "notes": list(bindungsfehler),
        "external_fingerprint": None,
    }
    if not register:
        block["state"] = "not_declared"
        block["live"] = False
        block["reason"] = (
            f"{rel(EXTERN_REGISTER)} führt keine externe Bezugsquelle. "
            f"Es wird ausschließlich aufgeführtes Material gelesen."
        )
        return block

    # Eine nicht aufgeführte Quellen-ID still zu ignorieren wäre der
    # gefährlichste Fehltreffer überhaupt: ein Tippfehler erzeugte dann einen
    # glaubwürdig aussehenden Negativbefund („die Quelle wurde durchsucht und
    # hat nichts hergegeben"). Deshalb fail closed, bevor gerankt wird.
    unbekannt = sorted(set(quellen_filter or []) - set(register))
    if unbekannt:
        block["state"] = "invalid_query"
        block["live"] = False
        block["reason"] = (
            f"Nicht aufgeführte Quelle(n) {unbekannt}. Es wurde nichts "
            f"durchsucht — dies ist kein Negativbefund. Aufgeführt sind: "
            f"{sorted(register)}."
        )
        return block

    treffer, wurzeln, protokoll, dokumentpfade = [], [], [], []
    for xid in sorted(register):
        zeile = register[xid]
        if quellen_filter and xid not in quellen_filter:
            continue
        status = _extern_quelle_status(xid, zeile, bindung)
        eintrag = {
            "id": xid, "title": zeile["titel"], "kind": zeile["art"],
            "scope": zeile["scope"], "trust": zeile["trust"],
            "rights": zeile["rechte"], "target": zeile["ziel"],
            "bound": status["modus"] != "unbound",
            "mode": status["modus"],
        }
        block["sources"].append(eintrag)
        if status["modus"] == "unbound":
            block["notes"].append(status["grund"])
            continue
        if status["modus"] == "netz" and not _netz_erlaubt():
            eintrag["bound"] = False
            block["notes"].append(
                f"{xid}: {EXTERN_OFFLINE_ENV} ist gesetzt — nicht abgerufen"
            )
            continue

        if zeile["art"] == "skillsafe-vault":
            if status["modus"] != "lokal":
                block["notes"].append(
                    f"{xid}: ein fremder Tresor wird nur lokal gelesen"
                )
                continue
            fremd, grund = _lese_fremden_tresor(status["wurzel"], status["anker"])
            if grund:
                block["state"] = "invalid_external_source"
                block["reason"] = f"{xid}: {grund}"
                return block
            wurzeln.append([xid, fremd["manifest_sha256"]])
            for dok in fremd["documents"]:
                dokumentpfade.append(f"{xid}:{dok['path']}")
                bestand = _bestand_score(dok["text"], query_norm, tokens)
                if bestand["coverage"] < EXTERN_ABDECKUNG_MIN or not bestand["satz"]:
                    continue
                treffer.append(_extern_treffer(
                    xid, dok["path"], bestand, 0, zeile))
            continue

        katalog = kataloge.get(xid)
        if not katalog:
            block["notes"].append(
                f"{xid}: kein Katalog sources/derived/{xid}__orchestrator.json "
                f"— 'vault.py orchestrator-template {xid}' erzeugt das Gerüst"
            )
            continue
        # Bei einer Netzquelle ist der Wurzel-Hash bewusst None; dann geht der
        # Bindungsschluessel in den Fingerprint, nicht eine erfundene Zahl.
        wurzeln.append([xid, katalog["meta"]["generated_from_sha256"] or "netz"])
        # Stufe 1 ist nur Prefilter: der Index wird nie roh geladen, sondern
        # gefiltert, und nur die besten Kandidaten werden überhaupt geöffnet.
        vorauswahl = sorted(
            ((_katalog_score(dok, query_norm, tokens), dok["path"], dok)
             for dok in katalog["documents"]),
            key=lambda eintrag: (-eintrag[0], eintrag[1]),
        )[:MAX_EXTERN_STUFE1]
        ttl = bindung["cache_ttl_seconds"]
        for katalog_score, relpfad, dok in vorauswahl:
            text, _, grund = _extern_dokument_text(
                status, relpfad, ttl, xid, protokoll)
            if grund:
                block["notes"].append(f"{xid}/{relpfad}: {grund}")
                continue
            dokumentpfade.append(f"{xid}:{relpfad}")
            bestand = _bestand_score(text, query_norm, tokens)
            # Abdeckung 0 fliegt raus, egal wie gut Stufe 1 aussah. Genau hier
            # wird der Katalogtext als schwaches Signal entwertet.
            if bestand["coverage"] < EXTERN_ABDECKUNG_MIN or not bestand["satz"]:
                continue
            treffer.append(_extern_treffer(
                xid, relpfad, bestand, katalog_score, zeile))

    treffer.sort(key=lambda t: (-t["score"], t["source_id"], t["document"],
                                t["sentence_index"]))
    block["hits"] = treffer[:MAX_EXTERN_TREFFER]
    if protokoll:
        block["fetched_at"] = date.today().isoformat()
        alter = [e["cache_age_seconds"] for e in protokoll]
        block["notes"].append(
            f"{len(protokoll)} Abruf(e), Cache-Alter {min(alter)}–{max(alter)} s"
        )
        _log_abrufe(protokoll)
    if block["hits"]:
        block["state"] = "external_candidates_found"
    elif block["state"] == "no_external_candidates":
        ohne = sorted(set(tokens)) if tokens else []
        block["reason"] = (
            "Kein aufgeführtes Dokument enthält die Anfragebegriffe "
            f"{ohne}. Fachbegriffe statt Eigennamen verwenden. Es wird "
            "bewusst kein bester Fehltreffer geliefert."
        )
    block["external_fingerprint"] = _sha256_bytes(json.dumps(
        {"algorithm": EXTERN_RETRIEVAL_PROFILE,
         "roots": sorted(wurzeln),
         "query": query_norm,
         "hits": [[t["source_id"], t["document"], t["sentence_index"],
                   t["score"]] for t in block["hits"]]},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8"))
    block["documents_read"] = sorted(set(dokumentpfade))
    return block


def _extern_treffer(xid, relpfad, bestand, katalog_score, zeile):
    """Einen externen Treffer bauen — immer als Zeiger, nie als Evidenz."""
    index, art, satz = bestand["satz"]
    verdaechtig = bool(PROMPT_INJECTION_RE.search(satz))
    return {
        "source_id": xid,
        # Redundant an JEDEM Treffer: der Unterschied zu einem Claim darf
        # sich nicht erst aus dem Kontext ergeben müssen.
        "role": "external_pointer",
        "is_evidence": False,
        "document": relpfad,
        "sentence_index": index,
        "block": art,
        # Ein Satz mit Instruktionssignatur wird gemeldet, nie ausgeliefert.
        "text": None if verdaechtig else satz,
        "text_sha256": _satz_digest(satz),
        "score": int(bestand["score"]),
        "score_catalog": int(katalog_score),
        "score_inventory": int(bestand["score"]),
        "coverage_percent": int(bestand["coverage"]),
        "trust": zeile["trust"],
        "signals": ["suspicious_instruction"] if verdaechtig else [],
    }


def _log_abrufe(protokoll):
    """Herkunftsprotokoll: jeder Netzabruf ist in log.md nachlesbar.

    Das ist der Unterschied zwischen „wie eine interne Quelle behandelt" und
    „unbeaufsichtigt": wer prüfen will, ob nur aufgeführte Ziele gelesen
    wurden, kann das nachlesen.
    """
    for eintrag in protokoll:
        if eintrag["cache_age_seconds"]:
            continue
        try:
            cmd_log("extern", (
                f"abruf {eintrag['url']} sha256={eintrag['sha256']} "
                f"bytes={eintrag['bytes']}"
            ), still=True)
        except (OSError, ValueError):
            pass


def _tracked_path(p: Path) -> bool:
    """Ob ein Tresorpfad Bestandteil des Integritätsmanifests ist."""
    rp = Path(rel(p))
    teile = rp.parts
    if not teile:
        return False
    # .vault-extern.json ist wie log.md bewusst außerhalb des Manifests: sie
    # enthält absolute Pfade dieses Hosts. Stünde sie im Manifest, wäre das
    # Artefakt nicht mehr portabel und die Paket-SHA-256 maschinenabhängig.
    if p in {MANIFEST, LOG, RELEASE_LOCK, BINDUNG}:
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


def cmd_log(aktion, text, still=False):
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
        if not still:
            print(f"🟢 log: angehängt — {eintrag}")
        return 0

    return _run_locked_mutation("log", arbeit)


def cmd_stats():
    (fehler, warn, seiten, claims, register, _,
     extern_kontext) = cmd_validate(still=True)
    worlds, concepts, _ = parse_concepts()
    media, _ = parse_media_representations(register)
    g = build_graph(seiten)
    dom, typ, status, tiers = {}, {}, {}, {}
    for s in seiten.values():
        fm = s["fm"]
        dom[fm.get("domain", "?")] = dom.get(fm.get("domain", "?"), 0) + 1
        typ[fm.get("type", "?")] = typ.get(fm.get("type", "?"), 0) + 1
        status[fm.get("status", "?")] = status.get(fm.get("status", "?"), 0) + 1
        tier = _trust_tier(fm.get("geprueft_von"))
        tiers[tier] = tiers.get(tier, 0) + 1
    print(f"Profil {PROFIL} — {len(seiten)} Seiten, {len(claims)} Claims, "
          f"{len(register)} Quellen, {len(g['kanten'])} Kanten "
          f"({len(fehler)} Fehler, {len(warn)} Warnungen)")
    print(f"  Begriffswelten: {len(worlds)}, Begriffe: {len(concepts)}, "
          f"Medienrepräsentationen: {len(media)}")
    # Bewusst eine eigene Zeile: die Kopfzeile oben ist das Muster, das
    # tools/check_docs.py liest. Ein zusätzliches Feld darin würde den
    # Zahlenwächter an der eigenen Erweiterung brechen.
    anker = sum(len(eintrag["anchors"])
                for eintrag in extern_kontext["anchors"].values())
    print(f"  Externe Bezugsquellen: {len(extern_kontext['register'])}, "
          f"Satzanker: {anker}, "
          f"Kataloge: {len(extern_kontext['orchestrators'])}")
    for name, d in (("Domänen", dom), ("Typen", typ), ("Status", status),
                    ("Trust-Tiers", tiers)):
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
    fehler, _, _, _, _, router, _ = cmd_validate(still=True)
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

        (fehler, warnungen, seiten, claims, register, _,
         _) = cmd_validate(still=True)
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
            endfehler, _, endseiten, _, _, _, _ = cmd_validate(still=True)
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


# --------------------------------------------------------- OKF-Export

def _yaml_scalar(value):
    """Skalar so ausgeben, dass jeder YAML-Parser ihn wieder gleich liest."""
    text = str(value)
    heikel = (
        not text
        or text != text.strip()
        or text[0] in "-?:,[]{}#&*!|>'\"%@`"
        or ": " in text
        or text.endswith(":")
        or " #" in text
    )
    if not heikel:
        return text
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _okf_actor(actor):
    """Deutsche Aktorkennung auf die Konvention aus OKF v0.2 §7 abbilden."""
    for praefix, ersatz in ACTOR_OKF.items():
        if actor.startswith(praefix):
            return ersatz + actor[len(praefix):]
    return actor


def _okf_description(body):
    """Ersten Satz der Kurzfassung ziehen. Kein Satz, kein Feld."""
    zeilen, sammeln = [], False
    for line in body.split("\n"):
        if line.startswith("## "):
            if sammeln:
                break
            sammeln = line[3:].strip().lower() == "kurzfassung"
            continue
        if sammeln:
            if not line.strip() and zeilen:
                break
            if line.strip():
                zeilen.append(line.strip())
    text = " ".join(zeilen)
    if not text:
        return None
    return _erster_satz(text)


def _erster_satz(text, maximum=400):
    """Ersten echten Satz zurückgeben, Abkürzungen und Zahlen respektierend.

    Teilt sich die Satzende-Entscheidung mit ``satzsegmentierung/v1``; zwei
    getrennte Logiken für dieselbe Frage würden garantiert auseinanderdriften.
    """
    for treffer in SATZENDE_RE.finditer(text):
        kopf = text[:treffer.start()]
        if not _ist_satzende(kopf):
            continue
        return kopf + treffer.group(1)
    return text if len(text) <= maximum else text[:maximum].rstrip() + " …"


def _okf_sources(fm, register, mit_quellen):
    """sources-Block nach §5.1 aus Frontmatter plus Registerzeile bauen."""
    zeilen = []
    for sid in fm.get("sources", []):
        eintrag = register.get(sid, {})
        if mit_quellen:
            resource = "/" + eintrag.get("ablage", f"sources/raw/{sid}")
        else:
            # §5.1 erlaubt ausdrücklich einen nicht folgbaren Deskriptor. Die
            # Rechte-Spalte ist Freitext; ob eine Ablage weitergegeben werden
            # darf, entscheidet ein Mensch über --with-sources, nicht ein Regex.
            resource = f"registered source {sid}, file not exported"
        zeilen.append(f"  - id: {sid}")
        zeilen.append(f"    resource: {_yaml_scalar(resource)}")
        if eintrag.get("titel"):
            zeilen.append(f"    title: {_yaml_scalar(eintrag['titel'])}")
        if _iso_date(eintrag.get("stand", "")):
            zeilen.append(f"    last_modified: {eintrag['stand']}")
        zeilen.append(f"    oksv_trust: {eintrag.get('trust', '?')}")
    return zeilen


def _okf_extern_sources(fm, extern):
    """sources-Block für aufgeführte externe Bezugsquellen nach §5.1.

    Ohne diesen Zweig verlässt eine ausschließlich extern belegte Seite den
    Tresor ohne jede Quellenangabe — belegte Aussagen ohne Beleg, und genau
    das ist der Kernwert, den der Export nicht verlieren darf.

    Der Bindungspfad aus .vault-extern.json erscheint hier NIEMALS: er ist
    host-lokal und hat außerhalb dieser Maschine keine Bedeutung.
    """
    zeilen = []
    for xid in fm.get("externe_quellen", []):
        eintrag = extern.get(xid, {})
        url = eintrag.get("url")
        if url:
            # Ein registriertes https-Präfix ist portabel und öffentlich —
            # der einzige Fall, in dem eine externe Ressource folgbar ist.
            resource = url
        else:
            titel = eintrag.get("titel") or xid
            resource = f"external reference {xid}, {titel}, not exported"
        zeilen.append(f"  - id: {xid}")
        zeilen.append(f"    resource: {_yaml_scalar(resource)}")
        if eintrag.get("titel"):
            zeilen.append(f"    title: {_yaml_scalar(eintrag['titel'])}")
        if _iso_date(eintrag.get("stand", "")):
            zeilen.append(f"    last_modified: {eintrag['stand']}")
        zeilen.append(f"    oksv_trust: {eintrag.get('trust', '?')}")
        zeilen.append(f"    oksv_external_kind: {eintrag.get('art', '?')}")
    return zeilen


def _okf_frontmatter(fm, body, register, concepts, mit_quellen, extern=None):
    zeilen = ["---", f"type: {_yaml_scalar(fm.get('type', ''))}"]
    if fm.get("title"):
        zeilen.append(f"title: {_yaml_scalar(fm['title'])}")
    description = _okf_description(body)
    if description:
        zeilen.append(f"description: {_yaml_scalar(description)}")
    tags = fm.get("tags", [])
    if tags:
        zeilen.append("tags: [" + ", ".join(_yaml_scalar(t) for t in tags) + "]")
    zeilen.append(f"status: {STATUS_OKF.get(fm.get('status'), 'stable')}")
    if fm.get("geprueft_von") and fm.get("geprueft_am"):
        # §5.2/§11: eine blanke Map gilt als einelementige Liste. Das Datum
        # bleibt Kalendertag; ein aufgefülltes T00:00:00Z würde Präzision
        # erfinden, die der Bestand nicht hat.
        zeilen.append(
            "verified: { by: %s, at: %s }"
            % (_yaml_scalar(_okf_actor(fm["geprueft_von"])), fm["geprueft_am"])
        )
    quellen = (_okf_sources(fm, register, mit_quellen)
               + _okf_extern_sources(fm, extern or {}))
    if quellen:
        zeilen.append("sources:")
        zeilen.extend(quellen)
    # Producer-eigene Zusatzschlüssel, nach §4.1 ausdrücklich erlaubt. Der
    # Präfix hält sie von v0.2-Standardfeldern fern.
    zeilen.append(f"oksv_profile: {PROFIL}")
    for feld in ("domain", "version", "confidence", "stand"):
        if fm.get(feld):
            zeilen.append(f"oksv_{feld}: {_yaml_scalar(fm[feld])}")
    if fm.get("concepts"):
        zeilen.append("oksv_concepts: [" + ", ".join(fm["concepts"]) + "]")
        labels = [
            concepts[b]["preferred"] for b in fm["concepts"] if b in concepts
        ]
        if labels:
            # Als Frontmatter-Liste, nicht als HTML-Kommentar im Rumpf: ein
            # Label mit '-->' hätte den Kommentar geschlossen und alles
            # dahinter zu sichtbarem Bundle-Inhalt gemacht. preferred wird
            # schwächer geprüft als Claim-Text, deshalb bekommt es hier keinen
            # Weg in den Rumpf.
            zeilen.append(
                "oksv_concept_labels: ["
                + ", ".join(_yaml_scalar(label) for label in labels) + "]"
            )
    # Das Trust-Tier wird bewusst NICHT geschrieben. KONZEPT.md sagt zu, dass
    # es nur abgeleitet und nie gespeichert wird; ein Konsument leitet es nach
    # §5.3 selbst aus verified ab. Es hier auszugeben wäre genau die
    # Speicherung, die das Profil ausschließt.
    zeilen.append("---")
    return zeilen


def _okf_body(seite, register, extern=None, anchors=None):
    """Body verbatim, plus Fußnoten nach §5.1 und Beziehungen als Links."""
    ausgabe = []
    for line in seite["body"].split("\n"):
        treffer = CLAIM_RE.match(line) if line.startswith(CLAIM_START) else None
        ausgabe.append(f"{line}[^{treffer.group(2)}]" if treffer else line)
    text = "\n".join(ausgabe).rstrip("\n")

    if seite["relationen"]:
        text += "\n\n## Beziehungen\n"
        for relation in seite["relationen"]:
            ziel = relation["ziel"][len("knowledge/"):]
            name = Path(ziel).stem
            text += f"\n- {relation['typ']}: [{_markdown_text(name)}](/{ziel})"
        text += "\n"

    extern = extern or {}
    anchors = anchors or {}
    verwendet = sorted({claim["quelle"] for claim in seite["claims"]})
    if verwendet:
        # Das Fußnotenlabel MUSS die Quellen-ID sein, nicht die C-ID: §5.1
        # nennt sources[].id als Join-Key in die sources-Liste.
        text += "\n\n"
        for sid in verwendet:
            if sid.startswith("X-"):
                titel = extern.get(sid, {}).get("titel") or sid
                # Ohne die Anker wäre die Fußnote im Bundle wertlos: der
                # Satzwortlaut wandert nicht mit, also muss wenigstens der
                # Zeiger auffindbar bleiben.
                stellen = sorted({
                    (anchors.get(sid, {}).get("anchors", {})
                     .get(claim["anker"], {}).get("document"),
                     anchors.get(sid, {}).get("anchors", {})
                     .get(claim["anker"], {}).get("sentence_index"))
                    for claim in seite["claims"]
                    if claim["quelle"] == sid and claim.get("anker")
                })
                fundstellen = ", ".join(
                    f"{dokument} Satz {index}"
                    for dokument, index in stellen if dokument
                )
                if fundstellen:
                    titel = f"{titel} — {fundstellen}"
            else:
                titel = register.get(sid, {}).get("titel") or sid
            text += f"[^{sid}]: {titel}\n"

    return text.rstrip("\n") + "\n"


def _markdown_text(value):
    """Linktext so ausgeben, dass eine Klammer den Link nicht zerlegt."""
    return (str(value).replace("\\", "\\\\")
            .replace("[", "\\[").replace("]", "\\]"))


def _okf_index_root(domaenen, quelle_beschreibung):
    zeilen = [
        "---",
        f'okf_version: "{OKF_VERSION}"',
        "---",
        "",
        "# Bundle",
        "",
        quelle_beschreibung,
        "",
        "# Subdirectories",
        "",
    ]
    for domain in sorted(domaenen):
        zeilen.append(f"* [{_markdown_text(domain)}]({domain}/) - Wissensdomäne des Tresors.")
    return "\n".join(zeilen) + "\n"


def _okf_index_domain(domain, seiten):
    zeilen = [f"# {domain}", ""]
    for rp in sorted(seiten):
        fm = seiten[rp]["fm"]
        name = Path(rp).name
        titel = fm.get("title") or Path(rp).stem
        beschreibung = _okf_description(seiten[rp]["body"]) or "Wissensseite."
        zeilen.append(f"* [{_markdown_text(titel)}]({name}) - {beschreibung}")
    return "\n".join(zeilen) + "\n"


def _okf_log():
    """log.md in die §9-Form bringen: Datumsgruppen, neueste zuerst."""
    if not _safe_regular_file(LOG):
        return None
    gruppen = {}
    try:
        log_text = read(LOG)
    except (OSError, UnicodeError):
        return None
    for line in log_text.split("\n"):
        treffer = re.match(r"^## \[(\d{4}-\d{2}-\d{2})\] ([a-z]+) \| (.+)$", line)
        if not treffer:
            continue
        datum, aktion, text = treffer.groups()
        gruppen.setdefault(datum, []).append((aktion, text))
    if not gruppen:
        return None
    zeilen = ["# Directory Update Log", ""]
    for datum in sorted(gruppen, reverse=True):
        zeilen.append(f"## {datum}")
        for aktion, text in gruppen[datum]:
            zeilen.append(f"* **{aktion.capitalize()}**: {text}")
        zeilen.append("")
    return "\n".join(zeilen).rstrip("\n") + "\n"


def _export_ziel_pruefen(ziel: Path):
    """Fail-closed: kein Skill-Ladeort, nicht im Tresor, kein Fremdinhalt."""
    lexikalisch = Path(os.path.abspath(ziel))
    if lexikalisch.is_symlink():
        return "Ziel ist ein Symlink"
    # Containment und Ladeort erst nach dem Auflösen prüfen: ROOT ist selbst
    # aufgelöst (Path(__file__).resolve()), und auf macOS liegt /var hinter
    # einem Symlink auf /private/var. Ohne resolve() greift die Prüfung dort
    # nie. Der lexikalische Pfad wird zusätzlich geprüft, damit auch ein
    # buchstäblich benannter Ladeort auffällt.
    aufgeloest = lexikalisch.resolve()
    if aufgeloest == ROOT or ROOT in aufgeloest.parents:
        return "Ziel liegt innerhalb des Tresors"
    verboten = sorted(
        (set(aufgeloest.parts) | set(lexikalisch.parts))
        & EXPORT_VERBOTENE_SEGMENTE
    )
    if verboten:
        return (
            f"Ziel liegt in einem Skill-Ladeort ({', '.join(verboten)}); ein "
            f"exportiertes Bundle hat keine Engine und keine Regeln und darf "
            f"nicht als Skill geladen werden"
        )
    if not aufgeloest.exists():
        return None
    if not aufgeloest.is_dir():
        return "Ziel existiert und ist kein Verzeichnis"
    if not any(aufgeloest.iterdir()):
        return None
    if _ist_frueherer_export(aufgeloest):
        return None
    return (
        "Ziel ist nicht leer und kein früherer OKF-Export "
        "(erkannt am okf_version im Wurzel-index.md)"
    )


def _ist_frueherer_export(ordner: Path) -> bool:
    """Wurzel-index.md mit okf_version im Frontmatter (§12).

    Bewusst nicht über _safe_regular_file: das verlangt einen Pfad innerhalb
    des Tresors, und das Exportziel liegt per Definition außerhalb. Die
    Härtung (kein Symlink, echte einfach verlinkte Datei) gilt hier trotzdem.
    """
    kandidat = ordner / "index.md"
    try:
        status = os.lstat(str(kandidat))
        if not stat.S_ISREG(status.st_mode) or status.st_nlink != 1:
            return False
        zeilen = kandidat.read_text(encoding="utf-8").split("\n")
    except (OSError, UnicodeError):
        return False
    if not zeilen or zeilen[0].strip() != "---":
        return False
    for line in zeilen[1:]:
        if line.strip() == "---":
            return False
        if line.startswith("okf_version:"):
            return True
    return False


def cmd_export(ziel, mit_quellen=False):
    """Bestand als OKF-v0.2-Bundle außerhalb des Tresors ausgeben."""
    fehler, _, seiten, _, register, _, extern_kontext = cmd_validate(still=True)
    if fehler:
        print("🔴 export: ABBRUCH — validate ist rot; erst den Bestand "
              "reparieren.")
        for f in fehler[:10]:
            print(f"   {f}")
        return 1
    manifest_fehler, _ = _manifest_status()
    if manifest_fehler:
        print("🔴 export: ABBRUCH — Stand entspricht nicht dem Manifest; "
              "exportiert wird nur ein freigegebener Release.")
        for f in manifest_fehler[:10]:
            print(f"   {f}")
        return 1
    _, concepts, concept_fehler = parse_concepts()
    if concept_fehler:
        print("🔴 export: ABBRUCH — Begriffswelten sind nicht valide.")
        return 1

    ziel_pfad = Path(os.path.abspath(ziel))
    problem = _export_ziel_pruefen(ziel_pfad)
    if problem:
        print(f"🔴 export: ABBRUCH — {problem}.")
        return 1

    try:
        version = read(VERSION).strip() if _safe_regular_file(VERSION) else "?"
    except (OSError, UnicodeError):
        version = "?"
    herkunft = (
        f"Export aus dem Wissenstresor (Profil {PROFIL}, Bestand v{version}). "
        f"Dies ist eine Momentaufnahme in OKF {OKF_VERSION}, kein Tresor: sie "
        f"trägt keine Engine, kein Manifest und keine Regeln. "
        + ("Registrierte Rohquellen liegen unter sources/raw/."
           if mit_quellen else
           "Registrierte Rohquellen sind nicht enthalten; sources[].resource "
           "ist deshalb ein Deskriptor und kein folgbarer Pfad.")
    )

    dateien = {}
    domaenen = {}
    for rp, seite in sorted(seiten.items()):
        domain = seite["fm"].get("domain", "unbekannt")
        name = Path(rp).name
        kopf = _okf_frontmatter(
            seite["fm"], seite["body"], register, concepts, mit_quellen,
            extern=extern_kontext["register"])
        rumpf = _okf_body(seite, register,
                          extern=extern_kontext["register"],
                          anchors=extern_kontext["anchors"])
        dateien[f"{domain}/{name}"] = "\n".join(kopf) + "\n" + rumpf
        domaenen.setdefault(domain, {})[rp] = seite

    dateien["index.md"] = _okf_index_root(domaenen, herkunft)
    for domain, inhalt in sorted(domaenen.items()):
        dateien[f"{domain}/index.md"] = _okf_index_domain(domain, inhalt)
    log_text = _okf_log()
    if log_text:
        dateien["log.md"] = log_text

    kopien = []
    if mit_quellen:
        for sid, eintrag in sorted(register.items()):
            quelle, pfadfehler = _safe_relative_path(ROOT, eintrag.get("ablage", ""))
            if pfadfehler or not quelle.is_file():
                print(f"🔴 export: ABBRUCH — Ablage von {sid} ist nicht "
                      f"sicher lesbar.")
                return 1
            kopien.append((eintrag["ablage"], quelle))

    # Erst vollständig in ein frisches Staging schreiben, dann das Ziel in
    # einem Zug ersetzen. Das löst drei Dinge auf einmal: das Staging enthält
    # keine Symlinks, also kann kein vorbereiteter Link im Zielordner den
    # Schreibvorgang aus dem Ziel heraustragen; ein Abbruch hinterlässt keinen
    # Halbstand; und ein früherer Export wird ersetzt statt übermischt, sodass
    # keine verwaisten Dokumente aus einem alten Bestand liegen bleiben.
    try:
        ziel_pfad.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(
            prefix=f".{ziel_pfad.name}.okf-staging-", dir=str(ziel_pfad.parent)
        ))
    except OSError as exc:
        print(f"🔴 export: ABBRUCH — Staging nicht anlegbar: {exc}")
        return 1

    verdraengt = None
    try:
        for rel_pfad in sorted(dateien):
            datei = staging / rel_pfad
            datei.parent.mkdir(parents=True, exist_ok=True)
            datei.write_text(dateien[rel_pfad], encoding="utf-8")
        for rel_pfad, quelle in kopien:
            datei = staging / rel_pfad
            datei.parent.mkdir(parents=True, exist_ok=True)
            datei.write_bytes(quelle.read_bytes())
        if ziel_pfad.exists():
            verdraengt = Path(tempfile.mkdtemp(
                prefix=f".{ziel_pfad.name}.okf-alt-", dir=str(ziel_pfad.parent)
            ))
            os.rmdir(str(verdraengt))
            os.rename(str(ziel_pfad), str(verdraengt))
        try:
            os.rename(str(staging), str(ziel_pfad))
        except OSError:
            if verdraengt is not None and not ziel_pfad.exists():
                os.rename(str(verdraengt), str(ziel_pfad))
                verdraengt = None
            raise
    except (OSError, UnicodeError) as exc:
        shutil.rmtree(str(staging), ignore_errors=True)
        if verdraengt is not None and verdraengt.exists():
            shutil.rmtree(str(verdraengt), ignore_errors=True)
        print(f"🔴 export: ABBRUCH — Schreiben fehlgeschlagen, Ziel "
              f"unverändert: {exc}")
        return 1
    if verdraengt is not None:
        shutil.rmtree(str(verdraengt), ignore_errors=True)

    print(f"🟢 export: {len(dateien)} Dokumente"
          + (f" + {len(kopien)} Rohquellen" if kopien else "")
          + f" nach {ziel_pfad} geschrieben (OKF {OKF_VERSION}).")
    print("   Der Zielordner wurde vollständig ersetzt, nicht ergänzt: ein "
          "Export ist eine Momentaufnahme, kein gepflegter Bestand.")
    print("   Einbahnstraße: der Tresor liest kein fremdes OKF zurück. "
          "Rückweg ist der reguläre Ingest.")
    if mit_quellen:
        print("   Die kopierten Rohquellen sind byteidentisch und deshalb "
              "keine OKF-Konzeptdokumente; mit --with-sources erfüllt das "
              "Bundle §11 Bedingung 2 bewusst nicht (siehe "
              "references/export-okf.md).")
    else:
        print("   Ohne --with-sources bleiben Rohquellen im Tresor; "
              "Rechte klärt ein Mensch, nicht das Script.")
    return 0


def cmd_doctor():
    print("── doctor: Gesamtdiagnose ─────────────────────────────────────")
    (fehler, warnungen, seiten, claims, register, router,
     extern_kontext) = cmd_validate(still=True)
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

    # Prüfangabe: nur melden, wenn der Bestand das Feld überhaupt nutzt. Ein
    # Tresor, der es gar nicht führt, ist nicht auffällig, sondern schlicht
    # unverifiziert — dann wäre der Hinweis auf jeder Seite reines Rauschen.
    # Hinweisstufe, damit ein Kalenderstand nie eine grüne Ampel kippt.
    if any(s["fm"].get("geprueft_von") for s in seiten.values()):
        for rp, s in sorted(seiten.items()):
            fm = s["fm"]
            if fm.get("confidence") == "hoch" and not fm.get("geprueft_von"):
                hinweise.append(
                    f"{rp}: confidence hoch, aber keine Prüfangabe "
                    f"(Trust-Tier {TIER_UNVERIFIED}) — der Bestand nutzt "
                    f"geprueft_von bereits, diese Seite nicht")

    print("── Externe Bezugsquellen ──────────────────────────────────────")
    extern_register = extern_kontext["register"]
    if not extern_register:
        print("   keine aufgeführt — der Tresor liest ausschließlich sich selbst")
    else:
        bindung, bindungsfehler = parse_bindung()
        fehler.extend(bindungsfehler)
        for xid in sorted(extern_register):
            zeile = extern_register[xid]
            status = _extern_quelle_status(xid, zeile, bindung)
            print(f"   {xid} {zeile['art']:<16} {status['modus']}")
            if status["modus"] == "unbound":
                # Ungebunden ist KEIN Fehler: sonst wäre jedes frisch
                # entpackte Paket auf jedem neuen Host rot, und AD-08 fiele.
                # Fail-closed greift erst bei der Nutzung.
                hinweise.append(f"{xid}: {status['grund']}")
                continue
            anker_datei = extern_kontext["anchors"].get(xid)
            if not anker_datei or status["modus"] != "lokal":
                continue
            for aid in sorted(anker_datei["anchors"]):
                anker = anker_datei["anchors"][aid]
                text, _, grund = _lies_externes_dokument(
                    status["wurzel"], status["anker"], anker["document"])
                if grund:
                    warnungen.append(
                        f"{xid}/{anker['document']}: nicht lesbar — {grund}")
                    continue
                # Hash-first, Index nur als Hinweis: eine eingefügte Zeile
                # verschiebt den Satz, bricht ihn aber nicht.
                treffer = [i for i, _, satz in _saetze(text)
                           if _satz_digest(satz) == anker["text_sha256"]]
                if not treffer:
                    warnungen.append(
                        f"{xid}/{aid}: zitierter Satz nicht mehr gefunden "
                        f"(Drift) — der Beleg braucht Kuratierung")
                elif anker["sentence_index"] not in treffer:
                    warnungen.append(
                        f"{xid}/{aid}: Satz steht jetzt an Position "
                        f"{treffer[0]} statt {anker['sentence_index']} "
                        f"(verschoben, nicht gebrochen)")

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
    # Ohne dieses Flag verlässt kein Byte den Skill-Ordner. Es macht am
    # Aufruf sichtbar, dass hier bewusst live nachgeschlagen wird.
    query_parser.add_argument("--extern", action="store_true")
    query_parser.add_argument("--source", dest="quelle", action="append")
    media_parser = sub.add_parser("media-template")
    media_parser.add_argument("source_id")
    extern_parser = sub.add_parser("extern")
    extern_parser.add_argument("aktion", choices=["list", "bind", "unbind"])
    extern_parser.add_argument("source_id", nargs="?")
    extern_parser.add_argument("pfad", nargs="?")
    anchor_parser = sub.add_parser("anchor-template")
    anchor_parser.add_argument("source_id")
    anchor_parser.add_argument("dokument")
    orchestrator_parser = sub.add_parser("orchestrator-template")
    orchestrator_parser.add_argument("source_id")
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
    e = sub.add_parser("export")
    e.add_argument("--okf", action="store_true", required=True)
    e.add_argument("--out", required=True)
    e.add_argument("--with-sources", action="store_true")
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
        sys.exit(cmd_query(a.frage, world=a.world, limit=a.limit,
                           extern=a.extern, quellen_filter=a.quelle))
    elif a.cmd == "media-template":
        sys.exit(cmd_media_template(a.source_id))
    elif a.cmd == "extern":
        if a.aktion != "list" and not a.source_id:
            print("🔴 extern: bind/unbind brauchen eine X-nnnn")
            sys.exit(1)
        if a.aktion == "bind" and not a.pfad:
            print("🔴 extern: bind braucht einen absoluten Pfad")
            sys.exit(1)
        sys.exit(cmd_extern(a.aktion, a.source_id, a.pfad))
    elif a.cmd == "anchor-template":
        sys.exit(cmd_anchor_template(a.source_id, a.dokument))
    elif a.cmd == "orchestrator-template":
        sys.exit(cmd_orchestrator_template(a.source_id))
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
    elif a.cmd == "export":
        sys.exit(cmd_export(a.out, mit_quellen=a.with_sources))


if __name__ == "__main__":
    main()
