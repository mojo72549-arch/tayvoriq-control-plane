package com.projectlumen.pilot.robust;

import java.util.Locale;

final class MediaLanguage {
    enum Code { ALL, DE, TR, OTHER }

    private MediaLanguage() { }

    static Code detect(Channel channel) {
        if (channel == null) return Code.OTHER;
        String group = normalize(channel.group);
        String name = normalize(channel.name);

        if (containsAny(group,
                "türk", "turk", "turkey", "turkish", "türkiye", "dizi", "sinema",
                "| tr |", "[tr]", " tr:", "tr |")) return Code.TR;
        if (containsAny(group,
                "deutsch", "germany", "german", "deutschland", "bundesliga",
                "| de |", "[de]", " de:", "de |")) return Code.DE;

        if (startsOrContains(name,
                "trt", "kanal d", "show tv", "atv", "a haber", "habertürk",
                "haberturk", "teve2", "tv8", "star tv", "now tv tr", "beyaz tv",
                "fox tr", "bein sports tr")) return Code.TR;

        if (startsOrContains(name,
                "rtl", "rtl zwei", "rtl2", "ard", "das erste", "zdf", "sat.1",
                "sat 1", "pro7", "pro sieben", "vox", "kabel eins", "n-tv", "ntv",
                "welt", "3sat", "dmax", "tele 5", "phoenix", "arte de", "sky de")) {
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

    private static String normalize(String value) {
        return value == null ? "" : value.toLowerCase(Locale.ROOT).trim();
    }

    private static boolean containsAny(String value, String... needles) {
        for (String needle : needles) if (value.contains(needle)) return true;
        return false;
    }

    private static boolean startsOrContains(String value, String... brands) {
        for (String brand : brands) {
            if (value.startsWith(brand) || value.contains(" " + brand)
                    || value.contains("|" + brand) || value.contains("- " + brand)) return true;
        }
        return false;
    }
}
