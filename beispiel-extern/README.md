# Beispiel für einen externen Markdown-Baum

Dieser Ordner ist **kein Teil des Tresors**. Er liegt bewusst neben
`wissenstresor/` und dient als greifbare, versionierte externe Bezugsquelle
für die Demo und die Tests: ein gepflegter Markdown-Baum, wie ihn jede
Fachabteilung hat.

Er wird nicht mitpaketiert, steht in keinem Manifest und wird von der Engine
ausschließlich lesend angefasst — und auch das nur, wenn er über
`vault.py extern bind X-0001 <pfad>` maschinenlokal gebunden wurde.

Warum ein Geschwisterordner und nicht ein Unterordner des Tresors: Die
Engine verbietet fail-closed, dass sich eine externe Wurzel und der Tresor
gegenseitig enthalten. Sonst wäre nicht mehr entscheidbar, ob ein Dokument
eigener Bestand oder fremdes Material ist — und genau diese Grenze trägt die
ganze Konstruktion.

Die Inhalte sind erfunden und dienen nur der Demonstration des Rankings. Sie
sind ausdrücklich **keine Rechtsauskunft**. Zwei Dokumente ähneln sich im
Katalogtext absichtlich stark und unterscheiden sich im Bestand deutlich —
daran lässt sich zeigen, warum eine Rankingstufe nicht reicht.
