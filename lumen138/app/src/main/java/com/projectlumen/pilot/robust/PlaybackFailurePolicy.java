package com.projectlumen.pilot.robust;

/** Deterministic playback failure classification without exposing stream URLs. */
final class PlaybackFailurePolicy {
    static final int NO_HTTP_STATUS = -1;

    private PlaybackFailurePolicy() { }

    static int httpStatus(String details) {
        if (details == null) return NO_HTTP_STATUS;
        String marker = "httpStatus=";
        int start = details.indexOf(marker);
        if (start < 0) return NO_HTTP_STATUS;
        start += marker.length();
        int end = start;
        while (end < details.length() && Character.isDigit(details.charAt(end))) end++;
        if (end == start) return NO_HTTP_STATUS;
        try { return Integer.parseInt(details.substring(start, end)); }
        catch (NumberFormatException ignored) { return NO_HTTP_STATUS; }
    }

    static boolean isHttpFailure(String errorName, int status) {
        return status > 0 || contains(errorName, "BAD_HTTP_STATUS");
    }

    static boolean shouldAutoRetry(int status, int attempts) {
        if (attempts >= 1) return false;
        return status == 408 || status == 425 || status == 429
                || status == 500 || status == 502 || status == 503
                || status == 504 || status == 509;
    }

    static long retryDelayMs(int status) {
        if (status == 429 || status == 509) return 5_000L;
        if (status >= 500) return 2_500L;
        return 1_800L;
    }

    static String diagnosticCode(String errorName, int status) {
        if (status > 0) return status == 509
                ? "HTTP_509_PROVIDER_LIMIT"
                : "HTTP_" + status + "_SERVER_RESPONSE";
        return errorName == null || errorName.isBlank()
                ? "ERROR_CODE_UNSPECIFIED" : errorName;
    }

    static String message(String errorName, String details) {
        int status = httpStatus(details);
        if (status == 509) {
            return "Der Anbieter hat den Filmabruf mit HTTP 509 abgewiesen. "
                    + "Meist ist das Verbindungslimit erreicht oder der Abruf vorübergehend gesperrt. "
                    + "Andere laufende Streams schließen und nach kurzer Pause erneut versuchen.";
        }
        if (status == 429) {
            return "Der Anbieter hat zu viele Abrufe erkannt (HTTP 429). "
                    + "Bitte kurz warten und danach erneut versuchen.";
        }
        if (status == 401 || status == 403) {
            return "Der Server hat den Abruf abgewiesen (HTTP " + status + "). "
                    + "Zugang, Freischaltung oder Streamadresse prüfen.";
        }
        if (status == 404 || status == 410) {
            return "Der Film ist unter dieser Serveradresse nicht mehr verfügbar (HTTP "
                    + status + "). Die Playlist sollte aktualisiert werden.";
        }
        if (status >= 500) {
            return "Der Streaming-Server ist vorübergehend nicht verfügbar (HTTP "
                    + status + "). Bitte später erneut versuchen.";
        }
        if (status > 0) {
            return "Der Streaming-Server hat den Abruf mit HTTP " + status + " abgewiesen.";
        }
        if (contains(errorName, "TIMEOUT")) {
            return "Der Streaming-Server antwortet nicht rechtzeitig.";
        }
        if (contains(errorName, "NETWORK_CONNECTION_FAILED")) {
            return "Die Netzwerkverbindung zum Streaming-Server ist fehlgeschlagen.";
        }
        if (contains(errorName, "PARSING") || contains(errorName, "CONTENT_TYPE")) {
            return "Der Server hat Daten geliefert, deren Medienformat nicht erkannt oder gelesen werden konnte.";
        }
        if (contains(errorName, "DECODER") || contains(errorName, "DECODING")) {
            return "Der Video- oder Audiocodec wird auf diesem Gerät nicht unterstützt.";
        }
        return "Der genaue technische Fehler wurde in der Diagnose gespeichert.";
    }

    private static boolean contains(String value, String token) {
        return value != null && value.contains(token);
    }
}
