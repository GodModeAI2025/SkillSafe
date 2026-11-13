#!/usr/bin/env python3
"""Prüft, ob die in README.md, index.html und KONZEPT.md veröffentlichten
Zahlen noch stimmen.

In dieser Form ist das Wächterarbeit, die sonst niemand macht: README und
Landingpage nennen Version, Bestandszahlen, Testzahl, Paketeinträge, den
SHA-256 des reproduzierbaren Pakets und die Messwerte der Suche. Alle sind an
echte Ausgabe gekoppelt, und genau solche Kopplungen veralten still. Die
Ende-zu-Ende-Zahlen stehen in README, Landingpage und wissenstresor/KONZEPT.md;
sie sind an die Protokolle unter tests/e2e/ gebunden.

Read-only, nur Standardbibliothek, kein Schreibzugriff auf das Repository.
Läuft aus der Repository-Wurzel:

    python3 tools/check_docs.py

Exit 0, wenn alles übereinstimmt, sonst 1 mit einer Liste der Abweichungen.
"""

import html
import importlib.util
import json
import re
import subprocess
import tempfile
import sys
import unicodedata
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
SKILL = REPOSITORY / "wissenstresor"
README = REPOSITORY / "README.md"
LANDING = REPOSITORY / "index.html"
KONZEPT = REPOSITORY / "wissenstresor" / "KONZEPT.md"
LIESMICH = REPOSITORY / "tests" / "e2e" / "LIESMICH.md"
RECALL_TOOL = REPOSITORY / "tools" / "recall_check.py"
E2E_ORDNER = REPOSITORY / "tests" / "e2e"
# Zeilenbeschriftung der veröffentlichten Messtabelle je Fragengruppe.
RECALL_ZEILEN = {
    "entwicklung": "Jetzt, eigene Fragen",
    "kontrolle": "Jetzt, blinde Kontrolle",
}
GRUNDZAHLEN = (
    "null eins zwei drei vier fünf sechs sieben acht neun zehn elf zwölf "
    "dreizehn vierzehn fünfzehn sechzehn siebzehn achtzehn neunzehn").split()
ZEHNER = {2: "zwanzig", 3: "dreißig", 4: "vierzig", 5: "fünfzig",
          6: "sechzig", 7: "siebzig", 8: "achtzig", 9: "neunzig"}


def zahlwort(zahl):
    """Eine Grundzahl von 0 bis 99, wie sie im Fließtext steht."""
    if not 0 <= zahl < 100:
        raise ValueError(f"kein Zahlwort für {zahl}")
    if zahl < 20:
        return GRUNDZAHLEN[zahl]
    zehner, einer = divmod(zahl, 10)
    if not einer:
        return ZEHNER[zehner]
    return ("ein" if einer == 1 else GRUNDZAHLEN[einer]) + "und" + ZEHNER[zehner]


def ordnungswort(zahl):
    """Eine Ordnungszahl im Dativ: 'zweiten', 'dritten', 'zwanzigsten'."""
    besonders = {1: "ersten", 3: "dritten", 7: "siebten", 8: "achten"}
    if zahl in besonders:
        return besonders[zahl]
    return zahlwort(zahl) + ("ten" if zahl < 20 else "sten")


def zahl_aus_wort(wort, ordnung=False):
    """Eine Zahl aus Ziffern oder Wort: "20", "zwanzig", "2.", "zweiten".

    None, wenn es keine ist.
    """
    wort = wort.strip()
    if ordnung and re.fullmatch(r"\d+\.", wort):
        return int(wort[:-1])
    if not ordnung and wort.isdecimal():
        return int(wort)
    wort = wort.casefold()
    # "eine mit dem Befund des Scripts": die Eins vor einem Substantiv;
    # "keine Verstöße", "die beiden übrigen".
    if not ordnung and wort in ("ein", "eine", "einer", "einen", "einem",
                                "eines"):
        return 1
    if not ordnung and wort in ("kein", "keine", "keinen", "keiner", "null"):
        return 0
    if not ordnung and wort in ("beide", "beiden"):
        return 2
    for zahl in range(100):
        if wort == (ordnungswort(zahl) if ordnung
                    else zahlwort(zahl)).casefold():
            return zahl
    return None


def _zelle(roh):
    """Der sichtbare Inhalt einer Tabellenzelle.

    Ohne Tags, Entities aufgelöst, ohne Markdown-Hervorhebung, Leerraum
    zusammengezogen: So sieht die Zelle im gerenderten Dokument aus, gleich
    wie sie notiert ist.
    """
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", roh)
    text = re.sub(r"\[([^\]]*)\]\[[^\]]*\]", r"\1", text)
    text = html.unescape(re.sub(r"<[^>]*>", "", text))
    text = re.sub(r"[*_`]", "", text)
    text = re.sub(r"\s*,\s*", ", ", text)
    return re.sub(r"\s+", " ", text).strip()


def _beschriftung(zelle):
    """Eine Zeilenbeschriftung zum Vergleich: NFKC, ohne Groß/Klein."""
    text = unicodedata.normalize("NFKC", zelle)
    text = re.sub(r"\s*,\s*", ", ", text)
    return re.sub(r"\s+", " ", text).strip().casefold()


