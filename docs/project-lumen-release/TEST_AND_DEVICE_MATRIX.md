# Testprotokoll und Gerätematrix

Stand: 29. Juli 2026  
Legende: **PASS**, **FAIL**, **PENDING**, **BLOCKED**, **N/A**

## Automatisierte Prüfungen

| Prüfung | Basis 13.1.49 P0 | RC 13.2.0 | Evidenz / Bemerkung |
|---|---:|---:|---|
| JVM-Unit-Tests | PASS (30/30) | PASS (32/32) | Run `30462893915`; 0 Fehler, 0 übersprungen |
| Parser mit 100.000 M3U-Einträgen | PASS (Host-JVM) | PASS (Host-JVM) | Run `30462893915`; kein Geräte-/Speicherlastnachweis |
| Elternschutz-Release-Invariante | N/A (deaktiviert) | PASS | `ReleaseParentalPolicyTest` |
| Filterung gesperrter Erwachsenen-Kataloge | N/A | PASS | `ReleaseParentalPolicyTest` |
| Debug-Lint | PASS | PASS | Run `30462893915` |
| Release-Lint | nicht belegt | PASS | Run `30462893915`, `abortOnError` |
| Debug-APK-Build | PASS | PASS | SHA-256 `3528738ce622631c19644f1500bfb09939926c594b1f4726f07bbf177e2f1f8a` |
| Release-AAB-Build | nicht vorhanden | PASS (unsigniert) | SHA-256 `6d89d853b1a2f7432d8a1fef1010ae0bc085d38e0cbad3f760ab3e9e153be8ed`; **kein Store-Artefakt** |
| Secret-Scan aktueller Baum | FAIL (Pilot-Kennwort/Schlüsselweg) | PASS | Run `30462893915`; Historienrotation bleibt P0 |
| Abhängigkeits-/CVE-Scan | nicht belegt | BLOCKED | Kein SBOM/OSV/Dependabot-Nachweis |
| Instrumentation-/UI-Tests | nicht vorhanden | BLOCKED | Testprojekt und Emulator-/Gerätefarm fehlen |
| Netzwerk-Fault-Injection | nicht vorhanden | BLOCKED | Zeitüberschreitung, DNS, 404/500, Abbruch/Wiederanlauf |
| Prozess-/Geräte-Neustart | nicht vorhanden | BLOCKED | Reale Geräte bzw. Emulatoren erforderlich |
| 8-Stunden-Soak-/ANR-Test | nicht vorhanden | BLOCKED | Reale Geräte/Play Pre-launch/Amazon LAT erforderlich |
| Speicherknappheit / nahezu voller Speicher | nicht vorhanden | BLOCKED | Reale Geräte erforderlich |
| Upgrade/Migration von Altversionen | nicht vorhanden | BLOCKED | Signatur-/Paketstrategie zuerst festlegen |

## RC-Buildnachweis

| Feld | Wert |
|---|---|
| GitHub Actions | Run `30462893915` – PASS |
| Geprüfter Head-Commit | `4d5e48314ab11e3ac6a7b38bb496d9b419669bab` |
| Workflow-Merge-SHA | `0af121d09756540f0919d0dc7d13070cffeb7c31` |
| Artefakt-ID | `8728452999` |
| Artefakt-ZIP SHA-256 | `245c799aa54ca56e7a78e28d17624f4aacc10522232dabe4035998a455c3cd22` |
| Interne Debug-APK | `3528738ce622631c19644f1500bfb09939926c594b1f4726f07bbf177e2f1f8a` |
| Unsigniertes AAB | `6d89d853b1a2f7432d8a1fef1010ae0bc085d38e0cbad3f760ab3e9e153be8ed` |
| Buildzeit | 2 min 28 s; 98 Tasks |
| Signatur | Debug-APK v2 verifiziert; AAB absichtlich unsigniert |

## Android-/Fire-Gerätematrix

