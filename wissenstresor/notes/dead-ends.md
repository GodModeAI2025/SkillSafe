# Dead-End-Log — verworfene Ansaetze

Zweck: Entscheidungen gegen etwas festhalten, damit spaetere Sessions sie
nicht erneut pruefen. Format: `## [JJJJ-MM-TT] Ansatz — Grund der Verwerfung`.

## [2026-07-04] Embeddings/Vektorindex im Tresor — verworfen
Nachbarschaftssuche im Einbettungsraum ist eine Blackbox ("Warum diese
Quelle?" nicht beantwortbar), erzeugt Infrastruktur (Store, Modell,
Re-Indexierung, Tuning) und schickt je nach Setup Inhalte an externe
Schnittstellen. Ersatz: ROUTER (kuratiert) + INDEX (generiert) +
erschoepfende Volltextsuche (Plan B). Details: KONZEPT.md, Frage 1.

## [2026-07-04] Claims in separaten Ledger-Dateien — verworfen
Getrennte Ledger (wie im OKSV-Vollausbau) erhoehen im puren Skill nur die
Zahl der Dateien pro Lesevorgang. Claims leben in der Seite, die sie stuetzen;
die tresorweite Eindeutigkeit der IDs prueft der Validator.

## [2026-07-04] POLE+O-Vokabular als Basis-Registry — verworfen
POLE+O (Person, Object, Location, Event, Organization) zielt auf
Entitaeten-Extraktion fuer persoenliche Assistenten und Ermittlungsarbeit.
Der Tresor ist dokument-/konzeptzentriert; uebernommen wird das PRINZIP
(kleine fixe Basis, additiv erweitern, Clash-getrieben), nicht das Vokabular.
Quelle der Abwaegung: S-0003.

## [2026-07-04] Facts als Embedding-Triplets — verworfen
Iusztins Fact-Primitiv (Subjekt/Praedikat/Objekt + Vektor, nur semantisch
auffindbar) uebernommen als faktensammlung-Typ MIT Claim-Grammatik statt
Triplet-Zwang und Volltextsuche statt Embedding (Determinismus). Bi-temporale
Gueltigkeit (valid_from/valid_until) nicht uebernommen — stand/status/
Supersession decken den Bedarf; bei Bedarf Ausbaupfad.