LISTENMARKE_RE = re.compile(r"^( {0,3}(?:[-*+]|\d{1,9}[.)]))( +|$)")


def _code_zeilen(zeilen):
    """Welche Zeilen Code sind, wie CommonMark sie liest.

    Eingezäunte Blöcke, auch im Zitat ("> ```"). Eingerückter Code nur nach
    einer Leerzeile oder als Fortsetzung eines eingerückten Blocks und, in
    einem Listenpunkt, erst vier Stellen hinter dessen Inhaltsrand; sonst
    setzt eine eingerückte Zeile den Absatz oder den Listenpunkt fort und ist
    sichtbarer Text.
    """
    maske, zaun = [], None
    leer_davor, code_davor, rand = True, False, None
    for roh in zeilen:
        zeile = roh.expandtabs(4)
        ohne_zitat = re.sub(r"^\s*(?:>\s?)+", "", zeile)
        treffer = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", ohne_zitat)
        if zaun is not None:
            maske.append(True)
            if (treffer and treffer.group(1)[0] == zaun[0]
                    and len(treffer.group(1)) >= len(zaun)
                    and not treffer.group(2).strip()):
                zaun = None
            leer_davor, code_davor = False, False
            continue
        if treffer and not (treffer.group(1)[0] == "`"
                            and "`" in treffer.group(2)):
            zaun = treffer.group(1)
            maske.append(True)
            leer_davor, code_davor = False, False
            continue
        if not zeile.strip():
            maske.append(False)
            leer_davor = True
            continue
        einzug = len(zeile) - len(zeile.lstrip(" "))
        basis = rand if rand is not None else 0
        if (leer_davor or code_davor) and einzug >= basis + 4:
            maske.append(True)
            leer_davor, code_davor = False, True
            continue
        marke = LISTENMARKE_RE.match(zeile)
        if marke:
            rand = len(marke.group(1)) + max(1, len(marke.group(2)))
        elif einzug == 0 and leer_davor:
            rand = None
        maske.append(False)
        leer_davor, code_davor = False, False
    return maske


def _sichtbar(text):
    """Markdown ohne Code und ohne HTML-Kommentare, Zeilenzahl erhalten."""
    zeilen = text.splitlines()
    maske = _code_zeilen(zeilen)
    # Codespans können "<!--" enthalten; für die Suche nach Kommentaren
    # zählen sie nicht.
    sichtbar = "\n".join(
        "" if code else re.sub(r"`[^`\n]*`", lambda m: " " * len(m.group(0)),
                               zeile)
        for zeile, code in zip(zeilen, maske))
    return re.sub(r"<!--.*?-->", lambda m: "\n" * m.group(0).count("\n"),
                  sichtbar, flags=re.S)


