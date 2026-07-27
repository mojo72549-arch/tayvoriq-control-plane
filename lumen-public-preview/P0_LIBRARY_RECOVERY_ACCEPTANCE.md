# Project Lumen 13.1.36 – P0 Bibliotheksschutz

## Ziel

Eine erfolgreich importierte Bibliothek muss App-Schließen, Prozess-Kill, Kaltstart, App-Upgrade und Geräte-Neustart ohne Datenverlust und ohne Absturz überstehen.

## Technische Schutzmaßnahmen

- Zwei vollständige Bibliotheksgenerationen: aktiv und vorherig.
- Neue Daten werden ausschließlich in einem Staging-Verzeichnis geschrieben.
- Playlist, Schnellstart-Katalog, Manifest, Eintragszahl, Dateilängen und SHA-256-Prüfsummen werden vor Aktivierung erstellt.
- Eine Generation wird erst nach vollständigem Schreiben und READY-Marker atomar aktiviert.
- Der vorherige gültige Stand bleibt als Recovery-Pfad erhalten.
- Vorhandene 13.1.25–13.1.35-Daten werden als Legacy-Stand geöffnet und anschließend in das neue Generationsformat migriert.
- Maximal ein Restore-Worker; doppelte Wiederherstellungsversuche werden entprellt.
- `Throwable` und `OutOfMemoryError` werden durch den Restore-Crash-Guard behandelt.
- Bei defektem Schnellstart-Katalog erfolgt ein lokaler Fallback über die verschlüsselte Rohquelle.
- Bei defekter aktiver Generation wird die vorherige gültige Generation geprüft.
- Temporäre oder unvollständige Generationen werden niemals aktiv.

## Diagnosecodes

- `LIBRARY-GENERATION-COMMIT-OK`
- `RESTORE-CATALOG-OK`
- `RESTORE-PREVIOUS-GENERATION-OK`
- `RESTORE-CATALOG-MISSING`
- `RESTORE-CATALOG-CORRUPT`
- `RESTORE-GENERATION-MISMATCH`
- `RESTORE-FALLBACK-OK`
- `RESTORE-RECOVERY-COMMIT-OK`
- `RESTORE-DEBOUNCED`
- `RESTORE-OOM`
- `RESTORE-CRASH-GUARD`
- `RESTORE-LEGACY-MIGRATION-OK`

## Pflichtabnahme auf Samsung SM-G980F

1. 13.1.36 über den vorhandenen Pilot-Build installieren; App-Daten nicht löschen.
2. Bestehende Bibliothek öffnen und Legacy-Migration abwarten.
3. App normal schließen und erneut öffnen.
4. App aus der Übersicht entfernen und erneut öffnen.
5. Direkt nach einem erfolgreichen Import schließen und erneut öffnen.
6. Während eines neuen Imports den Prozess beenden; nach Neustart muss der vorherige Stand erscheinen.
7. Startseite und Live-Bereich mehrfach schnell öffnen; es darf nur ein Restore laufen.
8. Gerät neu starten und Bibliothek prüfen.
9. Systemstatus öffnen und verwendeten Recovery-Code dokumentieren.

## Erwartung

- Kein Crash.
- Keine verschwundene Bibliothek nach Kaltstart.
- Ein neuer unvollständiger Import ersetzt niemals den vorherigen gültigen Stand.
- Der Katalog wird bevorzugt geöffnet; Rohquelle nur als kontrollierter Fallback.
- Ein beschädigter aktiver Stand führt zur vorherigen Generation oder zu einem stabilen Fehlerbild.
- Zugangsdaten, vollständige URLs und Servernamen bleiben aus der Diagnose entfernt.

## Freigabegrenze

CI bestätigt Integration, Android-Kompilierung, Security-Gates und Pilot-Signatur. Das P0-Gate ist erst nach zwei vollständigen realen Persistenz-/Recovery-Runden auf Samsung SM-G980F und einem schwächeren Fire-TV-Gerät geschlossen. Performance-R7.3 bleibt bis dahin nachgeordnet.
