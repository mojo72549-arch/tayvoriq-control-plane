# TAYVORIQ – inkrementelles Architektur-Refactoring
Stand: 2026-10-19 · Status: Arbeit im isolierten Refactoring-Branch

## Nicht verhandelbares Nutzerziel
Telegram-Trendauswahl -> unveränderlicher freigegebener Request -> Quellen und Dubletten -> technische Vorbereitung -> Skript/Sprache/Visuals/9:16-Master -> strikte Qualitätsprüfung -> Video über Telegram zur Nutzerfreigabe -> nach Nutzerfreigabe verifizierter YouTube-Upload. TikTok wird derzeit als MP4 + Caption manuell bereitgestellt; ein automatischer TikTok-Publisher ist ein separater, noch nicht nachgewiesener Integrationsschritt.

Die derzeitige Sperre durch telegram-3401-trend-1 darf beim Umbau nicht still gelöst, umgeschrieben oder umgangen werden. Keine Qualitäts-Gates abschalten, um einen Lauf grün zu melden.

## Ausgangsbefund (GitHub-Laufdaten, keine Vermutung)
- Golden Path 38249921806 vom 12.10.2026: Produktion erreicht, vor dem finalen Render scheitert die Sprach-/Transkriptprüfung an POST_AUDIO_QUALITY_GATE_BLOCKED:pre-render-transcript-contract-failed. Eigennamen wie Cariad werden uneinheitlich transkribiert. Kein publishbarer Master.
- Delivery Watch 38252226552 vom 12.10.2026: NameError wegen os.environ ohne import os im inline Retry-Binder; der Wiederholungsversuch scheitert.
- Lifecycle 39272999168 vom 19.10.2026: BLOCKED / EXECUTOR_COMPLETED_WITHOUT_REQUEST_PROGRESS. Wiederholte Status-Commits sind kein Produktionsfortschritt.
- Stand heute: Request telegram-3401-trend-1 bleibt in ACTIVE / DISPATCHED, quality-gates unverändert; Telegram-Auslieferung und YouTube-Upload sind nicht erreicht.

## Zielarchitektur (schrittweise, kein Big-Bang)
1. **Request Contract:** Ein versionierter, unveränderlicher Freigabe- und Quellenkontext; eindeutige request_id, run_id, attempt und recovery_generation; nie neue Themenwahl während Recovery.
2. **Lifecycle Controller:** Einziger fachlicher Dispatcher; entscheidet deterministisch START/WAIT/RECOVER/BLOCKED/REVIEW_READY auf Basis verifizierter Zustandsbelege statt Workflow-Abschluss oder Prozentanzeige. Derzeit in tools/tayvoriq_lifecycle_controller_v1.py.
3. **Recovery Engine:** Fehlerklassen VOICE, VISUAL, SUBTITLE, RENDER, AUDIT, CONTROL_BINDING, DETERMINISTIC_CODE, EXTERNAL. Ein benannter Owner pro Request, bounded retry, stabile Signatur und Checkpoint-Wiederverwendung. Workflow-YAML orchestriert nur, Fachlogik wird in testbare Python-Module ausgelagert.
4. **Media Pipeline:** Stimme, Bildbelege, Untertitel und Render als separate Artefakt-Checkpoints mit eindeutiger Version und Prüfrechnung. Eigennamen-Transkriptprüfung mit Ground Truth und gezielter Sprachreparatur testen, nicht Schwellen pauschal absenken.
5. **Delivery Ledger:** Review-URL, Telegram-Sendequittung, eindeutige Nutzerentscheidung, YouTube-Video-ID/Upload-Quittung pro request_id. Idempotente Plattformveröffentlichung und keine Doppel-Uploads. TikTok-Automatisierung erst nach verifizierter Plattformanbindung.
6. **Observability:** Ein maschinenlesbarer Status mit last_successful_gate, active_gate, failure_class, retry_budget, owner, last_progress_at, next_action. Ein fehlerhafter Recovery-Executor muss eigene FATAL/NEEDS_CODEFIX-Ausgangsbedingung melden; keine endlosen HEALTH-Commits.

## Inkrementeller Lieferplan
- **Slice R1 (dieser Branch):** Same-run-Retry-Binding aus Inline-Python lösen; canonical owner, approval und immutable hashes prüfen; aktuellen Golden-Path-Versuch explizit übergeben; atomare JSON-Aktualisierung; Idempotenz und Fail-Closed-Tests. Zusätzlich GitHub-Rerun nur mit exakter N+1-Acknowledgment-Quittung und Schutz gegen doppeltes Dispatch. Keine automatische Production-Aktivierung.
- **Slice R2:** Sprach-/Transkript-Gate analysieren und gezielte Eigennamen-/ASR-Reparatur in Tests nachstellen. Publikationsstandard beibehalten. Studio-Fixkandidat: `mojo72549-arch/shorts-agent-studio` PR #299 (Basis: zuletzt verifizierter Production-Green-SHA `edf226a307fd1ccb746eb8b6583a1695e27ea792`), mit eng begrenzten Cariad-Ausspracheformen und unveränderten >=0,95 ASR-/Postmux-Gates. Aktuell noch keine vollständige Produktionsfreigabe oder behobener Workflow-Stillstand.
- **Slice R3:** Retry-Policy und Lifecycle-Controller auf gemeinsamen typed Decision Contract führen; kein Churn zwischen Delivery Watch, Codefix, Orchestrator.
- **Slice R4:** Master/Review/Telegram/YouTube mit Receipt-Ledger und Recovery nach Crash; TikTok als eigene Integrationsentscheidung.
- **Slice R5:** End-to-End-Probelauf mit nachweisbaren Artefakten; kontrollierte Freigabe nach main; vorhandenen gebundenen Auftrag nur nach Frischeprüfung des Nachrichtenanlasses fortsetzen.

## Qualitäts- und Rollout-Gates
- Tests gegen identische Request-IDs, falsche Run-IDs, geänderte Freigaben/Hashes, doppelte Versuche und veraltete Recovery-Generationen.
- Parse-/Syntaxprüfung des geänderten YAML sowie Python-Kompilierung.
- Kein geänderter produktiver State-/Request-Pointer durch PR, Branch oder bloßen Tests.
- Kein GitHub-Workflow-„SUCCESS“ gilt ohne fertigen Master, striktes Quality PASS und Telegram-Review als gelieferter Inhalt.
- YouTube gilt erst nach verifizierter Upload-Quittung als veröffentlicht. TikTok solange ausdrücklich MANUAL.
- Vor Merge: vollständiger Regressionstest plus isolierter kontrollierter Workflow-Test. Nach Merge: aktueller Request nur gemäß Approval-/Recovery-Vertrag behandeln.
