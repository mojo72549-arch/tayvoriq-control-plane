package com.projectlumen.pilot.robust;

import java.util.AbstractList;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;

/**
 * Fail-closed classification for explicit, adult-branded and FSK-18 content.
 * The normal catalog is permanently family-safe. Protected rows are exposed
 * only through the dedicated parent activity.
 */
final class AdultContentPolicy {
    static final byte CLASS_UNKNOWN = -1;
    static final byte CLASS_SAFE = 0;
    static final byte CLASS_EXPLICIT = 1;
    static final byte CLASS_AGE_18 = 2;
    static final byte CLASS_ADULT_BRAND = 3;

    private static final int TOKEN_LIMIT = 32;
    private static final int PREVIOUS_NONE = 0;
    private static final int PREVIOUS_AFTER = 1;
    private static final int PREVIOUS_RED = 2;
    private static final int PREVIOUS_NUR = 3;
    private static final int PREVIOUS_18 = 4;
    private static final int PREVIOUS_FSK = 5;
    private static final int PREVIOUS_AB = 6;
    private static final int PREVIOUS_ADULTS = 7;
    private static final int PREVIOUS_MAN = 8;
    private static final int PREVIOUS_BLUE = 9;
    private static final int PREVIOUS_DIGITAL = 10;
    private static final int PREVIOUS_REALITY = 11;
    private static final int PREVIOUS_NAUGHTY = 12;

    private AdultContentPolicy() { }

    static boolean isAdult(Channel channel) {
        return channel != null && channel.adult;
    }

    static byte classifyRaw(String group, String name, String url) {
        byte groupClass = scan(group, true);
        if (groupClass != CLASS_SAFE) return groupClass;
        byte nameClass = scan(name, false);
        if (nameClass != CLASS_SAFE) return nameClass;
        return scan(url, false);
    }

    /** Conservative generic check used by tests and defensive UI guards. */
    static boolean isAdultText(String value) {
        return scan(value, false) != CLASS_SAFE;
    }

    static List<Channel> protect(List<Channel> source) {
        if (source instanceof ProtectedChannelList) return source;
        return new ProtectedChannelList(source);
    }

    static List<Channel> protectClassified(List<Channel> raw, List<Channel> safe) {
        return new ProtectedChannelList(raw, safe);
    }

    static List<Channel> raw(List<Channel> source) {
        if (source instanceof ProtectedChannelList) {
            return ((ProtectedChannelList) source).raw();
        }
        return source == null ? Collections.emptyList() : source;
    }

    static List<Channel> adultContent(List<Channel> source, Channel.Type type) {
        List<Channel> raw = raw(source);
        if (raw.isEmpty()) return Collections.emptyList();
        ArrayList<Channel> result = new ArrayList<>();
        for (Channel channel : raw) {
            if (channel != null && channel.adult && (type == null || channel.type == type)) {
                result.add(channel);
            }
        }
        return Collections.unmodifiableList(result);
    }

    static List<Channel> adultMovies(List<Channel> source) {
        return adultContent(source, Channel.Type.MOVIE);
    }

    static String classLabel(byte value) {
        if (value == CLASS_AGE_18) return "FSK 18";
        if (value == CLASS_ADULT_BRAND) return "Adult-Marke";
        if (value == CLASS_EXPLICIT) return "Erwachseneninhalt";
        return "Sicher";
    }

    /**
     * Allocation-bounded scanner without regex or token arrays. Weak words such
     * as HOT or SEX are accepted only in category/group labels. FSK 18, 18+ and
     * AB 18 are protected in both categories and titles.
     */
    private static byte scan(String value, boolean broadGroupRules) {
        if (value == null || value.isBlank()) return CLASS_SAFE;
        StringBuilder token = new StringBuilder(TOKEN_LIMIT);
        boolean overflow = false;
        int previous = PREVIOUS_NONE;

        for (int index = 0; index <= value.length(); index++) {
            char original = index < value.length() ? value.charAt(index) : ' ';
            if (original == '+' && !overflow && tokenEquals(token, "18")) {
                return CLASS_AGE_18;
            }

            char normalized = normalizeChar(original);
            if (Character.isLetterOrDigit(normalized)) {
                if (!overflow) {
                    if (token.length() < TOKEN_LIMIT) token.append(normalized);
                    else overflow = true;
                }
                continue;
            }

            if (!overflow && token.length() > 0) {
                byte direct = directClass(token, broadGroupRules);
                if (direct != CLASS_SAFE) return direct;

                if (previous == PREVIOUS_RED && tokenEquals(token, "light")) {
                    return CLASS_ADULT_BRAND;
                }
                if (previous == PREVIOUS_FSK && tokenEquals(token, "18")) {
                    return CLASS_AGE_18;
                }
                if (previous == PREVIOUS_AB && tokenEquals(token, "18")) {
                    return CLASS_AGE_18;
                }
                if (previous == PREVIOUS_ADULTS && tokenEquals(token, "only")) {
                    return CLASS_EXPLICIT;
                }
                if (previous == PREVIOUS_MAN && tokenEquals(token, "x")) {
                    return CLASS_ADULT_BRAND;
                }
                if (previous == PREVIOUS_BLUE && tokenEquals(token, "hustler")) {
                    return CLASS_ADULT_BRAND;
                }
                if (previous == PREVIOUS_DIGITAL && tokenEquals(token, "playground")) {
                    return CLASS_ADULT_BRAND;
                }
                if (previous == PREVIOUS_REALITY && tokenEquals(token, "kings")) {
                    return CLASS_ADULT_BRAND;
                }
                if (previous == PREVIOUS_NAUGHTY && tokenEquals(token, "america")) {
                    return CLASS_ADULT_BRAND;
                }

                if (broadGroupRules) {
                    if (previous == PREVIOUS_AFTER && tokenEquals(token, "dark")) {
                        return CLASS_EXPLICIT;
                    }
                    if (previous == PREVIOUS_NUR
                            && (tokenEquals(token, "erwachsene")
                            || tokenEquals(token, "erwachsenen"))) {
                        return CLASS_EXPLICIT;
                    }
                    if (previous == PREVIOUS_18 && isMediaContext(token)) {
                        return CLASS_AGE_18;
                    }
                }

                previous = nextPrevious(token);
            } else {
                previous = PREVIOUS_NONE;
            }
            token.setLength(0);
            overflow = false;
        }
        return CLASS_SAFE;
    }

