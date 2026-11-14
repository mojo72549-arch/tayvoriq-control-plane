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
