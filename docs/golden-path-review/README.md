# TAYVORIQ Produktionsreview und Migration

## Gesicherter Stand am 13. November 2026

| Quelle | Ref | Commit |
| --- | --- | --- |
| Control Plane | `main` | [`03a29eb557b0824dc85a699b8af4b10363ef4c4c`](https://github.com/mojo72549-arch/tayvoriq-control-plane/commit/03a29eb557b0824dc85a699b8af4b10363ef4c4c) |
| Control Plane | Definition des Referenzlaufs | [`b44b34b6609c5550dc95b99fe1785055260003b3`](https://github.com/mojo72549-arch/tayvoriq-control-plane/commit/b44b34b6609c5550dc95b99fe1785055260003b3) |
| Studio | `main` | [`649b73dc339d1c904a4f801c54429453e09712a9`](https://github.com/mojo72549-arch/shorts-agent-studio/commit/649b73dc339d1c904a4f801c54429453e09712a9) |
| Studio | `feature/multi-platform-distribution-package` | [`64a3cd6e1727c70deb507dd95a80ba064675aadc`](https://github.com/mojo72549-arch/shorts-agent-studio/commit/64a3cd6e1727c70deb507dd95a80ba064675aadc) |
| Studio | Control-Plane-Pin und ausgeführter Checkout | [`45674ac1838c09e1da6d1438cd15dca096afce21`](https://github.com/mojo72549-arch/shorts-agent-studio/commit/45674ac1838c09e1da6d1438cd15dca096afce21) |

Der Studio-Branch-Head enthält gegenüber dem Produktionspin genau einen Commit, der nur `.automation/tayvoriq-quality-status.json` aktualisiert. Die Workflow-Datei des Porsche-Laufs ist gegenüber dem gesicherten Control-Plane-Head unverändert. Beide Refactoring-Branches basieren auf den oben genannten Branch-Heads.

## Inventar

- [Dateien](dateien.csv) umfasst 625 Dateien im Control Plane und 840 im Studio. `ARCHIVE` für operative Records bezeichnet die geplante Aufbewahrung der bisherigen Daten nach Migration. Die laufenden Besitzer und aktiven Records stehen in der Matrix unten.
- [Workflows und Trigger](workflows.csv) enthält 140 YAML-Definitionen im Control Plane und 25 im Studio. Die GitHub-API meldete 216 Control-Plane-Registrierungen mit Status `active`. 76 davon hatten auf dem gepinnten `main` keine Datei. Ein API-Status belegt keine Ausführung. Die Runs-Spalten beziehen sich auf die abgerufenen Stichproben und den Referenzlauf. Die YAML-Spalten beschreiben Trigger, Eingabefilter, Concurrency, Actions und erwähnte Folgeworkflows. Erwähnungen können Kommentare oder deaktivierte Aufrufe enthalten. Die aktiven Kanten des Referenzpfads sind unten belegt.
- [Python-Imports](python-imports.csv) erfasst statische Imports und dynamische Ladepunkte in den lokal lesbaren Python-Dateien. Der ausgeführte Stack und die konkret wirksamen Overrides stehen unten. Die Importliste enthält keine vollständige Laufzeitauflösung dynamischer Ziele.
- [Sonderpfade](sonderpfade.csv) enthält dateinamengebundene Kandidaten. Zusätzlich enthalten generische Dateien themengebundene Pfade, etwa Porsche und das Enzymthema in `tayvoriq_dual_platform_render_v11.py`, Stuttgart 21 und Sonnenfinsternis in `tayvoriq_dual_platform_render_v34.py`, Tankrabatt in `tayvoriq_editorial_visual_standard_v1.py` und Spiele-, Raumfahrt- und Serienzweige in den Runtime-Patches. Die Dateikategorie `runtime_patch` erfasst auch `sitecustomize.py` und weitere Startmechanismen. Klassifikationen sind Vorschläge für die Migration und erteilen keine Löschfreigabe.

## Belegter Ausführungspfad des Porsche-Requests

Der Request `telegram-3549-trend-1` bindet `trend_id=1` an `20261111-morning-agentv2`. Der Quellenhash lautet `40fafb396465932e17cdc4bbfabb99ab1f9d170a45c78f4b244920dfc792dff6`. Freigegebener Winkel ist die Differenz zwischen dem gemeldeten Milliardenverlust und dem positiven bereinigten Ergebnis der Holding. `3549` identifiziert die Trendkarte. Eine Review-Nachrichten-ID für diesen Lauf liegt nicht vor.

| Station | Workflow / Modul | Eingabe → Ausgabe und Checkpoint | Ergebnis im Referenzlauf / Verantwortlicher |
| --- | --- | --- | --- |
| Trendfreigabe | `deploy-telegram-approval-worker.yml`, Worker v7 → v2 | Callback und Auswahl → `tayvoriq_trend_approved`, Approval-Key | Request-Datei und Auswahl belegen die Bindung. Control Plane besitzt die Freigabe. |
| Request-Bindung | `tayvoriq-request-dispatch.yml`, `tayvoriq_orchestration_contract.py` | Auswahl-Snapshot → Request-JSON, aktiver Pointer und Golden-Path-Run-ID | Verifizierte Request-Bindung auf `42983272199`. Dispatcher und aktiver Pointer verwalten Claims. |
| Quellen und Dubletten | `tayvoriq-deliver-video-now.yml`, `tayvoriq_source_evidence_v1.py`, `tayvoriq_global_duplicate_gate_v1.py` | Unveränderliche Quellenevidenz → materialisiertes Quellenpaket und Dublettenentscheidung | Schritte 7–8 bestanden. Kontrolliertes Replay übernimmt denselben Hash. |
| Implementierung und Vorprüfung | Golden Path, `tayvoriq_resolve_production_green_v1.py` | Green-Pointer → exakter Checkout, Produktionsmanifest und Replay-Readiness | Schritt 30 war die letzte substanzielle erfolgreiche Vorprüfung. Schritt 15 protokollierte `AUTOCODEFIX_OVERLAY_DIFFERENT_REQUEST`. |
| Redaktion und Skript | `tayvoriq_autonomous_entrypoint.py` → `tayvoriq_self_heal_controller.py` → Review-Pipeline v19 → Render-Bootstrap → Master-Reuse/v27/v2/v34 → v11 und Runtime-Guards | Quellen, Winkel und Sprechertext → Editorial-Paket, Script-Gate | Golden Floor wies Meta-Erzählung vor der Master-Erstellung ab. Studio besitzt den redaktionellen Fehler. |
| Stimme, Visuals, Musik und Untertitel | Dual-Platform-Renderer und Studio-Provider, `tayvoriq_editorial_visual_standard_v1.py` | Geprüftes Skript → validierte Zwischenprodukte | Kein fertiger Artefaktsatz für den Referenzlauf belegt. |
| Rendering | Studio-Renderpfad, `tayvoriq_dual_platform_master_reuse.py` | Geprüfte Zwischenprodukte → zwei MP4s und `job.json` | Controller-Handoff `process_exit=1`, `reusable_master=false`. Schritt 33 grün wegen explizitem `exit 0`. |
| Publishability | Golden Path, Schritt 41 | Controller-/Recovery-Ausgang → Publishability; im Altstand Prüfung der Statusfelder | Fehlgeschlagen. Kein herunterladbares MP4-Artefakt in der Run-Artefaktliste. |
| Finales Audit | Golden Path, `tayvoriq_publication_quality_gate_v2.py` | Job und beide Varianten → Qualitätsbericht | Übersprungen. |
| Review-Seite | Studio `tayvoriq_build_dual_review_site.py`, Golden Path `Publish review page` | Geprüfte Varianten und Review-Seite → Pages-Commit | Übersprungen. |
| Telegram-Review | Golden Path, Studio `tayvoriq_send_telegram.py` | Geprüftes Review → Telegram-Videoquittung und Abschluss | `Send Telegram review` übersprungen. Der ausgeführte Telegram-Schritt meldete den technischen Stopp. |
| Veröffentlichung | Worker/Decision-Bridge, `tayvoriq-control-approved-publish.yml`, YouTube Publisher und TikTok-Paket | Menschliche Freigabe, identisches Review → Plattformquittung | Nicht erreicht. Der untersuchte Control-Publisher unterscheidet YouTube-Veröffentlichung und TikTok-Paketübergabe. Ein TikTok-Paket allein belegt keinen TikTok-Post. |

Referenznachweise: [Produktion 42983272199](https://github.com/mojo72549-arch/tayvoriq-control-plane/actions/runs/42983272199), [Codefix 42984875924](https://github.com/mojo72549-arch/tayvoriq-control-plane/actions/runs/42984875924), [Editorial-CI 42982398154](https://github.com/mojo72549-arch/shorts-agent-studio/actions/runs/42982398154) und [allgemeine Studio-CI 42982398167](https://github.com/mojo72549-arch/shorts-agent-studio/actions/runs/42982398167).

## P0, P1 und P2

| Priorität | Befund | Korrektur bzw. Nachweis |
| --- | --- | --- |
| P0 | Das Produktionsresultat wurde in Schritt 33 als erfolgreicher Prozess-Handoff dargestellt. Schritt 41 prüfte nur Prozessstatus und Exit-Code. | Artefaktprüfung vor `master_ready`, mit 9:16, MP4, Audio und positiver Dauer für beide Varianten. Das finale Qualitätsaudit bleibt verpflichtend. |
| P0 | `production_completion` enthielt keine Telegram-Quittung. Lifecycle akzeptierte trotzdem `REVIEW_READY`. | Telegram-Videoquittung und positive numerische `message_id` in den Request übernehmen. Alte Records ohne Quittung als historische Evidenz behandeln und nicht automatisch erneut senden. |
| P0 | Die Wortprüfung verlangte `Wertberichtigung` in beiden Originalquellen. Der SWR-Satz enthält `Wertminderungen`. | Tests verwenden die beiden tatsächlich gebundenen Aussagen. Semantische Varianten werden nur mit übereinstimmenden, pro Quelle belegten Angaben verarbeitet. |
| P0 | Der Auto-Codefix änderte `tayvoriq_preapproval_ai_audit_v6.py` für einen Fehler im Skript-Gate. Wegen abweichender Basis meldete er `AUTOCODEFIX_OVERLAY_BASE_NOT_GREEN` und endete grün. | Fehlerklasse vor Provider-Aufrufen stoppen, Abschluss ohne verifizierten Replay fehlschlagen lassen, automatischen Codefix nach produktivem Nachweis stilllegen. |
| P1 | Studio-CI schrieb `all_tayvoriq_tests_passed`, während der getrennte Editorial-Vertrag auf demselben Code scheiterte. Der Legacy-Lauf war beratend. | Die betroffenen Vertragstests werden Pflichtbestandteil derselben Studio-CI. |
| P1 | v15 und der Runtime-Guard `tayvoriq_german_hyphen_guard` überschreiben v11s Normalisierung. Dadurch ging die Story bei der Formatwandlung verloren. Der Szenensplit trennte die Ursache vom Folgesatz. | Story in der Normalisierung erhalten und ausdrücklich kausale Passagen im Szenenplan zusammenhalten. Weitere nachgelagerte Formatwandlungen und Renderbeleg bleiben abzudecken. |
| P1 | Lifecycle und Recovery verteilen sich auf Orchestrator, Delivery Watch, Continuity, Codefix Builder und Promoter. Mehrere Wege erzeugen Push- oder Dispatch-Ereignisse. | Zentraler Request-Claim und ein Recovery-Router. Aktuelle Trigger vor Umschaltung einzeln über die Matrix prüfen. |
| P1 | In den 150 jüngsten Control-Plane-Commits trugen 110 den Titel `ops: record verified lifecycle decision`, 27 `ops(tayvoriq): refresh control center health`. Aktiver Pointer `ACTIVE`, Request `DISPATCHED`, Lifecycle `BLOCKED`, Ops-Incident `RECOVERY_CODEFIX_REQUIRED` beschreiben denselben Porsche-Run aus verschiedenen Dateien. | Status aus einer verbindlichen Request-Quelle ableiten und reine Polling-Updates außerhalb des Codebranches speichern. |
| P2 | Gerenderte Review-Videos, Plattformpakete und ältere Versionen besitzen zahlreiche historische Namensvarianten. | Artefaktmanifest mit SHA-256, Plattform, Gate und Zustellnachweis. Historische Links und Dateien bis zur Rückrollprobe erhalten. |

## Zustands- und Ownership-Matrix für den Zielpfad

| Zustand | Owner | Nächste Aktion und Beleg |
| --- | --- | --- |
| `APPROVED` | Control Plane | Request einmalig beanspruchen und gebundene Quellen samt Hash prüfen |
| `SOURCES_VALID` | Studio | Geprüftes Skript mit Quellenreferenzen und Story-Format erzeugen |
| `SCRIPT_READY` | Studio | Deutsche Stimme und Aussprache prüfen und persistieren |
| `AUDIO_READY` | Studio | Szenen und Material samt Provenienz und Timing prüfen |
| `VISUALS_READY` | Studio | Musik, Untertitel und Plattformpakete zu validen MP4s rendern |
| `MASTER_READY` | Studio | Finales Inhalts-, Medien- und Plattform-Audit ausführen |
| `QUALITY_PASSED` | Control Plane | Genau dieses Review zustellen, Quittung mit Request, Run und Master verknüpfen |
| `REVIEW_DELIVERED` | Control Plane | Plattformfreigabe für dieses Review abwarten und dedupliziert verarbeiten |
| `PUBLISHED` | Control Plane | Plattformquittungen speichern und Auftrag abschließen |
| `SOURCE_FAILED`, `SCRIPT_FAILED`, `AUDIO_FAILED`, `VISUAL_FAILED`, `RENDER_FAILED`, `QUALITY_FAILED` | Studio für Fehlerbeleg, Control Plane für Recovery | Nur einen als transient eingestuften, betroffenen Schritt aus gültigen Checkpoints erneut ausführen. Bei deterministischem Defekt nach `CODE_DEFECT` übergeben. |
| `DELIVERY_FAILED` | Control Plane | Zustellresultat abgleichen. Sicher bestätigte Fehlzustellung begrenzt erneut versuchen; unbekannte Ausgänge vor erneutem Versand aufklären. |
| `EXTERNAL_BLOCKER` | Control Plane | Den belegten Blocker mit Request und betroffenem Gate dokumentieren |
| `CODE_DEFECT` | Control Plane | Nach einem geprüften PR denselben Request am gescheiterten Schritt fortsetzen |

Checkpoint-Schlüssel müssen Request, Quellenhash, Eingabeartefakt-Hashes und stufenspezifische Implementierung binden. Approval und Publishing verwenden eigene Idempotenzschlüssel. Vorhandene Publish-IDs und Telegram-Quittungen sind beim Import Terminalbelege. Ein gemeinsamer atomarer Claim muss auch zwischen unterschiedlichen Workflows gelten. Ein reiner GitHub-Concurrency-Name innerhalb eines Workflows genügt für diese Übergangsphase nicht.

## Migration und Rollback

1. Read-only Baseline und Inventar sichern. Status-, Replay- und Editorial-Korrekturen in kleinen Draft-PRs verifizieren. Die zwei produktiven Branches und der Control-Pin sind separate Rückrollpunkte.
2. Auf isolierten Ständen den Review-Vertrag beweisen. Ein Kandidatenlauf muss Schreibziele und externe Seiteneffekte explizit begrenzen. Der bestehende Workflow setzt und pusht Betriebszustände nach `main` und veröffentlicht eine Review-Seite auf einem separaten Pages-Repository. Ein Start auf einem anderen Branch isoliert diese Seiteneffekte allein nicht.
3. Kanonische Render- und Review-Einstiegspunkte konsolidieren. Für jedes Runtime-Override zuerst ausgeführte Funktion, Reihenfolge und Regression sichern, dann den notwendigen Code in den kanonischen Pfad verlagern. Die Zielzahl ist sechs Kernworkflows für Freigabe/Dispatch, Produktion, Recovery/Orchestrierung, Review, Veröffentlichung und CI/Monitoring. Worker-Deployment kann separat bleiben, sofern es reine Infrastruktur ist.
4. Den freigegebenen Porsche-Request mit gleichem Quellenhash und Content-Angle als historischen Review-Referenzfall bis zur Videoquittung führen. Aktualität und Freigabe für eine spätere Veröffentlichung separat prüfen. Kein Test erhält eine Veröffentlichungsfreigabe.
5. Drei unterschiedliche, aufeinanderfolgende echte Reviews mit MP4, bestandenem Audit und Telegram-Nachrichten-ID belegen. Erst dann Legacy-Trigger reversibel deaktivieren, Workflow-Dateien und Branch-Pins archivieren und Rückrollprobe ausführen. Eine finale Löschung bleibt außerhalb dieses Migrationsschritts.

## Testbasis und Grenzen

Der lokale Control-Plane-Basislauf hatte 359 bestandene und fünf fehlgeschlagene Python-Tests. Die fünf Basisfehler betreffen Audience Growth, Editorial-Semantik und drei historische Recovery-Erwartungen. Die vier Node-Tests für den Telegram-Worker bestanden. Die Studio-Editorial-CI am Referenz-SHA zeigte `test_scene_plan_is_explanatory_and_not_uniform` und `test_story_first_v2_uses_narrative_body_without_losing_fact_contract`. Die gezielten Nachtests sind in den PRs dokumentiert. Laufzeitbelege für Live-Stimme, reale Visuals, Telegram-Zustellung und Plattformveröffentlichung sind eigene Abnahmeschritte.