    private static byte directClass(StringBuilder token, boolean broadGroupRules) {
        if (tokenEquals(token, "fsk18") || tokenEquals(token, "fsk18plus")
                || tokenEquals(token, "18plus") || tokenEquals(token, "18only")
                || tokenEquals(token, "ab18") || tokenEquals(token, "r18")
                || tokenEquals(token, "nc17") || tokenEquals(token, "mature18")) {
            return CLASS_AGE_18;
        }

        if (tokenEquals(token, "xxx") || tokenEquals(token, "adult")
                || tokenEquals(token, "adults") || tokenEquals(token, "erotik")
                || tokenEquals(token, "erotic") || tokenEquals(token, "porno")
                || tokenEquals(token, "porn") || tokenEquals(token, "yetiskin")
                || tokenEquals(token, "erwachsene") || tokenEquals(token, "erwachsenen")) {
            return CLASS_EXPLICIT;
        }

        if (tokenEquals(token, "pornhub") || tokenEquals(token, "playboy")
                || tokenEquals(token, "hustler") || tokenEquals(token, "brazzers")
                || tokenEquals(token, "redlight") || tokenEquals(token, "dorcel")
                || tokenEquals(token, "penthouse") || tokenEquals(token, "xhamster")
                || tokenEquals(token, "youporn") || tokenEquals(token, "redtube")
                || tokenEquals(token, "bangbros") || tokenEquals(token, "vivid")
                || tokenEquals(token, "babestation") || tokenEquals(token, "exxxotica")
                || tokenEquals(token, "wicked") || tokenEquals(token, "privatexxx")) {
            return CLASS_ADULT_BRAND;
        }

        if (broadGroupRules && (tokenEquals(token, "sex") || tokenEquals(token, "sexy")
                || tokenEquals(token, "hot") || tokenEquals(token, "venus")
                || tokenEquals(token, "babe") || tokenEquals(token, "babes")
                || tokenEquals(token, "private"))) {
            return CLASS_EXPLICIT;
        }
        return CLASS_SAFE;
    }

    private static int nextPrevious(StringBuilder token) {
        if (tokenEquals(token, "after")) return PREVIOUS_AFTER;
        if (tokenEquals(token, "red")) return PREVIOUS_RED;
        if (tokenEquals(token, "nur")) return PREVIOUS_NUR;
        if (tokenEquals(token, "18")) return PREVIOUS_18;
        if (tokenEquals(token, "fsk")) return PREVIOUS_FSK;
        if (tokenEquals(token, "ab")) return PREVIOUS_AB;
        if (tokenEquals(token, "adults") || tokenEquals(token, "adult")) return PREVIOUS_ADULTS;
        if (tokenEquals(token, "man")) return PREVIOUS_MAN;
        if (tokenEquals(token, "blue")) return PREVIOUS_BLUE;
        if (tokenEquals(token, "digital")) return PREVIOUS_DIGITAL;
        if (tokenEquals(token, "reality")) return PREVIOUS_REALITY;
        if (tokenEquals(token, "naughty")) return PREVIOUS_NAUGHTY;
        return PREVIOUS_NONE;
    }

    private static boolean isMediaContext(StringBuilder token) {
        return tokenEquals(token, "vod") || tokenEquals(token, "movie")
                || tokenEquals(token, "movies") || tokenEquals(token, "film")
                || tokenEquals(token, "filme") || tokenEquals(token, "cinema")
                || tokenEquals(token, "sinema") || tokenEquals(token, "plus")
                || tokenEquals(token, "only") || tokenEquals(token, "bereich")
                || tokenEquals(token, "category") || tokenEquals(token, "kategorie");
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
            ArrayList<Channel> rawCopy = new ArrayList<>(input.size());
            ArrayList<Channel> safeCopy = new ArrayList<>(input.size());
            for (Channel channel : input) {
                if (channel == null) continue;
                rawCopy.add(channel);
                if (!channel.adult) safeCopy.add(channel);
            }
            raw = Collections.unmodifiableList(rawCopy);
            safe = Collections.unmodifiableList(safeCopy);
        }

        ProtectedChannelList(List<Channel> sourceRaw, List<Channel> sourceSafe) {
            raw = Collections.unmodifiableList(new ArrayList<>(
                    sourceRaw == null ? Collections.emptyList() : sourceRaw));
            safe = Collections.unmodifiableList(new ArrayList<>(
                    sourceSafe == null ? Collections.emptyList() : sourceSafe));
        }

        List<Channel> raw() { return raw; }

        @Override public Channel get(int index) { return safe.get(index); }
        @Override public int size() { return safe.size(); }
        @Override public Iterator<Channel> iterator() { return safe.iterator(); }
    }
}
