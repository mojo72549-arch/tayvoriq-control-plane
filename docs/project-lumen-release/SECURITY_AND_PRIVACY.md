# Security- und Datenschutzbericht

Stand: 29. Juli 2026  
Geltungsbereich: Android-RC auf Basis 13.1.49 P0

## Datenfluss

Project Lumen liefert keine Medien oder Quellen mit. Die App verbindet sich direkt vom Endgerät zu den vom Nutzer angegebenen Quellen. Es gibt im geprüften Quellstand keine zentrale Project-Lumen-Speicherung von Playlists, URLs, Zugangsdaten oder Wiedergabedaten und keine eingebaute Analyse-/Werbe-SDK-Abhängigkeit.

Lokal verarbeitet werden können:

- vom Nutzer angegebene Playlist-Adresse und Playlist-Inhalte,
- Sender-/Medientitel, Gruppen, Logos und Stream-Adressen,
- Such- und Filterzustand,
- Elternschutzstatus und PIN-Prüfmaterial,
- technische Debugdaten in Debug-Builds.

## Umgesetzte Kontrollen

| Kontrolle | RC-Status |
|---|---:|
| `allowBackup=false` | umgesetzt |
| App-interne Activities nicht exportiert | umgesetzt |
| Eltern-PIN genau sechs Ziffern | umgesetzt |
| PIN-Prüfung über Android Keystore/HMAC | umgesetzt |
| Sperre nach Neustart | umgesetzt |
| Sperre nach zehn Minuten | umgesetzt |
| Wiedergabestopp bei Sperre/Ablauf | umgesetzt, Geräteprüfung ausstehend |
| Erwachsenenbereiche bei Sperre filtern | umgesetzt, automatischer Test ergänzt |
| Katalogcache verschlüsselt | AES-256-GCM, Android Keystore |
| Klartext-Altcache | wird auf Android verworfen und aus verschlüsselter Quelle neu aufgebaut |
| Release-Diagnose-/Loganzeige | deaktiviert |
| Vollständiges lokales Löschen | Nutzerbestätigung + Android-Appdaten-Löschung |
| Produktionsschlüssel im Repository | im RC entfernt; CI-Gate ergänzt |

## Wesentliche Restrisiken

### Kritisch

1. **Kompromittierte Pilot-Signaturhistorie.** Im früheren Quell-/Workflowstand waren Schlüsselmaterial und Kennwort rekonstruierbar. Dieser Schlüssel darf nicht als Produktions- oder Upload-Schlüssel verwendet werden. Rotation ist zwingend.
2. **Produktionsidentität ungeklärt.** Paket-ID, Entwickleridentität, Datenschutzverantwortlicher und Support-Domain fehlen.
3. **Unvollständiger Testnachweis.** Kein mobiler/TV-Instrumentationstest, kein Penetrationstest und kein verifizierter Logcat-/Crashdump-Datenschutztest.

### Hoch

1. **Klartext-HTTP global erlaubt.** Viele nutzereigene IPTV-Quellen verwenden HTTP; dadurch können Adressen, Tokens und Medienverkehr im Netz sichtbar sein. Vor Release entweder technisch einschränken oder mit klarer Warnung und dokumentierter Risikofreigabe behandeln.
2. **Quellen können Geheimnisse in URLs enthalten.** UI, Fehlertexte, Supportexporte und Crashberichte müssen diese Werte immer redigieren. Ein externer Crash-/Analytics-Dienst darf erst nach Datenschutz- und Redaktionsprüfung integriert werden.
3. **Historische Git-Daten.** Das Entfernen aus dem aktuellen Baum löscht Geheimnisse nicht aus der Historie. Rotation hat Vorrang; bei Bedarf Historienbereinigung separat und koordiniert durchführen.

### Mittel

- Dependency-/CVE- und SBOM-Nachweis fehlt.
- Verschlüsselungs- und Migrationspfad muss auf API 26/28/30/36 inklusive beschädigtem Cache getestet werden.
- Löschung über Android-Appdaten ist vollständig, beendet aber den Prozess; UX und TV-Fokus müssen auf Geräten geprüft werden.

## Datenschutzentwurf – Kernaussagen

Vor Veröffentlichung juristisch prüfen und mit Anbieterangaben, Kontakt, Rechtsgrundlagen, Aufbewahrungsfristen und Länderbezug ergänzen:

> Project Lumen ist ein lokaler, inhaltsneutraler Mediaplayer. Die App enthält keine Sender, Filme, Serien oder Playlists. Medienquellen werden ausschließlich vom Nutzer hinzugefügt und direkt auf dessen Gerät verarbeitet. Project Lumen betreibt keinen zentralen Playlist-, Zugangsdaten- oder Medienproxy-Dienst. Lokale App-Daten können in der App vollständig gelöscht werden. Netzwerkbetreiber und die vom Nutzer gewählten Medienanbieter können technisch erforderliche Verbindungsdaten erhalten. Bei unverschlüsselten HTTP-Quellen ist der Übertragungsweg nicht vertraulich.

Nicht behaupten, dass „keine Daten verarbeitet“ werden. Lokale Verarbeitung und direkte Verbindungen zu Drittquellen sind Datenverarbeitung und müssen transparent beschrieben werden.

## Freigabegates

- Neuer Produktions-/Upload-Schlüssel in Secret Store/HSM, niemals im Repository.
- Vollständiger Secret-Scan von aktuellem Baum und Historie; alle gefundenen Werte widerrufen.
- SBOM und Open-Source-Lizenzbericht erzeugen und juristisch prüfen.
- Netzwerk-Security-Konfiguration und HTTP-Produktentscheidung freigeben.
- Logcat, Fehlerdialoge, Crashdump und Supportablauf mit geheimnishaltigen Test-URLs prüfen.
- Datenschutzangaben in Google Play Data Safety, Amazon Appstore und Apple App Privacy konsistent ausfüllen.
- Datenlöschung, Elternschutz und Ablauf aktiver Wiedergabe auf Geräten nachweisen.