class _HtmlTabellen(HTMLParser):
    """Zeilen und Zellen einer HTML-Seite, wie ein Browser sie liest.

    Eine Zelle endet auch ohne "</td>" an der nächsten Zelle oder Zeile;
    Kommentare zählen nicht.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.zeilen, self._zeile, self._zelle = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._zeile_ende()
            self._zeile = []
        elif tag in ("td", "th"):
            self._zelle_ende()
            if self._zeile is None:
                self._zeile = []
            self._zelle = []

    def handle_endtag(self, tag):
        if tag in ("td", "th"):
            self._zelle_ende()
        elif tag in ("tr", "thead", "tbody", "tfoot", "table"):
            self._zeile_ende()

    def handle_data(self, data):
        if self._zelle is not None:
            self._zelle.append(data)

    def _zelle_ende(self):
        if self._zelle is not None and self._zeile is not None:
            self._zeile.append(_zelle("".join(self._zelle)))
        self._zelle = None

    def _zeile_ende(self):
        self._zelle_ende()
        if self._zeile:
            self.zeilen.append(self._zeile)
        self._zeile = None

    def close(self):
        super().close()
        self._zeile_ende()


TRENNZEILE_RE = re.compile(
    r"^\s*\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)+\|?\s*$")


def tabellenzeilen(text, html_seite):
    """Jede Tabellenzeile eines Dokuments als Liste ihrer sichtbaren Zellen.

    Markdown: jede Zeile, die mit "|" beginnt, und jede Zeile mit "|" in
    einem Tabellenblock (auch ohne Strich am Rand), außerhalb von
    Codeblöcken und HTML-Kommentaren. HTML: über einen Parser.
    """
    if html_seite:
        leser = _HtmlTabellen()
        leser.feed(re.sub(r"<!--.*?-->", "", text, flags=re.S))
        leser.close()
        return leser.zeilen
    sichtbar = _sichtbar(text)
    # HTML-Tabellen im Markdown zählen wie die der Landingpage.
    leser = _HtmlTabellen()
    leser.feed(sichtbar)
    leser.close()
    gefunden = list(leser.zeilen)
    # Eine Tabelle im Zitat ist auch eine Tabelle.
    zeilen = [re.sub(r"^\s*(?:>\s?)+", "", zeile)
              for zeile in sichtbar.splitlines()]
    in_tabelle = False
    for nummer, zeile in enumerate(zeilen):
        if not zeile.strip():
            in_tabelle = False
            continue
        if TRENNZEILE_RE.match(zeile):
            in_tabelle = True
            continue
        naechste = zeilen[nummer + 1] if nummer + 1 < len(zeilen) else ""
        if "|" in zeile and (in_tabelle or zeile.lstrip().startswith("|")
                             or TRENNZEILE_RE.match(naechste)):
            inhalt = zeile.strip()
            inhalt = inhalt[1:] if inhalt.startswith("|") else inhalt
            inhalt = inhalt[:-1] if inhalt.endswith("|") else inhalt
            if re.search(r"<\s*t[dhr]\b", inhalt, flags=re.I):
                continue
            gefunden.append([_zelle(zelle) for zelle in inhalt.split("|")])
    return gefunden


def lauf(argv, cwd, timeout=120):
    ergebnis = subprocess.run(
        [sys.executable, "-B", *argv],
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
    )
    return ergebnis.returncode, ergebnis.stdout + ergebnis.stderr


def recall_stand():
    """Die Messwerte der Suche, mit demselben Werkzeug wie von Hand."""
    spec = importlib.util.spec_from_file_location("skillsafe_recall", RECALL_TOOL)
    werkzeug = importlib.util.module_from_spec(spec)
    vorher = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(werkzeug)
    finally:
        sys.dont_write_bytecode = vorher
    fragen, _ = werkzeug.lade_gold(werkzeug.STANDARD_GOLD, SKILL)
    sichtung = werkzeug.sichtung_pruefen(SKILL, fragen[0]["frage"])
    zeilen, _ = werkzeug.messe(SKILL, fragen, [], 8, sichtung["seite_von"])
    werte = {}
    for gruppe in RECALL_ZEILEN:
        zahl = werkzeug.zusammenfassung(
            [zeile for zeile in zeilen if zeile["gruppe"] == gruppe])
        werte[gruppe] = (zahl["gesamt"], zahl["treffer"], zahl["pflicht"],
                         zahl["hinweis"], zahl["still"])
    return werte


def e2e_stand():
    """Die Zahlen der Ende-zu-Ende-Läufe, aus den Protokollen unter tests/e2e/.

    Nachrechnen lassen sie sich nur gegen den Stand, an den ihre Siegel
    gebunden sind (tests/e2e/LIESMICH.md). Hier wird deshalb nicht neu
    gemessen, sondern gebunden: Was README und Landingpage nennen, muss dem
    'ergebnis' entsprechen, das tools/antwort_check.py zum Messzeitpunkt in
    das Protokoll geschrieben hat.
    """
    werte = {}
    for datei in sorted(E2E_ORDNER.glob("runde-*.json")):
        try:
            daten = json.loads(datei.read_text(encoding="utf-8"))
            runde = int(daten["runde"])
            ergebnis = daten["ergebnis"]
            zahlen = tuple(int(ergebnis[feld]) for feld in (
                "antworten", "positiv", "positiv_gefunden",
                "vom_ranking_verfehlt", "davon_gefunden", "negativ",
                "negativ_korrekt", "verstoesse"))
            quittiert = [eintrag for eintrag in daten["antworten"]
                         if eintrag["quittung"]]
            eintrag = {
                "zahlen": zahlen,
                "version": str(daten["stand"]["version"]),
                "agenten": int(daten["agenten"]),
                "quittungen": (int(ergebnis["quittungen"]),
                               int(ergebnis["quittungen_gueltig"])),
                # Negativfragen, die mit einer Quittung abgelehnt wurden; die
                # übrigen korrekt abgelehnten fragten nach einer Kennung, die
                # es nicht gibt (antworten.md, Schritt 2b).
                "negativ_quittiert": sum(
                    1 for antwort in quittiert if antwort["art"] == "negativ"),
                # Wie viele Sichtungen über wie viele Stapel liefen.
                "stapel": dict(Counter(
                    len(antwort["quittung"]) for antwort in quittiert)),
            }
        except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
            raise SystemExit(
                f"{datei} ist kein vollständiges Protokoll (runde, stand, "
                f"agenten, antworten, ergebnis): {exc!r}") from exc
        if runde in werte:
            raise SystemExit(
                f"{datei}: Runde {runde} liegt doppelt unter {E2E_ORDNER}")
        werte[runde] = eintrag
    if not werte:
        raise SystemExit(f"Unter {E2E_ORDNER} liegt kein Protokoll runde-*.json")
    return werte


def e2e_eintraege(protokolle):
    """Die Werte aus e2e_stand() als Einträge des geprüften Stands."""
    stand = {}
    for runde, eintrag in protokolle.items():
        for feld, wert in eintrag.items():
            name = "runde" if feld == "zahlen" else feld
            stand[f"e2e_{name}_{runde}"] = wert
    return stand


def ist_stand():
    """Die echten Werte einsammeln. Kein Schreibkommando."""
    stand = {}
    stand["version"] = (SKILL / "VERSION").read_text(encoding="utf-8").strip()
    # Die Profilnummer steht in der Engine, nicht in einer Ausgabe. Sie ist
    # auf der Landingpage einmal still veraltet (1.2 statt 1.3), deshalb
    # wird sie hier gelesen statt angenommen.
    treffer = re.search(
        r'^PROFIL = "([^"]+)"',
        (SKILL / "scripts/vault.py").read_text(encoding="utf-8"), re.M)
    if not treffer:
        raise SystemExit("PROFIL in scripts/vault.py nicht gefunden")
    stand["profil"] = treffer.group(1)

    rc, stats = lauf(["scripts/vault.py", "stats"], SKILL)
    if rc != 0:
        raise SystemExit(f"stats ist rot, erst den Bestand reparieren:\n{stats}")
    treffer = re.search(
        r"(\d+) Seiten, (\d+) Claims, (\d+) Quellen, (\d+) Kanten", stats
    )
    if not treffer:
        raise SystemExit(f"stats-Ausgabe nicht lesbar:\n{stats}")
    stand["seiten"], stand["claims"], stand["quellen"], stand["kanten"] = (
        int(wert) for wert in treffer.groups()
    )

    rc, verify = lauf(["scripts/vault.py", "checksum", "--verify"], SKILL)
    if rc != 0:
        raise SystemExit(f"checksum --verify ist rot:\n{verify}")
    treffer = re.search(r"verify: (\d+) Dateien", verify)
    stand["manifest"] = int(treffer.group(1)) if treffer else None

    # Die Suite braucht länger als jedes einzelne Kommando; auf einem
    # langsamen Runner lag sie schon vor der Recall-Messung nahe an 120 s.
    rc, tests = lauf(["-m", "unittest", "discover", "-s", "tests", "-t", "."],
                     REPOSITORY, timeout=900)
    if rc != 0:
        raise SystemExit(f"Testsuite ist rot:\n{tests[-2000:]}")
    treffer = re.search(r"Ran (\d+) tests", tests)
    stand["tests"] = int(treffer.group(1)) if treffer else None

    # Bewusst in ein Temporärverzeichnis: der Wächter ist read-only und darf
    # weder dist/ anfassen noch an einem vorhandenen Archiv scheitern.
    with tempfile.TemporaryDirectory(prefix="skillsafe-check-docs-") as temp:
        ziel = Path(temp) / "pruefpaket.skill"
        rc, paket = lauf(
            ["tools/build_skill_package.py", "--output", str(ziel)], REPOSITORY
        )
    if rc != 0:
        raise SystemExit(f"Paketbau ist rot:\n{paket}")
    stand["paket_sha"] = re.search(r"sha256: ([0-9a-f]{64})", paket).group(1)
    stand["paket_dateien"] = int(re.search(r"files: (\d+)", paket).group(1))

    # Externe Zaehler stehen bewusst auf einer eigenen stats-Zeile: ein
    # zusaetzliches Feld in der Kopfzeile haette den Waechter an der eigenen
    # Erweiterung brechen lassen.
    treffer = re.search(
        r"Externe Bezugsquellen: (\d+), Satzanker: (\d+), Kataloge: (\d+)", stats
    )
    if not treffer:
        raise SystemExit(f"stats nennt keine externen Zahlen:\n{stats}")
    stand["extern"], stand["anker"], stand["kataloge"] = (
        int(wert) for wert in treffer.groups()
    )
    for gruppe, werte in recall_stand().items():
        stand[f"recall_{gruppe}"] = werte
    stand.update(e2e_eintraege(e2e_stand()))
    return stand


def pruefe(stand):
    readme = README.read_text(encoding="utf-8")
    landing = LANDING.read_text(encoding="utf-8")
    konzept = KONZEPT.read_text(encoding="utf-8")
    liesmich = LIESMICH.read_text(encoding="utf-8")
    abweichungen = []

    def verlange(text, muster, name, erwartet, datei):
        gefunden = re.search(muster, text)
        if not gefunden:
            abweichungen.append(f"{datei}: {name} nicht gefunden (Muster {muster!r})")
            return
        ist = gefunden.group(1)
        if str(ist) != str(erwartet):
            abweichungen.append(
                f"{datei}: {name} steht auf {ist!r}, echt ist {erwartet!r}"
            )

    verlange(readme, r"\*\*Aktueller Release: v([0-9.]+)\*\*", "Version",
             stand["version"], "README.md")
    verlange(readme, r"\*\*Aktueller Release: v[0-9.]+\*\* \(Profil `([^`]+)`\)",
             "Profil", stand["profil"], "README.md")
    verlange(readme, r"Abnahme: (\d+) Tests bestanden", "Testzahl",
             stand["tests"], "README.md")
    verlange(readme, r"Tests bestanden · (\d+) manifestierte Dateien",
             "manifestierte Dateien", stand["manifest"], "README.md")
    verlange(readme, r"manifestierte Dateien · (\d+) sichere", "Paketeinträge",
             stand["paket_dateien"], "README.md")
    verlange(readme, r"`([0-9a-f]{64})`", "Paket-SHA-256",
             stand["paket_sha"], "README.md")
    verlange(readme, r"Herkunft des Tresors mit seinen eigenen Mitteln: (\d+) Seiten",
             "Seiten", stand["seiten"], "README.md")
    verlange(readme, r"eigenen Mitteln: \d+ Seiten, (\d+) Claims", "Claims",
             stand["claims"], "README.md")

    verlange(landing, r'href="#funktionen">Was v([0-9.]+) kann</a>', "Version (CTA)",
             stand["version"], "index.html")
    verlange(landing, r"Claims<br>v([0-9.]+)</span>", "Version (Stempel)",
             stand["version"], "index.html")
    verlange(landing, r"<span>SkillSafe v([0-9.]+) ·", "Version (Footer)",
             stand["version"], "index.html")
    verlange(landing, r'class="eyebrow">Profil ([^ <]+) · purer Skill<',
             "Profil (Hero)", stand["profil"], "index.html")
    # Die validate-Zeile im Demo-Terminal stand lange auf einem alten Stand
    # (5 Seiten, 26 Claims), weil nur die doctor-Zeile bewacht war.
    verlange(landing, r"validate: 0 Fehler, 0 Warnungen — (\d+) Seiten",
             "Seiten (validate)", stand["seiten"], "index.html")
    verlange(landing, r"validate: 0 Fehler, 0 Warnungen — \d+ Seiten, (\d+) Claims",
             "Claims (validate)", stand["claims"], "index.html")
    verlange(landing, r"\d+ Seiten, \d+ Claims, (\d+) Quellen, \d+ externe Quellen",
             "Quellen (validate)", stand["quellen"], "index.html")
    verlange(landing, r"\d+ Claims, \d+ Quellen, (\d+) externe Quellen",
             "externe Quellen (validate)", stand["extern"], "index.html")
    verlange(landing, r"verify: (\d+) Dateien unverändert", "manifestierte Dateien",
             stand["manifest"], "index.html")
    verlange(landing, r"(\d+) Seiten / \d+ Claims / \d+ Quellen", "Seiten (doctor)",
             stand["seiten"], "index.html")
    verlange(landing, r"\d+ Seiten / (\d+) Claims / \d+ Quellen", "Claims (doctor)",
             stand["claims"], "index.html")
    verlange(landing, r"\d+ Seiten / \d+ Claims / (\d+) Quellen", "Quellen (doctor)",
             stand["quellen"], "index.html")
    verlange(readme, r"(\d+) aufgeführte externe Bezugsquellen",
             "externe Bezugsquellen", stand["extern"], "README.md")
    verlange(readme, r"externe Bezugsquellen · (\d+) Satzanker", "Satzanker",
             stand["anker"], "README.md")

    # Messwerte der Suche: Fragen, direkt gefunden, Pflicht-Vollsichtung, nur
    # Hinweis, still verfehlt. Die Zeile "Vorher" steht bewusst nicht hier:
    # sie ist ein einmaliger Messwert des abgelösten Rankings.
    #
    # Gelesen wird die Tabelle so, wie sie gerendert aussieht: Fettdruck,
    # Leerraum und Attribute ändern nichts daran, welche Zeile welche ist.
    # Jede Zeile mit dieser Beschriftung zählt. Sonst stünde hinter der
    # richtigen unbemerkt eine zweite, falsche.
    zeilen = {"KONZEPT.md": tabellenzeilen(konzept, html_seite=False),
              "README.md": tabellenzeilen(readme, html_seite=False),
              "index.html": tabellenzeilen(landing, html_seite=True)}

    def als_wert(zelle):
        return int(zelle) if zelle.isdecimal() else zelle

    def runde_von(datei, zelle):
        # Am Anfang der Beschriftung; ein Zusatz („Runde 3 ¹", „Runde 5
        # (Nachtrag)", „4†") macht aus der Zeile keine andere. In KONZEPT
        # heißt die Zeile „3, vier Agenten"; als Rundenzeile zählt dort jede
        # Zeile, deren Beschriftung mit einer Zahl beginnt und Agenten nennt.
        beschriftung = _beschriftung(zelle)
        muster = {"README.md": r"ende zu ende, ?runde\s*(\d+)",
                  "index.html": r"runde\s*(\d+)",
                  "KONZEPT.md": r"(?:runde\s*)?(\d+)"}[datei]
        treffer = re.match(muster, beschriftung)
        if datei == "KONZEPT.md" and "agenten" not in beschriftung:
            return None
        return int(treffer.group(1)) if treffer else None

    def verlange_zeile(datei, passt, name, erwartet, version=None):
        treffer = [zellen for zellen in zeilen[datei]
                   if zellen and passt(zellen[0])]
        if not treffer:
            abweichungen.append(f"{datei}: {name} nicht gefunden")
            return
        if len(treffer) > 1:
            abweichungen.append(
                f"{datei}: {name} steht {len(treffer)}-mal da, erwartet ist "
                f"genau eine Zeile"
            )
        for zellen in treffer:
            rest = zellen[1:]
            if version is not None:
                ist_version = rest[0] if rest else None
                if ist_version != f"v{version}":
                    abweichungen.append(
                        f"{datei}: Stand der {name} steht auf "
                        f"{ist_version!r}, echt ist 'v{version}'")
                rest = rest[1:]
            ist = tuple(als_wert(zelle) for zelle in rest)
            if ist != tuple(erwartet):
                abweichungen.append(
                    f"{datei}: {name} steht auf {ist!r}, echt ist "
                    f"{tuple(erwartet)!r}"
                )

    for gruppe, beschriftung in RECALL_ZEILEN.items():
        erwartet = stand[f"recall_{gruppe}"]
        for datei in ("README.md", "index.html"):
            verlange_zeile(
                datei,
                lambda zelle, soll=_beschriftung(beschriftung):
                    _beschriftung(zelle).startswith(soll),
                f"Messwerte {gruppe!r}", erwartet)

    # Ende-zu-Ende-Läufe. README führt alle acht Zahlen je Runde und den
    # Stand, die Landingpage fünf davon: Fragen, gefunden, davon nach
    # verfehltem Ranking, korrekt abgelehnt, Verstöße. Dort heißt die Zeile
    # nur "Runde n", damit die Tabelle auf einem Telefon nicht umbricht.
    # Erkannt wird eine Rundenzeile an ihrer Nummer, auch als "Runde 03".
    runden = sorted(
        (int(key.rsplit("_", 1)[1]) for key in stand
         if key.startswith("e2e_runde_")))
    for runde in runden:
        werte = stand[f"e2e_runde_{runde}"]
        name = f"Ende-zu-Ende-Runde {runde}"
        verlange_zeile(
            "README.md",
            lambda zelle, r=runde: runde_von("README.md", zelle) == r,
            name, werte, version=stand.get(f"e2e_version_{runde}"))
        verlange_zeile(
            "index.html",
            lambda zelle, r=runde: runde_von("index.html", zelle) == r,
            name, (werte[0], werte[2], werte[4], werte[6], werte[7]))
        verlange_zeile(
            "KONZEPT.md",
            lambda zelle, r=runde: runde_von("KONZEPT.md", zelle) == r,
            name, werte, version=stand.get(f"e2e_version_{runde}"))
        # Dort nennt die Beschriftung auch, wie viele Agenten es waren.
        for zellen in zeilen["KONZEPT.md"]:
            if zellen and runde_von("KONZEPT.md", zellen[0]) == runde:
                genannt = re.search(r"(\w+)\s+(?:frische\s+)?agenten",
                                    _beschriftung(zellen[0]))
                wort = genannt.group(1) if genannt else ""
                if zahl_aus_wort(wort) != stand.get(f"e2e_agenten_{runde}"):
                    abweichungen.append(
                        f"KONZEPT.md: {name} nennt {wort!r} Agenten, das "
                        f"Protokoll {stand.get(f'e2e_agenten_{runde}')}")
    # Umgekehrt: keine Zeile ohne Protokoll. Eine Runde, zu der nichts unter
    # tests/e2e/ liegt, ist eine Behauptung ohne Beleg.
    for datei in ("README.md", "index.html", "KONZEPT.md"):
        gefunden = {runde_von(datei, zellen[0])
                    for zellen in zeilen[datei] if zellen} - {None}
        ohne = sorted(gefunden - set(runden))
        if ohne:
            abweichungen.append(
                f"{datei}: Ende-zu-Ende-Runde "
                f"{', '.join(str(runde) for runde in ohne)} steht in der "
                f"Tabelle, aber kein Protokoll unter tests/e2e/ belegt sie"
            )

    # Die Summen im Fließtext, aus denselben Protokollen.
    if runden:
        pruefe_summen(stand, runden, readme, landing, abweichungen,
                      konzept=konzept, liesmich=liesmich)
    return abweichungen


def _fliesstext(text, html_seite):
    """Text zum Suchen: ohne Kommentare und Tags, Entities aufgelöst,
    Anführungszeichen vereinheitlicht, Leerraum zusammengezogen. Ein Satz
    darf so an jeder Stelle umbrechen."""
    if html_seite:
        text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    else:
        text = _sichtbar(text)
        text = re.sub(r"\[\^[^\]]*\]", "", text)
        text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
        text = re.sub(r"\[([^\]]*)\]\[[^\]]*\]", r"\1", text)
        text = re.sub(r"\\\n", " ", text)
        text = re.sub(r"[*_`]", "", text)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    # Unsichtbare Zeichen trennen ein Wort nicht: "Ein&shy;und&shy;zwanzig".
    text = re.sub("[\u00ad\u200b\u200c\u200d\u2060\ufeff]", "", text)
    text = re.sub("[„“”«»″‚‘’‹›']", '"', text)
    return re.sub(r"\s+", " ", text)


def pruefe_summen(stand, runden, readme, landing, abweichungen, konzept=None,
                  liesmich=None):
    """Was README und Landingpage über alle Ende-zu-Ende-Runden sagen.

    Jede Fundstelle eines Satzes zählt, wie bei den Tabellenzeilen: Sonst
    stünde hinter der richtigen unbemerkt eine zweite, falsche. Zahlen dürfen
    als Ziffern oder als Wort dastehen.
    """
    texte = {"README.md": _fliesstext(readme, html_seite=False),
             "index.html": _fliesstext(landing, html_seite=True)}
    if konzept is not None:
        texte["KONZEPT.md"] = _fliesstext(konzept, html_seite=False)
    if liesmich is not None:
        texte["LIESMICH.md"] = _fliesstext(liesmich, html_seite=False)

    def summe(stelle):
        return sum(stand[f"e2e_runde_{runde}"][stelle] for runde in runden)

    def melde(datei, text):
        abweichungen.append(f"{datei}: Ende-zu-Ende-Summe: {text}")

    def fundstellen(datei, muster, was, pflicht=True):
        treffer = list(re.finditer(muster, texte[datei]))
        if not treffer and pflicht:
            melde(datei, f"{was} nicht gefunden (Muster {muster!r})")
        return treffer

    agenten = sum(stand[f"e2e_agenten_{runde}"] for runde in runden)
    for datei in [name for name in ("README.md", "index.html", "KONZEPT.md")
                  if name in texte]:
        for treffer in fundstellen(datei, r"(\w+) frische Agenten bekamen je",
                                   "Zahl der Agenten"):
            if zahl_aus_wort(treffer.group(1)) != agenten:
                melde(datei, f"{treffer.group(1)!r} frische Agenten, die "
                             f"Protokolle nennen {agenten}")

    # "Alle N Fragen, deren Claim das Ranking verfehlte, wurden über die
    # Vollsichtung gefunden" stimmt nur, wenn es wirklich alle waren.
    verfehlt, gefunden = summe(3), summe(4)
    for treffer in fundstellen(
            "README.md", r"Alle (\w+) Fragen, deren Claim das Ranking "
            r"verfehlte, wurden über die Vollsichtung gefunden",
            "Summe der vom Ranking verfehlten Fragen"):
        if (zahl_aus_wort(treffer.group(1)), gefunden) != (verfehlt, verfehlt):
            melde("README.md", f"'Alle {treffer.group(1)}' verfehlte Fragen "
                               f"gefunden, die Protokolle zählen {gefunden} "
                               f"von {verfehlt}")

    # Weitere Zahlen derselben Protokolle: die Grenzen der Messung in KONZEPT
    # und LIESMICH, und wie viele Agenten die erste Runde hatte.
    for datei, muster, was in (
            ("KONZEPT.md", r"Grenzen dieser Messung, ausdrücklich: (\w+) "
             r"Fragen", "Fragen in den Grenzen der Messung"),
            ("LIESMICH.md", r"(\w+) Fragen, ein Demo-Bestand",
             "Fragen in den Grenzen der Messung")):
        if datei not in texte:
            continue
        for treffer in fundstellen(datei, muster, was):
            if zahl_aus_wort(treffer.group(1)) != summe(0):
                melde(datei, f"{treffer.group(0)!r}, die Protokolle zählen "
                             f"{summe(0)} Fragen")
    if "KONZEPT.md" in texte and 1 in runden:
        for treffer in fundstellen(
                "KONZEPT.md", r"(\w+) von (\w+) Agenten der ersten Runde",
                "Agenten der ersten Runde"):
            if zahl_aus_wort(treffer.group(2)) != stand["e2e_agenten_1"]:
                melde("KONZEPT.md", f"{treffer.group(0)!r}, das Protokoll "
                                    f"nennt {stand['e2e_agenten_1']} Agenten")

    # Der Abnahmeblock in KONZEPT nennt alle Summen in einem Satz.
    if "KONZEPT.md" in texte:
        negativ_k, korrekt_k = summe(5), summe(6)
        quittiert_k = sum(stand[f"e2e_negativ_quittiert_{runde}"]
                          for runde in runden)
        soll = (agenten, summe(0), summe(7), summe(2), summe(1), summe(4),
                korrekt_k, negativ_k, quittiert_k, korrekt_k - quittiert_k)
        for treffer in fundstellen(
                "KONZEPT.md", r"(\w+) frische Agenten, (\w+) Fragen, (\w+) "
                r"Verstöße · bei (\w+) von (\w+) Fragen mit erwartetem Claim "
                r"wurde er gefunden, (\w+) davon nach verfehltem Ranking · "
                r"(\w+) von (\w+) Negativfragen korrekt abgelehnt, (\w+) mit "
                r"gültiger Quittung und (\w+) Frage", "Abnahmeblock Ende zu Ende"):
            ist = tuple(zahl_aus_wort(wert) for wert in treffer.groups())
            if ist != soll:
                melde("KONZEPT.md", f"Abnahmeblock {ist!r}, die Protokolle "
                                    f"zählen {soll!r}")

    # "In den ersten drei Runden reichte jeder Agent zu jeder Frage eine
    # gültige, vollständige Quittung ein, in Runde 4 zu zehn von zwölf
    # Fragen": die ersten Runden ohne Lücke, die genannte mit genau so
    # vielen Quittungen, alle gültig, und danach keine weitere Runde.
    if "KONZEPT.md" in texte:
        for treffer in fundstellen(
                "KONZEPT.md", r"In den ersten (\w+) Runden reichte jeder Agent "
                r"zu jeder Frage eine gültige, vollständige Quittung ein, in "
                r"Runde (\w+) zu (\w+) von (\w+) Fragen; die (\w+) übrigen",
                "Quittungen je Runde"):
            erste, letzte, mit, von, uebrig = (zahl_aus_wort(wert)
                                               for wert in treffer.groups())
            echt = {runde: (stand[f"e2e_runde_{runde}"][0],)
                    + tuple(stand[f"e2e_quittungen_{runde}"])
                    for runde in runden}
            stimmt = (
                None not in (erste, letzte, mit, von, uebrig)
                and letzte == max(runden)
                and runden == list(range(1, letzte + 1))
                and erste == letzte - 1
                and uebrig == von - mit
                and all(echt[runde] == (echt[runde][0],) * 3
                        for runde in runden[:erste])
                and echt[letzte] == (von, mit, mit))
            if not stimmt:
                melde("KONZEPT.md", f"{treffer.group(0)!r}, die Protokolle "
                                    f"(Fragen, Quittungen, gültig): {echt!r}")

    # Die Negativfragen: korrekt abgelehnt, mit gültiger Quittung oder als
    # Befund über eine Kennung, die es nicht gibt.
    negativ, korrekt = summe(5), summe(6)
    quittiert = sum(stand[f"e2e_negativ_quittiert_{runde}"] for runde in runden)
    quittungen = [stand[f"e2e_quittungen_{runde}"] for runde in runden]
    erwartet = (negativ, quittiert, korrekt - quittiert)
    for treffer in fundstellen(
            "README.md", r'Alle (\w+) Negativfragen wurden korrekt abgelehnt: '
            r'(\w+) mit gültiger Quittung als "Nicht im Bestand", (\w+) mit '
            r'dem Befund des Scripts', "Summe der Negativfragen"):
        ist = tuple(zahl_aus_wort(wert) for wert in treffer.groups())
        if ist != erwartet or korrekt != negativ:
            melde("README.md", f"Negativfragen {ist!r}, die Protokolle zählen "
                               f"{erwartet!r} bei {korrekt} korrekt "
                               f"abgelehnten")
    seite = (quittiert, negativ, korrekt - quittiert)
    for treffer in fundstellen(
            "index.html", r'(\w+) von (\w+) mit gültiger Quittung als "Nicht '
            r'im Bestand", (\w+) mit dem Befund des Scripts',
            "Summe der Negativfragen"):
        ist = tuple(zahl_aus_wort(wert) for wert in treffer.groups())
        if ist != seite:
            melde("index.html", f"Negativfragen {ist!r}, die Protokolle "
                                f"zählen {seite!r}")
    if any(gueltig != alle for alle, gueltig in quittungen):
        melde("README.md", "nicht jede Quittung der Protokolle ist gültig, "
                           "der Text sagt 'mit gültiger Quittung'")

    # "in allen vier Runden alle (24 von 24, …)": Zahl der Runden und die
    # Paare gefunden/mit Claim, Runde für Runde.
    paare = ", ".join(
        f"{stand[f'e2e_runde_{runde}'][2]} von "
        f"{stand[f'e2e_runde_{runde}'][1]}" for runde in runden)
    for treffer in fundstellen("index.html",
                               r"in allen (\w+) Runden alle \(([^)]*)\)",
                               "gefundene Claims je Runde"):
        if (zahl_aus_wort(treffer.group(1)) != len(runden)
                or treffer.group(2) != paare or summe(2) != summe(1)):
            melde("index.html", f"'in allen {treffer.group(1)} Runden alle "
                                f"({treffer.group(2)})', die Protokolle: "
                                f"{len(runden)} Runden, ({paare})")

    # "In Runde 2 bis 4 liefen je sechs Sichtungen über drei Stapel": genau
    # in diesen Runden, und in keiner anderen, gleich viele. KONZEPT sagt
    # "je sechs davon", gemeint sind die Quittungen des Satzes davor.
    formen = [(r"[Ii]n Runde (\w+) bis (\w+) liefen je (\w+) "
               r"(?:Sichtungen|davon) über (\w+) Stapel", False),
              (r"[Ii]n der (\w+\.?) bis (\w+\.?) Runde liefen je "
               r"(\w+) (?:Sichtungen|davon) über (\w+) Stapel", True)]
    # Je Datei ist eine Form Pflicht; jede andere wird geprüft, wo sie steht.
    pflichtform = {"README.md": 0, "index.html": 1, "KONZEPT.md": 0}
    stapelsaetze = [(datei, muster, ordnung, nummer == pflichtform[datei])
                    for datei in texte if datei in pflichtform
                    for nummer, (muster, ordnung) in enumerate(formen)]
    for datei, muster, ordnung, pflicht in stapelsaetze:
        for treffer in fundstellen(datei, muster,
                                   "Sichtungen über mehrere Stapel",
                                   pflicht=pflicht):
            von = zahl_aus_wort(treffer.group(1), ordnung=ordnung)
            bis = zahl_aus_wort(treffer.group(2), ordnung=ordnung)
            je = zahl_aus_wort(treffer.group(3))
            stapel = zahl_aus_wort(treffer.group(4))
            mit = {runde for runde in runden
                   if je is not None and stapel is not None
                   and stand[f"e2e_stapel_{runde}"].get(stapel, 0) == je}
            if (von is None or bis is None or bis > max(runden)
                    or mit != set(range(von, bis + 1))):
                melde(datei, f"{treffer.group(0)!r}, die Protokolle: so viele "
                             f"Sichtungen in Runde "
                             f"{', '.join(map(str, sorted(mit))) or 'keiner'}")


def main():
    stand = ist_stand()
    abweichungen = pruefe(stand)
    if abweichungen:
        print("🔴 check-docs: veröffentlichte Zahlen weichen ab.")
        for eintrag in abweichungen:
            print(f"   {eintrag}")
        print("\nEchter Stand:")
        for schluessel, wert in sorted(stand.items()):
            print(f"   {schluessel}: {wert}")
        return 1
    print(f"🟢 check-docs: {len(stand)} Werte geprüft, README.md, index.html "
          f"und KONZEPT.md stimmen mit der echten Ausgabe überein.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
