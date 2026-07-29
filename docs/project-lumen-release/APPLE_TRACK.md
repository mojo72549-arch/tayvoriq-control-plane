# Separater Apple-Entwicklungs- und Release-Track

Stand: 29. Juli 2026  
Status: **BLOCKED / noch kein buildbares Apple-Projekt**

Die stabile Android-App wird nicht migriert oder durch plattformübergreifenden Code ersetzt. iOS/iPadOS und tvOS erhalten native Anwendungen mit gemeinsamem Apple-Core.

## Sinnvolle Wiederverwendung

| Bereich | Wiederverwendung |
|---|---|
| Produktregeln | vollständig als plattformneutrale Spezifikation |
| M3U/M3U8-Grammatik und 100k-Testkorpora | vollständig |
| Datenmodell für Medien, Gruppen und Quellen | semantisch, nicht als Java-Binärmodul |
| Jugendschutzregeln | vollständig als Akzeptanztests |
| Branding, Farb-/Abstands-/Typografietokens | nach Apple-HIG-Anpassung |
| Fehlerklassen und Netzwerk-Testfälle | vollständig als Spezifikation |
| Android UI, Activities, Media3/ExoPlayer, Android Keystore | nicht wiederverwenden |

## Vorgeschlagene Apple-Architektur

- Swift 6 / SwiftUI für iPhone, iPad und Apple TV.
- Gemeinsames Swift Package `LumenCore` für Parser, Modelle, Index, Filter und Migrationen.
- AVFoundation/`AVPlayer` für HLS und unterstützte Apple-Medienformate.
- SwiftData oder SQLite-basierter lokaler Index; schreibgeschützte Snapshot-Leser für große Bibliotheken.
- Keychain/Secure Enclave, soweit verfügbar, für PIN-Prüfmaterial; keine PIN im Klartext.
- Gemeinsame Testkorpora mit dem Android-Parser, damit Klassifizierung und Jugendschutz identisch bleiben.
- Getrennte SwiftUI-Navigation für Touch und tvOS-Fokus; keine erzwungene 1:1-Übernahme der Android-Oberfläche.

## Umsetzungsphasen

1. **Spezifikation einfrieren:** Datenmodell, Parserregeln, Adult-Klassifizierung, Zeit-/Sperrsemantik, Fehlercodes.
2. **LumenCore:** Streaming-Parser, normalisierte Modelle, persistenter Index, verschlüsselte Quellenablage, Migrationen.
3. **iOS/iPadOS Shell:** Import, Start/Live/Filme/Serien/Mehr, Suche, Elternschutz, AVPlayer.
4. **tvOS Shell:** Focus Engine, Siri Remote, Back/Menu, Vollbildplayer, TV-gerechte Dichte.
5. **Qualität:** XCTest, XCUITest, 100k-Import, Prozess-/Neustart, langsames Netzwerk, Speicherwarnung, 8-Stunden-Soak.
6. **Release:** eindeutige Bundle-IDs, Apple Developer Team, Zertifikate/Provisioning, App Privacy, TestFlight intern/extern.

## Nicht verhandelbare Parität

- Keine mitgelieferten Quellen oder Inhalte.
- Erwachsene Inhalte gesperrt und in allen Oberflächen unsichtbar.
- Sechsstellige Eltern-PIN; Sperre bei Neustart und nach zehn Minuten.
- Aktive Erwachsenenwiedergabe endet beim Ablauf.
- Lokale Quellen und Zugangsdaten werden nicht zentral übertragen.
- Vollständige lokale Löschung.
- Keine URL-/Token-Leaks in Fehlern, Logs oder Crashberichten.
- Gleiche M3U-Testkorpora und erwartete Ergebnisse wie Android.

## Apple-spezifische Risiken

- MPEG-TS außerhalb HLS muss gegen AVFoundation und reale Quellen geprüft werden; keine Transcoding-/Proxy-Lösung ergänzen.
- iOS/tvOS-Hintergrund- und Netzwerkregeln unterscheiden sich von Android; Wiederverbindung muss plattformgerecht implementiert werden.
- Externe TestFlight-Builds können vor Freigabe zur Beta-Prüfung vorgelegt werden müssen.
- App-Review, App-Privacy-Angaben, Altersfreigabe und „Reader App“-Regeln sind vor Einreichung anhand der finalen Funktionen zu prüfen.
- Ein Apple-Build kann in der aktuellen Linux-Umgebung weder erstellt noch signiert werden. Xcode, Apple-Developer-Team und App-Store-Connect-Zugang sind zwingend.

## Apple Release-Gates

- Buildbares Xcode-Workspace mit iOS-, iPadOS- und tvOS-Targets.
- Archivierung mit aktueller von Apple akzeptierter Xcode-Version.
- Signierte Archive und Upload nach App Store Connect.
- XCTest/XCUITest und TestFlight-Gerätematrix grün.
- App Privacy, Privacy Manifest und benötigte API-Begründungen vollständig.
- Finale Icons/Screenshots für jede Gerätegröße.
- Keine offenen P0/P1-Befunde.

## Offizielle Referenzen

- [App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/)
- [App Privacy Details](https://developer.apple.com/app-store/app-privacy-details/)
- [User Privacy and Data Use](https://developer.apple.com/app-store/user-privacy-and-data-use/)
- [AVPlayer](https://developer.apple.com/documentation/avfoundation/avplayer/)
- [HTTP Live Streaming](https://developer.apple.com/streaming/)
- [TestFlight](https://developer.apple.com/testflight/)
- [Builds hochladen](https://developer.apple.com/help/app-store-connect/manage-builds/upload-builds/)