| Ziel | Mindestfall | Status | Abnahmekriterien |
|---|---|---:|---|
| Android Smartphone | API 26, API 30, API 36; klein/mittel/groß | BLOCKED | Touch, Rotation, Import, Suche, Player, Hintergrund/Vordergrund |
| Android Tablet | API 28, API 34/36; 7–13 Zoll | BLOCKED | Mehrspaltenlayout, Quer-/Hochformat, keine abgeschnittenen Texte |
| Android TV | API 26, API 30, API 34/36 | BLOCKED | D-Pad, Back, Fokus, Launcher-Banner, HLS/TS |
| Google TV | Referenzgerät aktuelle Generation | BLOCKED | Fokus, Resume, Netzwerkabbruch, Store-Pre-launch |
| Fire TV Stick Lite / 3. Gen. | Fire OS 7 / API 28 | BLOCKED | Amazon LAT, D-Pad, Back, Decoder-/Speicherlast |
| Fire TV Stick 4K Max 2. Gen. | Fire OS 8 / API 30 | BLOCKED | 4K-UI, HLS/TS, Fault-/Soak-Test |
| Fire TV Cube 3. Gen. | Fire OS 7 / API 28 | BLOCKED | D-Pad, Audio/Video, Resume |
| Fire TV Stick 2. Gen. | Fire OS 5 / API 22 | N/A | Unter `minSdk 26`; nicht kompatibel |
| Fire TV Fire OS 6 | API 25 | N/A | Unter `minSdk 26`; nicht kompatibel |
| Fire TV Vega | Fire TV Stick 4K Select / Vega | BLOCKED | Separater VPKG-Track und reales Vega-Gerät erforderlich |

## Apple-Gerätematrix

| Ziel | Status | Abnahmekriterien |
|---|---:|---|
| iPhone – klein/Standard/Max | BLOCKED | SwiftUI-Touch, Dynamic Type, Rotation, AVPlayer/HLS, lokale Daten |
| iPad – kompakt/Standard/Pro | BLOCKED | Split View, Querformat, Tastatur/Fokus, große Bibliothek |
| Apple TV HD / 4K | BLOCKED | tvOS-Fokus, Siri Remote, Menu/Back, Top Shelf sofern genutzt |
| TestFlight intern/extern | BLOCKED | Apple-Projekt, Bundle-IDs, Signing, App Store Connect fehlen |

## Verbindliche manuelle Tests

Jeder Fall ist mit Geräte-/OS-Version, Build-Hash, Startzeit, Ergebnis, Screenshot/Video und Ticketnummer zu protokollieren:

1. Erstimport gültiger und beschädigter M3U/M3U8-Dateien (1, 1.000, 10.000, 100.000 Einträge).
2. Neustart, Force-Stop, Prozess-Kill und Geräte-Neustart während/nach Import.
3. Offline, langsame Verbindung, DNS-Fehler, Timeout, HTTP 404/500, Stream-Abbruch und Wiederverbindung.
4. HLS live/VOD und MPEG-TS mit erreichbaren, rechtmäßig bereitgestellten Teststreams.
5. Eltern-PIN: Erstkonfiguration, Fehlversuche, Sperre, Neustart, zehn Minuten Ablauf, laufende Wiedergabe.
6. Suche/Kategorien mit gesperrten Erwachsenen-Inhalten: keine Titel, Poster, Vorschläge, Historie oder Diagnosedaten.
7. D-Pad-Durchlauf jeder Oberfläche; sichtbarer Fokus, Back-Verhalten, kein Fokusverlust.
8. Wenig Speicher, große Bilder, Speicherbereinigung und Löschung aller App-Daten.
9. Upgrade von jeder unterstützten Altversion mit unveränderten und beschädigten lokalen Daten.
10. Mindestens acht Stunden Wiedergabe/Navigation mit ANR-, Crash-, Speicher- und Temperaturbeobachtung.

## Abschlussregel

Ein **PASS** darf nur gesetzt werden, wenn reproduzierbare Evidenz vorliegt. Fehlende Geräte oder Accounts sind kein PASS, sondern **BLOCKED**. Öffentliche Veröffentlichung erfordert null offene P0/P1-Befunde.
