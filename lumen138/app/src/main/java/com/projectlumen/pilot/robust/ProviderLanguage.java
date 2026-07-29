package com.projectlumen.pilot.robust;

import java.text.Normalizer;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * Detects language facets from the provider supplied group-title values.
 *
 * The UI never assumes that German or Turkish exists. Only facets that are
 * actually present in the current protected catalog are exposed. Unknown
 * provider prefixes may become their own facet when they clearly look like a
 * language prefix; genre-only groups remain available through the group picker.
 */
final class ProviderLanguage {
    static final String ALL = "";

    static final class Facet {
        final String id;
        final String label;
        final String flag;

        Facet(String id, String label, String flag) {
            this.id = id == null ? ALL : id;
            this.label = label == null || label.isBlank() ? "Alle" : label;
            this.flag = flag == null ? "" : flag;
        }

        String display() {
            return flag.isBlank() ? label : flag + " " + label;
        }
    }

    private static final class Definition {
        final Facet facet;
        final List<String> names;
        final Set<String> codes;
        final List<String> channelHints;

        Definition(String id, String label, String flag,
                   String[] names, String[] codes, String[] channelHints) {
            facet = new Facet(id, label, flag);
            this.names = normalizedList(names);
            this.codes = new HashSet<>(normalizedList(codes));
            this.channelHints = normalizedList(channelHints);
        }
    }

