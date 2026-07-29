package com.projectlumen.pilot.robust;

import java.util.Locale;

/**
 * Deterministic country/language classifier. Classification is computed once per
 * channel and then reused for every catalog switch.
 */
final class MediaLanguage {
    enum Code { ALL, DE, TR, EN, OTHER }

    private MediaLanguage() { }

    static Code detect(Channel channel) {
        return channel == null || channel.language == null ? Code.OTHER : channel.language;
    }

    static Code detectRaw(String rawGroup, String rawName) {
        String group = normalize(rawGroup);
        String name = normalize(rawName);

        Code groupCode = explicitGroup(group);
        if (groupCode != Code.OTHER) return groupCode;

        if (turkishBrand(name, rawName)) return Code.TR;
        if (germanBrand(name, rawName)) return Code.DE;
        if (englishBrand(name)) return Code.EN;

        if (containsPhrase(group, "turkce") || containsPhrase(group, "turkish")
                || containsPhrase(group, "turkiye") || containsPhrase(group, "yerli")
                || containsPhrase(group, "dizi") || containsPhrase(group, "sinema")
                || containsPhrase(group, "turk dublaj")) return Code.TR;

        if (containsPhrase(group, "deutsch") || containsPhrase(group, "german")
                || containsPhrase(group, "deutschland") || containsPhrase(group, "bundesliga")
                || containsPhrase(group, "deutsche filme") || containsPhrase(group, "staffel")) {
            return Code.DE;
        }

        if (containsPhrase(group, "english") || containsPhrase(group, "united kingdom")
                || containsPhrase(group, "united states") || containsPhrase(group, "british")
                || containsPhrase(group, "american") || containsPhrase(group, "english movies")
                || containsPhrase(group, "english series") || containsPhrase(group, "uk tv")) {
            return Code.EN;
        }
        return Code.OTHER;
    }

    static String label(Code code) {
        if (code == Code.DE) return "Deutsch";
        if (code == Code.TR) return "Türkçe";
        if (code == Code.EN) return "English";
        if (code == Code.OTHER) return "Weitere";
        return "Alle";
    }

    static String shortLabel(Channel channel) {
        Code code = detect(channel);
        if (code == Code.DE) return "DE";
        if (code == Code.TR) return "TR";
        if (code == Code.EN) return "EN";
        return "•";
    }

    private static Code explicitGroup(String group) {
        if (hasToken(group, "tr") || hasToken(group, "tur") || hasToken(group, "turkey")
                || hasToken(group, "turkiye") || hasToken(group, "turk")
                || containsPhrase(group, "türk") || containsPhrase(group, "turkish")) {
            return Code.TR;
        }
        if (hasToken(group, "de") || hasToken(group, "ger") || hasToken(group, "germany")
                || hasToken(group, "deutschland") || hasToken(group, "deutsch")
                || containsPhrase(group, "german")) {
            return Code.DE;
        }
        if (hasToken(group, "en") || hasToken(group, "eng") || hasToken(group, "english")
                || hasToken(group, "uk") || hasToken(group, "gb") || hasToken(group, "usa")
                || hasToken(group, "us") || containsPhrase(group, "united kingdom")
                || containsPhrase(group, "united states")) {
            return Code.EN;
        }
        return Code.OTHER;
    }

    private static boolean turkishBrand(String name, String rawName) {
        if (brand(name, "trt", "kanal d", "show tv", "a haber", "haberturk",
                "teve2", "tv8", "star tv", "beyaz tv", "halk tv", "sozcu tv",
                "ulke tv", "cnn turk", "kanal 7", "360 tv", "dmax tr",
                "bein sports tr", "turksat", "now tv tr", "fox tr", "tabii")) return true;
        if (brand(name, "atv") && !containsPhrase(name, "atv germany")) return true;
        String raw = rawName == null ? "" : rawName.toLowerCase(Locale.ROOT);
        return brand(name, "ntv") && !raw.contains("n-tv") && !raw.contains("n tv de");
    }

    private static boolean germanBrand(String name, String rawName) {
        String raw = rawName == null ? "" : rawName.toLowerCase(Locale.ROOT);
        if (raw.contains("n-tv")) return true;
        return brand(name, "rtl", "rtl zwei", "rtl2", "super rtl", "ard", "das erste",
                "zdf", "sat 1", "sat1", "pro7", "prosieben", "pro sieben", "vox",
                "kabel eins", "welt", "3sat", "dmax", "tele 5", "phoenix", "arte de",
                "sky de", "sport1", "tagesschau24", "sixx", "one de", "nitro",
                "comedy central de", "nickelodeon de", "servus tv de", "kika");
    }

    private static boolean englishBrand(String name) {
        return brand(name, "bbc", "bbc one", "bbc two", "itv", "itv1", "itv2",
                "channel 4", "channel 5", "sky uk", "sky news", "cnn", "cnn international",
                "fox news", "msnbc", "abc", "cbs", "nbc", "pbs", "hbo", "showtime",
                "paramount network", "discovery us", "discovery uk", "national geographic uk",
                "comedy central uk", "nickelodeon uk", "cartoon network uk", "mtv uk");
    }

    private static boolean brand(String value, String... brands) {
        for (String brand : brands) {
            if (value.equals(brand) || value.startsWith(brand + " ")
                    || value.contains(" " + brand + " ")) return true;
        }
        return false;
    }

    private static boolean hasToken(String value, String token) {
        int from = 0;
        while (from < value.length()) {
            int index = value.indexOf(token, from);
            if (index < 0) return false;
            int end = index + token.length();
            boolean left = index == 0 || value.charAt(index - 1) == ' ';
            boolean right = end == value.length() || value.charAt(end) == ' ';
            if (left && right) return true;
            from = index + 1;
        }
        return false;
    }

    private static boolean containsPhrase(String value, String phrase) {
        return hasTokenSequence(value, normalize(phrase));
    }

    private static boolean hasTokenSequence(String value, String phrase) {
        int from = 0;
        while (from < value.length()) {
            int index = value.indexOf(phrase, from);
            if (index < 0) return false;
            int end = index + phrase.length();
            boolean left = index == 0 || value.charAt(index - 1) == ' ';
            boolean right = end == value.length() || value.charAt(end) == ' ';
            if (left && right) return true;
            from = index + 1;
        }
        return false;
    }

    private static String normalize(String value) {
        if (value == null || value.isBlank()) return "";
        String lower = value.toLowerCase(Locale.ROOT);
        StringBuilder out = new StringBuilder(lower.length());
        boolean space = true;
        for (int i = 0; i < lower.length(); i++) {
            char c = fold(lower.charAt(i));
            if (Character.isLetterOrDigit(c)) {
                out.append(c);
                space = false;
            } else if (!space) {
                out.append(' ');
                space = true;
            }
        }
        int length = out.length();
        while (length > 0 && out.charAt(length - 1) == ' ') out.setLength(--length);
        return out.toString();
    }

    private static char fold(char value) {
        if (value == 'ı') return 'i';
        if (value == 'ş') return 's';
        if (value == 'ğ') return 'g';
        if (value == 'ç') return 'c';
        if (value == 'ö') return 'o';
        if (value == 'ü') return 'u';
        if (value == 'ä') return 'a';
        if (value == 'ß') return 's';
        return value;
    }
}
