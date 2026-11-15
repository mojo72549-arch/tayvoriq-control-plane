# TAYVORIQ 2.0 – Server-Orchestrierung, vorbereitet (SHADOW)
Stand: 15.11.2026. Dies ist ein isoliertes Vorbereitungspaket. Kein Server wurde gebucht, keine Produktion umgeschaltet, keine Credentials hinterlegt und keine n8n-Automatik aktiviert.

## Ziel
Zwei Shorts pro Tag mit echter Trendfreigabe und einem einzigen fachlich aktiven Slot.
Zielzeit ca. 30 Minuten, angestrebter Regelbereich 40–45 Minuten bis zur verifizierten Telegram-Review-Zustellung. Das sind SLOs, keine garantierten Laufzeiten. Qualität darf niemals für die Uhr abgeschwächt werden.

## Rollen
- Hetzner CX23: dauerhafte, schlanke Steuerung (n8n + PostgreSQL); kein Chatterbox, keine GPU- oder Video-Renderarbeit.
- n8n: visualisierter Workflow, Auftrags- und Timeoutsteuerung. Fachliche Entscheidungen werden von einem versionierten State-/Recovery-Vertrag erzwungen.
- PostgreSQL: verbindlicher Auftragszustand, atomare Owner-Claims, append-only Ereignisse und Zustellquittungen.
- GitHub Actions: bestehende Python-Produktion, Audio/Visual/Render, Qualitätsprüfungen als Worker. Kein konkurrierender Produktions- oder Recovery-Owner nach Cutover.
- Control Center: einzige nutzerorientierte Statusoberfläche; n8n ist Technikansicht.
- Telegram: Trend auswählen, geprüftes Video erhalten, anschließend Veröffentlichung freigeben oder ablehnen. Nie automatisch öffentlich posten.

## Verbindliche Stationen
GP-00 Trendfreigabe → GP-10 Request-Lock → GP-20 Quellen/Dubletten → GP-30 Preflight
→ GP-40 Studio-Produktion → GP-50 lokaler Repair (nur bei Bedarf)
→ GP-60 Publishability → GP-70 Final Quality → GP-80 Telegram-Review
→ GP-90 ausdrücklich freigegebene Veröffentlichung.
Morgen-/Abendlauf bleiben gemäß Golden-Path-Projektstandard serialisiert:
Ein Abendlauf bleibt HELD, bis der Morgen-Review erfolgreich zugestellt wurde.
STATE BEFORE PERCENTAGE: Prozentangaben sind nie eine Erfolgsquittung.

## Kanonische Zustände und Belege
APPROVED → SOURCES_LOCKED → PREFLIGHT_PASSED → PRODUCTION_RUNNING
→ MASTER_PUBLISHABLE → QUALITY_PASSED → REVIEW_READY → REVIEW_DELIVERED
→ AWAITING_PUBLICATION_APPROVAL → PUBLISHING → PUBLISHED.
Terminal / Stop: BLOCKED, EXPIRED, REJECTED, CANCELLED.
Für REVIEW_DELIVERED ist eine bestätigte Telegram-Video-/Review-Message-ID mit exaktem Artefakt-Hash erforderlich.
Für PUBLISHED sind ausdrückliche, an den Review-Hash gebundene Nutzerfreigabe und echte Plattform-ID/URL erforderlich.
Ein grüner GitHub-Run oder eine Telegram-Fortschrittsmeldung genügt nicht.

Unveränderliche Request-Schlüssel:
request_id, slot, selection_id, approval_message_id, approved_at,
source_context_sha256, contract_sha256, studio_sha, owner_epoch.
Jedes Workflow-Ereignis protokolliert: event_id, request_id, run_id,
run_attempt, stage, stage_status, started_at, finished_at, expected_output,
actual_evidence, artifact_sha256 (sofern vorhanden), recovery_owner.
Events sind idempotent und append-only. Der Owner-Claim ist atomar; alter
GitHub- und neuer n8n-Orchestrator dürfen niemals denselben Request steuern.

## Recovery-Vertrag
- TRANSIENT_PROVIDER / TRANSIENT_NETWORK: begrenzter Retry mit Backoff.
- VOICE / VISUAL / SUBTITLE / RENDER / AUDIT: nur defekten Checkpoint
  plus abhängige Artefakte reparieren, vorhandene geprüfte Assets erhalten.
- TRANSCRIPT_NORMALIZATION_DEFECT: kein erneuter unveränderter Voice-Run;
  reproduzierbarer Regressionstest, geprüfter Studio-Commit, dann gebundener Replay.
