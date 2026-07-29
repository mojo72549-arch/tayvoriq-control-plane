package com.projectlumen.pilot.robust;

import java.util.AbstractList;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;

/**
 * Fail-closed classification for explicit adult and age-18 content.
 *
 * Precision rule: a single ambiguous movie title or brand word must never be
 * enough to move normal content into the parent-only catalog. Explicit group
 * labels win, age labels are kept separate, and URL evidence is deliberately
 * limited to unambiguous path tokens.
 */
final class AdultContentPolicy {
    static final byte CLASS_UNKNOWN = -1;
    static final byte CLASS_SAFE = 0;
    static final byte CLASS_EXPLICIT = 1;
    static final byte CLASS_AGE_18 = 2;
    static final byte CLASS_ADULT_BRAND = 3;

    private static final int MODE_GROUP = 1;
    private static final int MODE_TITLE = 2;
    private static final int MODE_URL = 3;
    private static final int TOKEN_LIMIT = 36;

    private static final int PREVIOUS_NONE = 0;
    private static final int PREVIOUS_FSK = 1;
    private static final int PREVIOUS_AB = 2;
    private static final int PREVIOUS_ADULTS = 3;
    private static final int PREVIOUS_NUR = 4;
    private static final int PREVIOUS_FOR = 5;
    private static final int PREVIOUS_RED = 6;
    private static final int PREVIOUS_WICKED = 7;
    private static final int PREVIOUS_VIVID = 8;
    private static final int PREVIOUS_PLAYBOY = 9;
    private static final int PREVIOUS_HUSTLER = 10;
    private static final int PREVIOUS_PENTHOUSE = 11;
    private static final int PREVIOUS_PRIVATE = 12;

    private AdultContentPolicy() { }

    static boolean isAdult(Channel channel) {
        return channel != null && channel.adult;
    }

    static byte classifyRaw(String group, String name, String url) {
        byte groupClass = scan(group, MODE_GROUP);
        if (groupClass != CLASS_SAFE) return groupClass;

        byte titleClass = scan(name, MODE_TITLE);
        if (titleClass != CLASS_SAFE) return titleClass;

        return scan(url, MODE_URL);
    }

    /** Generic label check used by tests and defensive UI validation. */
    static boolean isAdultText(String value) {
        return scan(value, MODE_GROUP) != CLASS_SAFE;
    }

    static boolean isExplicitClass(byte value) {
        return value == CLASS_EXPLICIT || value == CLASS_ADULT_BRAND;
    }

    static boolean isAge18Class(byte value) {
        return value == CLASS_AGE_18;
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
        if (value == CLASS_ADULT_BRAND) return "XXX-Marke";
        if (value == CLASS_EXPLICIT) return "XXX / Erotik";
        return "Sicher";
    }

