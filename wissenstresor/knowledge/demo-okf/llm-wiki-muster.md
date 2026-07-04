---
type: konzept
title: LLM-Wiki-Muster (Karpathy) und Praxisregeln
domain: demo-okf
status: aktiv
confidence: mittel
version: 1.0.0
stand: 2026-07-04
sources: [S-0002]
tags: [llm-wiki, karpathy, ingest, lint, kompression, map-first]
relations:
  - basiert_auf -> demo-okf/okf.md
---

# LLM-Wiki-Muster (Karpathy) und Praxisregeln

## Kurzfassung
Das LLM-Wiki-Muster trennt unveränderliche Rohquellen von einer persistenten,
kuratierten Wiki-Schicht, die das Modell anstelle der Rohdokumente liest;
Kernoperationen sind Ingest, Query und Lint mit grep-barem Log. Aus den
Praxisberichten im Kommentarbereich folgen zwei harte Regeln dieses Tresors:
Seiten lohnen nur, wenn sie Fakten aus vielen Quellen verdichten und zur
Abfragezeit als vertrauenswürdig gelten (Kompressionsregel) — und Relevanz
wird über die Map entschieden, nie durch Lesen von Seitenkörpern (Map-first).
Konfidenz dieser Seite ist "mittel", weil die Quelle ein lebendes Dokument
mit Trust-Stufe T3 ist.

## Claims
- **C-0101** [S-0002 | Gist-Text | Wortlaut] Das LLM-Wiki-Muster hält unveränderliche Rohquellen getrennt von einer persistenten, kuratierten Wiki-Schicht, die das Modell statt der Rohdokumente liest.
- **C-0102** [S-0002 | Gist-Text | Wortlaut] Kernoperationen sind Ingest, Query und Lint; das Log erhält chronologische, mit Datums-Präfix grep-bare Einträge.
- **C-0103** [S-0002 | Kommentarbereich | Wortlaut] Ein kontrolliertes Experiment im Kommentarbereich zeigt: Wiki-Seiten, die einzelne kleine Quellen nur spiegeln, sparen nichts und erzeugen doppelte Kosten, wenn das Modell Wiki und Quelle liest; Nutzen entsteht erst, wenn eine Seite Fakten aus vielen Quellen verdichtet und ihr zur Abfragezeit vertraut wird.
- **C-0104** [S-0002 | Kommentarbereich | Auslegung] Für den Wissenstresor folgen daraus die Kompressionsregel (verdichten statt spiegeln; Locator dient der menschlichen Nachprüfung, nicht der Re-Verifikation pro Anfrage) und die Map-first-Regel als verbindliche Vorgaben; Lint auf festem Rhythmus ist Pflicht, weil Drift der Querverweise der häufigste gemeldete Fehlermodus ist.

## Kontext und Grenzen
Der Kommentarbereich wächst laufend; Stand dieser Auswertung ist 2026-07-04.
Bei erneutem Abruf der Quelle: Register-Stand aktualisieren, Seite
re-validieren, Version anheben.
