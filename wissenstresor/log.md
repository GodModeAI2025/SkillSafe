# Log — chronologische Historie (append-only)

Format: `## [JJJJ-MM-TT] aktion | Text` — grep-bar mit Unix-Werkzeugen.
Aktionen: ingest, update, lint, release, note, onboarding.
Eintraege nur ueber `python3 scripts/vault.py log <aktion> "<text>"`.

## [2026-07-04] release | Wissenstresor v1.0.0 aufgebaut: Engine (vault.py), Profil oksv-lite/1.0, Demo-Domaene demo-okf
## [2026-07-04] ingest | S-0001 (Google Cloud Blog, OKF-Ankuendigung) registriert; Seite demo-okf/okf.md mit C-0001..C-0005
## [2026-07-04] ingest | S-0002 (Karpathy-Gist llm-wiki inkl. Kommentare) registriert; Seite demo-okf/llm-wiki-muster.md mit C-0101..C-0104
## [2026-07-04] release | v0.1.0 — 2 Seiten, 9 Claims, 2 Quellen (minor)
## [2026-07-04] release | v0.1.1 — 2 Seiten, 9 Claims, 2 Quellen (patch)
## [2026-07-04] onboarding | faktensammlung: Fallback-Typ fuer atomare Einzelaussagen ohne eigene Seite (Clash aus S-0003-Ingest; Befoerderung ab ~3 verwandten Claims)
## [2026-07-04] ingest | S-0003 (Iusztin: Stop Chasing the Perfect Ontology) registriert; Seiten demo-okf/ontologie-strategie.md (C-0201..C-0205) und demo-okf/fakten.md (C-0290..C-0291); Router um Ontologie-Schlagworte erweitert
## [2026-07-04] release | v0.2.0 — 4 Seiten, 16 Claims, 3 Quellen (minor)
## [2026-07-04] release | v0.2.1 — 4 Seiten, 16 Claims, 3 Quellen (patch)
## [2026-07-04] note | Engine erweitert: doctor meldet Split-Kandidaten ueber Claims-/Zeilenschwelle (vault.py); befuellen.md/KONZEPT.md um Anweisung fuer Nicht-Text-Quellen (PDF/Bild/OCR, fail-closed bei unsicherer Erkennung) ergaenzt
## [2026-07-04] release | v0.3.0 — 4 Seiten, 16 Claims, 3 Quellen (minor)
## [2026-07-05] note | Konzept fuer mehrere Tresore (Organisation/Abteilung/Projekt/privat) ergaenzt: AD-06 in KONZEPT.md, neue Referenzdatei references/mehrere-tresore.md (Namenskonvention, Bootstrap-Rezept, Grenzen), SKILL.md Regel 1 praezisiert (Attributions-/Vermischungsrisiko bei mehreren geladenen Tresoren), dead-ends.md um verworfene interne ACL ergaenzt
## [2026-07-05] release | v0.4.0 — 4 Seiten, 16 Claims, 3 Quellen (minor)
## [2026-07-05] note | Prioritaetsreihenfolge zwischen Scopes ergaenzt: Organisation < Fachbereich < Projekt (jeweils Ueberschreibung fuer den eigenen Scope), Persoenlich rein additiv, nie ueberschreibend. AD-06/KONZEPT.md erweitert, neue Sektion 8 in references/mehrere-tresore.md, kurzer Verweis in references/antworten.md
## [2026-07-05] release | v0.5.0 — 4 Seiten, 16 Claims, 3 Quellen (minor)
## [2026-07-05] note | Praezisierung: Fachbereich und Projekt koennen jeweils sowohl ueberschreiben als auch ergaenzen, persoenlich kann nur ergaenzen (KONZEPT.md AD-06, references/mehrere-tresore.md Sektion 8). Landingpage (index.html) um Sektion 'Mehrere Tresore' ergaenzt, Nav-Link 'Tresore' hinzugefuegt
## [2026-07-05] release | v0.5.1 — 4 Seiten, 16 Claims, 3 Quellen (patch)
## [2026-07-26] release | v0.5.2 — 4 Seiten, 16 Claims, 3 Quellen (patch)
## [2026-07-26] release | v0.6.0 — 4 Seiten, 16 Claims, 3 Quellen (minor)
## [2026-07-26] release | v0.6.1 — 4 Seiten, 16 Claims, 3 Quellen (patch)
## [2026-07-28] note | Parser lehnt verschachteltes Frontmatter fail-closed ab (Blockform hob Unterschluessel still ins Top-Level); validate und Paketbau fuehren unabhaengig eine Allowlist erlaubter Dateiarten mit Verbot ausfuehrbarer Inhalte
## [2026-07-28] release | v0.6.2 — 4 Seiten, 16 Claims, 3 Quellen (patch)
## [2026-07-28] ingest | S-0004 OKF-Spezifikation v0.2 (Volltext, Apache-2.0, T1): neue Seite demo-okf/okf-v02.md mit C-0301..C-0310, Begriffe B-0005..B-0009, definition_claim von B-0001 auf C-0301, okf.md auf veraltet mit ersetzt-Relation, ROUTER erweitert; AD-09 (keine ausfuehrbaren Verweise) und Abschnitt 'Verhaeltnis zu OKF v0.2' in KONZEPT.md, Kompatibilitaetsaussage in schema/profil.md geschaerft
## [2026-07-28] release | v0.7.0 — 5 Seiten, 26 Claims, 4 Quellen (minor)
## [2026-07-28] note | Profil oksv-lite/1.2: optionale Pruefangabe geprueft_von/geprueft_am (Paar, Aktorgrammatik mensch/prozess/agent, Kalendertag), Trust-Tier nach OKF v0.2 §5.3 abgeleitet und nie gespeichert, nie im Score; Envelope und stats um Tier erweitert, doctor-Hinweis nur wenn der Bestand das Feld nutzt
## [2026-07-28] release | v0.8.0 — 5 Seiten, 26 Claims, 4 Quellen (minor)
## [2026-07-28] note | Neues Kommando export --okf: freigegebener Bestand als OKF-v0.2-Bundle ausserhalb des Tresors, byteidentisch, status/Aktor/Fussnoten/Relationen/index/log uebersetzt; Ziel fail-closed gegen Skill-Ladeorte, Tresorinneres und Fremdinhalt, Rohquellen nur mit --with-sources; neue Referenzdatei references/export-okf.md, Exportgrenze in AD-06
## [2026-07-28] release | v0.9.0 — 5 Seiten, 26 Claims, 4 Quellen (minor)
## [2026-07-28] note | Haertungsrelease nach externem Audit: eingeruecktes '---' beendete das Frontmatter still (Terminator jetzt strikt); Export schreibt ueber Staging und ersetzt das Ziel atomar (Symlink im Zielordner trug den Export heraus, Halbstand und verwaiste Dokumente bei Re-Export); Trust-Tier wird nicht mehr ins Bundle geschrieben (Widerspruch zur Zusage 'nie gespeichert'); reservierte Dateinamen index.md/log.md und Tag-Zeichen ,[] abgelehnt; Begriffslabels injection-geprueft und als Frontmatter statt HTML-Kommentar exportiert; Linktexte escaped; _trust_tier typfest; Dekodierfehler in Export und Log abgefangen; Satzende-Erkennung respektiert deutsche Abkuerzungen
## [2026-07-28] release | v0.10.0 — 5 Seiten, 26 Claims, 4 Quellen (minor)
## [2026-07-28] note | Betriebsreife: Ausgabe auf Nicht-UTF-8-Konsolen gehaertet (cp1252 brach mit UnicodeEncodeError ab), Bootstrap-Workflow in die Tabelle aufgenommen
## [2026-07-28] release | v0.10.1 — 5 Seiten, 26 Claims, 4 Quellen (patch)
## [2026-08-06] extern | abruf https://raw.githubusercontent.com/GodModeAI2025/SkillSafe/main/README.md sha256=cf118096dc60b2b1341d8565b7562aae64ba8c2341f9145836473aaa55c02255 bytes=11800
## [2026-08-06] extern | abruf https://raw.githubusercontent.com/GodModeAI2025/SkillSafe/main/BETRIEB.md sha256=f87b27a1949b8e2e3017675c0b2bb17b7c823ce9ebe045e496018c21db90da73 bytes=10573
## [2026-08-06] release | v0.11.0 — 6 Seiten, 28 Claims, 4 Quellen (minor)
## [2026-08-06] release | v0.11.1 — 6 Seiten, 28 Claims, 4 Quellen (patch)
## [2026-08-06] release | v0.11.2 — 6 Seiten, 28 Claims, 4 Quellen (patch)
