package com.projectlumen.pilot.robust;

import java.util.AbstractList;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;

/**
 * Fail-closed adult-content classification and catalog projection.
 * Raw entries remain available for an explicitly unlocked parent session,
 * but locked callers never receive adult rows in lists, search or counters.
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
        if (normalized.contains(" 18+ ") || normalized.contains(" adults only ")
                || normalized.contains(" adult only ") || normalized.contains(" after dark ")
                || normalized.contains(" red light ")) return true;

        String[] tokens = normalized.trim().split(" +");
        for (String token : tokens) {
            if (token.equals("xxx") || token.equals("adult") || token.equals("adults")
                    || token.equals("18plus") || token.equals("erotik")
                    || token.equals("erotic") || token.equals("porno")
                    || token.equals("porn") || token.equals("pornhub")
                    || token.equals("sex") || token.equals("seks")
                    || token.equals("playboy") || token.equals("hustler")
                    || token.equals("brazzers") || token.equals("redlight")) {
                return true;
            }
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

    private static String normalize(String value) {
        String lower = value.toLowerCase(Locale.ROOT)
                .replace('+', 'plus')
                .replace('ı', 'i')
                .replace('ş', 's')
                .replace('ğ', 'g')
                .replace('ç', 'c')
                .replace('ö', 'o')
                .replace('ü', 'u');
        StringBuilder result = new StringBuilder(lower.length() + 2);
        result.append(' ');
        boolean previousSpace = true;
        for (int i = 0; i < lower.length(); i++) {
            char c = lower.charAt(i);
            boolean allowed = Character.isLetterOrDigit(c);
            if (allowed) {
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
