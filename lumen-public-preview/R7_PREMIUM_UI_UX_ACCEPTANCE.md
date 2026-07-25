# Project Lumen 13.1.33 – R7 Premium UI/UX

## Ziel

Project Lumen wirkt wie ein moderner Premium-Mediaplayer und nicht wie ein technisches Playlist-Werkzeug. Der Rubu-inspirierte Hintergrund nutzt einen dunklen Navy-/Petrol-Verlauf mit dezenten Cyan-, Blau- und Violett-Lichtern. Die technische Diagnose bleibt vollständig erhalten, wird aber als sekundärer Systemstatus dargestellt.

## Umgesetzt

- gemeinsame Premium-Farbpalette für Haupt- und Detailseiten
- animierter Gradient-Hintergrund auf Smartphone und Tablet
- statischer, ressourcenschonender Gradient auf TV und im Energiesparmodus
- mobile Navigation unten: Start, Live, Filme, Serien, Mehr
- TV-/Fire-TV-Navigation als linke Seitenleiste
- kompakter Header mit Suche und aktivem Profil
- verkürzte Texte und klare Hauptaktionen
- Startseite mit Weiterschauen, Favoriten, Länder-Hubs, Live, Filme und Serien
- konsistente Vektorflaggen für Deutschland, Türkei, Großbritannien und Weitere
- hochwertigere Medienkarten mit Live-, Sprach- und Favoritenstatus
- Quellenansicht auf Server-Login, Playlist-Link und lokale Datei reduziert
- strukturierter Mehr-Bereich für Bibliothek, Profile, Quellen und System
- Diagnose bleibt als Systemstatus, Logansicht und Logexport vollständig verfügbar
- R2-Film-/Serienflüsse, R3-EPG/Suche/Favoriten, R4-Profile/PIN und R5-Lizenzgrundlage bleiben erhalten

## UX-Regeln

- maximal fünf permanente Hauptbereiche
- Überschriften kurz und eindeutig
- Unterzeilen grundsätzlich einzeilig
- keine URL, Parser-ID oder technische Klassifikation auf Medienkarten
- Hauptaktion über große Touch- und D-Pad-Flächen
- lange Betätigung einer Medienkarte schaltet den Favoritenstatus
- technische Fehlercodes ausschließlich im Systemstatus beziehungsweise in der Diagnose

## Geräteabnahme

R7 ist technisch gebaut, aber erst nach realer Prüfung freigabefähig:

1. Samsung SM-G980F: Hochformat, Querformat, kleine und sehr große Bibliothek.
2. Android TV/Google TV: vollständige D-Pad-Navigation, Fokus und Zurück-Verhalten.
3. Fire TV: Seitenleiste, Fokus, schwächere Hardware und statischer Hintergrund.
4. Tablet: Bottom-Navigation, Querformat und Posterreihen.
5. Diagnose: Systemstatus öffnen, technische Details anzeigen und bereinigtes Log teilen.

## Produkt-Gate

R7 ist GRÜN, wenn die neue Navigation ohne Sackgassen funktioniert, alle Hauptfunktionen in höchstens drei Aktionen erreichbar sind, RTL/RTL Zwei unter Deutsch und TRT 1/TRT 2 unter Türkisch erscheinen, die Diagnose vollständig erreichbar bleibt und zwei Regressionen ohne P0/P1 abgeschlossen sind.
