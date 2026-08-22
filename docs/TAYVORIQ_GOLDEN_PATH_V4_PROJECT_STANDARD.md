# TAYVORIQ Golden Path V4 – verbindlicher Projektstandard

**Status:** VERBINDLICHER ZIEL- UND BERICHTSSTANDARD  
**Gültig ab:** 2026-08-22  
**Geltungsbereich:** TAYVORIQ Control Plane, Produktionsorchestrierung, Recovery, Telegram-Benachrichtigungen, Morgen-/Abend-Slots  
**Qualitätsprinzip:** Quality-Gates werden nicht abgeschwächt.

## 1. Zweck

Dieser Standard ist die kanonische Architektur- und Betriebsgrundlage für alle weiteren TAYVORIQ-Arbeiten. Neue Änderungen, Hotfixes, Recovery-Mechanismen und Benachrichtigungen müssen gegen diesen Standard geprüft werden.

Das Zielbild lautet:

> **Freigabe in Telegram → immutable Request → evidenzgebundene Produktion → lokalisierte Reparatur → Publishability → finale Quality-Gates → Telegram-Review → Veröffentlichung → Freigabe des nächsten Slots.**

Der Nutzer interveniert nach der Trendfreigabe nicht mehr in technische Produktionsschritte. Nur ein echter externer Blocker oder eine notwendige neue Themenfreigabe darf Benutzeraktion verlangen.

---

## 2. Architekturprinzipien

1. **Single Golden Path Owner**  
   Genau ein Golden-Path-Workflow besitzt die fachliche End-to-End-Produktion eines freigegebenen Requests.

2. **Immutable Request Binding**  
   Thema, Trend, `source_request_id`, Quellenkontext, Content-Angle und Freigabe bleiben über Produktion und Recovery eindeutig gebunden.

3. **State before Percentage**  
   Der kanonische fachliche Zustand ist die Wahrheit. Prozentwerte sind nur Darstellung und dürfen keine eigene Logik besitzen.

4. **Local Repair before Full Restart**  
   Ein vorhandener verifizierter Checkpoint wird wiederverwendet. Repariert wird ausschließlich der tatsächlich fehlerhafte Pfad, sofern dies sicher möglich ist.

5. **Fail Closed**  
   Wenn Publishability oder ein Pflicht-Gate nicht bestanden ist, darf weder Review noch Veröffentlichung stattfinden.

6. **One Recovery Owner**  
   Pro Request darf zu einem Zeitpunkt nur ein Recovery-Owner aktiv sein.

7. **Bounded Recovery**  
   Kein unbegrenzter Retry-Loop. Recovery ist generationenbegrenzt und muss bei deterministischen Fehlern gezielt stoppen.

8. **Telegram reports truth**  
   Telegram meldet ausschließlich verifizierte State-Transitions der kanonischen State Machine.

9. **Strict Slot Serialization**  
   Der Abendlauf darf erst freigegeben werden, wenn der Morgenlauf fachlich vollständig erfolgreich abgeschlossen wurde.

10. **No quality-gate weakening**  
    Fehler werden durch Reparatur behoben, nicht durch Lockerung von Audio-, Visual-, Fakten-, Render- oder Publikationsgates.

---

## 3. Golden Path – verbindliche Stationen

### GP-00 – Telegram Approval

**Input:** ausgewählter Trend  
**Ergebnis:** freigegebener Auftrag mit eindeutiger `source_request_id`

### GP-10 – Request Lock

Bindet mindestens:

- `request_id`
- `source_request_id`
- `trend_id`
- Thema
- Slot
- Freigabezeit
- Telegram-Message-ID
- Content-Angle
- Source-Context-Hash

**Invariant:** Kein späterer Recovery-Lauf darf still ein anderes Thema oder einen anderen Request übernehmen.

### GP-20 – Evidence & Duplicate Gate

Pflichtprüfungen:

- mindestens zwei unabhängige Nachrichtenquellen, sofern der Trendvertrag dies verlangt
- strukturierter Source Context
- Source-Hash-Integrität
- Fakten-Guardrails
- globaler Dublettencheck

**State nach Erfolg:** `SOURCES_LOCKED`

### GP-30 – Technical Preflight

Prüft:

- Runner/Execution Contract
- benötigte Secrets
- Python/FFmpeg/Tools
- Produktionsabhängigkeiten
- Implementierungs-Checkout
- Review-Pages-Checkout
- Produktionsmanifest

