# Project Lumen 13.1.32 RC1 – Orchestrierung und Go/No-Go

## Sprintstatus

| Sprint | Technischer Stand | Produkt-Gate |
|---|---|---|
| R0 | stabile Import-/Restore-Baseline übernommen | reale Wiederholungsabnahme nachweispflichtig |
| R1 | Länder-/Sprach-Hubs und Medienklassifikation vorhanden | reale Stichprobe erforderlich |
| R2 | nachgeliefert: Film-Detail, Serien/Staffel/Episode, verschlüsseltes Weiterschauen | Geräte-/D-Pad-Abnahme offen |
| R3 | EPG, lokale Suche und Favoriten übernommen | reale EPG-/TV-Abnahme offen |
| R4 | verschlüsselte Profile, PIN, getrennte Favoriten/Verläufe und zentraler Kinderfilter | Umgehungs- und TV-Tests offen |
| R5 | Gerätecode, signierte Entitlement-Prüfung und Store-Abstraktion vorbereitet | echtes Billing/Backend blockiert Grün |
| R6 | Compliance-, Rechts-, Geräte- und Go/No-Go-Paket definiert | externe Freigaben und zwei Testläufe offen |

**Gesamtampel: GELB. Public Sale: NO-GO.**

## R5 – verbindliche Produkt- und Datengrenze

Project Lumen verkauft ausschließlich eine Softwarelizenz. Sender, Filme, Serien, Playlists, Zugangsdaten, EPG-Daten und Stream-URLs sind weder Kaufbestandteil noch Backend-Daten.

Der Produktionsfluss lautet: Store-Kauf oder Wiederherstellung → serverseitige Prüfung des Store-Belegs → signiertes, zeitlich begrenztes Entitlement → lokale Prüfung von Signatur, Gerätebindung, Gültigkeit und Offline-Fenster. Pending-, stornierte, erstattete oder wiederverwendete Belege dürfen keine Berechtigung erzeugen.

Zulässige Backend-Daten sind Store, Produkt-ID, Kaufbeleg/-token, pseudonyme App-/Gerätekennung, Transaktionsstatus, Entitlement-Zeiten und bereinigte Supportcodes. Verboten sind Playlistdateien, Playlist- und Stream-URLs, Kataloge, EPG-Inhalte, Zugangsdaten, Such- und Wiedergabeverlauf.

Offen bleiben Play- und Amazon-Store-Flavors, echte Produkt-IDs, serverseitige Store-Verifikation, Signaturschlüssel im Secret-Management, Replay-Schutz, Refund/Chargeback, Geräteentkopplung und Ende-zu-Ende-Tests.

## R6 – Pflicht-Gerätematrix

- Samsung SM-G980F / Android 13 als Smartphone-Referenz.
- Mindestens zwei Android-TV-/Google-TV-Geräte unterschiedlicher Leistung.
- Mindestens zwei Fire-TV-Generationen, darunter eine schwächere Klasse.
- Ein Tablet für Touch und Querformat.
- Kleine, mittlere und sehr große Playlists bis 100.000 Einträge.
- Lokale Datei, HTTP, HTTPS, Redirect, langsamer Server, Timeout und abgebrochener Download.

Pro Gerät müssen Neuinstallation, Upgrade, Import, verschlüsselte Speicherung, Kaltstart, Fast Restore, Länder-Hubs, Live/Film/Serie, Film-Detail, Staffel/Episode, Weiterschauen, EPG, Suche, Favoriten, Profile, PIN, Kinderfilter, vollständige D-Pad-Bedienung, App-Abbruch, Geräte-Neustart und Speicherknappheit geprüft werden. Für Store-Builds kommen Kaufabbruch, Pending, Erfolg, Wiederherstellung, Offline-Fenster, Refund und Gerätewechsel hinzu.

Freigabe erst nach zwei vollständigen Runden ohne P0/P1. Jeder Lauf dokumentiert Build-Hash, Gerät, OS, Diagnose-ID und Ergebnis.

## R6 – Recht und Store

Vor einer Einreichung sind Markenname, Anbieter/Impressum, EULA/AGB für reine Softwarelizenz, Datenschutzerklärung, Data-Safety-Angaben, Copyright-/Abuse-Prozess, Open-Source-Notices, Codec-/Patentrisiken, Jugendschutz, Preis/Testphase/Verlängerung/Kündigung/Erstattung sowie Backend-Hosting und Subprozessoren formal zu prüfen.

Verbindliche Store-Aussage:

> Project Lumen ist ein lokaler Mediaplayer. Die App enthält, verkauft und vermittelt keine Sender, Filme, Serien, Playlists, Abonnements oder Zugangsdaten. Nutzer fügen ausschließlich eigene, rechtmäßig nutzbare Quellen hinzu.

## Aktueller No-Go-Grund

Der RC1-Pilot ist eine technische Integrationsstufe, keine Verkaufsfreigabe. Reale TV-/Fire-TV-Abnahmen, vollständige Jugendschutz-Umgehungstests, echte Store-Käufe mit Backend-Verifikation, zwei Regressionen sowie schriftliche Legal-, Security- und Product-Freigaben fehlen noch.
