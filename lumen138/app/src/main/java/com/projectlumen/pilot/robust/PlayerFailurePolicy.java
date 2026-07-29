package com.projectlumen.pilot.robust;

/** Pure decision logic for player failures; kept Android-free for regression tests. */
final class PlayerFailurePolicy {
    private PlayerFailurePolicy() { }

    static String category(String errorName, int httpStatus) {
        if (httpStatus >= 0) return "HTTP";
        String value = safe(errorName);
        if (value.contains("CONTENT_TYPE")) return "CONTENT_TYPE";
        if (value.contains("PARSING")) return "PARSING";
        if (value.contains("DECODER") || value.contains("DECODING")) return "DECODER";
        if (value.contains("TIMEOUT")) return "TIMEOUT";
        if (value.contains("NETWORK_CONNECTION_FAILED") || value.contains("IO_NETWORK")) {
            return "NETWORK";
        }
        return "OTHER";
    }

    static boolean shouldAutoRetryHttp(int httpStatus, int retriesAlreadyUsed) {
        if (retriesAlreadyUsed >= 1) return false;
        return httpStatus == 408 || httpStatus == 425 || httpStatus == 429
                || httpStatus == 509 || httpStatus >= 500 && httpStatus <= 599;
    }

    static long retryDelayMs(int httpStatus) {
        if (httpStatus == 429 || httpStatus == 509) return 1_800L;
        return 1_200L;
    }

    static boolean isContainerFailure(String errorName, int httpStatus) {
        if (httpStatus >= 0) return false;
        String value = safe(errorName);
        return value.contains("PARSING") || value.contains("CONTENT_TYPE");
    }

    static String diagnosticCode(String errorName, int httpStatus) {
        if (httpStatus >= 0) return "HTTP_" + httpStatus;
        String category = category(errorName, httpStatus);
        if (category.equals("CONTENT_TYPE")) return "STREAM_CONTENT_TYPE";
        if (category.equals("PARSING")) return "STREAM_CONTAINER_PARSING";
        if (category.equals("DECODER")) return "DEVICE_DECODER";
        if (category.equals("TIMEOUT")) return "STREAM_TIMEOUT";
        if (category.equals("NETWORK")) return "NETWORK_CONNECTION";
        return safe(errorName).isBlank() ? "PLAYER_UNKNOWN" : safe(errorName);
    }

    static String friendlyMessage(String errorName, int httpStatus) {
        if (httpStatus == 401 || httpStatus == 403) {
            return "Der Streaming-Server hat den Zugriff abgewiesen. Zugang, Freischaltung oder Streamadresse prüfen.";
        }
        if (httpStatus == 404 || httpStatus == 410) {
            return "Der Film ist unter dieser Streamadresse beim Anbieter nicht verfügbar.";
        }
        if (httpStatus == 429) {
            return "Der Anbieter meldet zu viele Abrufe. Kurz warten und danach erneut versuchen.";
        }
        if (httpStatus == 509) {
            return "Der Streaming-Server hat den Abruf mit HTTP 509 abgewiesen. Das ist ein Anbieter- oder Serverlimit; es wurde keine abspielbare Videodatei ausgeliefert.";
        }
        if (httpStatus >= 500 && httpStatus <= 599) {
            return "Der Streaming-Server ist momentan nicht verfügbar und antwortet mit HTTP "
                    + httpStatus + ".";
        }
        if (httpStatus >= 400) {
            return "Der Streaming-Server hat den Abruf mit HTTP " + httpStatus + " abgewiesen.";
        }

        String category = category(errorName, httpStatus);
        if (category.equals("TIMEOUT")) {
            return "Der Streaming-Server antwortet nicht rechtzeitig.";
        }
        if (category.equals("NETWORK")) {
            return "Die Netzwerkverbindung zum Streaming-Server ist fehlgeschlagen.";
        }
        if (category.equals("CONTENT_TYPE")) {
            return "Der Server hat statt eines unterstützten Videos einen anderen Inhaltstyp geliefert.";
        }
        if (category.equals("PARSING")) {
            return "Der gelieferte Videocontainer konnte nicht gelesen werden. Der Kompatibilitätsmodus kann ein anderes Streamprofil testen.";
        }
        if (category.equals("DECODER")) {
            return "Der Video- oder Audiocodec wird auf diesem Gerät nicht unterstützt.";
        }
        return "Der genaue technische Fehler wurde in der Diagnose gespeichert.";
    }

    private static String safe(String value) {
        return value == null ? "" : value.toUpperCase(java.util.Locale.ROOT);
    }
}
