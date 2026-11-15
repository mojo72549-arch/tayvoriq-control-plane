# TAYVORIQ V2 – Readiness- und Cutover-Checkliste (nur Planung)

**Stand: 2026-11-14 | NICHT AKTIVIERT**  
Bezug: [Zukunftsarchitektur](../../docs/architecture/TAYVORIQ_V2_FUTURE_MIGRATION_BLUEPRINT.md), [Golden Path V4](../../docs/TAYVORIQ_GOLDEN_PATH_V4_PROJECT_STANDARD.md).

## A. Vorbereitungszustand

- [x] Architektur mit nur einem künftigen Orchestrator dokumentiert
- [x] Separaten, nicht angewendeten PostgreSQL-Ledger-Entwurf angelegt
- [x] Shadow-/Canary-/Rollback-Stufen mit Abnahmeregeln beschrieben
- [ ] Ist-Workflow-Liste und aktive Trigger gegen Repository-Stand verifizieren
- [ ] Echte laufende/fest gebundene Requests inventarisieren und Cutover-Sperre festlegen
- [ ] Offene Studio-/Control-Plane-Fixes stabil in aktiven Produktion-SHAs verifizieren
- [ ] Sicherheits- und Ressourcenbudget für eigenen Hetzner-Server abnehmen
- [ ] Bindende Festlegung für Morning/Evening und getrennte Publish-Freigabe treffen

## B. Tests vor *jedem* Shadow-Dispatch (Testdaten only)

| ID | Test | Erwarteter Nachweis |
| --- | --- | --- |
| V2-01 | Identischer Telegram-Trend zweimal zugestellt | Ein gebundener Request; zweites Event idempotent |
| V2-02 | Identisches GitHub-`workflow_run`-Signal doppelt | Nur eine Zustandsänderung; kein Doppel-Dispatch |
| V2-03 | Alte `owner_epoch` sendet spätes Ergebnis | Rückmeldung abgelehnt, keine Statusänderung |
| V2-04 | Zwei n8n-Worker konkurrieren | Genau einer erhält die Lease + monotone Fencing-Epoch |
| V2-05 | Source-Hash oder freigegebenes Thema verändert | BLOCKED; keine stillen Rebinds |
| V2-06 | DHL-ASR „Deh Hah Ell“ → „DHL“, „Onlinepreis“/„Online-Preis“ | Deterministische Normalisierung mit exakt passenden Regressionstests; Threshold 0,95 bleibt |
| V2-07 | Provider 429 / Netzunterbrechung | Bounded Retry mit gleichem Request; Budget respektiert |
| V2-08 | Visual-Gate schlägt nach erfolgreichem Voice-Gate fehl | Visual-only Repair; Voice-/Quellen-Hashes unverändert |
| V2-09 | Kontrollierter Crash nach Telegram-Send, bevor Receipt geschrieben ist | Send-Ergebnis als UNKNOWN, Remote-Reconciliation statt blindem Doppelversand |
| V2-10 | Quality-Fail bei existierendem MP4 | Kein Review und keine Publikation |
| V2-11 | Review erfolgreich zugestellt, Nutzer lehnt ab | Keine Plattformveröffentlichung |
| V2-12 | Review zugestellt, aber kein Publikations-OK | Keine Plattformveröffentlichung |
| V2-13 | Nutzer genehmigt Veröffentlichung zweimal | Maximal ein YouTube-Upload, ein bestätigtes Publish-Receipt |
| V2-14 | YouTube-Upload technisch erfolgreich, Quittung verloren | Vor Wiederholung Plattform-ID/Reconciliation prüfen |
| V2-15 | TikTok-Paket erstellt ohne automatischen TikTok-Post | Nicht als veröffentlicht melden |
| V2-16 | Morgen-Request scheitert nach Workflow-SUCCESS | Abendslot bleibt HELD |
| V2-17 | Morgen-Review zugestellt | Slotschutz ausschließlich gemäß zuvor abgenommener V4-Regel |
| V2-18 | Neuer Owner wird zurückgenommen | Erst altes Lease-/Runner-Outcomes reconciliert, dann kontrolliert neue Epoch |
| V2-19 | SQL-Backup zerstörungsfrei zurückgespielt | Daten-/Belegintegrität und RPO/RTO gemessen |
| V2-20 | Veraltetes Studio-SHA vs freigegebener CI-Fix | Kein vermeintlich reparierter produktiver Run; Revision explizit bestätigt |