- SOURCE / DUPLICATE / EXPIRED / fehlende APPROVAL: hart blockieren.
- TELEGRAM_AMBIGUOUS: Quittung/idempotenten Versand prüfen statt blind duplizieren.
- PUBLISH_AMBIGUOUS: Plattform-ID abgleichen statt zweite Veröffentlichung starten.
Jede Reparatur protokolliert exakte Ursache, erlaubten Scope, Budget und Ergebnis.
Keine alten EXPIRED-Requests reaktivieren, keine Gate-Abschwächung, kein Themenwechsel.

## Telemetrie und Zeitbudget
Messen statt versprechen: P50/P90 Freigabe→Telegram, Voice-/Render-/Audit-Zeit,
Cache-Treffer, Recovery-Quote, fehlerhafte Erfolgsmeldungen (Ziel null),
tatsächliche €/Video und Zustellquote.
Initiale Zielbudgets: 3 Min Quellen/Preflight, 20 Min Studio, 5 Min Audit,
2 Min Telegram; bis 45 Min Puffer für begrenzte Recovery.
Bei Zeitüberschreitung Ursachenbefund und sinnvolle Korrektur; kein pauschales
hartes Töten einer laufenden validen Produktion, kein Blind-Restart.

## Migrationsphasen (nur mit Nachweisen)
0. Dieser Branch: Compose + leere Secret-Vorlage + verbindlicher Vertrag.
   Keine Kosten, keine produktiven Änderungen.
1. Nach ausdrücklicher Freigabe separaten CX23 bereitstellen: nur privat,
   mit SSH-Schlüsseln, Firewall, Docker/Compose, getrennt vom CRM-Server.
   n8n liest zunächst GitHub- und Telegram-Quittungen nur beobachtend.
   Keine Schreib-Tokens, keine Produktion, keine Veröffentlichung.
2. In isoliertem Feature-Branch signierte Events/Callbacks und DB-Adapter
   entwickeln. Offline-Tests für Idempotenz, Owner-Lock, Telegram-Duplikate,
   deterministischen Codefehler, EXPIRED-Sperre und State-Übergänge.
3. Pilot: exakt EIN neuer Auftrag, atomarer Owner-Wechsel, konkurrierende
   GitHub-Triggers für diesen Request vorher deaktivieren. Publikationsgate
   bleibt 100 % Telegram-gesteuert. Rollback darf keinen Doppel-Owner erzeugen.
4. Erst nach bestandenem echtem E2E-Review, Telegram-Freigabetest,
   Publish-ID-Prüfung, Restart/DB-Restore, belegtem Rollback und mehreren
   erfolgreichen Morgen-/Abendläufen alte Recovery-Orchestrierung abschalten.

## Lokale Einrichtung (noch NICHT ausgeführt)
1. Dateien dieses Ordners auf einen künftig freigegebenen Server übertragen.
2. .env.example nach .env kopieren. Für POSTGRES_PASSWORD und
   N8N_ENCRYPTION_KEY jeweils einen eigenen zufälligen Wert erzeugen,
   beispielsweise mit: openssl rand -hex 32. Datei chmod 600; NIE committen.
3. Eine konkret getestete n8n-Version als N8N_IMAGE_TAG festlegen, nie latest.
4. Im Ordner: docker compose --env-file .env config
   danach erst: docker compose --env-file .env up -d
5. Editor zunächst ausschließlich über SSH-Tunnel auf 127.0.0.1:5678
   nutzen. Bei späterem HTTPS-Zugang N8N_SECURE_COOKIE auf true setzen,
   TLS, Zugriffskontrolle, Secret-Verwahrung und Firewall erneut prüfen.
6. Backup: PostgreSQL, n8n_data und separater Encryption Key; Restore testen.
   Erst danach die read-only Monitoring-Integration aktivieren.

## Budget und offene Punkte
CX23 (2 vCPU/4 GB) ist als Steuerzentrale geplant; Zielbudget 8–10 EUR
monatlich inklusive gewählter IP-/Backup-Optionen. Vor Bestellung tatsächlichen
Bruttopreis und zusätzliche Kosten prüfen. Render-Runner/API-Nutzung ist nicht
durch das Serverbudget abgedeckt. Ressourcenverbrauch und n8n-Version müssen
vor Livebetrieb auf dem konkreten Host geprüft werden.

Noch NICHT implementiert: n8n-Workflow, PostgreSQL-Fachschema, Event-API,
signierte Webhooks, Callback-Adapter, Server, Deploy, Cutover oder Benchmark.
Das Paket allein ist keine neue funktionsfähige Produktionspipeline.
