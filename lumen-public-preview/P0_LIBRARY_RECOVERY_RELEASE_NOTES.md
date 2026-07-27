# Project Lumen 13.1.36 – P0 Bibliotheksschutz

- letzte gültige Bibliothek bleibt bis zur vollständigen Aktivierung einer neuen Generation erhalten
- aktive und vorherige Generation als Recovery-Pfade
- atomare Aktivierung über Staging, Manifest und READY-Marker
- SHA-256-Manifest für Playlist und Schnellstart-Katalog
- bestehende ältere Bibliothek wird lokal migriert
- maximal ein Restore gleichzeitig
- kontrollierter Katalog-, Rohquellen- und Vorgänger-Fallback
- Crash-Guard für Throwable und OutOfMemoryError
- R7.2 Netzwerkdiagnose und R7.1 Responsive UI bleiben enthalten