## C. Live-Abnahmereihenfolge (noch kein Termin)

1. **Read-only Shadow**: keine Telegram-, GitHub- oder Publish-Schreiboperation; Belege und Zustände vergleichen.
2. **Isolierter Simulationsauftrag**: alle V2-01 bis V2-20 Tests mit Fakes und echten konkurrierenden DB-Transaktionen.
3. **Ein autorisierter Canary**: exakt eine neue Freigabe, ein Prozess-Owner, echte MP4-/Gate-/Telegram-Quittungen, getrennte Publish-Entscheidung.
4. **Stabilitätsfenster**: mehrfache vollständige Referenzproduktionen mit gleicher Qualitätsgrenze; Ausfall- und Rückkehrtest.
5. **Eigener Cutover-Change**: inventarisierte alte Schreiber stoppen, neue Lease mit Fencing setzen, neue aktive Version kontrollieren, echte Ende-zu-Ende-Receipts belegen.
6. **Rollback-Drill**: kein doppeltes Veröffentlichen; kein Verlust von ursprünglichen Approvals, Quellen und Artefakten.

## D. Freigabekriterien (Go / No-Go)

**GO nur wenn alle Punkte grün sind:**
- [ ] Qualitätsprüfungen, DHL-/Sprachregression, Merge-/Studio-SHA + Produktionsreferenz geprüft
- [ ] Eindeutiger Writer mit Lease/Fencing und atomaren Zustandsübergängen getestet
- [ ] Zwei-Slot-Regel inkl. separater Telegram-Videoveröffentlichung abgenommen
- [ ] Mindestens eine echte End-to-End-Review-Zustellung mit korrekter Message-ID
- [ ] Plattform-IDs als Quittung nach ausdrücklicher Nutzerfreigabe
- [ ] Backups, Restore, Zugriffsschutz, Monitoring und Incident-Stopp belegt
- [ ] Rückfallverfahren eingeübt; alter und neuer Controller nie gleichzeitig Writer
- [ ] Nutzer hat den tatsächlichen Cutover explizit freigegeben

**NO-GO sobald:** kein verifizierter Master, fehlendes Gate, unsicheres Callback, unklarer Owner, Datenbankinkonsistenz, keine echte Telegram-Quittung, nicht verifizierte Publikation oder gestiegene Doppel-Dispatch-Gefahr.

**Hinweis:** Diese Checkliste erzeugt weder Produktiv-Authentifizierung noch aktive Infrastruktur. Der SQL-Entwurf ist nicht getestet und nicht angewendet.

## E. Konsolidierung der bereits vorhandenen Vorbereitungs-PRs

