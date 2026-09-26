# TAYVORIQ: Erkenntnisgewinn, Story und Folgegrund

Stand: 27.09.2026. Verbindliche fachliche Zielvorgabe für zukünftige Shorts.
Implementierungsstatus: Vorprüfung als Änderung vorbereitet, noch nicht produktiv aktiviert.
Das bereits fertiggestellte Zellforschungs-Short und seine Freigabe bleiben unverändert.

## Markenversprechen

TAYVORIQ erklärt komplexe wichtige Entwicklungen schnell und verständlich und zeigt,
was hinter einer Meldung steckt. Der Folgegrund entsteht aus dem erlebten Verständnisgewinn.
Eine angehängte Abo-Aufforderung ersetzt diesen Mehrwert nicht.

## Redaktioneller Ablauf

Thema recherchieren → stärksten belegbaren Blickwinkel wählen → konkreten Erkenntnisgewinn
formulieren → Story entwickeln → separat prüfen → gegebenenfalls einmal überarbeiten
und erneut prüfen → erst nach Bestehen zur Auswahl und später zur Medienproduktion geben.

Die Geschichte beginnt mit einer konkreten Frage oder Konsequenz. Es folgen der nötige
Kontext, die Erklärung, ein relevanter oder überraschender Kern und dessen Bedeutung.
Das Ende löst das Versprechen des Einstiegs ein. Eine optionale Fortsetzung vertieft die
Erkenntnis; sie hält die versprochene Antwort nicht zurück. Jede Passage trägt etwas Neues bei.

## Sieben Pflichtfragen

| Kriterium | Nachweis im tatsächlich gesprochenen Text |
| --- | --- |
| Hook | Sofort erkennbarer Anlass zum Weitersehen; keine allgemeine Einleitung. |
| Erkenntnisgewinn | Ein Mechanismus, Zusammenhang oder Unterschied, den die Überschrift nicht erklärt. |
| Relevantes Detail | Mindestens ein belegter überraschender oder besonders bedeutsamer Punkt. |
| Bedeutung | Verständliche Konsequenz für Forschung, Technik oder Alltag; Unsicherheit erkennbar. |
| Spannungsbogen | Jede Passage führt weiter; die zentrale Frage wird beantwortet. |
| TAYVORIQ-Mehrwert | Einordnung über die bloße Nachricht hinaus. |
| Folgegrund | Ein zum Thema passendes Versprechen weiteren Verständnisses, das dieses Video einlöst. |

Kein Kriterium wird durch einen hohen Gesamtscore ausgeglichen. Fakten, aufgelöster Hook
und ehrliche Folgeversprechen sind zusätzliche Pflichtbedingungen. Bei Studien werden
Modell, Beobachtung, Kausalität und mögliche Anwendung auseinandergehalten.
Kein erfundener Alltagsnutzen und keine ungesicherte Zukunftsaussage als Tatsache.

## Vorbereiteter Code

- Die Normalisierung erhält die vom Trend-Prompt angeforderte Mini-Story.
- Auch der Groq-Recherche- und Formatierungspfad erhält die vollständigen Vorgaben.
- Die fünf ausgewählten Geschichten werden in einem separaten Modellaufruf geprüft.
- Jede Bewertung braucht eine Begründung und ein wörtliches Beispiel aus dem hörbaren Text.
  Erkenntnisgewinn darf nicht nur in Metadaten oder CTA stehen.
- Schwache Texte werden einmal gezielt umgeschrieben und danach separat erneut geprüft.
- Höchstens drei Modellaufrufe pro Auswahlprüfung; keine Suche, Stimme oder Medienproduktion.
- Thema, Blickwinkel, Quellen und Faktenvertrag bleiben bei der Überarbeitung unverändert.
- Fehlerhafte/unvollständige Prüfergebnisse und nicht verfügbare Prüfer blockieren die Auswahl.
- Prüfbericht und Hash werden im anschließend zu sperrenden Quellenpaket gespeichert.

Die Modellbewertung ist eine redaktionelle Einschätzung. Sie garantiert keine Zuschauerbindung
oder Followerzahlen. Gemessene Retention und Follow-Conversion bleiben ohne Plattformdaten leer.

## Noch erforderliche Produktionsintegration vor Aktivierung

Der aktuelle Studio-Pfad `c59404a84638cf4e7e0e68d1b4199d82645db4ca` rekonstruiert in
`tools/tayvoriq_dual_platform_render_v34.py` und
`runtime_patches/tayvoriq_verified_source_budget_guard.py` den gesprochenen Text aus
den fünf Faktenantworten. Das muss mit der separat geprüften Story vereinbart werden.

Erforderlich ist ein nachgewiesener Übergang vom geprüften Storytext zur finalen TTS-Eingabe:
Story/CTA/Quellenbindung validieren, spätere Textänderungen erneut prüfen, unverändert
übernommene Stories ohne erneute Generierung weiterreichen. Bestehende Fakten-, Sprach-,
Dauer-, Quellen- und Publikationsprüfungen bleiben bestehen. Plattformabhängige CTA-Anpassungen
müssen berücksichtigt werden. Bestehende abgeschlossene Requests bleiben unverändert.

Die bestehende Körpertextgrenze von 38–49 Wörtern wird im vorbereiteten Kontrollpfad
eingehalten. Ein Ausbau auf reichere 35–60-Sekunden-Erklärungen erfordert eine abgestimmte
Änderung des Produktions-Dauervertrags, nicht nur längere Texte im Recherche-Prompt.

Studio-AGENTS.md fordert vor Änderungen an Rendering-Dateien eine gesonderte Freigabe.
Deshalb wird diese vorbereitete Änderung als Draft-PR gehalten, bis die Produktionsintegration
autorisiert und mit einem kostenfreien Übergabetest verifiziert ist.

## Verifikation

48 gezielte Offline-Tests bestanden: neue Redaktionstests sowie bestehende Retention-,
Story-Prompt-, Quellenkohärenz-, Semantikvertrags-, Auswahl- und Dublettenprüfungen.
Die Providerantworten sind Testdaten; kein kostenpflichtiger Modell-/Medienaufruf wurde ausgeführt.

Drei zusätzliche Tests scheitern identisch am unveränderten Basisstand `165b24f`:
`test_audience_report_rewards_followable_repeatable_topic`,
`test_resilience_uses_providerless_path_when_llm_providers_are_blocked` und
`test_accepts_source_bound_explanatory_angle`.
Sie sind kein Nachweis einer Regression dieser Änderung und wurden nicht abgeschwächt.
