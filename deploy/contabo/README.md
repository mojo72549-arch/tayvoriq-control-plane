# TAYVORIQ auf dem Contabo VPS testen

Der Pilot richtet Ollama auf einem dedizierten Ubuntu 24.04 VPS mit x86-64 ein. Das Profil ist für 8 geteilte vCPU und 24 GB RAM ausgelegt. Es lädt Qwen3.5 9B und Gemma 4 12B nacheinander und speichert die Gewichte dauerhaft. Ollama ist auf die lokale Adresse beschränkt und hat den Cloud-Modus deaktiviert. FFmpeg wird als Basiswerkzeug für die spätere Studio-Installation eingerichtet.

Starte den Pilot im Stammverzeichnis dieses Checkouts auf dem bereitgestellten VPS.

```bash
sudo bash deploy/contabo/bootstrap.sh
python3 tools/tayvoriq_local_editorial_benchmark.py \
  requests/telegram-3696-trend-1.json requests/telegram-3728-trend-1.json \
  > editorial-comparison.json
```

Der Tarif- und der Bahnfall stammen aus früheren Aufträgen. Der Test vergleicht beide Modelle auf exakt denselben gespeicherten Quellen. Status, Modellkennung, Text, Ladezeit und Laufzeit erscheinen pro Fall im JSON-Bericht. Ein Fehler in der Antwort oder in den automatischen Prüfungen ergibt einen Fehlercode. Die Texte dienen ausschließlich der internen Beurteilung.

Bei der Auswahl zuerst prüfen, ob beide Tarifpositionen den richtigen Parteien zugeordnet sind, eine Forderung als solche erkennbar bleibt und der Einstieg im selben Video eingelöst wird. Dann die Texte laut lesen. Ein guter Schluss gibt einen konkreten Grund wiederzukommen, etwa die Einordnung eines neuen Angebots. Das Publikum soll auch eine Antwort bekommen, wenn es kein weiteres Video ansieht. Die Modellzeiten getrennt von Ladezeiten beurteilen und den Vergleich zur üblichen Produktionszeit wiederholen.

Der Pilot startet ausschließlich Ollama. Die Integration in Studio, der lokale Bild- und Tonvergleich mit den bestehenden Prüfungen und der Nachweis der zehn Minuten bis zum Review sind Abnahmen für die Produktionsumstellung. Bis dahin laufen Slots und Freigaben im bestehenden Workflow. Der folgende Befehl stoppt den Pilot und behält die heruntergeladenen Modelle.

```bash
sudo docker compose --file deploy/contabo/compose.yaml down
```
