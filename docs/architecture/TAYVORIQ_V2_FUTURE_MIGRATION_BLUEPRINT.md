# TAYVORIQ 2.0 – Zukunftsarchitektur (Vorbereitung, kein Cutover)

**Stand:** 2026-11-14  
**Status:** Vorschlag / Shadow-Readiness / **NICHT PRODUKTIV**  
**Betroffene Systeme:** Control Plane, privates Studio, GitHub Actions, Telegram, Control Center; später gesonderte Hetzner-Instanz, n8n, PostgreSQL.  
**Vorrang:** [Golden Path V4](../TAYVORIQ_GOLDEN_PATH_V4_PROJECT_STANDARD.md), bestehende unveränderliche Telegram-Freigaben und alle verbindlichen Quality-Gates.

## 1. Ziel und Nicht-Ziele

Täglich sollen **bis zu zwei** redaktionell passende deutsche Shorts (Morgen / Abend) entstehen, jeweils nach **Telegram-Trendfreigabe** des Nutzers. Ein fertiger Qualitätsmaster geht zuerst als **Video-Review in Telegram**. **Veröffentlicht wird nur nach einer getrennten ausdrücklichen Freigabe**; ein Review-Empfang ist keine Veröffentlichungserlaubnis. Angestrebt werden ca. 30 Minuten aktive Produktion; 40–45 Minuten dienen vorläufig als Beobachtungs-/Eskalationsbereich, nicht als Zusicherung oder Anlass zum Abschwächen von Gates.

Diese Vorbereitung **kauft keinen Server, aktiviert keinen Scheduler, verschiebt keine Secrets, installiert keine Dienste, versendet keine Telegram-Nachrichten und löst keinen Produktionslauf aus**. Bestehende Requests, Branches, Status-Refs und Recovery-Owner bleiben unverändert.

## 2. Zielsystem und eindeutige Zuständigkeiten

| Baustein | Verantwortung | Darf nicht |
| --- | --- | --- |
| PostgreSQL | Kanonische Aufträge, Slots, signierte/fest gebundene Freigabe- und Outcome-Nachweise, Fencing-Epoch, Eventlog | Erfolg ohne verifizierte Nachweise behaupten |
| n8n (Hetzner) | **Ein** übergeordneter Ablauf-/Timer-Owner; ruft eine testbare Python-Policy auf, dispatcht idempotent, visualisiert die Ausführung | Eigenständig Fachzustände erraten, alternative Recovery-Logik starten oder Qualitätsgates überschreiben |
| Python Decision Engine | Reine und testbare Entscheidung: WAIT / DISPATCH / LOCAL_REPAIR / BLOCKED / REVIEW_READY / PUBLISH_APPROVED / COMPLETE; prüft DB- und Runner-Belege | Themenbindung austauschen, Fehler durch blindes Re-Run kaschieren |
| GitHub Actions | Versioniert gepinnte Ausführung von Script, Voice, Visual, Subtitle, Render, Audits, Review/Delivery; liefert Artefakt-/Gate-Receipts zurück | Selbständig einen zweiten Scheduler-/Recovery-Owner spielen |
| TAYVORIQ Control Center | Lesende Sicht auf identische State-/Gate-Belege, vorläufige Laufzeitmessungen, dokumentierte Freigaben und gesperrte Slots | Aus Workflow-SUCCESS auf Videoerfolg schließen |
| Telegram | Trendfreigabe, Video-Review, **separate Publikationsfreigabe/Ablehnung**, bestätigte Zustellquittungen | Senden als genehmigte Publikation interpretieren |

**Wichtige Entscheidung:** n8n ist der einzige **Prozess-Owner**, aber die **fachlichen Zustandsregeln gehören in testbares Python**, PostgreSQL ist die Wahrheit. Keine parallelen Watchdog-Entscheider. Optional ist eine reine read-only Watchdog-Probe zulässig.

**Infrastrukturgrenzen:** Neuer, separater Server; **keine** Vermischung mit der bestehenden CRM-/Rockatech-Produktionsmaschine. Hetzner CX23 (2 vCPU / 4 GB) ist eine zu messende Startannahme, kein Kapazitätsnachweis. CPU-intensives Rendering bleibt auf einem geeigneten GitHub-Runner. Dauerhafte MP4-/Checkpoint-Aufbewahrung benötigt einen expliziten Speicher-/Retention-Vertrag (GitHub-Artifact-Retention allein nicht als Langzeitspeicher behandeln).

## 3. Unverrückbare Request- und Freigabekette

```text
DISCOVERY -> GEO/EVIDENCE/DUPLICATE GATES -> Telegram Trend APPROVED
-> immutable REQUEST_LOCK -> GitHub preflight + Produktion
-> lokale Reparatur (nur bei belegtem Fehler)
-> PUBLISHABILITY PASS -> FINAL QUALITY PASS
-> Telegram REVIEW_DELIVERED (mit echtem message_id und Master-Hash)
-> Telegram USER_PUBLISH_APPROVED (separate signierte Entscheidung)
-> idempotente Plattformpublikation mit echtem Plattform-Receipt
-> COMPLETED -> nächster zulässiger Slot
```

