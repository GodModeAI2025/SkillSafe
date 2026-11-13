---
type: konzept
title: Mietminderung bei Schimmelbefall
domain: demo-extern
status: aktiv
confidence: mittel
version: 1.0.1
stand: 2026-08-06
sources: []
externe_quellen: [X-0001]
tags: [mietminderung, schimmel, mangel, anzeigepflicht, externe-quelle]
---

# Mietminderung bei Schimmelbefall

## Kurzfassung
Nach dem Beispielhandbuch `X-0001` ist erheblicher Schimmelbefall in
Wohnräumen ein Mangel, der zur Mietminderung berechtigt, und dieser Mangel
ist dem Vermieter unverzüglich anzuzeigen.

## Claims
- **C-0401** [X-0001 | A-0004 | Wortlaut] Erheblicher Schimmelbefall in Wohnräumen ist nach dem Beispielhandbuch ein Mangel, der zur Mietminderung berechtigt.
- **C-0402** [X-0001 | A-0007 | Wortlaut] Der Mangel ist dem Vermieter nach dem Beispielhandbuch unverzüglich anzuzeigen.

## Kontext und Grenzen
Geltungsbereich dieser Seite ist die Demonstration satzweiser externer Belege,
nicht das Mietrecht. Die Seite belegt sich vollständig aus der externen
Bezugsquelle `X-0001`, die neben dem Tresor liegt und nicht in ihn kopiert
wurde. Jeder Claim zeigt über einen Satzanker auf genau einen Satz dort,
nachrechenbar über dessen SHA-256. Der Tresor friert damit nur den zitierten
Satz ein, nicht das Handbuch, und bleibt trotzdem offline antwortfähig.
Inhaltlich ist die Seite bewusst schmal: ein Bauteil-Beispiel. Die Quelle
`X-0001` ist ein erfundenes Beispielhandbuch mit Trust `T3`; ihre Aussagen
sind keine Rechtsauskunft und werden hier nur als Beleg-Mechanik geführt.

Ändert sich ein zitierter Satz in der externen Quelle, meldet `doctor` das als
Anker-Drift — gelb, nicht rot. Der Tresor kontrolliert die fremde Quelle
nicht, also blockiert ihre Änderung keinen Release; sie erzeugt
Kuratierungsarbeit.

Verwandt, aber getrennt: Die Domäne `demo-okf` dokumentiert die Herkunft des
Tresors selbst. Inhalte werden zwischen beiden Domänen nie verschmolzen.
