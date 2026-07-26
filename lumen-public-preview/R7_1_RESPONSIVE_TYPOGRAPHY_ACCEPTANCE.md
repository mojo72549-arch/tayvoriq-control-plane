# Project Lumen 13.1.34 – R7.1 Responsive Typography & Compact Device Polish

## Ziel

Die bestehende R7-Premiumoberfläche bleibt erhalten, wird aber auf schmalen und älteren Android-Geräten robust. Schrift darf nicht abgeschnitten, ungewollt in einzelne Silben geteilt oder durch starre Höhen nach unten gedrückt werden.

## Technische Änderungen

- vier Breitenklassen: Compact bis 360 dp, Standard 361–411 dp, Large ab 412 dp und TV
- einzeilige LUMEN-Wortmarke mit deaktivierter Silbentrennung
- zweizeiliger Header auf Compact-Geräten: Marke und Suche oben, Profil darunter
- responsive Begrüßung, Seitentitel, Bereichstitel, Karten- und Buttontexte
- maximal zwei Zeilen mit Ellipsis für normale Überschriften und Kartentexte
- kürzerer Hero-Text und vollbreiter Primärbutton auf Compact-Geräten
- kompaktere Bottom-Navigation mit einzeiligen Labels
- Kartenmindesthöhen statt starrer Textausschnitte
- kleinere Medien- und Länderkarten für schmale Displays
- mindestens 48 dp hohe Eingaben und Hauptaktionen
- reduzierte Abstände auf Compact-Geräten ohne Verlust der Lesbarkeit
- gleiche Typografie-Grundregeln auf Film-, Serien-, Profil- und Aktivierungsseiten

## Geräteabnahme

Pflichtgerät ist das Samsung SM-G980F mit Android 13. Zusätzlich sind mindestens ein Gerät bis 360 dp Breite, ein Standardgerät, ein großes Smartphone oder Tablet sowie Android TV/Fire TV zu prüfen.

## Prüfpunkte

1. LUMEN steht in einer Zeile und wird nicht zu `LUM / EN` umgebrochen.
2. Suche und Profil überdecken die Wortmarke nicht.
3. `Guten Morgen`, `Guten Tag` und `Guten Abend` bleiben vollständig lesbar.
4. Die leere Hero-Karte zeigt `Deine Medien`, einen kurzen Untertitel und den vollständigen CTA.
5. Kein Haupttext wird vertikal abgeschnitten.
6. Kartenuntertitel dürfen auf Compact-Geräten zwei Zeilen nutzen.
7. Die Bottom-Navigation bleibt vollständig sichtbar und nimmt weniger Höhe ein.
8. Nach Hinzufügen einer Quelle bleiben Start, Live, Filme, Serien und Mehr lesbar.
9. Schriftvergrößerung in den Android-Einstellungen darf keine Hauptaktion unbedienbar machen.
10. Diagnose und Systemstatus bleiben vollständig erreichbar.

## Freigabegrenze

CI prüft Integration, Kompilierung, Signatur und statische Layoutregeln. Die visuelle Produktabnahme bleibt offen, bis die genannten Geräte und mindestens die Android-Schriftgrößen 100 %, 115 % und 130 % real geprüft wurden.