    private static final List<Definition> DEFINITIONS = Collections.unmodifiableList(Arrays.asList(
            def("de", "Deutsch", "🇩🇪",
                    arr("deutsch", "german", "germany", "deutschland"),
                    arr("de", "ger", "deu"),
                    arr("rtl", "rtl zwei", "ard", "das erste", "zdf", "sat 1", "pro7", "vox", "kabel eins")),
            def("tr", "Türkisch", "🇹🇷",
                    arr("türkisch", "turkisch", "turkish", "türkiye", "turkiye", "turkey", "türk"),
                    arr("tr", "tur"),
                    arr("trt", "kanal d", "show tv", "atv", "a haber", "haberturk", "teve2", "tv8", "beyaz tv")),
            def("el", "Griechisch", "🇬🇷",
                    arr("griechisch", "greek", "greece", "hellas", "ellinika", "ελληνικα", "ελληνικά"),
                    arr("gr", "el", "gre"),
                    arr("ert", "mega channel", "skai", "alpha tv", "ant1", "open beyond")),
            def("en", "Englisch", "🇬🇧",
                    arr("englisch", "english", "united kingdom", "great britain", "british", "uk", "usa", "united states", "american"),
                    arr("en", "eng", "uk", "us", "usa"),
                    arr("bbc", "itv", "channel 4", "sky uk", "cnn", "fox news", "nbc", "cbs", "abc usa")),
            def("ar", "Arabisch", "🇸🇦",
                    arr("arabisch", "arabic", "arab", "العربية", "عربي"),
                    arr("ar", "ara"),
                    arr("al jazeera", "al arabiya", "mbc", "rotana")),
            def("fr", "Französisch", "🇫🇷",
                    arr("französisch", "franzoesisch", "french", "france", "français", "francais"),
                    arr("fr", "fra", "fre"),
                    arr("tf1", "france 2", "canal plus france", "m6")),
            def("it", "Italienisch", "🇮🇹",
                    arr("italienisch", "italian", "italy", "italia", "italiano"),
                    arr("it", "ita"),
                    arr("rai 1", "rai 2", "rai 3", "mediaset", "canale 5")),
            def("es", "Spanisch", "🇪🇸",
                    arr("spanisch", "spanish", "spain", "españa", "espana", "español", "espanol"),
                    arr("es", "esp"),
                    arr("rtve", "la 1", "antena 3", "telecinco")),
            def("pt", "Portugiesisch", "🇵🇹",
                    arr("portugiesisch", "portuguese", "portugal", "português", "portugues", "brasil", "brazil"),
                    arr("pt", "por", "br"),
                    arr("rtp", "sic", "tvi", "globo")),
            def("nl", "Niederländisch", "🇳🇱",
                    arr("niederländisch", "niederlaendisch", "dutch", "netherlands", "holland", "nederlands"),
                    arr("nl", "nld", "dut"),
                    arr("npo", "rtl nederland", "sbs6")),
            def("pl", "Polnisch", "🇵🇱",
                    arr("polnisch", "polish", "poland", "polska", "polski"),
                    arr("pl", "pol"),
                    arr("tvp", "polsat", "tvn polska")),
            def("ro", "Rumänisch", "🇷🇴",
                    arr("rumänisch", "rumaenisch", "romanian", "romania", "română", "romana"),
                    arr("ro", "ron", "rum"),
                    arr("pro tv", "antena 1 romania", "digi24")),
            def("bg", "Bulgarisch", "🇧🇬",
                    arr("bulgarisch", "bulgarian", "bulgaria", "български", "българия"),
                    arr("bg", "bul"),
                    arr("bnt", "btv bulgaria", "nova bg")),
            def("sq", "Albanisch", "🇦🇱",
                    arr("albanisch", "albanian", "albania", "shqip", "shqipëri", "shqiperi"),
                    arr("al", "sq", "sqi", "alb"),
                    arr("top channel", "klan tv", "rtsh")),
            def("ru", "Russisch", "🇷🇺",
                    arr("russisch", "russian", "russia", "русский", "россия"),
                    arr("ru", "rus"),
                    arr("russia 1", "ntv russia", "ren tv")),
            def("uk", "Ukrainisch", "🇺🇦",
                    arr("ukrainisch", "ukrainian", "ukraine", "українська", "україна"),
                    arr("ua", "ukr"),
                    arr("1 plus 1 ukraine", "inter ukraine", "ictv")),
            def("bs", "Bosnisch", "🇧🇦",
                    arr("bosnisch", "bosnian", "bosnia", "bosna"),
                    arr("ba", "bs", "bos"),
                    arr("bhrt", "hayat tv")),
            def("hr", "Kroatisch", "🇭🇷",
                    arr("kroatisch", "croatian", "croatia", "hrvatska", "hrvatski"),
                    arr("hr", "hrv"),
                    arr("hrt 1", "nova tv croatia", "rtl hrvatska")),
            def("sr", "Serbisch", "🇷🇸",
                    arr("serbisch", "serbian", "serbia", "srbija", "srpski"),
                    arr("rs", "sr", "srp"),
                    arr("rts 1", "pink rs", "prva srpska")),
            def("mk", "Mazedonisch", "🇲🇰",
                    arr("mazedonisch", "macedonian", "macedonia", "македонски", "македонија"),
                    arr("mk", "mkd", "mac"),
                    arr("mrt 1", "sitel")),
            def("sl", "Slowenisch", "🇸🇮",
                    arr("slowenisch", "slovenian", "slovenia", "slovenija", "slovenski"),
                    arr("si", "sl", "slv"),
                    arr("rtv slo", "pop tv slovenia")),
            def("hu", "Ungarisch", "🇭🇺",
                    arr("ungarisch", "hungarian", "hungary", "magyar", "magyarország", "magyarorszag"),
                    arr("hu", "hun"),
                    arr("m1 hungary", "rtl klub", "tv2 hungary")),
            def("cs", "Tschechisch", "🇨🇿",
                    arr("tschechisch", "czech", "czechia", "czech republic", "česko", "cesko", "čeština", "cestina"),
                    arr("cz", "cs", "ces", "cze"),
                    arr("ct1", "nova cz", "prima cz")),
            def("sk", "Slowakisch", "🇸🇰",
                    arr("slowakisch", "slovak", "slovakia", "slovensko", "slovenčina", "slovencina"),
                    arr("sk", "slk", "slo"),
                    arr("stvr", "markiza", "joj")),
            def("da", "Dänisch", "🇩🇰",
                    arr("dänisch", "daenisch", "danish", "denmark", "danmark", "dansk"),
                    arr("dk", "da", "dan"),
                    arr("dr1", "tv2 danmark")),
            def("sv", "Schwedisch", "🇸🇪",
                    arr("schwedisch", "swedish", "sweden", "sverige", "svenska"),
                    arr("se", "sv", "swe"),
                    arr("svt1", "tv4 sweden")),
            def("no", "Norwegisch", "🇳🇴",
                    arr("norwegisch", "norwegian", "norway", "norge", "norsk"),
                    arr("no", "nor"),
                    arr("nrk1", "tv2 norge")),
            def("fi", "Finnisch", "🇫🇮",
                    arr("finnisch", "finnish", "finland", "suomi", "suomalainen"),
                    arr("fi", "fin"),
                    arr("yle tv1", "mtv3 finland")),
            def("fa", "Persisch", "🇮🇷",
                    arr("persisch", "persian", "farsi", "iran", "فارسی", "ایران"),
                    arr("fa", "fas", "per", "ir"),
                    arr("iran international", "manoto")),
            def("ku", "Kurdisch", "☀️",
                    arr("kurdisch", "kurdish", "kurd", "kurdistan", "کوردی"),
                    arr("ku", "kur"),
                    arr("kurdistan 24", "rudaw")),
            def("he", "Hebräisch", "🇮🇱",
                    arr("hebräisch", "hebraeisch", "hebrew", "israel", "עברית"),
                    arr("he", "heb", "il"),
                    arr("kan 11", "keshet 12", "reshet 13")),
            def("hi", "Hindi", "🇮🇳",
                    arr("hindi", "india", "indian", "हिन्दी", "हिंदी"),
                    arr("hi", "hin", "in"),
                    arr("star plus", "zee tv", "sony sab")),
            def("ur", "Urdu", "🇵🇰",
                    arr("urdu", "pakistan", "pakistani", "اردو"),
                    arr("ur", "urd", "pk"),
                    arr("geo tv", "ary digital", "hum tv")),
            def("zh", "Chinesisch", "🇨🇳",
                    arr("chinesisch", "chinese", "china", "mandarin", "中文", "中国"),
                    arr("zh", "zho", "chi", "cn"),
                    arr("cctv", "hunan tv", "dragon tv")),
            def("ja", "Japanisch", "🇯🇵",
                    arr("japanisch", "japanese", "japan", "日本語", "日本"),
                    arr("ja", "jpn", "jp"),
                    arr("nhk", "fuji tv", "tv asahi")),
            def("ko", "Koreanisch", "🇰🇷",
                    arr("koreanisch", "korean", "korea", "한국어", "대한민국"),
                    arr("ko", "kor", "kr"),
                    arr("kbs", "mbc korea", "sbs korea")),
            def("th", "Thailändisch", "🇹🇭",
                    arr("thailändisch", "thailaendisch", "thai", "thailand", "ภาษาไทย"),
                    arr("th", "tha"),
                    arr("channel 3 thailand", "thai pbs")),
            def("vi", "Vietnamesisch", "🇻🇳",
                    arr("vietnamesisch", "vietnamese", "vietnam", "tiếng việt", "tieng viet"),
                    arr("vi", "vie", "vn"),
                    arr("vtv1", "vtv3")),
            def("id", "Indonesisch", "🇮🇩",
                    arr("indonesisch", "indonesian", "indonesia", "bahasa indonesia"),
                    arr("id", "ind"),
                    arr("rcti", "sctv indonesia")),
            def("ms", "Malaiisch", "🇲🇾",
                    arr("malaiisch", "malay", "malaysia", "bahasa melayu"),
                    arr("ms", "msa", "may", "my"),
                    arr("tv1 malaysia", "astro ria"))
    ));

