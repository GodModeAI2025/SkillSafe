---
type: konzept
title: Ontologie-Strategie — kleine fixe Basis, Clash-getriebene Erweiterung
domain: demo-okf
status: aktiv
confidence: mittel
version: 1.0.0
stand: 2026-07-04
sources: [S-0003]
tags: [ontologie, typen, pole+o, facts, knowledge-graph, registry]
relations:
  - praezisiert -> demo-okf/llm-wiki-muster.md
---

# Ontologie-Strategie — kleine fixe Basis, Clash-getriebene Erweiterung

## Kurzfassung
Die Ontologie — was wird Knoten, was wird Kante — ist der härteste Teil
jeder Graph- oder Memory-Schicht; der Versuch, sie vorab vollständig zu
entwerfen, friert Projekte ein ("Overkill Trap"), und auch rein
dateibasierte Wissensspeicher stehen vor derselben Modellierungsfrage.
Tragfähig ist der umgekehrte Weg: eine kleine, fixe, generische Typ-Basis,
die nur dann additiv erweitert wird, wenn echte Daten nachweislich mit ihr
kollidieren — reale Domänen-Ontologien landen so bei nur 10–12 Typen.
Für Aussagen, die (noch) in keinen Typ passen, dient ein bewusst generisches
Fallback-Primitiv; reifes Wissen wandert später in typisierte Seiten.
Konfidenz "mittel": Einzelquelle der Trust-Stufe T3.

## Claims
- **C-0201** [S-0003 | Einleitung und "The Overkill Trap" | Wortlaut] Die Ontologie (welche Knoten, welche Kanten) ist der härteste Teil einer Graph-/Memory-Schicht; der Versuch, sie vorab perfekt zu entwerfen, friert Projekte ein — auch dateibasierte "virtuelle Wissensgraphen" stehen vor derselben Frage, welche Primitive und Entitäten überhaupt extrahiert werden.
- **C-0202** [S-0003 | "The POLE+O Data Model" | Wortlaut] Empfohlen wird eine kleine, fixe, generische Basis (POLE+O: Person, Object, Location, Event, Organization), die per Subtypen additiv erweitert wird; der zitierte Neo4j-Domänenkatalog mit 22 fertigen Ontologien landet durchgängig bei 10–12 Entitätstypen (5 gemeinsame Basis- plus 5–7 Domänen-Nomen).
- **C-0203** [S-0003 | Explorations-Loop und Beispiele | Wortlaut] Subtypen werden nicht theoretisiert, sondern entdeckt: generisch starten, Extraktion über echte Daten laufen lassen, Fehlklassifikationen (Clashes) inspizieren, pro Clash genau einen Subtyp ergänzen oder umbenennen, wiederholen — ein Clash ist ein Signal für eine gezielte Ergänzung, nicht für ein Schema-Redesign.
- **C-0204** [S-0003 | "Facts: The Trick You Haven't Thought Of" | Wortlaut] "Facts" sind das generische Fallback-Primitiv für alles, was in keinen Typ passt: atomare, einzeln gespeicherte Aussagen ohne Kanten, nur über Suche auffindbar; sie verhindern die Schema-Explosion, und mit reifendem Graph migrieren Aussagen von Facts zu typisierten Entitäten und Kanten.
- **C-0205** [S-0003 | Gesamtdokument | Auslegung] Für den Wissenstresor bestätigt das das Type-Onboarding-Design (kleine Registry als fixe Basis, fail-closed, Erweiterung nur bei nachgewiesenem Clash) und begründet den Typ faktensammlung als Fallback: atomare Claims ohne eigene Seite landen in fakten.md der Domäne und werden bei Verdichtung zu Konzeptseiten befördert.

## Kontext und Grenzen
Der Artikel argumentiert im Kontext von Neo4j/GraphRAG mit Embeddings;
übernommen wird das Ontologie-Vorgehen, nicht die Speichertechnik
(siehe notes/dead-ends.md). Preferences als eigenes Primitiv sind für einen
evidenzgebundenen Fach-Tresor nicht Kern — der Onboarding-Mechanismus kann
einen solchen Typ jederzeit ergänzen, wenn ein Bestand ihn braucht.
