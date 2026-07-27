# Project Lumen 13.1.35 – R7.2 Netzwerk & Diagnose

## Anlass

Die Diagnose `MS2UN7V9` zeigte zunächst einen Verbindungs-/Antwort-Timeout und danach zwei sofortige DNS-Fehler (`UnknownHostException`, `EAI_NODATA`) im Mobilfunknetz. Es wurden 0 Bytes empfangen; Authentifizierung, Playlist-Parser und Speicherung wurden nicht erreicht. Der bisherige Bibliotheksstand blieb korrekt erhalten.

Zusätzlich zeigte der Bericht drei App-seitige Qualitätsmängel:

- DNS-Fehler wurden nur als allgemeines `IMPORT-CONNECT` gemeldet.
- Ein dritter langer Verbindungsversuch wurde trotz wiederholter fehlgeschlagener Namensauflösung gestartet.
- Der Servername erschien in Ursache und Stacktrace, obwohl die Diagnose vollständige Adressen und Servernamen ausblenden soll.
- Die Diagnose meldete weiterhin statisch `App=13.1.25`, unabhängig von der tatsächlich installierten Version.
- Einige Ziele kombinierten vollständigen Nachrichtentext und Dateianhang, wodurch Fragmente doppelt oder unübersichtlich erscheinen konnten.

## Technische Korrekturen

- `IMPORT-DNS` für `UnknownHostException` und `EAI_NODATA`.
- höchstens ein automatischer DNS-Wiederholungsversuch; danach klarer Abbruch statt drittem 90-Sekunden-Versuch.
- `IMPORT-OFFLINE`, wenn Android keine nutzbare Internetfähigkeit erkennt.
- keine Rohmeldung des Netzwerk-Stacks in der normalen Nutzeroberfläche.
- der bekannte Servername wird auch aus Ursachen und Stacktraces entfernt.
- kompakte, begrenzte Ursache-/Stack-Ausgabe statt wiederholter vollständiger Trace-Blöcke.
- tatsächliche Paketversion aus Android PackageManager statt fest codierter Versionsnummer.
- Diagnose enthält zusätzlich Internet-/Validierungsstatus des aktiven Netzes.
- bei modernen Android-Versionen wird die vollständige bereinigte Diagnose nur einmal als Datei angehängt; der Nachrichtentext bleibt kurz.
- doppelte Port-Angabe in der Sitzungszusammenfassung entfernt.
- vorhandene Bibliothek und verschlüsselte Daten bleiben bei allen Netzwerkfehlern unverändert.

## Geräteabnahme Samsung SM-G980F

1. Version 13.1.35 über die bisherige Pilotversion installieren.
2. Mobilfunk aktivieren, WLAN deaktivieren.
3. bekannte eigene Playlist-Quelle starten.
4. Bei erfolgreicher DNS-Auflösung muss der Import normal fortfahren.
5. Bei fehlender DNS-Auflösung muss `IMPORT-DNS` erscheinen.
6. Nach spätestens zwei DNS-Fehlern muss der Import enden; kein dritter 90-Sekunden-Versuch.
7. Die zuvor gespeicherte Bibliothek muss weiterhin geöffnet werden können.
8. Diagnose exportieren und prüfen:
   - App-Version beginnt mit `13.1.35`.
   - Servername, Zugangsdaten und vollständige URL erscheinen nirgends.
   - Host wird nur als Host-ID ausgewiesen.
   - keine duplizierten unformatierten Stack-Fragmente am Dateiende.
9. Den gleichen Test über WLAN wiederholen, um Netz-/DNS-Unterschiede sichtbar zu machen.

## Produktgrenze

R7.2 nutzt keinen Proxy, kein VPN, keinen fremden DNS-Dienst, keinen TLS-Bypass und verändert weder Serveradresse noch Zugangsdaten. Die App klassifiziert und erklärt den Zustand des aktuellen Netzes; sie kann eine extern fehlende DNS-Zuordnung oder einen nicht antwortenden Anbieter-Server nicht selbst reparieren.