Pflichtbindung vom Eingang bis zur Veröffentlichung:
`request_id`, `source_request_id`, `trend_id`, `slot`, `telegram_approval_message_id`, `topic`, `content_angle`, `source_context_hash`, `studio_commit_sha`, `run_id`, `attempt`, `recovery_generation`, `master_sha256`. Für Publishing zusätzlich `review_message_id`, `review_hash`, `user_decision_message_id` und `platform_content_id`. Source-/Approval-Hashes dürfen durch Recovery nicht neu erfunden werden.

**Morgen/Abend:** V4 hält den Abendslot gesperrt, bis der Morgenauftrag die vorgeschriebenen verifizierten Erfolgs-Gates inklusive Telegram-Review durchlaufen hat. Ein fehlgeschlagener oder nur „COMPLETED“-GitHub-Workflow entsperrt nichts. Ob die **separate Veröffentlichungsgenehmigung** zusätzlich zur Abendslotfreigabe nötig ist, muss *vor Cutover* explizit festgelegt werden; bis dahin **keine stillschweigende Lockerung** des derzeitigen Slotschutzes.

## 4. Event-/Entscheidungsvertrag (Entwurf)

Alle schreibenden Befehle enthalten:
- `request_id`, `expected_version`, `owner_epoch` (Fencing), `idempotency_key`, `actor`, `event_type`, `observed_at`;
- bei GitHub-Receipts: genaues Repo, Workflow, `run_id`, `attempt`, gepinnte Studio-Revision und die verifizierte Outcome-URI/Hashes;
- bei Telegram-Receipts: Chat-/Message-ID und nachprüfbare Zuordnung zum gebundenen Review-Hash;
- bei Publish: eindeutige Nutzerentscheidung und Plattform-Quittung/Video-ID.

Transaktionen vergleichen `expected_version` und den einzigen gültigen `owner_epoch`; veraltete oder doppelte Events werden idempotent abgelehnt. Externe HTTP-Calls (GitHub/Telegram/Plattform) werden über einen transaktionalen **Outbox-/Inbox-Vertrag** betrieben: zuerst den Befehl sicher speichern, dann senden, Quittung verifizieren, später dieselbe Operation sicher wiederaufnehmen. Bei unbekanntem Telegram-Sendeausgang keine blinde erneute Zustellung.

**Sicherheit:** TLS, nicht öffentlich erreichbare n8n-Adminoberfläche (VPN/Access-Proxy), RBAC soweit verfügbar, eigene Datenbankrolle, Secrets nur in geschütztem Secret-Store/Runtime, regelmäßige verschlüsselte Backups mit Restore-Probe, Firewall/Updates, MFA für Admin-Zugänge. **Kein** Token/Telegram-Chat-Secret im Repository oder Event-JSON.

## 5. Fehlerreaktion statt Retry-Schleife

| Fehlerfamilie | Einzige erlaubte Strategie |
| --- | --- |
| TRANSIENT_NETWORK / PROVIDER_429 | Bounded Backoff innerhalb Budget; dieselbe Freigabe/Request-Bindung |
| DHL/ASR deterministische Textnormalisierung (z. B. „Deh Hah Ell“ vs. „DHL“, „Onlinepreis“ vs. „Online-Preis“) | Testfall, **code-/regelbasierter Fix** und vorhandenes Audio erneut prüfen; **keine** sinnlosen Voll-Retries und keine Absenkung der 0,95-Schwelle |
| VOICE / VISUAL / SUBTITLE / RENDER | Nur defekten Checkpoint reparieren; übrige Hashes/Artefakte erhalten |
| CODE / CONTRACT / INVARIANT | DETERMINISTIC_STOP, minimaler reproduzierbarer Test, isolierter PR, CI, gepinnte Freigaberevision; kein automatischer Live-Code-Patch |
| EVIDENCE / DUPLICATE / TOPIC_STALE | Failsafe BLOCKED; keine neuen Fakten erfinden, ggf. echte neue Themenfreigabe |
| TELEGRAM_OUTCOME_UNKNOWN | Receipt abfragen, nicht doppelt senden |
| PLATFORM_POST_UNKNOWN | Plattformstatus/idempotenten Schlüssel abgleichen, nie zweiten Upload ohne Abgleich |

Messung für jeden Gatewechsel: `started_at`, `last_progress_at`, `ended_at`, `elapsed_seconds`, `queue_seconds`, `retry_seconds`, `reused_checkpoint_count`, `actual_outcome`. Nicht echte Fortschrittsprozente, sondern verifizierte Daten.