**Entscheidung für die spätere Umsetzung: genau EINE Pilot-Implementierung, keine drei parallelen Orchestratoren.**
Dieser Blueprint (#237) ist der fachliche Abnahmevertrag; die zwei älteren offenen
Prototypen sind nur Bausteinquellen, **keine zusätzlichen produktiven Systeme**:

- **#235** (`plan/hetzner-n8n-shadow-20261114`): gehärtete CX23-Compose-/Backup-/Betriebsvorlage übernehmen und nach realer Docker-/Security-Prüfung aktualisieren.
- **#236** (`plan/tayvoriq-cx23-readonly-orchestrator-20261114`): manuell deaktivierten, rein lesenden n8n-GitHub-Beobachter als Ausgangspunkt übernehmen. Der Observer liefert **keinen** Telegram-Review-Nachweis und darf nie aus `ops-health.green` einen Review-Erfolg ableiten.
- **#237** (dieser PR): fachliche Architektur, unveränderliche Freigabebindung, PostgreSQL-Ledger-Entwurf, 20 Abnahmetests und Cutover-Kriterien. SQL **nicht** produktiv anwenden.

Vor einem zukünftigen Merge die beiden Pilotskizzen **in genau einen neuen, isolierten Implementierungs-PR konsolidieren** und die älteren alternativen PRs nach Codeübernahme schließen. Kein paralleler `compose up`, keine drei State-Stores, keine neuen produktiven GitHub-Schedules durch diese Planung. Die bereits gemergten #229 (Ergebnisnachweise) und #230 (atomare Request-Transitions) sind **bestehende Verträge**, die integriert statt neu erfunden werden. #231 bleibt ein separater Referenzbeleg, kein Ersatz für Live-Abnahme.

### Minimaler Pilot – überprüfbare Reihenfolge

1. **Kostenentscheidung getrennt:** Eigenen CX23 nur nach gesonderter Bestellung/Freigabe; CRM-Server unberührt. n8n + PostgreSQL, kein GPU-Rendering auf 4 GB RAM. Budget 8–10 EUR/Monat als Ziel für die Steuerung, nicht für KI-/Runner-/Medienkosten.
2. **Offline-Abnahme:** Compose-Konfiguration und Image-Digests prüfen; `n8n`-Export auf deaktivierten Trigger, ausschließlich GET und fehlende Schreib-Credentials kontrollieren; getrennte DB/n8n-Backups + Restore nachweisen.
3. **Read-only Shadow:** `request_id`, Hashes, `run_id`, `run_attempt`, `studio_sha`, Gate- und Telegram-Receipts aus echten GitHub-Daten visualisieren. Veraltete oder widersprüchliche Zustände sind `UNKNOWN`, niemals `SUCCESS`.
4. **Synthetische Race-/Failure-Tests:** V2-01 bis V2-20 einschließlich DHL-ASR 0,95, Doppel-Callback, Fencing, Crash nach Telegram-Send, Ablehnung und EXPIRED. Alle ohne echte Telegram-/Plattformaktionen.
5. **Gesperrter Canary:** Explizit freigegebener neuer Auftrag; alter Writer für diesen Auftrag nachweislich aus; SHA-gebundener Runner und unveränderte Python-Gates; Telegram-Review nur mit echter `message_id`, Plattform-Upload nur nach separatem Nutzerentscheid.
6. **Cutover nur mit GO:** Mehrfacher vollständiger End-to-End-Nachweis, Restore- und Rollback-Test und separate Nutzerfreigabe. Bei Misserfolg keine parallelen Recovery-Owner starten.

### Messbarer Nutzen statt weiterer Skriptsammlungen

- Startpunkt: **verifizierte Trendfreigabe**; Endpunkt: **bestätigte Telegram-Video-Review-Zustellung**, nicht GitHub-Workflow-SUCCESS.
- Zielwerte zur späteren Prüfung: **p50 ca. 30 Minuten, p90 höchstens 45 Minuten**. Bei nicht behebbarem deterministischem Fehler sicher blockieren; nie Quality-Gates senken, um die Zeit zu erreichen.
- Pro Stage messen: Queue-/Cold-Start, Quellen, Skript, Voice, Visuals, Render, finaler Quality-Gate, Telegram-Transport; Zeit und Kosten auch bei gescheiterten Versuchen.
- Recovery-Budget begrenzen: nur betroffene Checkpoints, Retry ausschließlich bei transientem Fehler; identischer Code/identische Inputs bei deterministischem Fehler dürfen nicht wiederholt gerendert werden.
- Produktiv-Status `REVIEW_DELIVERED` nur nach positivem QA-/MP4-/Telegram-Receipt; `PUBLISHED` nur nach gebundener Nutzerfreigabe **und** Plattform-ID. Fehlende Quittungen bleiben `UNKNOWN/BLOCKED`.

**Stand:** Nur GitHub-Vorbereitung. Kein eigener Server, kein produktiv aktives n8n, kein Cutover und keine neue Videozustellung durch diese Änderung.