    private static byte scan(String value, int mode) {
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
                byte direct = directClass(token, mode);
                if (direct != CLASS_SAFE) return direct;

                if ((previous == PREVIOUS_FSK || previous == PREVIOUS_AB)
                        && tokenEquals(token, "18")) {
                    return CLASS_AGE_18;
                }
                if (previous == PREVIOUS_ADULTS && tokenEquals(token, "only")) {
                    return CLASS_EXPLICIT;
                }
                if (previous == PREVIOUS_FOR
                        && (tokenEquals(token, "adults") || tokenEquals(token, "adult"))) {
                    return CLASS_EXPLICIT;
                }
                if (previous == PREVIOUS_NUR
                        && (tokenEquals(token, "erwachsene")
                        || tokenEquals(token, "erwachsenen"))) {
                    return CLASS_EXPLICIT;
                }
                if (previous == PREVIOUS_RED && tokenEquals(token, "light")) {
                    return CLASS_ADULT_BRAND;
                }

                // Ambiguous brand words need a second, adult-specific token.
                if (mode != MODE_URL && previous == PREVIOUS_WICKED
                        && (tokenEquals(token, "pictures") || tokenEquals(token, "adult")
                        || tokenEquals(token, "xxx") || tokenEquals(token, "studios"))) {
                    return CLASS_ADULT_BRAND;
                }
                if (mode != MODE_URL && previous == PREVIOUS_VIVID
                        && (tokenEquals(token, "entertainment") || tokenEquals(token, "adult")
                        || tokenEquals(token, "xxx"))) {
                    return CLASS_ADULT_BRAND;
                }
                if (mode != MODE_URL && (previous == PREVIOUS_PLAYBOY
                        || previous == PREVIOUS_HUSTLER || previous == PREVIOUS_PENTHOUSE)
                        && (tokenEquals(token, "tv") || tokenEquals(token, "channel")
                        || tokenEquals(token, "adult") || tokenEquals(token, "xxx"))) {
                    return CLASS_ADULT_BRAND;
                }
                if (mode != MODE_URL && previous == PREVIOUS_PRIVATE
                        && (tokenEquals(token, "spice") || tokenEquals(token, "xxx")
                        || tokenEquals(token, "adult"))) {
                    return CLASS_ADULT_BRAND;
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

    private static byte directClass(StringBuilder token, int mode) {
        if (tokenEquals(token, "fsk18") || tokenEquals(token, "fsk18plus")
                || tokenEquals(token, "18plus") || tokenEquals(token, "18only")
                || tokenEquals(token, "ab18") || tokenEquals(token, "r18")
                || tokenEquals(token, "nc17") || tokenEquals(token, "mature18")) {
            return CLASS_AGE_18;
        }

        if (tokenEquals(token, "xxx") || tokenEquals(token, "adult")
                || tokenEquals(token, "adults") || tokenEquals(token, "erotik")
                || tokenEquals(token, "erotic") || tokenEquals(token, "erotica")
                || tokenEquals(token, "erotico") || tokenEquals(token, "erotique")
                || tokenEquals(token, "erotiek") || tokenEquals(token, "erotyka")
                || tokenEquals(token, "erotika") || tokenEquals(token, "porno")
                || tokenEquals(token, "porn") || tokenEquals(token, "yetiskin")
                || tokenEquals(token, "erwachsene") || tokenEquals(token, "erwachsenen")
                || tokenEquals(token, "adulte") || tokenEquals(token, "adultes")
                || tokenEquals(token, "adulto") || tokenEquals(token, "adultos")
                || tokenEquals(token, "adulti") || tokenEquals(token, "doroslych")
                || tokenEquals(token, "odrasli") || tokenEquals(token, "odrasle")
                || tokenEquals(token, "volwassen") || tokenEquals(token, "порно")
                || tokenEquals(token, "эротика") || tokenEquals(token, "للكبار")
                || tokenEquals(token, "اباحي") || tokenEquals(token, "إباحي")) {
            return CLASS_EXPLICIT;
        }

        if (tokenEquals(token, "pornhub") || tokenEquals(token, "brazzers")
                || tokenEquals(token, "xhamster") || tokenEquals(token, "youporn")
                || tokenEquals(token, "redtube") || tokenEquals(token, "bangbros")
                || tokenEquals(token, "dorcel") || tokenEquals(token, "privatexxx")
                || tokenEquals(token, "exxxotica") || tokenEquals(token, "babestation")) {
            return CLASS_ADULT_BRAND;
        }

        if (mode == MODE_GROUP) {
            if (tokenEquals(token, "sex") || tokenEquals(token, "sexy")
                    || tokenEquals(token, "hot") || tokenEquals(token, "venus")
                    || tokenEquals(token, "babe") || tokenEquals(token, "babes")
                    || tokenEquals(token, "private")) {
                return CLASS_EXPLICIT;
            }
            if (tokenEquals(token, "playboy") || tokenEquals(token, "hustler")
                    || tokenEquals(token, "penthouse")) {
                return CLASS_ADULT_BRAND;
            }
        }
        return CLASS_SAFE;
    }

    private static int nextPrevious(StringBuilder token) {
        if (tokenEquals(token, "fsk")) return PREVIOUS_FSK;
        if (tokenEquals(token, "ab")) return PREVIOUS_AB;
        if (tokenEquals(token, "adult") || tokenEquals(token, "adults")) return PREVIOUS_ADULTS;
        if (tokenEquals(token, "nur")) return PREVIOUS_NUR;
        if (tokenEquals(token, "for")) return PREVIOUS_FOR;
        if (tokenEquals(token, "red")) return PREVIOUS_RED;
        if (tokenEquals(token, "wicked")) return PREVIOUS_WICKED;
        if (tokenEquals(token, "vivid")) return PREVIOUS_VIVID;
        if (tokenEquals(token, "playboy")) return PREVIOUS_PLAYBOY;
        if (tokenEquals(token, "hustler")) return PREVIOUS_HUSTLER;
        if (tokenEquals(token, "penthouse")) return PREVIOUS_PENTHOUSE;
        if (tokenEquals(token, "private")) return PREVIOUS_PRIVATE;
        return PREVIOUS_NONE;
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
        if (lower == 'ö' || lower == 'ó' || lower == 'ò' || lower == 'ô') return 'o';
        if (lower == 'ü' || lower == 'ú' || lower == 'ù' || lower == 'û') return 'u';
        if (lower == 'ä' || lower == 'á' || lower == 'à' || lower == 'â') return 'a';
        if (lower == 'é' || lower == 'è' || lower == 'ê' || lower == 'ë') return 'e';
        if (lower == 'í' || lower == 'ì' || lower == 'î' || lower == 'ï') return 'i';
        if (lower == 'ñ') return 'n';
        if (lower == 'ł') return 'l';
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
