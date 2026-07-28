package com.projectlumen.pilot.robust;

import java.text.Normalizer;
import java.util.Locale;

/** Conservative local classifier used only to protect clearly labelled adult content. */
final class AdultContentClassifier {
    private AdultContentClassifier() { }

    static boolean isAdult(Channel channel) {
        return channel != null && isAdult(channel.name, channel.group, channel.url);
    }

    static boolean isAdult(String name, String group, String url) {
        String title = normalize(name);
        String category = normalize(group);
        String address = normalizeUrl(url);
        String combined = title + " | " + category;

        // Avoid the well-known non-pornographic channel name unless another explicit marker exists.
        boolean adultSwimOnly = combined.contains("adult swim")
                && !containsExplicitMarker(combined.replace("adult swim", ""));
        if (adultSwimOnly) return false;

        if (containsExplicitMarker(combined)) return true;
        return containsUrlSegment(address, "adult")
                || containsUrlSegment(address, "xxx")
                || containsUrlSegment(address, "porn")
                || containsUrlSegment(address, "porno")
                || containsUrlSegment(address, "erotic")
                || containsUrlSegment(address, "erotik");
    }

    private static boolean containsExplicitMarker(String value) {
        if (value.contains("18+") || value.contains("18 plus") || value.contains("18plus")) {
            return true;
        }
        String[] phrases = {
                "red light", "redlight", "for adults", "adult only", "adult movie",
                "adult movies", "adult film", "adult films", "erotic", "erotik",
                "yetişkin", "yetiskin", "playboy", "hustler", "penthouse", "brazzers"
        };
        for (String phrase : phrases) if (value.contains(phrase)) return true;

        return hasToken(value, "xxx")
                || hasToken(value, "porn")
                || hasToken(value, "porno")
                || hasToken(value, "pornography")
                || hasToken(value, "sex")
                || hasToken(value, "adult");
    }

    private static boolean hasToken(String value, String token) {
        int from = 0;
        while (true) {
            int index = value.indexOf(token, from);
            if (index < 0) return false;
            int before = index - 1;
            int after = index + token.length();
            boolean left = before < 0 || !Character.isLetterOrDigit(value.charAt(before));
            boolean right = after >= value.length() || !Character.isLetterOrDigit(value.charAt(after));
            if (left && right) return true;
            from = index + 1;
        }
    }

    private static boolean containsUrlSegment(String url, String segment) {
        return url.contains("/" + segment + "/")
                || url.contains("/" + segment + "?")
                || url.endsWith("/" + segment)
                || url.contains("category=" + segment)
                || url.contains("group=" + segment);
    }

    private static String normalize(String value) {
        String text = value == null ? "" : value.toLowerCase(Locale.ROOT).trim();
        text = Normalizer.normalize(text, Normalizer.Form.NFD)
                .replaceAll("\\p{M}+", "");
        return text.replace('_', ' ').replace('-', ' ');
    }

    private static String normalizeUrl(String value) {
        return value == null ? "" : value.toLowerCase(Locale.ROOT);
    }
}
