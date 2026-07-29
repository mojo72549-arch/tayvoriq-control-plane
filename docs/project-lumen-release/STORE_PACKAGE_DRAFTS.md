# Store-Paket – Entwurf und Readiness

Stand: 29. Juli 2026  
Öffentlicher Produktname: **NICHT FREIGEGEBEN**  
Interner Name: **Project Lumen**  
`Elvaniqo` darf vor Marken-, Domain- und Store-Prüfung nicht öffentlich verwendet werden.

## Metadatenentwurf

**Store-Titel:** `[ÖFFENTLICHER NAME NACH MARKENFREIGABE]`

**Kurzbeschreibung:**  
`Lokaler Mediaplayer für eigene und rechtmäßig bezogene M3U-/M3U8-Quellen.`

**Ausführliche Beschreibung:**

> [ÖFFENTLICHER NAME] ist ein inhaltsneutraler Mediaplayer für eigene und rechtmäßig bezogene Medienquellen. Importieren Sie M3U- und M3U8-Playlists auf Ihrem Gerät, organisieren Sie große Bibliotheken nach Medienart, Sprache und Land und spielen Sie unterstützte HLS- und MPEG-TS-Streams ab.
>
> Die App enthält keine Sender, Filme, Serien, Playlists oder Abonnements. Sie bietet keine Quellenvermittlung, kein Restreaming, kein Proxying, kein Transcoding und keine Umgehung von DRM, Geoblocking oder Zugriffsschutz. Nutzer sind für die Rechtmäßigkeit ihrer Quellen und Inhalte verantwortlich.
>
> Quellen und Katalogdaten werden lokal verarbeitet. Ein Elternschutz mit sechsstelliger PIN kann sensible Bereiche sperren. Lokale App-Daten lassen sich vollständig löschen.

Nur tatsächlich implementierte und bestandene Funktionen dürfen in die finale Beschreibung übernommen werden. Profile, Favoriten, EPG und Verlauf dürfen vor ihrer Implementierung nicht beworben werden.

## Release Notes – RC1

- Jugendschutz im Release wieder aktiviert.
- Automatische Sperre und Abbruch aktiver Wiedergabe gehärtet.
- Lokalen Katalogcache verschlüsselt.
- Vollständige Löschung lokaler App-Daten ergänzt.
- Diagnosefunktionen aus Release-Navigation entfernt.
- Android-Toolchain und Media3 aktualisiert.
- Release-Signing von eingebetteten Testschlüsseln getrennt.
- Release-CI für Tests, Lint, Secret-Scan und Artefaktnachweis ergänzt.

## Berechtigungen

| Berechtigung / Fähigkeit | Begründung |
|---|---|
| `INTERNET` | Abruf der ausschließlich vom Nutzer hinzugefügten Playlist- und Medienquellen |
| `ACCESS_NETWORK_STATE` | Erkennen von Offline-/Netzwerkwechselzuständen und verständliche Fehlerbehandlung |
| Touchscreen optional | Gemeinsames Paket für Touch-Geräte und TV |
| Leanback optional | Launcher-Unterstützung für Android TV/Google TV |

Keine Speicher-, Standort-, Kontakt-, Kamera-, Mikrofon- oder Werbe-ID-Berechtigung ist im geprüften Manifest deklariert.

## Benötigte Bild- und Textartefakte

Echte Screenshots dürfen erst aus dem finalen, signierten Build auf den Zielgeräten erzeugt werden.

- Einheitliches, rechtlich geprüftes App-Icon.
- Google Play Smartphone-/Tablet-Screenshots und Feature Graphic.
- Android-TV-/Google-TV-Screenshots und TV-Banner.
- Amazon Fire-TV-Screenshots und 1280×720-App-Icon/Background-Anforderungen nach aktueller Konsole.
- Apple App Store Screenshots je iPhone-/iPad-/Apple-TV-Größe.
- Supportseite, Datenschutzerklärung, Lizenzhinweise, Testanleitung.
- Altersfreigabe/Inhaltsangaben mit Elternschutz und nutzerbereitgestellten Inhalten.
- Keine fremden Logos, Senderbilder oder urheberrechtlich unklare Streams in Store-Grafiken.

## Google Play

| Gate | Status |
|---|---:|
| Target API 36 für gemeinsames Mobile-/TV-Paket | umgesetzt |
| Eindeutige Produktions-Paket-ID | BLOCKED |
| Play App Signing / Upload-Key | BLOCKED |
| Signiertes Release-AAB | BLOCKED |
| Data Safety | BLOCKED |
| Content Rating / Zielgruppe | BLOCKED |
| Datenschutz-/Support-URL | BLOCKED |
| Asset-Satz | BLOCKED |
| Pre-launch Report | BLOCKED |
| Interner/geschlossener Track | BLOCKED |

Aktuelle Richtlinie prüfen: [Google Play Target API](https://support.google.com/googleplay/android-developer/answer/11926878?hl=en).

## Amazon Appstore / Fire TV

| Gate | Status |
|---|---:|
| Fire OS 7/8 Android-Build | strukturell möglich, Gerätetest BLOCKED |
| Signiertes APK/AAB | BLOCKED |
| Amazon Live App Testing | BLOCKED |
| Fire-TV-Assets | BLOCKED |
| Unterstützte Gerätemodelle deklariert | Entwurf; Konsole BLOCKED |
| Vega-VPKG-Track | BLOCKED / separates Projekt |

Amazon akzeptiert für Fire OS APK/AAB; Vega benötigt einen separaten VPKG-Track. Referenzen: [Amazon Submission](https://developer.amazon.com/docs/app-submission/submitting-apps-to-amazon-appstore.html), [Fire TV Appstore Details](https://developer.amazon.com/docs/app-submission/appstore-details.html), [Vega Submission](https://developer.amazon.com/docs/vega/0.22/app-submission.html).

## Apple App Store

| Gate | Status |
|---|---:|
| iOS/iPadOS-Projekt | BLOCKED |
| tvOS-Projekt | BLOCKED |
| Bundle-IDs / Apple Team / Signing | BLOCKED |
| App Privacy / Privacy Manifest | BLOCKED |
| TestFlight intern/extern | BLOCKED |
| Apple-Assets | BLOCKED |
| App Review | BLOCKED |

## Interne Testanleitung

1. Nur das Hash-geprüfte interne Debug-Artefakt installieren; vorhandene Produktivdaten vorher sichern.
2. Keine realen geheimen Zugangsdaten in Testtickets, Screenshots oder Logs verwenden.
3. Testquelle muss rechtmäßig bereitgestellt sein und Fälle für HLS, MPEG-TS, Fehler, Offline und Erwachsenenklassifizierung enthalten.
4. Gesamte Matrix in `TEST_AND_DEVICE_MATRIX.md` ausführen.
5. Jeden Fehler mit Build-Hash, Gerät, OS, Reproduktion, erwarteter/tatsächlicher Ausgabe und anonymisiertem Anhang melden.
6. P0/P1 blockieren Signierung, Store-Upload und öffentliche Kommunikation.

## Bekannte Einschränkungen

- RC-AAB ist unsigniert und ausdrücklich nicht hochladbar.
- Keine Apple-Builds.
- Keine reale Geräte-/Store-Testevidenz.
- Profile, Favoriten, EPG und Verlauf sind im belegten Quellstand nicht als vollständige Funktionen vorhanden.
- Fire OS 5/6 liegen unter der Mindest-API; Vega ist kein Android-APK-Ziel.
- Markenname, Paket-ID, Datenschutztext, Lizenzen und Altersfreigabe sind nicht freigegeben.