**State nach Erfolg:** `PREFLIGHT_PASSED`

### GP-40 – Production Controller

Die Produktion umfasst logisch getrennte Pfade:

1. Script
2. Voice
3. Visuals
4. Subtitles
5. Render
6. Plattform-Package

**State währenddessen:** `PRODUCTION_RUNNING`

Der Produktionscontroller entscheidet nicht autonom über einen vollständigen neuen fachlichen Request. Er produziert oder übergibt einen präzisen Fehlerzustand.

### GP-50 – Checkpoint & Local Repair Router

Wenn ein wiederverwendbarer Produktionsstand vorhanden ist, wird er gesichert und der Fehler klassifiziert.

Unterstützte logische Reparaturklassen:

- `VOICE_REPAIR_REQUIRED`
- `VISUAL_REPAIR_REQUIRED`
- `SUBTITLE_REPAIR_REQUIRED`
- `RENDER_REPAIR_REQUIRED`
- `AUDIT_REPAIR_REQUIRED`
- `PACKAGE_REPAIR_REQUIRED`
- `CODE_REPAIR_REQUIRED`
- `EXTERNAL_ACTION_REQUIRED`
- `DUPLICATE_CONTENT_BLOCKED`

**Regel:** Ein lokaler Repair darf nur den betroffenen Pfad verändern. Bereits bestandene, unveränderte Pfade werden wiederverwendet.

### GP-60 – Publishability Gate

Prüft, ob ein technisch und fachlich publishbarer Master existiert.

**Erfolg:** `MASTER_PUBLISHABLE`  
**Fehler:** kein Review, keine Veröffentlichung.

### GP-70 – Final Quality Gate

Pflichtbereiche:

- Voice
- Visuals
- Fakten
- Plattformpakete
- technische Datei
- Publishability

**Erfolg:** `QUALITY_PASSED`

### GP-80 – Review Delivery

Erzeugt/veröffentlicht:

- Review-Seite
- Telegram-Review mit Video/Review-Link

**Erfolg:** `REVIEW_DELIVERED`

### GP-90 – Release

Nach allen erforderlichen Freigabe-/Publikationsregeln:

- YouTube-Publikation
- TikTok-Bereitstellung bzw. definierte TikTok-Auslieferung

**Finaler fachlicher Zustand:** `COMPLETED`

---

## 4. Kanonische State Machine

Die kanonische State Machine soll mindestens folgende Zustände unterscheiden:

```text
APPROVED
  ↓
REQUEST_LOCKED
  ↓
SOURCES_LOCKED
  ↓
PREFLIGHT_PASSED
  ↓
PRODUCTION_RUNNING
  ↓
RENDER_AVAILABLE
  ├─→ LOCAL_REPAIR_RUNNING
  │      └─→ RENDER_AVAILABLE
  ↓
MASTER_PUBLISHABLE
  ↓
QUALITY_PASSED
  ↓
REVIEW_DELIVERED
  ↓
PUBLISHED
  ↓
COMPLETED
```

Fehlerzustände verlaufen orthogonal und müssen den aktiven Gate-Typ enthalten:

```text
VOICE_FAILED
VISUAL_FAILED
SUBTITLE_FAILED
RENDER_FAILED
AUDIT_FAILED
PACKAGE_FAILED
CODE_FAILED
EXTERNAL_BLOCKED
DUPLICATE_BLOCKED
RECOVERY_EXHAUSTED
```

### Empfohlener kanonischer Job-State

```json
{
  "request_id": "telegram-...",
  "run_id": "...",
  "slot": "morning",
  "state": "VISUAL_REPAIR_RUNNING",
  "recovery_generation": 2,
  "run_attempt": 3,
  "last_successful_gate": "VOICE_PASSED",
  "active_gate": "VISUAL",
  "next_gate": "PUBLISHABILITY",
  "checkpoint_available": true,
  "user_action_required": false,
  "quality_gates_weakened": false
}
```

**Ziel:** Telegram, Watchdog und Recovery lesen denselben kanonischen Zustand. Keine Komponente soll aus veralteten Logzeilen eine andere Wahrheit ableiten.

---

## 5. Telegram-Benachrichtigungsstandard

### 5.1 Grundregel

Telegram meldet **State-Transitions**, keine künstlich fortlaufenden Prozentwerte.

