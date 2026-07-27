# Project Lumen 13.1.37 – P0 ANR / seitenweise Senderlisten

## Anlass

Auf dem Samsung SM-G980F zeigte Android nach dem erfolgreichen Import von 100.000 Inhalten beim Tippen auf „Senderliste öffnen“ den Dialog „App reagiert nicht“.

## Korrektur

- Medienfilterung, Zählung und Seitenermittlung laufen nicht mehr synchron auf dem Android-Hauptthread.
- Die UI zeigt sofort einen leichten Zwischenzustand und übernimmt danach ein unveränderliches Seitenergebnis aus einem Hintergrundworker.
- Live, Filme und Serien verwenden maximal 60 Listeneinträge pro Seite.
- Schnelle Mehrfachnavigation wird entprellt.
- Veraltete Worker-Ergebnisse werden über eine Generationsnummer verworfen.
- Diagnoseoverlay wird vor der Navigation sicher ausgeblendet.
- Android-App-Name und sichtbare Version werden auf 13.1.37 aktualisiert.
- Crash-sichere Bibliotheksgenerationen aus 13.1.36 bleiben erhalten.

## Diagnosecodes

- `UI-LIST-DEBOUNCED`
- `UI-LIST-PAGE-READY`
- `UI-LIST-RENDER-OK`

`UI-LIST-PAGE-READY` enthält geprüfte Einträge, Treffer, Seitengröße und Workerzeit. `UI-LIST-RENDER-OK` enthält ausschließlich die tatsächlich gerenderte Seitengröße und die Main-Thread-Zeit.

## Pflichtabnahme Samsung SM-G980F

1. APK direkt über den bestehenden Pilot installieren; App-Daten nicht löschen.
2. Prüfen, dass Android den Namen „Project Lumen 13.1.37“ anzeigt.
3. 100.000er-Bibliothek öffnen.
4. Im Fertig-Dialog „Senderliste öffnen“ tippen.
5. Erwartung: Zwischenzustand erscheint sofort; danach erste Seite mit höchstens 60 Einträgen.
6. 20-mal zwischen Start, Live, Filme und Serien wechseln.
7. Schnell mehrfach auf Live bzw. „Senderliste öffnen“ tippen.
8. Sprache, Suche im Medienbereich sowie Zurück/Weiter testen.
9. App schließen, aus Recents entfernen und erneut öffnen.
10. Systemstatus teilen und `UI-LIST-PAGE-READY` sowie `UI-LIST-RENDER-OK` prüfen.

## Erwartung

- Kein Android-ANR-Dialog.
- Kein schwarzer oder dauerhaft blockierter Bildschirm.
- Kein Verlust der Bibliothek.
- Maximal 60 Einträge werden je Seite an den Adapter übergeben.
- Veraltete Filter-/Seitenanfragen ersetzen keine neuere Auswahl.
- Senderwiedergabe bleibt erreichbar.

## Grenze

CI beweist Integration, Kompilierung, Sicherheitsprüfungen und Signatur. Das reale P0-Gate bleibt offen, bis zwei vollständige Samsung-Runden und eine Runde auf einem schwächeren Fire-TV-Gerät ohne ANR bestanden sind.