    private static final Set<String> NON_LANGUAGE = new HashSet<>(Arrays.asList(
            "", "all", "alle", "world", "international", "global", "general",
            "live", "tv", "channels", "channel", "movies", "movie", "filme", "film",
            "series", "serie", "serien", "vod", "cinema", "sinema", "dizi",
            "sports", "sport", "news", "nachrichten", "kids", "kinder", "music", "musik",
            "documentary", "dokumentation", "entertainment", "premium", "vip", "favorites",
            "adult", "xxx", "erotik", "18 plus", "radio", "regional", "local", "lokal"
    ));

    private static final Set<String> MEDIA_SUFFIX = new HashSet<>(Arrays.asList(
            "live", "tv", "channels", "channel", "movies", "movie", "filme", "film",
            "series", "serie", "serien", "vod", "cinema", "sinema", "dizi", "sports",
            "sport", "news", "kids", "music", "premium", "uhd", "fhd", "hd", "sd"
    ));

    private ProviderLanguage() { }

    static Facet allFacet() {
        return new Facet(ALL, "Alle", "🌍");
    }

    static Facet detect(Channel channel) {
        if (channel == null) return null;
        String groupRaw = channel.group == null ? "" : channel.group.trim();
        String group = normalize(groupRaw);
        String prefixRaw = providerPrefix(groupRaw);
        String prefix = normalize(prefixRaw);

        for (Definition definition : DEFINITIONS) {
            if (matchesPrefix(definition, prefix) || matchesLongName(definition, group)) {
                return definition.facet;
            }
        }

        String name = normalize(channel.name);
        for (Definition definition : DEFINITIONS) {
            if (matchesChannelHint(definition, name)) return definition.facet;
        }

        String generic = genericProviderLanguage(prefixRaw, groupRaw);
        if (generic == null) return null;
        String id = "provider:" + slug(generic);
        return new Facet(id, titleCase(generic), "🌐");
    }

    static boolean matches(Channel channel, String languageId) {
        if (languageId == null || languageId.isBlank()) return true;
        Facet detected = detect(channel);
        return detected != null && languageId.equals(detected.id);
    }

    private static boolean matchesPrefix(Definition definition, String prefix) {
        if (prefix.isBlank()) return false;
        if (definition.codes.contains(prefix)) return true;
        for (String name : definition.names) {
            if (prefix.equals(name) || prefix.startsWith(name + " ")
                    || prefix.endsWith(" " + name)) return true;
        }
        return false;
    }