Prozentwerte dürfen ergänzend angezeigt werden, aber niemals den fachlichen State ersetzen.

### 5.2 Nutzerrelevante Meilensteine

| State | Telegram-Titel | Pflichtinhalt |
|---|---|---|
| `APPROVED` | ✅ Trend übernommen | Thema, Request, keine Aktion nötig |
| `SOURCES_LOCKED` | 🔎 Fakten & Quellen gesichert | Quellen/Dublette gebunden |
| `PRODUCTION_RUNNING` | 🎬 Produktion gestartet | Script/Voice/Visual/Render aktiv |
| `LOCAL_REPAIR_RUNNING` | 🔧 Gezielte Reparatur läuft | konkretes Gate + was erhalten bleibt |
| `MASTER_PUBLISHABLE` | 🎞️ Master fertig | publishbarer Master bestätigt |
| `QUALITY_PASSED` | 🛡️ Qualitätsprüfung bestanden | Pflicht-Gates bestanden |
| `REVIEW_DELIVERED` | 📲 Review bereit | Video/Review-Link |
| `COMPLETED` | 🚀 Veröffentlichung abgeschlossen | Plattformstatus |

### 5.3 Reparaturmeldungen müssen Gate-spezifisch sein

Erforderliche Telegram-Stages:

- `voice_repair`
- `visual_repair`
- `subtitle_repair`
- `render_repair`
- `audit_repair`
- `package_repair`
- `code_repair`
- `external_blocker`
- `duplicate_blocked`

Beispiel Visual:

```text
🔧 TAYVORIQ · Visual-Reparatur läuft

Thema: <Thema>
Run: <Run-ID>
Recovery: Generation <n>

✅ Skript bleibt erhalten
✅ Sprecherstimme bleibt erhalten
✅ Quellen bleiben gebunden
⚠️ Visual-Gate ist noch nicht bestanden

➡️ Nur fehlerhafte Bildszenen werden repariert und erneut geprüft.
Für dich: ✅ Keine Aktion nötig.
```

**Verboten:** Eine Audio-Meldung, wenn `active_gate=VISUAL` ist.

### 5.4 Heartbeat-Policy

Interne Watchdog-Abfrage darf häufig erfolgen; Telegram bleibt weitgehend ruhig.

- interne Prüfung: z. B. alle 3 Minuten
- erste Nutzer-Liveness-Meldung: nach 18 Minuten ohne State-Wechsel
- zweite Nutzer-Liveness-Meldung: nach 45 Minuten ohne State-Wechsel
- dazwischen keine repetitiven Meldungen

Heartbeat enthält:

- aktueller State
- Zeit seit letztem echten State-Wechsel
- letzter sicherer Checkpoint
- ob neuer Fehler vorliegt
- niemals erfundenen Fortschritt

### 5.5 Same-run Retry

Ein Retry desselben GitHub-Run-IDs darf bereits gemeldete Meilensteine nicht erneut senden. Eine neue Recovery-Run-ID darf eine neue, aber konsistente Recovery-Sequenz beginnen.

---

## 6. Recovery-Architektur

### 6.1 Entscheidungskette

```text
Golden Path Failure
        ↓
Failure Classifier
        ↓
┌────────────────────────────────────┐
│ transient? → SAME-RUN RETRY        │
│ local quality? → LOCAL REPAIR      │
│ deterministic code? → CODE STOP   │
│ external? → EXTERNAL BLOCKER       │
│ duplicate? → DUPLICATE BLOCKER     │
└────────────────────────────────────┘
```

### 6.2 Recovery-Invarianten

Recovery darf nicht still verändern:

- Request-ID
- Trend
- Thema
- Quellen
- Fakten-Guardrails
- Content-Angle
- Slot

Ein neuer Recovery-Run muss den alten Run und seine Generation explizit referenzieren.

### 6.3 Circuit Breaker

Bei ausgeschöpfter Recovery-Policy:

- kein blinder Generation-5+-Loop
- Diagnosepaket sichern
- kanonischen Fehlerzustand speichern
- Telegram meldet konkret, welcher Gate-/Codefehler vorliegt
- nach Codefix darf gezielt derselbe Request wieder aufgenommen werden

---

## 7. Morgen-/Abend-Serialisierung

Der Abendlauf ist ein abhängiger Slot und bleibt `HELD`, bis der Morgenlauf vollständig abgeschlossen ist.

