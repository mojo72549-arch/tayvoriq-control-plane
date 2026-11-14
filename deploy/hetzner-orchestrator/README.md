# TAYVORIQ: zukünftiger Hetzner-/n8n-Orchestrator (SHADOW, NICHT AKTIV)

**Stand: 2026-11-14. Dies ist eine vorbereitete Option, kein Produktiv-Rollout.**
Diese Dateien starten bei Erstellung/PR/Merge **keinen** Server, Workflow, Retry, Telegram-Versand oder Upload.
Der vorhandene Golden Path und seine Freigabe- und Qualitätsgates bleiben allein zuständig.

## Entscheidung und Budget

- **Wozu?** Visueller Workflow, laufende Statushistorie, ein eindeutiger Recovery-Owner, nachvollziehbare Laufzeitbudgets.
- **Wofür nicht?** Keine lokale Audio-/GPU-/Videoerzeugung auf einem kleinen CX23. Video und Qualitätsgates bleiben vorerst bei den vorhandenen Runnern.
- **Ansatz:** eigener kleiner Server, n8n + PostgreSQL (ohne Redis/Queue-Sonderarchitektur), bestehendes TAYVORIQ Control Center als nutzerorientierte Oberfläche, Telegram als Freigabekanal.
- **Kostenbremse:** etwa 8–10 EUR/Monat als Ziel für den reinen Steuerungsserver; Preis und Backups/IP vor Bestellung neu prüfen. Bestehenden CRM-Server nicht mitbenutzen, keine neue GPU oder bezahlte API durch diesen PR.
- **Performance:** Zielwert ~30 Minuten von Trendfreigabe bis Telegram-Review, p90-Ziel <=45 Minuten **erst nach Messung/Optimierung**. Mehr Serversteuerung macht den Video-Renderer nicht von selbst schneller.

## Architektur und die eine Wahrheit

```text
Telegram Trend-Freigabe
  -> [einziger kanonischer Request-/Approval-State, Hashes, Owner-Lease]
  -> Quellen-/Dubletten-Gate (Runner)
  -> Skript / Voice / Visual / Render (Runner, Checkpoint-Artefakte)
  -> Publishability + finale Quality-Gates (Runner)
  -> Telegram-Video-Review (echte message_id und review_hash)
  -> USER-VERÖFFENTLICHUNGSFREIGABE (authenticated, bound)
  -> bestätigte Plattform-IDs
n8n später: NUR ein Lifecycle-Controller; kein zweiter neben GitHub.
Control Center: lesende Darstellung des kanonischen Status, keine eigene Erfolgslogik.
```

Bestehende Verträge in `docs/TAYVORIQ_GOLDEN_PATH_V4_PROJECT_STANDARD.md` sowie die
bereits gemergten PRs #229 (Evidence) und #230 (atomare Request-Transition) **wiederverwenden**,
keinen konkurrierenden Zustandsautomaten erfinden. Die #230-Adapter sind noch nicht live integriert.

Verbindliche Identität pro Lauf:
`request_id`, `source_context_sha256`, `contract_sha256`, `approval_key`,
`run_id`, `run_attempt`, `recovery_generation`, `studio_sha`,
`owner`, `last_successful_gate`, `active_gate`, `next_action`,
`observed_at`, `run_url`. Für Review/Release zusätzlich `quality_gate_receipt`,
`telegram_message_id`, `review_hash`, Nutzerfreigabe und Plattform-Receipt.

**Kein Erfolg durch Prozentanzeige, Workflow-SUCCESS oder technische Telegram-Meldung.**
`REVIEW_DELIVERED` erst mit bestandenem End-Gate, Mediennachweis und Telegram-Review-Sendequittung;
`PUBLISHED` nur nach authentifizierter, zum Review-Hash passender Freigabe und
verifizierter Plattform-ID je tatsächlich veröffentlichter Plattform. Nicht integrierte
Plattformen bleiben ausdrücklich `NOT_PUBLISHED` oder `MANUAL_HANDOFF`.

## Fehlerbehandlung (nicht verhandelbar)

| Klasse | Entscheidung des künftigen einzigen Orchestrators |
| --- | --- |
| Kurzzeitiger Provider-/Netzwerkfehler | Begrenzter Retry mit Backoff/Jitter und Circuit Breaker |
| `TRANSCRIPT_NORMALIZATION_DEFECT` | Deterministischer **Stopp**, Regressionstest + passender Studio-Commit; **keine** unveränderten Voice-Retries |
| Voice-/Visual-/Subtitle-/Render-Defekt | Nur betroffene Checkpoints ersetzen; unveränderte Hashes/Quellen/Assets behalten |
| Unklare Telegram-Zustellung | Receipt abgleichen; kein Blindversand, keine doppelte Freigabe |
| Quellenfehler, Duplicate, EXPIRED | Fail closed, **niemals** still reaktivieren |
| Codefix | CI + revisionsgebundener Patch + getesteter Production-Green-SHA, dann exakt gebundener Replay |
| Timeout/Retry erschöpft | `BLOCKED` + konkrete Ursache + Run-Link, kein Pseudo-`SUCCESS` |

Single writer / lease pro Request + idempotente Transition (`request_id`, Gate,
Attempt, Event-ID) verhindern parallele Recovery. Gate-Verschärfung niemals umgehen.
Autonom heißt reproduzierbare Reparatur und sichere Eskalation, nicht beliebige
Codeänderungen oder automatische Veröffentlichung.

## Umsetzung in vier getrennten Freigabephasen

