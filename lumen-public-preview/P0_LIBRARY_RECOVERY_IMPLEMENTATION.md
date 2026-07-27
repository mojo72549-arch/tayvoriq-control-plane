# Project Lumen 13.1.36 P0 – Implementierungsgrenze

Dieser Build ersetzt die bisherige einzelne aktive Bibliotheksdatei durch einen crash-sicheren Zwei-Generationen-Speicher. Der letzte gültige Stand bleibt erhalten, bis eine neue Generation vollständig geschrieben, synchronisiert, manifestiert und atomar aktiviert wurde.

Enthalten sind Legacy-Migration, aktiver/ vorheriger Recovery-Pfad, Rohquellen-Fallback, Restore-Entprellung, OOM-/Throwable-Crash-Guard und bereinigte Diagnosecodes. Die UI-, Profil-, EPG-, Such-, Favoriten- und Netzwerkfunktionen aus R4 bis R7.2 bleiben erhalten.

Nicht durch CI beweisbar sind Prozess-Kill, echtes Android-Low-Memory-Verhalten, Dateisystemfehler, Geräte-Neustart und Fire-TV-Speicherdruck. Diese Punkte bleiben Bestandteil der realen P0-Abnahme.