    private static boolean matchesLongName(Definition definition, String group) {
        String padded = " " + group + " ";
        for (String name : definition.names) {
            if (name.length() >= 4 && padded.contains(" " + name + " ")) return true;
        }
        return false;
    }

    private static boolean matchesChannelHint(Definition definition, String name) {
        String padded = " " + name + " ";
        for (String hint : definition.channelHints) {
            if (padded.startsWith(" " + hint + " ") || padded.contains(" " + hint + " ")) {
                return true;
            }
        }
        return false;
    }

    private static String genericProviderLanguage(String prefixRaw, String groupRaw) {
        String candidate = cleanCandidate(prefixRaw);
        if (!candidate.isBlank() && looksLikeLanguage(candidate)) return candidate;

        String normalized = normalize(groupRaw);
        String[] tokens = normalized.split(" +");
        if (tokens.length >= 2 && MEDIA_SUFFIX.contains(tokens[tokens.length - 1])) {
            StringBuilder value = new StringBuilder();
            for (int index = 0; index < tokens.length - 1; index++) {
                if (index > 0) value.append(' ');
                value.append(tokens[index]);
            }
            candidate = cleanCandidate(value.toString());
            if (looksLikeLanguage(candidate)) return candidate;
        }
        return null;
    }

    private static boolean looksLikeLanguage(String value) {
        String normalized = normalize(value);
        if (normalized.length() < 2 || normalized.length() > 24) return false;
        if (NON_LANGUAGE.contains(normalized)) return false;
        if (AdultContentPolicy.isAdultText(value)) return false;
        for (String stop : NON_LANGUAGE) {
            if (!stop.isBlank() && normalized.contains(" " + stop)
                    || !stop.isBlank() && normalized.startsWith(stop + " ")) return false;
        }
        boolean hasLetter = false;
        for (int index = 0; index < value.length(); index++) {
            if (Character.isLetter(value.charAt(index))) {
                hasLetter = true;
                break;
            }
        }
        return hasLetter;
    }

    private static String providerPrefix(String value) {
        if (value == null) return "";
        int end = value.length();
        char[] separators = new char[]{'|', ':', ';', '•', '/', '\\', '[', '(', '-'};
        for (char separator : separators) {
            int index = value.indexOf(separator);
            if (index > 0 && index < end) end = index;
        }
        return value.substring(0, end).trim();
    }

    private static String cleanCandidate(String value) {
        if (value == null) return "";
        String cleaned = value.trim().replaceAll("^[^\\p{L}\\p{N}]+|[^\\p{L}\\p{N}]+$", "");
        return cleaned.replaceAll("\\s+", " ").trim();
    }

    private static String titleCase(String value) {
        String cleaned = cleanCandidate(value);
        if (cleaned.isBlank()) return cleaned;
        String[] tokens = cleaned.split(" ");
        StringBuilder result = new StringBuilder(cleaned.length());
        for (String token : tokens) {
            if (result.length() > 0) result.append(' ');
            if (token.length() <= 3 && token.equals(token.toUpperCase(Locale.ROOT))) {
                result.append(token);
            } else {
                result.append(Character.toUpperCase(token.charAt(0)));
                if (token.length() > 1) result.append(token.substring(1).toLowerCase(Locale.ROOT));
            }
        }
        return result.toString();
    }

    private static String slug(String value) {
        return normalize(value).replace(' ', '-');
    }

    private static String normalize(String value) {
        if (value == null) return "";
        String decomposed = Normalizer.normalize(value.toLowerCase(Locale.ROOT), Normalizer.Form.NFD)
                .replace("ı", "i");
        StringBuilder result = new StringBuilder(decomposed.length());
        boolean previousSpace = true;
        for (int index = 0; index < decomposed.length(); index++) {
            char character = decomposed.charAt(index);
            if (Character.getType(character) == Character.NON_SPACING_MARK) continue;
            if (Character.isLetterOrDigit(character)) {
                result.append(character);
                previousSpace = false;
            } else if (!previousSpace) {
                result.append(' ');
                previousSpace = true;
            }
        }
        return result.toString().trim();
    }

    private static Definition def(String id, String label, String flag,
                                  String[] names, String[] codes, String[] hints) {
        return new Definition(id, label, flag, names, codes, hints);
    }

    private static String[] arr(String... values) {
        return values;
    }

    private static List<String> normalizedList(String[] values) {
        ArrayList<String> result = new ArrayList<>();
        if (values != null) {
            for (String value : values) {
                String normalized = normalize(value);
                if (!normalized.isBlank()) result.add(normalized);
            }
        }
        return Collections.unmodifiableList(result);
    }
}