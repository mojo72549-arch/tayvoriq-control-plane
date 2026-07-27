package com.projectlumen.pilot.robust;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

final class M3uParser {
    private static final Pattern GROUP = Pattern.compile("group-title=\\\"([^\\\"]*)\\\"", Pattern.CASE_INSENSITIVE);
    private static final Pattern TVG_ID = Pattern.compile("tvg-id=\\\"([^\\\"]*)\\\"", Pattern.CASE_INSENSITIVE);

    static List<Channel> parse(InputStream input, int maxEntries) throws Exception {
        ArrayList<Channel> result = new ArrayList<>();
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(input, StandardCharsets.UTF_8), 64 * 1024)) {
            String line;
            String pendingName = null;
            String pendingGroup = null;
            String pendingId = null;
            while ((line = reader.readLine()) != null && result.size() < maxEntries) {
                String value = line.trim();
                if (value.isEmpty() || value.equalsIgnoreCase("#EXTM3U")) continue;
                if (value.regionMatches(true, 0, "#EXTINF", 0, 7)) {
                    int comma = value.lastIndexOf(',');
                    pendingName = comma >= 0 && comma + 1 < value.length() ? value.substring(comma + 1).trim() : "Unbenannter Eintrag";
                    pendingGroup = attr(GROUP, value, "Weitere");
                    pendingId = attr(TVG_ID, value, "");
                    continue;
                }
                if (value.startsWith("#")) continue;
                if (value.startsWith("http://") || value.startsWith("https://")) {
                    String name = pendingName == null ? fallbackName(value) : pendingName;
                    String group = pendingGroup == null ? "Weitere" : pendingGroup;
                    String id = pendingId == null || pendingId.isBlank() ? hash(name + "|" + value) : pendingId;
                    result.add(new Channel(id, name, group, value, classify(name, group, value)));
                    pendingName = null;
                    pendingGroup = null;
                    pendingId = null;
                }
            }
        }
        return result;
    }

    private static String attr(Pattern pattern, String text, String fallback) {
        Matcher matcher = pattern.matcher(text);
        return matcher.find() ? matcher.group(1).trim() : fallback;
    }

    private static Channel.Type classify(String name, String group, String url) {
        String text = (name + " " + group + " " + url).toLowerCase(Locale.ROOT);
        if (text.contains("/series/") || text.contains("series") || text.contains("serie")
                || text.contains("dizi") || text.contains("episode") || text.contains("staffel")) return Channel.Type.SERIES;
        if (text.contains("/movie/") || text.contains(" movie") || text.contains("film")
                || text.contains("vod") || text.contains("cinema") || text.contains("sinema")) return Channel.Type.MOVIE;
        return Channel.Type.LIVE;
    }

    private static String fallbackName(String url) {
        int slash = url.lastIndexOf('/');
        String value = slash >= 0 ? url.substring(slash + 1) : url;
        int question = value.indexOf('?');
        if (question >= 0) value = value.substring(0, question);
        return value.isBlank() ? "Stream" : value;
    }

    private static String hash(String value) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8));
            StringBuilder out = new StringBuilder();
            for (int i = 0; i < 8; i++) out.append(String.format(Locale.ROOT, "%02x", digest[i]));
            return out.toString();
        } catch (Exception ignored) {
            return Integer.toHexString(value.hashCode());
        }
    }
}