### Release-Bedingung für den Abend

Alle folgenden Bedingungen müssen wahr sein:

```text
morning Golden Path = completed + success
AND Publishable Production Output = success
AND Publication Quality = success
AND Review Page = success
AND Telegram Review = success
```

Ein fehlgeschlagener oder nur beendeter Morgenlauf reicht **nicht**.

**Verboten:** Start des Abendjobs nur aufgrund einer Uhrzeit.

---

## 8. Projektberichterstattung – Pflichtblock

Jede zukünftige Projektberichterstattung oder größere TAYVORIQ-Änderung soll mindestens diesen Block enthalten:

### Golden Path V4 Compliance

- **Request Binding:** GREEN / AMBER / RED
- **Evidence & Duplicate Gate:** GREEN / AMBER / RED
- **Production:** GREEN / AMBER / RED
- **Local Recovery:** GREEN / AMBER / RED
- **Publishability:** GREEN / AMBER / RED
- **Final Quality:** GREEN / AMBER / RED
- **Telegram State Truth:** GREEN / AMBER / RED
- **Morning→Evening Serialization:** GREEN / AMBER / RED
- **Quality gates weakened:** MUST BE `false`

### Aktiver Auftrag

- Request-ID
- Thema
- Slot
- Run-ID
- Run-Attempt
- Recovery-Generation
- aktueller kanonischer State
- aktives Gate
- letzter erfolgreicher Gate
- Checkpoint verfügbar: ja/nein
- Nutzeraktion erforderlich: ja/nein

### Abweichungen

Jede Abweichung vom Standard muss mit:

1. Ursache
2. Auswirkung
3. Reparatur
4. Regressionstest
5. Status

dokumentiert werden.

---

## 9. Definition of Done für zukünftige Architekturänderungen

Eine Änderung an Golden Path, Recovery oder Benachrichtigungen ist erst abgeschlossen, wenn:

- der genaue fachliche State maschinenlesbar vorhanden ist
- Telegram denselben State korrekt meldet
- falsche Gate-Klassifikation durch Tests ausgeschlossen ist
- Same-run-Dubletten unterdrückt werden
- Recovery-Generation und Run-ID konsistent sind
- lokale Reparatur bestehende valide Artefakte bewahrt
- Publishability weiterhin fail-closed ist
- finaler Quality-Gate nicht abgeschwächt wird
- Morgen-/Abend-Serialisierung unverändert korrekt bleibt
- ein Regressionstest für den konkreten Fehler existiert

---

## 10. Aktuelle Umsetzungsprioritäten

Dieser Projektstandard beschreibt das verbindliche Zielbild. Bestehende Implementierungsteile werden schrittweise daran ausgerichtet.

Priorität:

1. **Gate-spezifische Failure Classification** – insbesondere Visual vs. Audio eindeutig machen.
2. **Kanonischen Job-State materialisieren** und als einzige Wahrheitsquelle für Telegram/Watchdog/Recovery nutzen.
3. **Visual-only Repair** für lokalisierte Visualfehler robust machen.
4. **Notification Router** auf State-Transitions statt Prozent-/Logheuristiken ausrichten.
5. **Regressionstests** für falsche Gate-Meldungen, Same-run-Spam und Recovery-Generation.
6. **Slot Serialization** als dauerhaftes unverhandelbares System-Invariant schützen.

---

## 11. Architektur-Kurzbild

```text
Trend Radar
    ↓
Telegram Approval
    ↓
Immutable Request
    ↓
Evidence + Duplicate Gate
    ↓
Golden Path
    ├── Script Gate
    ├── Voice Gate
    ├── Visual Gate
    ├── Subtitle Gate
    ├── Render Gate
    └── Package Gate
           ↓
    Local Repair Router
           ↓
    Publishability Gate
           ↓
    Final Quality Gate
           ↓
    Telegram Review
           ↓
    Publish
           ↓
    Release next Slot

Parallel:

Canonical State Event Stream
    ├── Telegram Notifications
    ├── Watchdog Monitoring
    └── Recovery Controller
```

---

## 12. Änderungsregel

Dieser Standard darf nicht stillschweigend durch Hotfixes umgangen werden. Änderungen am Zielbild müssen bewusst dokumentiert werden und dürfen insbesondere keine Qualitäts-, Request-Binding-, Recovery- oder Slot-Serialisierungsinvarianten schwächen.
