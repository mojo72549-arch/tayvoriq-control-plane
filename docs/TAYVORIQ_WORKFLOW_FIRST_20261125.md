# Workflow First: Implementierung und Nachweise

Stand: 25.11.2026. Die Änderung ergänzt die produktiven Zweige
`tayvoriq-control-plane/main` und `shorts-agent-studio/lab/cinematic-control-center`.
Der Produktionscontroller bleibt auf `feature/multi-platform-distribution-package`.

## Zustandsführung und Bedienung

Die Startseite zeigt 16 anklickbare Stationen. Ihr Zustand wird aus dem bestehenden
request-gebundenen Live-Endpunkt, dem exakten GitHub-Versuch und hashgeprüften
Produktionsartefakten abgeleitet. Es gibt keinen zusätzlichen Produktionscontroller.
Nicht separat belegte Stationen oder Laufzeiten bleiben ausdrücklich unbekannt.

Die API `/api/workflow` ist eine zusätzliche Ansicht derselben bestehenden
Serverfunktion `/api/live-v3`; sie führt keine Produktion aus. Die übrigen
Arbeitsbereiche und der bestehende Operator-Login bleiben erreichbar.

| Aktion | Bestehender Ausführungspfad | Schutz |
| --- | --- | --- |
| Neue Trends / eigener Themenwunsch | Agent Orchestrator → Telegram Trends Now → Radar V8 | Stabile Auswahlkennung bei Wiederholung; serialisierte Recherche; gleiche Quellen- und Qualitätsgates |
| Thema freigeben | Agent Orchestrator → Request Dispatcher | Originale Auswahl und Zustellbeleg; gleiche Request-ID wie Telegram; eine Themenwahl pro Auswahl |
| Fehlerstation prüfen | Agent Orchestrator, reconcile_only | Bindung an aktuellen Request und Run; vorhandene Repair-Policy und Checkpoints |
| Video freigeben | Bestehende artifact-decisions → Control Approved Publish V2 | Operator-Session; Request-, Quellen-, Nachrichten- und Studio-Bindung; alle sieben Datei-Hashes; Compare-and-swap |
| Video ablehnen | Bestehende artifact-decisions → vorhandener Review-Follow-up | Pflichtbegründung; zentraler Orchestrator entscheidet über gezielte Korrektur |

`approved_via` und die Historie kennzeichnen die tatsächliche Bedienoberfläche.
Die ursprüngliche Telegram-Auswahl bleibt als gemeinsame Auswahlidentität erhalten.
Eine HTTP-Annahme wird als angefordert angezeigt, niemals als laufende Produktion.
Fremde Origins und fehlender Bedienzugriff blockieren schreibende Aktionen.

## Archiv und Komponenten

`tools/tayvoriq_video_archive.py` erzeugt `state/tayvoriq-video-archive.json` aus den
vorhandenen Veröffentlichungsbelegen. Der zugehörige Workflow aktualisiert den
Index nach Publishing-Läufen und geänderten Belegen. Der Index bleibt unabhängig
von der aktiven Queue bestehen und bietet archivierte Videos nicht zum Upload an.

Eine Upload-Reservierung, Freigabe oder Telegram-Dateizustellung ist kein
Veröffentlichungsbeleg. Ein bestätigter YouTube-Abschluss ohne bestätigten
TikTok-Abschluss heißt `PARTIALLY_PUBLISHED`. Ein endgültiger Abschluss und das
Entfernen aus der aktiven Ansicht erfordern alle vorgesehenen Plattformen.

Beim initialen Aufbau sind 14 YouTube-Veröffentlichungen belegt. Für keines dieser
Videos ist ein TikTok-Plattformabschluss belegt. Fehlende historische Daten,
Metriken und Messzeiten werden nicht rekonstruiert oder auf null gesetzt.

Der Komponentenkatalog `state/tayvoriq-tool-catalog.json` unterscheidet konfigurierte
Abhängigkeiten und tatsächlich nachgewiesene Beiträge. Chatterbox und
MoneyPrinterTurbo sind auf die vorhandenen Produktions-Commits gepinnt. Für
Whisper und die FFmpeg-Binärversion wird keine ungemessene Laufzeitversion behauptet.

Der Berichtsgenerator liest zusätzliche Stations- und Skriptnachweise ausschließlich
aus dem SHA-256-geprüften `job.json` des request- und versuchsgebundenen Checkpoints.
Beim vorhandenen Lauf 45593112055, Versuch 1, wurden diese zusätzlichen Nachweise
aus dem unveränderten Diagnose-Checkpoint gewonnen. Die Produktion selbst wurde
dadurch nicht erneut gestartet oder verändert.

## Prüfung und verbleibende Abnahme

Die Python-Regression deckt unter anderem Auswahlbindung, gleiche Request-ID in
beiden Oberflächen, Slot-Serialisierung, einen Recovery-Owner, begrenzte Reparatur,
Erhalt gültiger Checkpoints, Artefaktfreigaben und das dauerhafte Archiv ab.
Die JavaScript-Prüfungen decken Quellen-/Versuchsbindung, stale Telegram-/Web-Reviews,
CAS-Konflikte, Wiederholungen, Fremd-Origins und ausgebliebene Dispatch-Bestätigungen ab.

Aus dem bestehenden erfolgreichen Lauf sind 10:07 Minuten zwischen Run-Start und
letztem Job-Schritt sowie 6:47 Minuten im lokalen Repair-Schritt messbar.
Das ist ein Recovery-Lauf mit wiederverwendeten Artefakten und kein Nachweis für
einen frischen regulären Produktionslauf unter zehn Minuten. Eine getrennte,
vollständige Messung externer Wartezeiten liegt nicht vor.

Für die vollständige fachliche Endabnahme stehen noch aus:

- Ein vom Nutzer freigegebener frischer Auftrag durch die neue Oberfläche und der
  anschließende Videoreview über die jeweils andere Oberfläche.
- Der Nachweis des Zehn-Minuten-Ziels für reguläre Neuproduktion.
- Ein tatsächlicher TikTok-Veröffentlichungsbeleg beziehungsweise die Anbindung
  einer autorisierten automatischen TikTok-Veröffentlichung. Der vorhandene
  Produktionsvertrag sieht derzeit `telegram_manual` vor.
- Ein separater Messnachweis für Musikexport und Ressourcenverbrauch einzelner
  Komponenten. Die vorhandene redaktionelle Musik-Policy erlaubt Stille und
  sparsame Akzente; daraus wird kein ausgeführter Musikexport abgeleitet.

Es wurden keine neuen Themen stellvertretend freigegeben und keine
Testveröffentlichungen auf produktiven Kanälen angefordert.
