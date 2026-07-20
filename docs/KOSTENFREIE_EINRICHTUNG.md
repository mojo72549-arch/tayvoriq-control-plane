# TAYVORIQ kostenfrei einrichten

Diese Anleitung richtet die Strecke ein:

`Video fertig -> Telegram-Prüfung -> Freigeben -> YouTube-Upload -> TikTok-Anleitung`

## Kostenrahmen

- GitHub Actions: kostenlos, solange dieses Repository öffentlich bleibt und Standard-Runner verwendet werden.
- GitHub Pages: kostenlos für die Review-Seite.
- Cloudflare Workers Free: ausreichend für den Telegram-Webhook.
- Telegram Bot API: kein kostenpflichtiger Dienst erforderlich.
- YouTube Data API: kontingentbasiert, aber ohne nutzungsabhängige Geldkosten für diesen Ablauf.
- TikTok bleibt zunächst ein manueller Upload, bis eine freigegebene TikTok-Developer-App vorhanden ist.

Keine kostenpflichtigen Cloudflare-, GitHub- oder Google-Tarife aktivieren.

## 1. GitHub-Repository

Alle Einstellungen werden in diesem Repository vorgenommen:

`mojo72549-arch/tayvoriq-control-plane`

Öffne:

`Settings -> Secrets and variables -> Actions -> New repository secret`

Die Secret-Namen müssen exakt stimmen.

## 2. Cloudflare Free

1. Kostenloses Cloudflare-Konto erstellen oder anmelden.
2. `Workers & Pages` öffnen und sicherstellen, dass der Free-Plan verwendet wird.
3. Unter `Workers & Pages` die `Account ID` kopieren.
4. Unter `My Profile -> API Tokens -> Create Token` die Vorlage `Edit Cloudflare Workers` wählen.
5. Den Zugriff auf das eigene Cloudflare-Konto begrenzen.
6. Token erstellen und sofort kopieren. Er wird nur einmal vollständig angezeigt.
7. In GitHub anlegen:

| GitHub Secret | Wert |
|---|---|
| `CLOUDFLARE_ACCOUNT_ID` | kopierte Cloudflare Account ID |
| `CLOUDFLARE_API_TOKEN` | neu erzeugter Cloudflare API Token |

Es wird keine eigene Domain benötigt. Der Worker läuft kostenfrei unter `workers.dev`.

## 3. GitHub-Freigabetoken

Der Cloudflare Worker muss nach einer Telegram-Freigabe einen `repository_dispatch` an GitHub senden.

1. GitHub-Profilbild öffnen.
2. `Settings -> Developer settings -> Personal access tokens -> Fine-grained tokens`.
3. `Generate new token`.
4. Name: `TAYVORIQ Telegram Approval`.
5. Repository access: `Only select repositories`.
6. Nur `tayvoriq-control-plane` auswählen.
7. Repository permission `Contents: Read and write` setzen.
8. Token erzeugen und direkt kopieren.
9. Als GitHub Secret speichern:

| GitHub Secret | Wert |
|---|---|
| `APPROVAL_GITHUB_TOKEN` | der Fine-grained GitHub Token |

## 4. Telegram-Webhook absichern

Auf dem eigenen Computer in PowerShell ausführen:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Die Ausgabe als folgendes GitHub Secret speichern:

| GitHub Secret | Wert |
|---|---|
| `TELEGRAM_WEBHOOK_SECRET` | die erzeugte zufällige Zeichenfolge |

Die bereits vorhandenen Secrets müssen ebenfalls vorhanden sein:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## 5. YouTube API und OAuth

### Google Cloud vorbereiten

1. In Google Cloud ein kostenloses Projekt `TAYVORIQ Upload` erstellen.
2. `APIs & Services -> Library` öffnen.
3. `YouTube Data API v3` suchen und aktivieren.
4. `OAuth consent screen` öffnen.
5. Zielgruppe `External` wählen.
6. App-Name `TAYVORIQ Upload`, Support-E-Mail und eigene Entwickler-E-Mail eintragen.
7. Den Scope `https://www.googleapis.com/auth/youtube.upload` hinzufügen.
8. Das eigene Google-Konto als Testnutzer hinzufügen.
9. `Credentials -> Create credentials -> OAuth client ID`.
10. Anwendungstyp `Desktop app` wählen.
11. Die Client-JSON-Datei herunterladen.

### Refresh Token lokal erzeugen

Repository lokal herunterladen oder klonen. Dann in PowerShell im Repository-Verzeichnis:

```powershell
py -m pip install google-auth-oauthlib
py tools/youtube_oauth_setup.py "C:\Pfad\zur\client_secret.json"
```

Im Browser mit dem Google-Konto anmelden, dem der TAYVORIQ-YouTube-Kanal gehört, und die Upload-Berechtigung bestätigen.

Danach entsteht lokal:

`youtube-github-secrets.json`

Die drei Werte daraus als GitHub Secrets speichern:

- `YOUTUBE_CLIENT_ID`
- `YOUTUBE_CLIENT_SECRET`
- `YOUTUBE_REFRESH_TOKEN`

Danach die lokale Datei `youtube-github-secrets.json` löschen. Sie darf niemals ins Repository hochgeladen werden.

Wichtig: Im Google-OAuth-Testmodus laufen Refresh Tokens für sensible Scopes nach sieben Tagen ab. Für einen dauerhaften Betrieb die OAuth-App nach dem Test auf `In production` stellen. Eine nicht verifizierte YouTube-API-Anwendung kann API-Uploads trotzdem auf `private` beschränken. Die Google-/YouTube-Prüfung kostet kein Geld, muss aber beantragt werden, bevor vollautomatisch öffentlich veröffentlicht werden kann.

## 6. Bereits vorhandene Produktions-Secrets prüfen

Zusätzlich müssen diese bisherigen Secrets im Repository vorhanden sein:

- `PEXELS_API_KEY`
- `PAGES_DEPLOY_TOKEN`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## 7. Cloudflare Worker deployen

1. Im Repository `Actions` öffnen.
2. Workflow `Deploy Telegram Approval Worker` auswählen.
3. `Run workflow` klicken.
4. Branch `main` auswählen.
5. Starten und auf einen grünen Abschluss warten.

Der Workflow:

- veröffentlicht den Cloudflare Worker,
- überträgt die Worker-Secrets,
- registriert den Telegram-Webhook,
- prüft den Webhook.

## 8. Gesamttest

1. Workflow `TAYVORIQ Emergency Video` manuell starten.
2. Auf Telegram-Nachricht warten.
3. `Review öffnen` anklicken und Video vollständig prüfen.
4. `Freigeben` anklicken.
5. Telegram muss bestätigen, dass der YouTube-Upload gestartet wurde.
6. Nach Abschluss kommt der YouTube-Link plus TikTok-Anleitung.

Beim ersten Test bleibt die YouTube-Sichtbarkeit auf `private`. Erst nach erfolgreichem End-to-End-Test und erforderlicher Google-/YouTube-Freigabe wird `YOUTUBE_PRIVACY` auf `public` umgestellt.
