package com.projectlumen.pilot.robust;

import java.util.AbstractList;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;

/**
 * Fail-closed adult-content classification.
 * The normal catalog is permanently family-safe. Adult movies are exposed only
 * through a dedicated parent-only projection and never by mutating MainActivity.
 */
final class AdultContentPolicy {
    private AdultContentPolicy() { }

    static boolean isAdult(Channel channel) {
        if (channel == null) return false;
        return isAdultGroup(channel.group)
                || isAdultName(channel.name)
                || isAdultUrl(channel.url);
    }

    static boolean isAdultText(String value) {
        return isAdultGroup(value) || isAdultName(value);
    }

    private static boolean isAdultGroup(String value) {
        String normalized = normalize(value);
        if (normalized.isEmpty()) return false;
        if (containsPhrase(normalized, "adults only")
                || containsPhrase(normalized, "adult only")
                || containsPhrase(normalized, "after dark")
                || containsPhrase(normalized, "red light")
                || containsPhrase(normalized, "nur erwachsene")) return true;

        return hasAnyToken(normalized,
                "xxx", "adult", "adults", "18", "18plus", "erotik", "erotic",
                "porno", "porn", "pornhub", "playboy", "hustler", "brazzers",
                "redlight", "yetiskin", "erwachsene", "erwachsenen", "sexy", "sex",
                "hot", "venus", "dorcel");
    }

    private static boolean isAdultName(String value) {
        String normalized = normalize(value);
        if (normalized.isEmpty()) return false;
        if (containsPhrase(normalized, "adults only")
                || containsPhrase(normalized, "adult only")
                || containsPhrase(normalized, "red light")) return true;

        // Deliberately conservative for titles: e.g. "Sex Education" remains visible.
        return hasAnyToken(normalized,
                "xxx", "adult", "18plus", "erotik", "erotic", "porno", "porn",
                "pornhub", "playboy", "hustler", "brazzers", "redlight",
                "yetiskin", "dorcel");
    }

    private static boolean isAdultUrl(String value) {
        String normalized = normalize(value);
        if (normalized.isEmpty()) return false;
        return hasAnyToken(normalized,
                "xxx", "adult", "18plus", "erotik", "erotic", "porno", "porn",
                "pornhub", "playboy", "hustler", "brazzers", "redlight", "dorcel");
    }

    static List<Channel> protect(List<Channel> source) {
        if (source instanceof ProtectedChannelList) return source;
        return new ProtectedChannelList(source);
    }

    static List<Channel> raw(List<Channel> source) {
        if (source instanceof ProtectedChannelList) {
            return ((ProtectedChannelList) source).raw();
        }
        return source == null ? Collections.emptyList() : source;
    }

    static List<Channel> adultMovies(List<Channel> source) {
        List<Channel> raw = raw(source);
        if (raw.isEmpty()) return Collections.emptyList();
        ArrayList<Channel> result = new ArrayList<>();
        for (Channel channel : raw) {
            if (channel != null && channel.type == Channel.Type.MOVIE && isAdult(channel)) {
                result.add(channel);
            }
        }
        return Collections.unmodifiableList(result);
    }

    private static String normalize(String value) {
        if (value == null || value.isBlank()) return "";
        String lower = value.toLowerCase(Locale.ROOT)
                .replace('+', ' ')
                .replace('ı', 'i')
                .replace('ş', 's')
                .replace('ğ', 'g')
                .replace('ç', 'c')
                .replace('ö', 'o')
                .replace('ü', 'u');
        StringBuilder result = new StringBuilder(lower.length());
        boolean previousSpace = true;
        for (int index = 0; index < lower.length(); index++) {
            char valueChar = lower.charAt(index);
            if (Character.isLetterOrDigit(valueChar)) {
                result.append(valueChar);
                previousSpace = false;
            } else if (!previousSpace) {
                result.append(' ');
                previousSpace = true;
            }
        }
        int length = result.length();
        while (length > 0 && result.charAt(length - 1) == ' ') {
            result.setLength(--length);
        }
        return result.toString();
    }

    private static boolean containsPhrase(String normalized, String phrase) {
        int from = 0;
        while (true) {
            int index = normalized.indexOf(phrase, from);
            if (index < 0) return false;
            int end = index + phrase.length();
            boolean left = index == 0 || normalized.charAt(index - 1) == ' ';
            boolean right = end == normalized.length() || normalized.charAt(end) == ' ';
            if (left && right) return true;
            from = index + 1;
        }
    }

    private static boolean hasAnyToken(String normalized, String... tokens) {
        int start = 0;
        while (start < normalized.length()) {
            while (start < normalized.length() && normalized.charAt(start) == ' ') start++;
            if (start >= normalized.length()) break;
            int end = start;
            while (end < normalized.length() && normalized.charAt(end) != ' ') end++;
            int length = end - start;
            for (String token : tokens) {
                if (token.length() == length && normalized.regionMatches(start, token, 0, length)) {
                    return true;
                }
            }
            start = end + 1;
        }
        return false;
    }

    private static final class ProtectedChannelList extends AbstractList<Channel> {
        private final List<Channel> raw;
        private final List<Channel> safe;

        ProtectedChannelList(List<Channel> source) {
            List<Channel> input = source == null ? Collections.emptyList() : source;
            raw = Collections.unmodifiableList(new ArrayList<>(input));
            ArrayList<Channel> filtered = new ArrayList<>(raw.size());
            for (Channel channel : raw) {
                if (!isAdult(channel)) filtered.add(channel);
            }
            safe = Collections.unmodifiableList(filtered);
        }

        List<Channel> raw() { return raw; }

        @Override public Channel get(int index) { return safe.get(index); }
        @Override public int size() { return safe.size(); }
        @Override public Iterator<Channel> iterator() { return safe.iterator(); }
    }
}
