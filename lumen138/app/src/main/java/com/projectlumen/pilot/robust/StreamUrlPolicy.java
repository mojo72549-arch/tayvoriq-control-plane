package com.projectlumen.pilot.robust;

import java.net.URL;
import java.util.Locale;

/** Pure URL policy shared by playback recovery tests and the Android player. */
final class StreamUrlPolicy {
    private StreamUrlPolicy() { }

    static boolean shouldForceMpegTs(String streamUrl) {
        if (streamUrl == null || streamUrl.isBlank()) return false;
        String lower = streamUrl.toLowerCase(Locale.ROOT);
        if (lower.contains(".m3u8") || lower.contains("format=m3u8")) return false;
        return lower.endsWith(".ts") || lower.contains(".ts?") || lower.contains("/live/");
    }

    static String httpCompatibilityUrl(String sourceUrl, Throwable failure) {
        try {
            URL parsed = new URL(sourceUrl);
            if (!"https".equalsIgnoreCase(parsed.getProtocol())) return null;
            int port = parsed.getPort();
            if (port <= 0 || port == 443 || !isTlsProtocolMismatch(failure)) return null;
            return new URL("http", parsed.getHost(), port, parsed.getFile()).toString();
        } catch (Exception ignored) {
            return null;
        }
    }

    static boolean isTlsProtocolMismatch(Throwable failure) {
        Throwable current = failure;
        for (int depth = 0; current != null && depth < 10; depth++, current = current.getCause()) {
            String message = current.getMessage();
            if (message == null) continue;
            String normalized = message.toLowerCase(Locale.ROOT);
            if (normalized.contains("unable to parse tls packet header")
                    || normalized.contains("not an ssl/tls record")
                    || normalized.contains("wrong version number")
                    || normalized.contains("plaintext connection")
                    || normalized.contains("unrecognized ssl message")
                    || normalized.contains("cleartext response on tls")) {
                return true;
            }
        }
        return false;
    }
}
