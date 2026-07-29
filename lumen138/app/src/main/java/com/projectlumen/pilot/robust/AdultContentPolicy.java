package com.projectlumen.pilot.robust;

import java.util.AbstractList;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;

/**
 * Fail-closed adult-content classification and catalog projection.
 *
 * The raw catalog is never modified or truncated. Locked callers receive a
 * filtered projection, while an explicitly unlocked parent session receives
 * the complete raw catalog again.
 */
final class AdultContentPolicy {
    private AdultContentPolicy() { }

    static boolean isAdult(Channel channel) {
        if (channel == null) return false;
        return isAdultText(channel.group) || isAdultText(channel.name);
    }

    static boolean isAdultText(String value) {
        if (value == null || value.isBlank()) return false;
        String normalized = normalize(value);

        if (containsPhrase(normalized,
                "18 plus", "ab 18", "adults only", "adult only", "for adults",
                "only adults", "after dark", "red light", "redlight tv",
                "erwachsene inhalte", "nur fur erwachsene", "yetişkin içerik",
                "yetiskin icerik", "18 yas ustu", "18 yaş üstü")) {
            return true;
        }

        String compact = normalized.replace(" ", "");
        if (compact.contains("18plus") || compact.contains("xxxvod")
                || compact.contains("adultvod") || compact.contains("pornovod")) {
            return true;
        }

        String[] tokens = normalized.trim().split(" +");
        for (String token : tokens) {
            if (isStrongAdultToken(token)) return true;
        }
        return false;
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

    static int rawSize(List<Channel> source) {
        return raw(source).size();
    }

    private static boolean isStrongAdultToken(String token) {
        return token.equals("xxx") || token.equals("adult") || token.equals("adults")
                || token.equals("18plus") || token.equals("erotik")
                || token.equals("erotic") || token.equals("porno")
                || token.equals("porn") || token.equals("pornhub")
                || token.equals("sex") || token.equals("seks")
                || token.equals("cinsel") || token.equals("yetiskin")
                || token.equals("erwachsene") || token.equals("erwachsenen")
                || token.equals("playboy") || token.equals("hustler")
                || token.equals("brazzers") || token.equals("dorcel")
                || token.equals("penthouse") || token.equals("redlight")
                || token.equals("babestation") || token.equals("bangbros")
                || token.equals("realitykings") || token.equals("naughtyamerica")
                || token.equals("vividxxx") || token.equals("passionxxx")
                || token.equals("privategold") || token.equals("maturexxx")
                || token.equals("milfxxx");
    }

    private static boolean containsPhrase(String normalized, String... phrases) {
        for (String phrase : phrases) {
            String candidate = normalize(phrase).trim();
            if (!candidate.isEmpty() && normalized.contains(" " + candidate + " ")) {
                return true;
            }
        }
        return false;
    }

    private static String normalize(String value) {
        String lower = value.toLowerCase(Locale.ROOT)
                .replace('+', ' ')
                .replace('ı', 'i')
                .replace('ş', 's')
                .replace('ğ', 'g')
                .replace('ç', 'c')
                .replace('ö', 'o')
                .replace('ü', 'u')
                .replace('ä', 'a')
                .replace('ß', 's');
        StringBuilder result = new StringBuilder(lower.length() + 2);
        result.append(' ');
        boolean previousSpace = true;
        for (int i = 0; i < lower.length(); i++) {
            char c = lower.charAt(i);
            if (Character.isLetterOrDigit(c)) {
                result.append(c);
                previousSpace = false;
            } else if (!previousSpace) {
                result.append(' ');
                previousSpace = true;
            }
        }
        if (!previousSpace) result.append(' ');
        return result.toString();
    }

    private static final class ProtectedChannelList extends AbstractList<Channel> {
        private final List<Channel> raw;
        private volatile long generation = Long.MIN_VALUE;
        private volatile List<Channel> visible = Collections.emptyList();

        ProtectedChannelList(List<Channel> source) {
            raw = Collections.unmodifiableList(new ArrayList<>(
                    source == null ? Collections.emptyList() : source));
        }

        List<Channel> raw() { return raw; }

        private List<Channel> current() {
            long wanted = ParentalControl.generation();
            List<Channel> snapshot = visible;
            if (generation == wanted) return snapshot;
            synchronized (this) {
                if (generation == wanted) return visible;
                if (ParentalControl.isUnlocked()) {
                    visible = raw;
                } else {
                    ArrayList<Channel> safe = new ArrayList<>(raw.size());
                    for (Channel channel : raw) {
                        if (!isAdult(channel)) safe.add(channel);
                    }
                    visible = Collections.unmodifiableList(safe);
                }
                generation = wanted;
                return visible;
            }
        }

        @Override public Channel get(int index) { return current().get(index); }
        @Override public int size() { return current().size(); }
        @Override public Iterator<Channel> iterator() { return current().iterator(); }
    }
}
