package com.projectlumen.pilot.robust;

import java.util.AbstractList;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;

/**
 * Fail-closed adult-content classification.
 * The normal catalog is permanently family-safe. Adult movies are exposed only
 * through a dedicated parent-only projection and never by mutating MainActivity.
 */
final class AdultContentPolicy {
    private static final int TOKEN_LIMIT = 24;
    private static final int PREVIOUS_NONE = 0;
    private static final int PREVIOUS_AFTER = 1;
    private static final int PREVIOUS_RED = 2;
    private static final int PREVIOUS_NUR = 3;

    private AdultContentPolicy() { }

    static boolean isAdult(Channel channel) {
        if (channel == null) return false;
        return scan(channel.group, true)
                || scan(channel.name, false)
                || scan(channel.url, false);
    }

    /** Conservative generic check used for player-side safeguards and tests. */
    static boolean isAdultText(String value) {
        return scan(value, false);
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

    /**
     * Single-pass token scanner. No regex, no lower-cased copy of long names and
     * no per-entry token array. Weak words such as HOT/SEX are accepted only in
     * group labels, never in ordinary movie titles.
     */
    private static boolean scan(String value, boolean broadGroupRules) {
        if (value == null || value.isBlank()) return false;
        StringBuilder token = new StringBuilder(TOKEN_LIMIT);
        boolean overflow = false;
        int previous = PREVIOUS_NONE;

        for (int index = 0; index <= value.length(); index++) {
            char original = index < value.length() ? value.charAt(index) : ' ';
            if (original == '+' && !overflow && tokenEquals(token, "18")) return true;

            char normalized = normalizeChar(original);
            if (Character.isLetterOrDigit(normalized)) {
                if (!overflow) {
                    if (token.length() < TOKEN_LIMIT) token.append(normalized);
                    else overflow = true;
                }
                continue;
            }

            if (!overflow && token.length() > 0) {
                if (isStrongToken(token)) return true;
                if (previous == PREVIOUS_RED && tokenEquals(token, "light")) return true;
                if (broadGroupRules) {
                    if (isWeakGroupToken(token)) return true;
                    if (previous == PREVIOUS_AFTER && tokenEquals(token, "dark")) return true;
                    if (previous == PREVIOUS_NUR
                            && (tokenEquals(token, "erwachsene")
                            || tokenEquals(token, "erwachsenen"))) return true;
                }
                previous = tokenEquals(token, "after") ? PREVIOUS_AFTER
                        : tokenEquals(token, "red") ? PREVIOUS_RED
                        : tokenEquals(token, "nur") ? PREVIOUS_NUR
                        : PREVIOUS_NONE;
            } else {
                previous = PREVIOUS_NONE;
            }
            token.setLength(0);
            overflow = false;
        }
        return false;
    }

    private static boolean isStrongToken(StringBuilder token) {
        return tokenEquals(token, "xxx")
                || tokenEquals(token, "adult")
                || tokenEquals(token, "adults")
                || tokenEquals(token, "18plus")
                || tokenEquals(token, "erotik")
                || tokenEquals(token, "erotic")
                || tokenEquals(token, "porno")
                || tokenEquals(token, "porn")
                || tokenEquals(token, "pornhub")
                || tokenEquals(token, "playboy")
                || tokenEquals(token, "hustler")
                || tokenEquals(token, "brazzers")
                || tokenEquals(token, "redlight")
                || tokenEquals(token, "yetiskin")
                || tokenEquals(token, "erwachsene")
                || tokenEquals(token, "erwachsenen")
                || tokenEquals(token, "dorcel");
    }

    private static boolean isWeakGroupToken(StringBuilder token) {
        return tokenEquals(token, "18")
                || tokenEquals(token, "sex")
                || tokenEquals(token, "sexy")
                || tokenEquals(token, "hot")
                || tokenEquals(token, "venus");
    }

    private static boolean tokenEquals(StringBuilder token, String expected) {
        if (token.length() != expected.length()) return false;
        for (int index = 0; index < expected.length(); index++) {
            if (token.charAt(index) != expected.charAt(index)) return false;
        }
        return true;
    }

    private static char normalizeChar(char value) {
        char lower = Character.toLowerCase(value);
        if (lower == 'ı') return 'i';
        if (lower == 'ş') return 's';
        if (lower == 'ğ') return 'g';
        if (lower == 'ç') return 'c';
        if (lower == 'ö') return 'o';
        if (lower == 'ü') return 'u';
        return lower;
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
