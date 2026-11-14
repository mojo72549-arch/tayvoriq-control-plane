# TAYVORIQ – vorbereitete CX23-/n8n-Option (NICHT produktiv)
Stand: 14.11.2026 · Phase 0: isolierte, lesende Architekturprobe.

## Zweck und feste Grenzen
TAYVORIQ soll künftig **einen** sichtbaren, dauerhaften Workflow-Owner besitzen:
Telegram-Trendfreigabe → gebundener Request → Quellen/Dublette → Skript/Audio/
Visuals/Render → Publishability → finale Quality → Telegram-Review →
**separate** Nutzerfreigabe → verifizierte Plattformquittung.
Grundlage ist `docs/TAYVORIQ_GOLDEN_PATH_V4_PROJECT_STANDARD.md`.
Keine neue fachliche Pipeline, kein Ersatz der bestehenden Qualitätsprüfungen.

**Dieser Branch ändert keine produktiven Workflows, Runner, Secrets, Request-
Pointer, aktiven Telegram-Bots oder Veröffentlichungsregeln.**
Bestehende aktive/EXPIRED-Requests werden nicht reaktiviert.
Kein Hetzner-Server wurde bestellt, kein Dienst gestartet, kein Token hinterlegt.

## Aufgabenteilung nach einer möglichen Freigabe
- **CX23 + n8n:** sichtbare Zustandsübergänge, Timer und Bedienoberfläche für
  Operatoren; keine KI-Skriptgenerierung und kein Video-Rendering auf 4 GB RAM.
- **Control Plane / Python:** geprüfte fachliche Regeln, Recovery-Entscheidungen,
  atomare Request-Claims und Freigaben. n8n wird nicht zur zweiten State Machine.
- **PostgreSQL:** künftig persistente Ereignisse, Lease-/Fencing- und
  Idempotenzbelege; erst NACH geplantem State-Cutover System of Record.
- **GitHub Actions / Studio:** CPU-intensive Jobs, Checkpoints, Media-/QA-Artefakte.
- **Control Center:** benutzerfreundlicher Blick auf denselben kanonischen State.
- **Telegram:** Trend- und eigenständige Publikationsfreigabe sowie Videoreview.
  REVIEW_DELIVERED braucht richtige Request/Run/Review-Bindung, QA-PASS und
  eine positive Telegram-Review-Message-ID. Status-'green' reicht nicht.
  PUBLISHED braucht die passende explizite Freigabe und Plattform-ID/Quittung.

## In diesem Branch enthalten
- `compose.yaml`: lokale, nicht öffentliche, optionale n8n/Postgres-Umgebung.
- `.env.example`: Platzhalter; keine Zugangsdaten.
- `observer.workflow.json`: **manuell** ausführbarer, reiner Read-only-
  Beobachter des öffentlichen Control-Plane-Pointers und Health-Snapshots.
  Meldet absichtlich KEINEN Review-Erfolg, da der Workflow keine
  authentifizierte Telegram-Quittung prüft. Kein Webhook, kein Dispatch.

## Optionaler Test auf einem EIGENEN Server (nicht auf dem CRM-Server)
1. Eigenen CX23 nur nach Kosten-/Zugriffsfreigabe bereitstellen; Ubuntu
   härten, SSH-Keys, Firewall, Updates, persistentes Backup und Restore testen.
2. `.env.example` lokal nach `.env` kopieren, **verifizierte exakte**
   Container-Versionen und lange zufällige Secrets setzen. .env nicht committen.
3. `docker compose --env-file .env -f compose.yaml config` vor Start prüfen;
   dann optional `docker compose --env-file .env -f compose.yaml up -d`.
4. n8n ausschließlich über SSH-Tunnel auf `127.0.0.1:5678` öffnen;
   öffentliches HTTPS/SSO wäre ein separater Sicherheits-Schritt.
5. `observer.workflow.json` in n8n importieren und manuell ausführen.
   `snapshot_stale=true` ist eine WARNUNG, kein gültiger Run-Beweis.
6. Auch ohne n8n-Start ist der vorhandene Produktivbetrieb unverändert.
Es gibt bewusst keinen Auto-Deploy und keine produktive Scheduler-Aktivierung.

## Nächste isolierte Lieferpakete – vor jeder Umschaltung
1. Authentifizierten, versionsgebundenen Event-/Status-Adapter bauen.
   Dedup-Key: Request + Gate + Event-ID. Quality-/Master-/Review-Quittungen
   nur aus verifizierten Artefakten übernehmen; Transport UNKNOWN bleibt UNKNOWN.
2. Atomare Lease/Claim-Übernahme mit Fencing-Token: genau ein Recovery-
   Entscheider. Legacy-Orchestrator bis zum Cutover ausdrücklich Owner.
   n8n bleibt bis zur Umstellung read-only.
3. Fachliche Recovery-Klassen: transient → begrenzter Retry;
   VOICE/VISUAL/SUBTITLE/RENDER → lokaler gültiger Checkpoint;
   deterministischer Code-/ASR-Normalisierungsfehler → geprüfter Codefix,
   KEIN Blind-Retry; externe Sperre → BLOCKED.
4. Telegram-Review und getrennte Freigabe-/Publish-Receipt-Kette Ende-zu-Ende
   testen. Rückrollpunkt und Kill-Switch dokumentieren. Nach Umstellung
   konkurrierende GitHub-Lifecycle-Trigger gezielt deaktivieren, nicht löschen.

## Abnahmekriterien und Tempo
- Drei aufeinanderfolgende **echte** neue Reviews: 9:16-MP4s + alle
  Pflichtgates PASS + Telegram-Review-`message_id` + Request/Run/Hash-Beleg.
- Publikationsfreigabe ist separat; ohne sie niemals veröffentlichen.
- Keine doppelte Zustellung / kein EXPIRED-Replay / keine Qualitätslockerung.
- Performance messen (Zeit von Trendfreigabe bis Video-Review):
  p50-Ziel 30 Min., p90-Ziel <=45 Min. – erst gemessen als Erfolg bezeichnen.
- 45 Min. sind ein Diagnose-/Eskalationsziel, **kein** Vorwand für Gate-Bypass.
- Zwei Slots pro Tag gemäß Golden-Path-Serialisierung, kein paralleler
  Ersatzauftrag bei laufendem oder blockiertem freigegebenem Request.
- Vor produktivem Cutover: Backup-Restore, Security-Review, Shadow-Run,
  Race-/Replay-/Crash-Tests und nachvollziehbarer Rollback.

## Live-Regressionsbeleg für die spätere Migration (14.11.2026)
Am DHL-Request `telegram-3577-trend-1` ist der Trennstrich zwischen
**Review geliefert** und **öffentlich veröffentlicht** besonders wichtig:
- Golden Path `43611802085`: GitHub `completed/success`, Publishability
  und finale Quality erfolgreich; das Job-Log bestätigt um 15:56 UTC
  die Telegram-**Video**-Quittung `message_id=3621`,
  `review_buttons=True`, `file_size=20897005`.
- Der aktive Pointer stand danach auf `COMPLETED`, die Request-Datei
  jedoch auf `DISPATCHED`, darin `production_completion.state=REVIEW_READY`.
  Der zuvor erzeugte Ops-Health-Snapshot zeigte noch einen alten Zustand.
- **Keine** öffentliche Veröffentlichung ist damit bewiesen.
  Die spätere kanonische State Machine MUSS Review-Zustellung,
  Publikationsentscheidung und Plattformquittung separat führen.
  Snapshot-Staleness und abweichende Records sind sichtbare Warnungen.
