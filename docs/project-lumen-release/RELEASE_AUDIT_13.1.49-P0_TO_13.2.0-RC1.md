# Project Lumen – Release-Audit 13.1.49 P0 → 13.2.0 RC1

Stand: 29. Juli 2026  
Bewerteter Ausgangsstand: `13.1.49-p0-no-parental`

## Entscheidung

**Öffentliche Veröffentlichung: NO-GO.**  
**Interne Android-Prüfung: CONDITIONAL GO**, sobald der CI-Lauf dieses Branches grün ist. Das erzeugte AAB ist absichtlich unsigniert und darf nicht in einen Store hochgeladen werden.

## Verifizierte Herkunft

| Nachweis | Wert |
|---|---|
| Repository | `mojo72549-arch/tayvoriq-control-plane` |
| Basis-Branch | `build/project-lumen-v13.1.49-no-parental` |
| Basis-Commit | `d6d161dbfeccd7333122aaf86558b1f1b823cae0` |
| Basis-Build | GitHub Actions Run `30453096886`, erfolgreich |
| Basis-Artefakt | `project-lumen-v13-1-49-no-parental-ca714578480d3c9bc43a1db7a1420eab3c1328b0` |
| Artefakt-ZIP SHA-256 | `59dcf4702d82c26001221ba0d585c3a4a66310ba437dc17fa77f12c61f2e62f6` |
| APK | `Project_Lumen_v13.1.49_P0_No_Parental.apk` |
| APK SHA-256 | `546c23db026d0db392eee70fb025a347dffbd7a0905afe02321f88c62fd6bf25` |
| Paket | `com.projectlumen.pilot.robust` |
| Version | `versionCode 1314900`, `versionName 13.1.49-p0-no-parental` |
| Audit-Branch | `agent/project-lumen-release-hardening` |

Die belegte P0-Basis war ausdrücklich ein Build **ohne aktiven Jugendschutz**. Das widerspricht den Produktanforderungen und wurde im RC korrigiert.

## Umgesetzte Härtungen

- RC-Version auf `13.2.0-rc1-release-hardening` / `1320001` angehoben.
- Elternschutz im Build wieder aktiviert und Einstellungsoberfläche wieder registriert.
- Sechsstellige Eltern-PIN bleibt Keystore-gestützt; Sperre bei Neustart und nach zehn Minuten bleibt aktiv.
- Aktive Wiedergabe wird bei Ablauf/Sperre beendet (Fail-Closed).
- Erwachsenen-Inhalte werden im gesperrten Katalog ausgefiltert; Regressionstest ergänzt.
- Release-Diagnoseansicht aus dem normalen Ablauf entfernt; Freigabe-/Löschfunktionen bleiben erreichbar.
- Bestätigte Funktion zum Löschen aller lokalen App-Daten ergänzt.
- Playlist-/Katalogcache auf AES-256-GCM mit Android Keystore umgestellt; alter Klartextcache wird auf Android verworfen und neu aufgebaut.
- Keine eingebetteten Release-Schlüssel oder Passwörter mehr; Release-Signing ausschließlich über vier externe `LUMEN_RELEASE_*`-Werte.
- Minifizierung und Resource-Shrinking für Release aktiviert.
- `compileSdk`/`targetSdk` auf API 36, AGP auf 8.13.2, Gradle auf 8.13 und Media3 auf 1.10.1 aktualisiert.
- CI prüft Secrets, Unit-Tests, Debug- und Release-Lint, Debug-APK, unsigniertes Release-AAB, Paket-/Versionsdaten und APK-Signaturschema.
- Unsigned-Artefakte tragen explizit `UNSIGNED_DO_NOT_UPLOAD`.

## Release-Blocker

| Priorität | Blocker | Status / Exit-Kriterium |
|---|---|---|
| P0 | Produktionssignatur fehlt; früherer Pilot-Schlüssel und Kennwort waren rekonstruierbar | Neuen, niemals eingecheckten Schlüssel erzeugen/rotieren; Play App Signing und Amazon-/Apple-Signing konfigurieren |
| P0 | Produktions-`applicationId` und Upgrade-Pfad ungeklärt | Juristische Entität/Domain festlegen; Paket-ID und Migration/Neuinstallation entscheiden |
| P0 | Kernversprechen Profile/Favoriten/EPG/Verlauf sind im belegten Quellstand nicht implementiert | Implementieren und mit Unit-, Integrations- und UI-Tests abdecken oder Store-Aussagen entfernen |
| P0 | Keine Instrumentation-/UI-/Prozess-/Neustarttests auf echten Geräten | Gerätematrix vollständig ausführen; alle P0/P1 schließen |
| P0 | Apple-Quellprojekte, Apple-Signing und TestFlight-Builds fehlen | Separaten nativen iOS/iPadOS/tvOS-Track umsetzen und in Xcode archivieren |
| P0 | Datenschutz-, Lizenz-, Marken- und Store-Prüfung nicht freigegeben | Freigaben dokumentieren; öffentlichen Namen erst danach einsetzen |
| P1 | Globaler Klartext-Netzwerkverkehr ist erlaubt | Produktentscheidung und Risikohinweis; nach Möglichkeit HTTPS erzwingen bzw. eng begrenzen |
| P1 | Keine nachgewiesene Speicherknappheit-, ANR-, Langzeit- oder Netzwerkunterbrechungsprüfung | Automatisierte Fault-/Soak-Tests und reale Gerätemessungen bestehen |
| P1 | Fire OS 5/6 liegen unter `minSdk 26`; Vega benötigt einen separaten VPKG-Track | Unterstützte Geräte offen angeben; Fire OS 7/8 testen; Vega separat entwickeln/testen |
| P1 | Store-Grafiken und echte Screenshots fehlen | Aus final signiertem Build auf den Zielgeräten erzeugen und redaktionell prüfen |

## Release-Gates

Ein öffentlicher Release darf erst erfolgen, wenn:

1. RC-CI, Dependency-/Secret-Scan, Unit-, Integrations- und UI-Tests grün sind.
2. 100.000-Einträge-Import, Prozessabbruch, Neustart, Speicherknappheit und 8-Stunden-Soak-Test auf Geräten bestanden sind.
3. Android-TV-/Google-TV-/Fire-TV-D-Pad-Fokusprüfung ohne Sackgassen bestanden ist.
4. Signierte AAB/APK/VPKG/IPA-Artefakte mit Hashes und Store-Zertifikaten vorliegen.
5. Datenschutz, Open-Source-Lizenzen, Markenname, Altersfreigabe und Store-Metadaten freigegeben sind.
6. Interne/geschlossene Tracks keine offenen P0/P1-Fehler mehr enthalten.

## Offene Produktentscheidungen

- Öffentlicher Name und Markenfreigabe; `Elvaniqo` bleibt bis dahin gesperrt.
- Rechtsgültige Entwickler-/Anbieteridentität und Support-Domain.
- Produktions-Paket-ID und Signatur-/Migrationsstrategie.
- Mindestunterstützung für ältere Fire-TV-Geräte.
- Ob HTTP-Quellen weiterhin zulässig bleiben; Nutzer müssen vor Klartext-Risiken gewarnt werden.
- Konkreter Funktionsumfang für Profile, Favoriten, EPG und Verlauf.
