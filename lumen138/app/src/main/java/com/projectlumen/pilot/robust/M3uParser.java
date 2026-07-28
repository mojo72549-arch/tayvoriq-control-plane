package com.projectlumen.pilot.robust;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

final class M3uParser {
    interface Progress {
        void update(long linesRead, int entries, long elapsedMs, boolean entryLimitReached);
    }

    private static final int READER_BUFFER = 1024 * 1024;
    private static final int PROGRESS_EVERY_ENTRIES = 5_000;
    private static final int DEADLINE_CHECK_EVERY_LINES = 2_048;

    static List<Channel> parse(InputStream input, int maxEntries, long timeoutMs,
                               Progress progress) throws Exception {
        ArrayList<Channel> result = new ArrayList<>(Math.min(maxEntries, 16_384));
        long startedNs = System.nanoTime();
        long deadlineNs = startedNs + timeoutMs * 1_000_000L;
        long linesRead = 0;
        int nextProgressEntry = PROGRESS_EVERY_ENTRIES;
        boolean limitReached = false;

        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(input, StandardCharsets.UTF_8), READER_BUFFER)) {
            String line;
            String pendingName = null;
            String pendingGroup = null;
            String pendingId = null;

            while ((line = reader.readLine()) != null) {
                linesRead++;

                if ((linesRead % DEADLINE_CHECK_EVERY_LINES) == 0
                        && System.nanoTime() > deadlineNs) {
                    long elapsed = elapsedMs(startedNs);
                    throw new IllegalStateException(
                            "Playlist-Prüfung wurde nach " + elapsed + " ms abgebrochen. "
                                    + result.size() + " Einträge wurden bis dahin erkannt.");
                }

                String value = cleanLine(line, linesRead == 1);
                if (value.isEmpty() || equalsIgnoreCase(value, "#EXTM3U")) continue;

                if (startsWithIgnoreCase(value, "#EXTINF")) {
                    int comma = value.lastIndexOf(',');
                    pendingName = comma >= 0 && comma + 1 < value.length()
                            ? value.substring(comma + 1).trim()
                            : "Unbenannter Eintrag";
                    pendingGroup = attribute(value, "group-title=\"", "Weitere");
                    pendingId = attribute(value, "tvg-id=\"", "");
                    continue;
                }

                if (value.charAt(0) == '#') continue;

                boolean supportedUrl = startsWithIgnoreCase(value, "http://")
                        || startsWithIgnoreCase(value, "https://");
                if (!supportedUrl) continue;

                if (result.size() < maxEntries) {
                    String name = pendingName == null || pendingName.isBlank()
                            ? fallbackName(value) : pendingName;
                    String group = pendingGroup == null || pendingGroup.isBlank()
                            ? "Weitere" : pendingGroup;
                    String id = pendingId == null || pendingId.isBlank()
                            ? stableFastId(name, value) : pendingId;
                    result.add(new Channel(id, name, group, value,
                            classify(name, group, value)));
                } else {
                    limitReached = true;
                }

                pendingName = null;
                pendingGroup = null;
                pendingId = null;

                if (result.size() >= nextProgressEntry) {
                    progress(progress, linesRead, result.size(), startedNs, limitReached);
                    nextProgressEntry += PROGRESS_EVERY_ENTRIES;
                }
            }
        }

        progress(progress, linesRead, result.size(), startedNs, limitReached);
        return AdultContentPolicy.protect(result);
    }

    private static String cleanLine(String line, boolean firstLine) {
        String value = line == null ? "" : line.trim();
        if (firstLine && !value.isEmpty() && value.charAt(0) == '\uFEFF') {
            value = value.substring(1).trim();
        }
        return value;
    }

    private static String attribute(String text, String key, String fallback) {
        int start = indexOfIgnoreCase(text, key, 0);
        if (start < 0) return fallback;
        start += key.length();
        int end = text.indexOf('"', start);
        if (end < 0) return fallback;
        String value = text.substring(start, end).trim();
        return value.isEmpty() ? fallback : value;
    }

    private static Channel.Type classify(String name, String group, String url) {
        if (containsIgnoreCase(url, "/series/") || containsIgnoreCase(group, "series")
                || containsIgnoreCase(group, "serie") || containsIgnoreCase(group, "dizi")
                || containsIgnoreCase(name, "episode") || containsIgnoreCase(name, "staffel")) {
            return Channel.Type.SERIES;
        }
        if (containsIgnoreCase(url, "/movie/") || containsIgnoreCase(group, "movie")
                || containsIgnoreCase(group, "film") || containsIgnoreCase(group, "vod")
                || containsIgnoreCase(group, "cinema") || containsIgnoreCase(group, "sinema")) {
            return Channel.Type.MOVIE;
        }
        return Channel.Type.LIVE;
    }

    private static String fallbackName(String url) {
        int slash = url.lastIndexOf('/');
        String value = slash >= 0 ? url.substring(slash + 1) : url;
        int question = value.indexOf('?');
        if (question >= 0) value = value.substring(0, question);
        return value.isBlank() ? "Stream" : value;
    }

    private static String stableFastId(String name, String url) {
        long hash = 0xcbf29ce484222325L;
        hash = fnv1a(hash, name);
        hash ^= '|';
        hash *= 0x100000001b3L;
        hash = fnv1a(hash, url);
        return Long.toUnsignedString(hash, 16);
    }

    private static long fnv1a(long hash, String value) {
        for (int i = 0; i < value.length(); i++) {
            hash ^= value.charAt(i);
            hash *= 0x100000001b3L;
        }
        return hash;
    }

    private static boolean startsWithIgnoreCase(String text, String prefix) {
        return text.length() >= prefix.length()
                && text.regionMatches(true, 0, prefix, 0, prefix.length());
    }

    private static boolean equalsIgnoreCase(String left, String right) {
        return left.length() == right.length()
                && left.regionMatches(true, 0, right, 0, right.length());
    }

    private static boolean containsIgnoreCase(String text, String needle) {
        return text != null && indexOfIgnoreCase(text, needle, 0) >= 0;
    }

    private static int indexOfIgnoreCase(String text, String needle, int fromIndex) {
        if (text == null || needle == null) return -1;
        int limit = text.length() - needle.length();
        for (int i = Math.max(0, fromIndex); i <= limit; i++) {
            if (text.regionMatches(true, i, needle, 0, needle.length())) return i;
        }
        return -1;
    }

    private static void progress(Progress progress, long linesRead, int entries,
                                 long startedNs, boolean limitReached) {
        if (progress != null) {
            progress.update(linesRead, entries, elapsedMs(startedNs), limitReached);
        }
    }

    private static long elapsedMs(long startedNs) {
        return (System.nanoTime() - startedNs) / 1_000_000L;
    }
}
