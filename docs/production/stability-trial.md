# TAYVORIQ – Abnahme und Stabilitätstest

Stand der Vorbereitung: 23.11.2026. Verantwortlich für technische Entscheidungen ist der Production Controller. Themenwahl und Freigabe des fertigen Videos sind zwei unabhängige Bedienhandlungen in Telegram.

## Start und Auswertung

Tag 1 ist der erste vollständige Berliner Kalendertag nach einem echten, freigegebenen Auftrag auf den verifizierten neuen Revisionen. Voraussetzung sind zwei technisch geprüfte Plattform-Master, das identische Review-Paket und eine positive Telegram-Message-ID. Das Versuchsraster umfasst sieben aufeinanderfolgende Kalendertage einschließlich Wochenende. Die 14 Zeilen der benachbarten CSV sind Planplätze. Die CSV löst keine Aufträge aus.

Die Morgenrecherche ist für 05:30 Uhr Europe/Berlin vorgesehen, die Abendrecherche für 19:00 Uhr. Das sind Startzeiten. Erfasst werden zusätzlich die Zeiten für Trendauswahl, Themenfreigabe, Renderbeginn, Abschluss der QA und Telegram-Empfang. Für eine interaktive Ersatzsuche die Zeit vom Klick bis zur zugestellten Auswahl gegen das Ziel von zehn Minuten messen. Verzögerung durch Themenwahl und Verzögerung im System getrennt ausweisen.

Jeder Slot benötigt eine frische, nachvollziehbare Auswahl und einen freigegebenen Request. Ein ungeeignetes Thema wird mit Begründung zurückgestellt. Ein Ersatz erhält neue Auswahl, Callback und Request-ID. Ein abhängiger Abendauftrag bleibt HELD bis zum erfolgreichen Morgenlauf mit den vier erfolgreichen Schritten „Assert publishable production output“, „Validate publication quality“, „Publish review page“ und „Send Telegram review“. Ein gescheiterter Morgen ist eine Abweichung. Ein nachgeholter Slot bleibt dem ursprünglichen Tag zugeordnet.

## Welche Belege zählen

| Stufe | Zu erfassender Beleg | Bei Ausfall |
|---|---|---|
| Recherche und Quellen | Auswahl-ID, Aktualität, zwei unabhängige belastbare Quellen, Quellenhash, Dublettenprüfung, umsetzbarer Visual-Plan | Quelle/Alternativthema erneut prüfen; neuer Auftrag nach Themenwechsel |
| Redaktion und Skript | Vertragshash, freigegebener Winkel, plattformspezifischer Hook, Zuschauerfrage und Antwort, Skript-QA | Nur beanstandete Redaktion überarbeiten; davon abhängige Inhalte neu prüfen |
| Stimme | Solltext, verwendete Aussprachen, ASR vor Render und nach Mux, kritische Begriffe, Schlusswort, Audiobeleg je Variante | Gleiche Aliase lokal normalisieren; inhaltliche oder numerische Abweichung blockiert; unveränderten Programmfehler nicht erneut synthetisieren |
| Visuals und Untertitel | Asset-Nachweis je Szene, Motiv im ersten Bild, passende Übergänge, zeitlich passende Untertitel; Sichtprüfung bei strittigem Motiv | Betroffene Szenen bzw. Untertitel korrigieren; unveränderte Eingaben beibehalten |
| Render und finale QA | Beide MP4, Dateigröße, Proberesultat, vollständige Dekodierung, H.264/AAC, 1080 × 1920, versionsgebundener Gate-Bericht | Validierte Inputs behalten; Fehler auf die betroffene Variante und Stufe eingrenzen |
| Telegram | Run, Commit des Review-Pakets, Paket-Hashes, tatsächliche Telegram-Message-ID | Technischen Master weiterverwenden; unklare Zustellung zuerst abgleichen |
| Veröffentlichung | Artefaktentscheidung, pro Plattform eigene Bestätigung und externe Video-ID | Bei unklarer Antwort zunächst beim Ziel abgleichen; bestehender TikTok-Pfad bleibt manuell |

