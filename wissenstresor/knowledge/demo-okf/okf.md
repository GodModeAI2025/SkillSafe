---
type: konzept
title: Open Knowledge Format (OKF)
domain: demo-okf
status: aktiv
confidence: hoch
version: 1.0.0
stand: 2026-07-04
sources: [S-0001]
tags: [okf, format, google, markdown, frontmatter]
relations:
  - formalisiert -> demo-okf/llm-wiki-muster.md
---

# Open Knowledge Format (OKF)

## Kurzfassung
OKF ist eine offene, anbieterneutrale Spezifikation von Google Cloud
(v0.1, Juni 2026), die Wissen als Verzeichnis von Markdown-Dateien mit
YAML-Frontmatter darstellt: eine Datei pro Konzept, der Dateipfad ist die
Identität, normale Markdown-Links bilden den Beziehungsgraphen. index.md
(progressive Offenlegung) und log.md (Historie) sind als optionale Dateien
vorgesehen. Google bezeichnet v0.1 ausdrücklich als Ausgangspunkt, nicht als
fertigen Standard; für einen evidenzgebundenen Tresor braucht es darum ein
strengeres Profil oberhalb von OKF (hier: oksv-lite/1.0).

## Claims
- **C-0001** [S-0001 | Abschnitt "How it works" | Wortlaut] OKF v0.1 repräsentiert Wissen als Verzeichnis von Markdown-Dateien mit YAML-Frontmatter; jede Datei beschreibt genau ein Konzept (Tabelle, Metrik, Runbook, API usw.).
- **C-0002** [S-0001 | Abschnitt "How it works" | Wortlaut] Der Dateipfad ist die Identität eines Konzepts; Konzepte verlinken sich über gewöhnliche Markdown-Links, wodurch das Verzeichnis zu einem Beziehungsgraphen wird.
- **C-0003** [S-0001 | Abschnitt "How it works" | Wortlaut] index.md-Dateien (für progressive Offenlegung beim Navigieren) und log.md-Dateien (für die chronologische Änderungshistorie) sind als optionale Bestandteile eines Bundles vorgesehen.
- **C-0004** [S-0001 | Einleitung und Abschluss | Wortlaut] Google bezeichnet OKF v0.1 als Ausgangspunkt und nicht als fertigen Standard; die Spezifikation formalisiert das LLM-Wiki-Muster in ein portables, interoperables Format.
- **C-0005** [S-0001 | Gesamtdokument | Auslegung] Weil die Spezifikation bewusst minimal ist, benötigt ein evidenzgebundener Wissenstresor ein strengeres Profil oberhalb von OKF; dieses Bundle definiert dafür oksv-lite/1.0 (siehe schema/profil.md).

## Kontext und Grenzen
Geltungsbereich dieser Seite: das Format selbst, nicht seine SEO-Wirkung.
Stand der Quelle ist die Ankündigung vom 2026-06-12; die Spezifikation ist
als v0.1 ausdrücklich im Fluss — bei Versionssprüngen Seite re-validieren.
