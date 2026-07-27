# Project Lumen 13.1.38 – Bibliothek direkt öffnen

## Produktverhalten

Eine vorhandene gültige Bibliothek ist der normale Startzustand. Diagnose, Quellenverwaltung und Einstellungen bleiben erreichbar, ersetzen aber nicht die Medienbibliothek.

## Enthalten

- automatische Wiederherstellung der letzten gültigen lokalen Bibliotheksgeneration
- automatischer Wechsel in die Medienliste nach erfolgreichem Restore
- Standardziel `Live-TV`
- Wiederherstellung von Medienart, Sprache/Land, Filter und Seite
- Start-, Quellen-, Einstellungs- und Diagnoseseiten werden nicht als nächster App-Start gespeichert
- neutraler Wiederherstellungszustand ohne primären Systemstatus-Button
- nach erfolgreichem Erstimport automatische Anzeige der bereits nutzbaren Liste
- Erfolgsmeldungen als kurze, nicht blockierende Hinweise
- Diagnose bleibt unter Systemstatus vollständig verfügbar
- P0-Persistenzschutz 13.1.36 und P0-ANR-Schutz 13.1.37 bleiben erhalten

## Samsung-Abnahme

1. 13.1.38 direkt über den vorhandenen Pilot-Build installieren; App-Daten nicht löschen.
2. 100.000er Bibliothek öffnen.
3. Live-TV öffnen, App schließen und aus Recents entfernen.
4. App neu öffnen.
5. Erwartung: lokaler Restore und danach automatische Live-Liste; kein manuelles Öffnen von Systemstatus.
6. Filme öffnen, App schließen und neu öffnen.
7. Erwartung: Film-Liste wird automatisch wieder geöffnet.
8. Sprache Türkisch oder Deutsch wählen, schließen und neu öffnen.
9. Erwartung: Auswahl wird lokal wiederhergestellt.
10. Einstellungen öffnen, App schließen und neu öffnen.
11. Erwartung: Bibliothek wird geöffnet, nicht Einstellungen.
12. Gerät neu starten und erneut prüfen.
13. Senderliste mehrfach schnell öffnen und zwischen Live, Filme und Serien wechseln.

## Erwartung

- Bibliothek bleibt vorhanden.
- Kein erneuter Netzwerkdownload beim normalen Start.
- Kein ANR.
- Kein blockierendes Erfolgs- oder Diagnosefenster.
- Systemstatus wird nur bei echtem Fehler oder Timeout primär.

## Grenze

Dieser Build verbessert den Wiederzugriff und Startfluss. Die separate R7.3-Pipeline für eine erste nutzbare Remote-Bibliothek innerhalb des 30-Sekunden-Zielkorridors bleibt ein eigener Performance-Umbau.
