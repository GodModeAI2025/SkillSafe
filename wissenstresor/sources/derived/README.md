# Abgeleitete Medienrepräsentationen

Hier liegen ausschließlich validierte Fundstellen-Dateien für registrierte
PNG-, JPEG-, GIF-, WebP-, TIFF- oder PDF-Quellen. Der Dateiname lautet
`S-nnnn__media.json`; das Schema ist in `schema/profil.md` definiert.

Eine Repräsentation ist keine zweite Wahrheitsquelle. OCR, Bildbeschreibung
und erkannte Diagrammteile bleiben Quelldaten und dürfen niemals direkt eine
Antwort speisen. Erst ein kuratierter Claim unter `knowledge/`, der genau
eine freigegebene `R-nnnn`-Region nennt, wird zu Evidenz.

Verdächtige eingebettete Instruktionen werden mit
`"suspicious_instruction": true` markiert. Solche Regionen können
manifestiert und untersucht, aber nicht von einem Claim referenziert werden.