1. **Vorbereitung (dieser PR):** isolierte, NICHT angeschlossene Compose-Vorlage und Betriebsvertrag. Keine Produktions-YAML, Secrets, Request-Pointer oder Schedules ändern.
2. **Beobachtermodus:** Server separat bereitstellen; TLS-/Zugriffsmodell prüfen; n8n liest ausschließlich GitHub-Run-/Receipt-Belege und bildet die echte Gate-Historie ab. Keine Schreib-Tokens, keine Dispatch-/Retry-/Telegram-Nodes, keine Automation zur Veröffentlichungsentscheidung. Gegen Control Center und GitHub vergleichen.
3. **Kontrollierter Cutover (eigene PR + explizite Freigabe):** PostgreSQL-Transaktions-/Lease-Adapter und atomare Transition für den kanonischen State implementieren; GitHub-Dispatch/Telegram-Callback-Antworten idempotent binden. **Alte GitHub-Controller/Recovery-Schedules vor Aktivierung des neuen Schreib-Owners deaktivieren**, Owner-Wechsel atomar und rückrollbar, bereits aktive Requests vorher sicher abschließen/abgrenzen. Nie zwei gleichzeitig schreibende Orchestratoren.
4. **Produktionsnachweis:** Mindestens drei kontrollierte, aktuelle E2E-Läufe (Normalpfad, lokal reparierbarer Fehler, Codefix/Blocker); jeweils vollständiger Master + Qualitätsbeleg + Telegram-Review-`message_id`, Nutzerentscheidung/Upload getrennt belegen. Erst danach neue tägliche Slots über neue Steuerung aktivieren. Bei Misserfolg auf alten, vorher nachweislich funktionsfähigen Owner zurück, ohne alten Request erneut zu senden.

## Setup-Vorlage (noch nicht ausführen, bis Server bewusst bestellt und gehärtet ist)

- Linux-Host separat betreiben (kein CRM auf derselben VM), SSH-Schlüssel, Sicherheitsupdates,
  Firewall nur für SSH via eingeschränkten Zugang, Container-/Systemlogs rotieren.
- Verifizierte, konkrete **Versions-Tags oder Image-Digests** für n8n und PostgreSQL festlegen.
  `.env.example` in lokale `.env` kopieren und je ein **verschiedenes** langes Zufallssecret
  für `POSTGRES_PASSWORD` und `N8N_ENCRYPTION_KEY` einsetzen; `chmod 600 .env`.
  Niemals .env, DB-Backups oder Telegram-/GitHub-Tokens in Git, Workflow-Exports oder Logs.
- Erst auf bewusst freigegebenem Host: `docker compose --env-file .env config` prüfen,
  danach `docker compose --env-file .env up -d`. Docker und Compose müssen vorhanden sein.
- Die n8n-Oberfläche wird absichtlich nur an **127.0.0.1:5678** gebunden;
  keine externen Webhooks. Fernzugriff nur per gesichertem Tunnel oder separat
  eingerichteter HTTPS-Zugangsschicht mit Zugangsschutz. Kein öffentliches Port 5678.
- N8N-Owner initial sicher einrichten, MFA aktivieren, keine fremden Community-Nodes,
  n8n-Sicherheitsaudit prüfen. n8n- und PostgreSQL-Datenvolumes **beide** sichern;
  restaurierbare Backups regelmäßig testen; Encryption Key gesondert sichern.
- Auf 4 GB RAM überwachen: RAM/Swap, DB-Disk, HTTP-Latenzen, Backup-Dauer.
  Keine MP4s in PostgreSQL oder n8n-Ausführungsdaten speichern: nur IDs, Hashes,
  Receipts, URLs und Referenzen. Große Artefakte bleiben beim Render-Worker.

## Abnahmekriterien und Soll-Laufzeiten

- **Shadow-Akzeptanz:** GitHub-Run-State, Gate-State, Request-ID, SHA, Fehler und Quittungen
  stimmen mit dem Observer überein. Bei Abweichung meldet n8n `UNKNOWN`, nicht `GREEN`.
- **Single-owner-Akzeptanz:** exakt ein aktiver Writer; Crash/Restart und doppelte Events
  führen nicht zu doppelten Retries, Telegram-Nachrichten oder Uploads.
- **Quality-Akzeptanz:** keine Schwellenwert-Senkung, keine neue Trendfreigabe für
  alten EXPIRED-Request, Veröffentlichung ausschließlich nach Telegram-Nutzerfreigabe.
- **Performance-Akzeptanz:** p50/p90 je Phase messen: Queue, Setup, Quellen,
  Skript, Voice, Visual, Render, Quality, Telegram. Ziele 30/45 Minuten
  beziehen sich auf **Review-Zustellung**, nicht auf CI-Test oder Workflow-Start.
  Ein 40-Minuten-Gesamtziel nach einem Fehler ist nur bei lokal behebbaren Defekten
  realistisch und darf niemals gegen die Quality-Gates durchgesetzt werden.

## Status / offene Aufgaben

- [x] Isolierte Compose-/Environment-/Betriebsvorlage im PR.
- [ ] Eigener Server gekauft/bereitgestellt: **NEIN**.
- [ ] n8n live installiert: **NEIN**.
- [ ] Read-only GitHub-Evidence-Adapter und visuelles Workflow-Dashboard: **NICHT IMPLEMENTIERT**.
- [ ] Schreibender Orchestrator / Cutover: **NICHT AKTIVIERT**.
- [ ] Performance- und E2E-Nachweis auf dieser Architektur: **NOCH NICHT ERBRACHT**.
