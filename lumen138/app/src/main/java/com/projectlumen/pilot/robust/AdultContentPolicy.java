package com.projectlumen.pilot.robust;

import java.util.AbstractList;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Fail-closed adult-content classification and catalog projection.
 * The normal catalog never mixes adult rows. A dedicated adult projection exists
 * only for a currently unlocked parent session.
 */
final class AdultContentPolicy {
    private static final AtomicLong SCOPE_GENERATION = new AtomicLong(1);
    private static volatile boolean adultMode;

    private AdultContentPolicy() { }

    static boolean isAdult(Channel channel) {
        if (channel == null) return false;
        return isAdultText(channel.group) || isAdultText(channel.name);
    }

    static boolean isAdultText(String value) {
        if (value == null || value.isBlank()) return false;
        String normalized = normalize(value);
        if (normalized.contains(" adults only ")
                || normalized.contains(" adult only ")
                || normalized.contains(" after dark ")
                || normalized.contains(" red light ")) return true;

        String[] tokens = normalized.trim().split(" +");
        for (String token : tokens) {
            if (token.equals("xxx") || token.equals("adult") || token.equals("adults")
                    || token.equals("18plus") || token.equals("erotik")
                    || token.equals("erotic") || token.equals("porno")
                    || token.equals("porn") || token.equals("pornhub")
                    || token.equals("playboy") || token.equals("hustler")
                    || token.equals("brazzers") || token.equals("redlight")) {
                return true;
            }
        }
        return false;
    }

    static boolean isAdultMode() {
        if (!ParentalControl.isUnlocked() && adultMode) setAdultMode(false);
        return adultMode && ParentalControl.isUnlocked();
    }

    static void setAdultMode(boolean enabled) {
        boolean next = enabled && ParentalControl.isUnlocked();
        if (adultMode != next) {
            adultMode = next;
            SCOPE_GENERATION.incrementAndGet();
        }
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

    private static long projectionGeneration() {
        return ParentalControl.generation() * 31L + SCOPE_GENERATION.get();
    }

    private static String normalize(String value) {
        String lower = value.toLowerCase(Locale.ROOT)
                .replace("+", "plus")
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
            long wanted = projectionGeneration();
            List<Channel> snapshot = visible;
            if (generation == wanted) return snapshot;
            synchronized (this) {
                if (generation == wanted) return visible;
                boolean adultOnly = isAdultMode();
                ArrayList<Channel> filtered = new ArrayList<>(raw.size());
                for (Channel channel : raw) {
                    boolean adult = isAdult(channel);
                    if (adultOnly ? adult : !adult) filtered.add(channel);
                }
                visible = Collections.unmodifiableList(filtered);
                generation = wanted;
                return visible;
            }
        }

        @Override public Channel get(int index) { return current().get(index); }
        @Override public int size() { return current().size(); }
        @Override public Iterator<Channel> iterator() { return current().iterator(); }
    }
}
