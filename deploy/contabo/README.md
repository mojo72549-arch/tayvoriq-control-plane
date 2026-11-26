# TAYVORIQ auf dem Contabo VPS vorbereiten

Das Paket ist für Ubuntu 24.04 x86-64 mit 8 geteilten vCPU, 24 GB RAM und 150 GB NVMe vorgesehen. Es richtet Ollama sowie den Ausführungsdienst für die bestehende Produktion ein. Die Freigabe erfolgt über den vorhandenen Telegram- und Control-Center-Weg.

| Anwendung | Aufgabe | Ausführungsort |
| --- | --- | --- |
| Bestehender Orchestrator | Quellenprüfung, Auftragsbindung, Reparatur und Status | GitHub Actions |
| Ollama mit Qwen3.5 9B oder Gemma 4 12B | Textpaket aus dem geprüften Quellenkontext | VPS |
| Studio mit Chatterbox V3 | Deutsche Stimme, Szenenaufbau und Untertitel | VPS |
| Pillow, MoviePy und FFmpeg | Szenengrafiken, Videoschnitt und MP4-Export | VPS |
| Bestehende Qualitätsprüfungen | Sprache, Fakten, Visuals, Datei und Plattformpaket | Produktionsworkflow auf VPS |
| Telegram und Control Center | Vorschau und Freigabe | Bestehende Anbindung |

## Server einrichten

Starte den Pilot im Stammverzeichnis dieses Checkouts auf dem bereitgestellten VPS.

```bash
sudo bash deploy/contabo/bootstrap.sh
sudo bash deploy/contabo/install-runner.sh
```

Das erste Skript installiert die Werkzeuge, legt den Benutzer `tayvoriq` an und lädt beide Sprachmodelle. Das zweite registriert einen GitHub-Runner für dieses Projekt. Es fragt den kurzlebigen Registrierungstoken direkt im Serverterminal ab. Der Token stammt aus GitHub Settings → Actions → Runners → New self-hosted runner. Der Runner läuft als Systemdienst und startet nach einem Serverneustart automatisch.

Ollama ist an die lokale Adresse gebunden. Der Runner arbeitet als eigener Benutzer. Die vorhandenen GitHub-Secrets versorgen die bestehenden Projektanbindungen. Modelle und Python-Abhängigkeiten liegen dauerhaft außerhalb des bei einem Checkout bereinigten Arbeitsverzeichnisses.

## Studio und Modelle prüfen

Die Studio-Erweiterung für `TAYVORIQ_LOCAL_LLM_REQUIRED` muss in der geprüften Produktionsversion enthalten sein. [Studio-Entwurf #353](https://github.com/mojo72549-arch/shorts-agent-studio/pull/353) ergänzt den lokalen Aufruf im normalen Textpaket-Einstieg. Bei einem ungültigen lokalen Ergebnis wird die Textstufe als Fehler behandelt.

Starte auf GitHub den Workflow **TAYVORIQ VPS Preflight**. Optional setzt `TAYVORIQ_VPS_STUDIO_REF` die zu prüfende Studio-Version. Der Workflow installiert dieselben CPU-Abhängigkeiten wie die Produktion, lädt das Chatterbox-V3-Modell ohne Spracherzeugung und prüft Ollama, FFmpeg und die lokale Studio-Schnittstelle.

Anschließend vergleicht er Qwen und Gemma mit dem archivierten VW-Auftrag und dem Flixtrain-Auftrag. Beide Modelle erhalten denselben gespeicherten Quellenstand. Modellkennung, Text, Lade- und Laufzeit sowie Prüfergebnisse erscheinen im Artefakt `tayvoriq-vps-preflight`. Jeder fehlerhafte Fall ergibt einen Fehlercode. Die Archivfälle dienen dem internen Vergleich.

Bei der Auswahl zuerst prüfen, ob beide Tarifpositionen den richtigen Parteien zugeordnet sind, eine Forderung als solche erkennbar bleibt und der Einstieg im selben Video eingelöst wird. Dann die Texte laut lesen. Ein guter Schluss gibt einen konkreten Grund wiederzukommen, etwa die Einordnung eines neuen Angebots. Das Publikum soll auch eine Antwort bekommen, wenn es kein weiteres Video ansieht. Die Modellzeiten getrennt von Ladezeiten beurteilen und den Vergleich zur üblichen Produktionszeit wiederholen.

## Produktion auf den VPS umstellen

Aktiviere die Umschaltung nach dem erfolgreichen Preflight und der normalen Prüfung beider Codeänderungen.

| GitHub-Repository-Variable | Wert |
| --- | --- |
| `TAYVORIQ_VPS_ENABLED` | `true` |
| `TAYVORIQ_OLLAMA_MODEL` | Das ausgewählte Modell, zunächst `qwen3.5:9b` |

Der bestehende Workflow **TAYVORIQ-X Golden Path** läuft dann auf dem Runner mit Label `tayvoriq-contabo`. Er ruft dieselbe Studio-Produktion auf, verwendet den lokalen Skriptanbieter und behält seine Qualitätsprüfungen und die Telegram-Freigabe. Ollama gibt nach der Textgenerierung den Modellspeicher frei. Stimme und Rendering erhalten dadurch mehr RAM.

Die Recherche des bestehenden Orchestrators und ihre Provider-Anbindungen benötigen eine eigene Umstellung, falls auch diese Modellaufrufe vollständig lokal laufen sollen. Die hier vorbereitete Umschaltung betrifft die Videoproduktion.

Für den ersten freigegebenen VPS-Auftrag die Zeit von der Trendfreigabe bis zur bestätigten Telegram-Vorschau messen. Ziel sind zehn Minuten. Downloads und Installation gehören zum vorbereitenden Preflight. Eine Zusage über die Rendergeschwindigkeit benötigt den tatsächlichen Lauf auf diesem VPS.

## Betrieb und Rückkehr zum bisherigen Ausführungsort

`TAYVORIQ_VPS_ENABLED=false` leitet neue Produktionsläufe wieder zum bisherigen GitHub-Runner. Ein laufender Auftrag wird zuerst über seinen vorhandenen Status und Checkpoint abgeschlossen.

Die Dienste lassen sich auf dem VPS prüfen.

```bash
sudo systemctl status "$(cat /opt/tayvoriq-runner/.service)"
sudo docker compose --file deploy/contabo/compose.yaml ps
df -h /var/cache/tayvoriq
```

Die Modelle bleiben beim Stoppen des Ollama-Dienstes gespeichert.

```bash
sudo docker compose --file deploy/contabo/compose.yaml down
```
