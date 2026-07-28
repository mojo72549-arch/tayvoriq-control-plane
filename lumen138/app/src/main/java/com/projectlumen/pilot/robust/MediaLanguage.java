package com.projectlumen.pilot.robust;

import java.util.Locale;

/** Deterministic country/language classifier. Explicit playlist groups win over brand fallbacks. */
final class MediaLanguage {
    enum Code { ALL, DE, TR, OTHER }

    private MediaLanguage() { }

    static Code detect(Channel channel) {
        if (channel == null) return Code.OTHER;
        String rawGroup = channel.group == null ? "" : channel.group;
        String rawName = channel.name == null ? "" : channel.name;
        String group = normalize(rawGroup);
        String name = normalize(rawName);

        Code groupCode = explicitGroup(group);
        if (groupCode != Code.OTHER) return groupCode;

        if (turkishBrand(name, rawName)) return Code.TR;
        if (germanBrand(name, rawName)) return Code.DE;

        if (containsPhrase(group, "turkce") || containsPhrase(group, "turkish")
                || containsPhrase(group, "turkiye") || containsPhrase(group, "yerli")
                || containsPhrase(group, "dizi") || containsPhrase(group, "sinema")
                || containsPhrase(group, "turk dublaj")) return Code.TR;

        if (containsPhrase(group, "deutsch") || containsPhrase(group, "german")
                || containsPhrase(group, "deutschland") || containsPhrase(group, "bundesliga")
                || containsPhrase(group, "deutsche filme") || containsPhrase(group, "staffel")) {
            return Code.DE;
        }
        return Code.OTHER;
    }

    static String label(Code code) {
        if (code == Code.DE) return "Deutsch";
        if (code == Code.TR) return "Türkçe";
        if (code == Code.OTHER) return "Weitere";
        return "Alle";
    }

    static String shortLabel(Channel channel) {
        Code code = detect(channel);
        if (code == Code.DE) return "DE";
        if (code == Code.TR) return "TR";
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
        return Code.OTHER;
    }

    private static boolean turkishBrand(String name, String rawName) {
        if (brand(name, "trt", "kanal d", "show tv", "a haber", "haberturk",
                "teve2", "tv8", "star tv", "beyaz tv", "halk tv", "sozcu tv",
                "ulke tv", "cnn turk", "kanal 7", "360 tv", "dmax tr",
                "bein sports tr", "turksat", "now tv tr", "fox tr")) return true;
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
                "comedy central de", "nickelodeon de");
    }

    private static boolean brand(String value, String... brands) {
        for (String brand : brands) {
            if (value.equals(brand) || value.startsWith(brand + " ")
                    || value.contains(" " + brand + " ")) return true;
        }
        return false;
    }

    private static boolean hasToken(String value, String token) {
        return (" " + value + " ").contains(" " + token + " ");
    }

    private static boolean containsPhrase(String value, String phrase) {
        return (" " + value + " ").contains(" " + normalize(phrase) + " ");
    }

    private static String normalize(String value) {
        if (value == null) return "";
        String lower = value.toLowerCase(Locale.ROOT)
                .replace('ı', 'i').replace('ş', 's').replace('ğ', 'g')
                .replace('ç', 'c').replace('ö', 'o').replace('ü', 'u')
                .replace('ä', 'a').replace('ß', 's');
        StringBuilder out = new StringBuilder(lower.length());
        boolean space = true;
        for (int i = 0; i < lower.length(); i++) {
            char c = lower.charAt(i);
            if (Character.isLetterOrDigit(c)) {
                out.append(c);
                space = false;
            } else if (!space) {
                out.append(' ');
                space = true;
            }
        }
        return out.toString().trim();
    }
}
