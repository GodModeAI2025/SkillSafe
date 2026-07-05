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