## 6. Migration ohne Big Bang (Release-Schalter anfangs aus)

**Phase A – Bestandswahrheit:** Verbindliche Ablaufgrafik und reale Workflow-Owner, Dispatchpunkte, Secret-/Serviceabhängigkeiten, laufende Requests, Kosten und Speicherorte erfassen. Vorherige Auditdokumente unter `docs/golden-path-review/` wiederverwenden. Offene PRs und aktive Requests nicht umlenken.

**Phase B – Datenmodell und Shadow:** PostgreSQL in separater Testumgebung aufsetzen; nur Events und Outcomes aus bestehenden GitHub-/Telegram-Belegen lesend spiegeln. Backfill idempotent; kein Dispatch aus Shadow. Integritätsprüfung: `request_id`, Source-Hash, Studio-SHA, Receipt, Slot-Sperre und Gate-Zustand müssen übereinstimmen.

**Phase C – Trockenlauf:** n8n mit **deaktivierten Produktions-Triggern** und Stub-/Fixture-Receipts verbinden. Mehrfachzustellung, Parallelität, GitHub-Ausfall, 429, ASR/DHL, Render-Reparatur, Crash nach Telegram-Send und Publish-Ablehnung testen. Keine echten Telegram-Befehle/Publikationen.

**Phase D – begrenzter Canary:** Cutover-Sperre & fencing sicherstellen. Neuen Controller **für genau einen explizit autorisierten Testrequest** als einzigen Writer einsetzen; alte Dispatch-/Recovery-Owner für diesen Request nachprüfbar sperren. Master, Telegram-Review und gesonderte Publish-Freigabe prüfen. Keine automatische Kanalveröffentlichung ohne ausdrückliche Nutzerentscheidung.

**Phase E – kontrollierter Cutover:** Erst nach wiederholten End-to-End-Erfolgen, nachvollziehbarer Rollback-Probe und User-Go: die alten Dispatcher/Watcher **inventarbasiert deaktivieren**; n8n übernimmt den einzigen fachlichen Owner. Alte Workflows nur nach Klassifikation entfernen, nicht blind löschen.

**Rollback:** Neuen Dispatch zuerst stoppen; laufende Attempts bis terminalem Outcome abgleichen; DB-/GitHub-Eventversionen und Fencing-Epoch prüfen; **erst danach** alten Owner mit neuer Epoch reaktivieren. Kein doppelter Telegram-Versand oder Plattform-Upload; keine Rücksetzung unveränderlicher Freigaben. Keine Datenbankmigration rückwärts ausführen, die Nachweise zerstört.

## 7. Cutover-Gates

Vor Live-Umschaltung müssen nachweisbar bestanden sein:
1. Tests für exakt gleiche Freigabe, Hash, Run, Version, Owner-Epoch, Double-Dispatch, Late Callback und Duplikat-Receipt.
2. DHL-Normalisierung sowie weitere deterministische Regressionen im aktiven Studio-Commit grün; Audio/Visual/Fakten/Untertitel/Render/Publishability-Gates unverändert.
3. Dokumentierter Replay von GitHub-Run -> Artifact -> Review-Page -> **Telegram-Nachricht mit Message-ID**; echte Publish-Freigabe getrennt.
4. Zwei-Slot-Serialisierung und Fehler-Endzustände `BLOCKED` / `DETERMINISTIC_STOP` nachweisbar.
5. Restore-Test, gemessener RAM/CPU, Secret-/Netzwerksicherheit, Alerts, eindeutiger on-call Ablauf.
6. Keine offenen parallelen Recovery-Schreiber; alle vorhandenen Anbindungen beibehalten, solange keine neue nachweislich dieselbe Funktion übernimmt.

**Technischer Entwurf:** `experimental/tayvoriq-v2/sql/001_request_ledger.sql`. Er ist ein isoliertes Startschema, **nicht** automatisch auf produktive Datenbanken anzuwenden.

## 8. Bewusste offene Entscheidungen

- Nach welchen belegten Bedingungen gilt der Morgenslot als freigabefähig: nur Telegram-Review oder auch getrennte Nutzer-Publish-Entscheidung? V4 nicht ohne explizites Go ändern.
- Dauerhafter Speicher für MP4s/Checkpoint-Artefakte; Aufbewahrung, Löschung, Kosten.
- Finales n8n-vs-Python-Verhältnis: n8n nur Koordination, **niemals** paralleler Fachcontroller.
- GitHub-Runner-Eignung und echte Kosten/Laufzeiten nach Messung statt Annahmen.
- YouTube-Upload-Receipt live nachweisen; TikTok nicht als automatisch veröffentlicht melden, bevor eine Plattform-ID existiert.

**Gültigkeitsgrenze:** Dieses Dokument ist eine **Vorbereitung**, kein Beweis für fertige Implementierung, eine aktive Hetzner-Instanz oder die Behebung aktueller Produktionsfehler.
