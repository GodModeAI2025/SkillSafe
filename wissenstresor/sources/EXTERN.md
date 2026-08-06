# Register externer Bezugsquellen

Die Allowlist dieses Tresors. Erreichbar ist **ausschliesslich**, was hier
namentlich steht; es gibt keinen Codepfad, der ein Ziel aus einer Anfrage,
einem Dokument oder einer Antwort uebernimmt. Diese Datei liegt im Manifest
und ist damit gegen Veraenderung gepinnt.

Eine aufgefuehrte Bezugsquelle ist deshalb **keine Internetrecherche**: keine
Suche, kein Suchendpunkt, kein Folgen von Links aus Inhalten. Eine
aufgefuehrte Netzquelle wird behandelt wie eine interne Quelle — auch dann,
wenn im Umfeld ausdruecklich keine Internetrecherche erlaubt ist. Jeder Abruf
steht mit URL, Pruefsumme und Zeitpunkt in `log.md`.

Spalten:

* **Art** — `markdown-tree` (gepflegter Markdown-Baum) oder `skillsafe-vault`
  (fremder Tresor; wird als Daten gelesen, sein Script nie ausgefuehrt).
* **Ziel** — festes `https://`-Praefix einer Netzquelle, oder `-` fuer eine
  lokale Quelle. Ein absoluter lokaler Pfad steht hier **nie**: er ist eine
  Eigenschaft des Hosts und braeche die Portabilitaet des Artefakts. Er
  gehoert in die nicht manifestierte Bindung `.vault-extern.json`.
* **Bindungsschluessel** — verbindet Registerzeile und Maschinenbindung.
* **Stand/Version** — bei `skillsafe-vault` zusaetzlich der Scope
  (organisation, fachbereich, projekt, persoenlich) fuer die Rangfolge aus
  `references/mehrere-tresore.md` §8.

| ID | Titel | Art | Ziel | Stand/Version | Bindungsschlüssel | Trust | Rechte |
|---|---|---|---|---|---|---|---|
| X-0001 | Beispielhandbuch des Repositoriums (beispiel-extern/) | markdown-tree | - | 2026-08-06 | beispiel-handbuch | T3 | Apache-2.0, Teil dieses Repositoriums |
| X-0002 | SkillSafe-Repositorium, Rohfassung des Hauptzweigs | markdown-tree | https://raw.githubusercontent.com/GodModeAI2025/SkillSafe/main/ | Hauptzweig, fortlaufend | skillsafe-repo-netz | T3 | Apache-2.0, Volltext erlaubt mit Attribution |
