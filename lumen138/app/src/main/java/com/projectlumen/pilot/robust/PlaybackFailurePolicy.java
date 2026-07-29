package com.projectlumen.pilot.robust;

import java.util.Locale;

/** Pure playback failure decisions used by the Media3 player and JVM tests. */
final class PlaybackFailurePolicy {
    private static final long TRANSIENT_RETRY_DELAY_MS = 2_500L;
    private static final String HTTP_509 = "HTTP_509";

    private PlaybackFailurePolicy() { }

    static Decision decide(String errorName, int httpStatus, int automaticRetryCount,
                           boolean forcedTs, String streamUrl) {
        String name = errorName == null ? "ERROR_CODE_UNSPECIFIED" : errorName;
        if (httpStatus > 0 || name.contains("BAD_HTTP_STATUS")) {
            int status = httpStatus;
            boolean transientFailure = isTransientHttp(status);
            boolean retry = transientFailure && automaticRetryCount < 1;
            return new Decision(
                    status == 509 ? HTTP_509
                            : status > 0 ? "HTTP_" + status : "HTTP_SERVER_ERROR",
                    httpMessage(status, retry),
                    retry,
                    retry ? TRANSIENT_RETRY_DELAY_MS : 0L,
                    false);
        }

        if (name.contains("TIMEOUT")) {
            boolean retry = automaticRetryCount < 1;
            return new Decision("SERVER_TIMEOUT",
                    retry
                            ? "Der Streaming-Server antwortet noch nicht. Die Verbindung wird einmal sauber neu aufgebaut."
                            : "Der Streaming-Server antwortet nicht rechtzeitig. Bitte später erneut versuchen.",
                    retry, retry ? TRANSIENT_RETRY_DELAY_MS : 0L, false);
        }

        if (name.contains("NETWORK_CONNECTION_FAILED")) {
            boolean retry = automaticRetryCount < 1;
            return new Decision("NETWORK_CONNECTION_FAILED",
                    retry
                            ? "Die Verbindung zum Streaming-Server wurde unterbrochen. Ein neuer Verbindungsversuch startet."
                            : "Die Netzwerkverbindung zum Streaming-Server ist fehlgeschlagen.",
                    retry, retry ? 1_500L : 0L, false);
        }

        if (name.contains("PARSING") || name.contains("CONTENT_TYPE")) {
            boolean fallback = !forcedTs && likelyTransportStream(streamUrl);
            return new Decision(name,
                    fallback
                            ? "Das Format wird einmal kontrolliert als MPEG-TS geöffnet."
                            : "Das gelieferte Streamformat konnte nicht erkannt oder gelesen werden.",
                    false, 0L, fallback);
        }

        if (name.contains("DECODER") || name.contains("DECODING")) {
            return new Decision(name,
                    "Der Video- oder Audiocodec wird auf diesem Gerät nicht unterstützt.",
                    false, 0L, false);
        }

        return new Decision(name,
                "Der genaue technische Fehler wurde in der Diagnose gespeichert.",
                false, 0L, false);
    }

    static boolean isTransientHttp(int status) {
        return status == 408 || status == 425 || status == 429
                || status == 500 || status == 502 || status == 503
                || status == 504 || status == 509;
    }

    private static String httpMessage(int status, boolean retrying) {
        if (status == 401 || status == 403) {
            return "Der Anbieter hat den Streamzugriff abgewiesen. Zugang, Berechtigung oder Streamadresse prüfen.";
        }
        if (status == 404 || status == 410) {
            return "Der Film ist auf dem Streaming-Server nicht mehr verfügbar.";
        }
        if (status == 429) {
            return retrying
                    ? "Der Anbieter meldet zu viele Anfragen (HTTP 429). Die App wartet kurz und versucht es einmal erneut."
                    : "Der Anbieter begrenzt derzeit die Anzahl der Anfragen (HTTP 429). Bitte später erneut versuchen.";
        }
        if (status == 509) {
            return retrying
                    ? "Der Anbieter meldet HTTP 509. Das ist kein defektes Videoformat. Die Verbindung wird geschlossen und einmal neu aufgebaut."
                    : "Der Anbieter lehnt den Abruf weiterhin mit HTTP 509 ab. Das kann auf ein serverseitiges Sitzungs-, Verbindungs- oder Übertragungslimit hindeuten. Bitte parallele Wiedergaben beenden oder später erneut versuchen.";
        }
        if (status >= 500) {
            return retrying
                    ? "Der Streaming-Server meldet HTTP " + status + ". Die App versucht es nach einer kurzen Pause erneut."
                    : "Der Streaming-Server meldet weiterhin HTTP " + status + ". Bitte später erneut versuchen.";
        }
        if (status > 0) {
            return "Der Streaming-Server hat den Abruf mit HTTP " + status + " abgelehnt.";
        }
        return "Der Streaming-Server hat mit einem Fehlerstatus geantwortet.";
    }

    private static boolean likelyTransportStream(String streamUrl) {
        if (streamUrl == null) return false;
        String lower = streamUrl.toLowerCase(Locale.ROOT);
        if (lower.contains(".m3u8")) return false;
        return lower.contains("/live/") || lower.endsWith(".ts") || lower.contains(".ts?");
    }

    static final class Decision {
        final String code;
        final String message;
        final boolean automaticRetry;
        final long retryDelayMs;
        final boolean transportStreamFallback;

        Decision(String code, String message, boolean automaticRetry,
                 long retryDelayMs, boolean transportStreamFallback) {
            this.code = code;
            this.message = message;
            this.automaticRetry = automaticRetry;
            this.retryDelayMs = retryDelayMs;
            this.transportStreamFallback = transportStreamFallback;
        }
    }
}