Jeder Request bleibt auch nach Ablehnung im Nenner. Ein Slot zählt als **technisch ausgeliefert**, wenn beide von QA bestätigten Master und der Telegram-Beleg zusammenpassen. Eine inhaltliche Ablehnung zählt separat als Qualitätsabweichung. Eine Veröffentlichung erfordert die spätere Freigabe und einen eigenen Plattformbeleg. Ein historischer oder isolierter Referenzlauf erfüllt die Startbedingung nicht.

## Kennzahlen

* Auslieferung je Tag und Slot, regulär und nach Recovery, mit Zahl der verschiedenen Requests und Telegram-Zustellungen. Ziel: 14 von 14. Jedes falsche SUCCESS, jede Dublette, jeder nicht freigegebene Upload und jeder Verstoß gegen Serialisierung ist ein P0-Abbruchkriterium.
* Laufzeit vom freigegebenen Request bis Telegram, zusätzlich Runner-Laufzeiten je Versuch, Summe statt Überschreiben. Bei 14 Beobachtungen auch alle Einzelwerte, Median und Maximum ausweisen.
* Provideraufrufe aus tatsächlichen Transportereignissen zählen, inklusive Fehlern und Retries. Rechercheereignisse heißen research_http_usage. Pro Versuch sind Provider, Modell, HTTP-Status, Laufzeit, Run/Attempt und verfügbare Tokenzahlen erfasst. Die GitHub-Run-ID verbindet reguläre Recherche ohne Auswahl-ID mit dem Auswahlbeleg. Musik-, Voice- oder Medienverbrauch außerhalb der erfassten Transporte separat aus Herstellerbelegen eintragen.
* Kosten je geliefertem Video = belegte Provider- und Runnerkosten aller Versuche im Fenster / technisch ausgelieferte Videos. Zusätzlich pro Request und mit Kosten erfolgloser Slots berichten. Fehlende Preise/Abrechnung, Null-Lieferungen und unbekannte Tokenwerte bleiben offen. Cache-Treffer getrennt von Provideraufrufen erfassen.
* Nach jedem Fehlslot den ursprünglichen Code, Input- und Artefakt-Fingerabdrücke, Run-Link, fehlerhafte Stufe, Reparaturumfang und Ergebnis an die Zeile hängen. Sieben Tage werden unabhängig vom erreichten Zähler ausgewertet.

## Vergleichswerte vor Versuchsbeginn

Der historische Stuttgart-Job 43776528221 lief vom 15.11. 23:45:35 UTC bis 16.11. 00:09:19 UTC (23:44 Minuten Runnerzeit für diesen Versuch). Der Review-Commit enthält 1.868.517 Byte YouTube und 1.855.388 Byte TikTok. Telegram-Beleg 3666, spätere Entscheidung REJECTED wegen schematischer Bilder. Das historische job.json meldet offene Gemini-/Groq-Circuits, einen Hugging-Face-HTTP-400 und lokale redaktionelle Ausweichpfade. Eine Rechnung oder vollständige Request-Zählung ist daraus nicht ableitbar.

Die neue technische Prüfung dekodierte am 23.11. den archivierten Bosch-Abstatt-Master vollständig. SHA-256 5776424f3dbb363470dd9dbd6a4190a4f76cb764917ac60618a5c7bf6914e548, 27,766667 Sekunden, 1080 × 1920, H.264/AAC. Die Prüfung fand keine der definierten Schwarzbild-, Stille- oder Streamzeit-Abweichungen. Die Datei belegt die Verträglichkeit der neuen Prüfung mit einem historischen Master.

[Stuttgart-Lauf](https://github.com/mojo72549-arch/tayvoriq-control-plane/actions/runs/43776528221) · [Review-Dateien](https://github.com/mojo72549-arch/mind-reset-daily/tree/18b4180225968b65ba273158ca8368b19e182358/tayvoriq/runs/43776528221) · [Studio-Änderung](https://github.com/mojo72549-arch/shorts-agent-studio/pull/322)
