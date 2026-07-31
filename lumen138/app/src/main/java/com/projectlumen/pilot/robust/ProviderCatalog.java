package com.projectlumen.pilot.robust;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/** Builds one immutable UI snapshot from the current protected catalog. */
final class ProviderCatalog {
    static final String ALL_GROUPS = "";
    static final String FAVORITES_GROUP = "★ Favoriten";
    static final String RECENT_GROUP = "↻ Zuletzt angesehen";
    private static final String UNCATEGORIZED = "Ohne Kategorie";

    static final class Snapshot {
        final List<ProviderLanguage.Facet> languages;
        final List<String> groups;
        final List<Channel> rows;
        final String selectedLanguage;
        final String selectedGroup;

        Snapshot(List<ProviderLanguage.Facet> languages,
                 List<String> groups,
                 List<Channel> rows,
                 String selectedLanguage,
                 String selectedGroup) {
            this.languages = Collections.unmodifiableList(new ArrayList<>(languages));
            this.groups = Collections.unmodifiableList(new ArrayList<>(groups));
            this.rows = Collections.unmodifiableList(new ArrayList<>(rows));
            this.selectedLanguage = selectedLanguage == null ? ProviderLanguage.ALL : selectedLanguage;
            this.selectedGroup = selectedGroup == null ? ALL_GROUPS : selectedGroup;
        }
    }

    private ProviderCatalog() { }

    static Snapshot build(List<Channel> source,
                          Channel.Type type,
                          String wantedLanguage,
                          String wantedGroup,
                          String query) {
        List<Channel> safe = source == null ? Collections.emptyList() : source;
        Channel.Type wantedType = type == null ? Channel.Type.LIVE : type;

        LinkedHashMap<String, ProviderLanguage.Facet> languageMap = new LinkedHashMap<>();
        for (Channel channel : safe) {
            if (channel == null || channel.type != wantedType) continue;
            ProviderLanguage.Facet facet = ProviderLanguageCache.detect(channel);
            if (facet != null && !facet.id.isBlank()) languageMap.putIfAbsent(facet.id, facet);
        }

        String selectedLanguage = wantedLanguage == null ? ProviderLanguage.ALL : wantedLanguage;
        if (ProviderLanguage.ALL.equals(selectedLanguage)
                || selectedLanguage.isBlank()
                || !languageMap.containsKey(selectedLanguage)) {
            selectedLanguage = languageMap.isEmpty()
                    ? ProviderLanguage.ALL : languageMap.keySet().iterator().next();
        }
        ProviderLanguage.Facet selectedFacet = languageMap.get(selectedLanguage);

        UserCollectionStore collections = UserCollectionStore.current();
        boolean hasFavorites = false;
        boolean hasRecent = false;
        int languageRows = 0;
        LinkedHashMap<String, String> groupMap = new LinkedHashMap<>();
        LinkedHashMap<String, Integer> groupCounts = new LinkedHashMap<>();
        for (Channel channel : safe) {
            if (channel == null || channel.type != wantedType) continue;
            if (!ProviderLanguageCache.matches(channel, selectedLanguage)) continue;
            languageRows++;
            if (collections != null && collections.isFavorite(channel)) hasFavorites = true;
            if (collections != null && collections.isRecent(channel)) hasRecent = true;
            String group = canonicalGroup(channel.group, selectedFacet);
            String key = group.toLowerCase(Locale.ROOT);
            groupMap.putIfAbsent(key, group);
            groupCounts.put(key, groupCounts.getOrDefault(key, 0) + 1);
        }

        LinkedHashMap<String, String> visibleGroups = new LinkedHashMap<>();
        if (hasFavorites) visibleGroups.put(FAVORITES_GROUP.toLowerCase(Locale.ROOT), FAVORITES_GROUP);
        if (hasRecent) visibleGroups.put(RECENT_GROUP.toLowerCase(Locale.ROOT), RECENT_GROUP);

        int providerGroupCount = groupMap.size();
        for (Map.Entry<String, String> entry : groupMap.entrySet()) {
            String group = entry.getValue();
            int count = groupCounts.getOrDefault(entry.getKey(), 0);
            if (isRedundantLanguageGroup(group, selectedFacet)) continue;
            if (isDominantProviderRoot(group, count, languageRows, providerGroupCount)) continue;
            visibleGroups.put(entry.getKey(), group);
        }

        String selectedGroup = wantedGroup == null ? ALL_GROUPS : wantedGroup.trim();
        if (!selectedGroup.isBlank()
                && !FAVORITES_GROUP.equals(selectedGroup)
                && !RECENT_GROUP.equals(selectedGroup)) {
            selectedGroup = canonicalGroup(selectedGroup, selectedFacet);
        }
        if (!selectedGroup.isBlank()
                && !visibleGroups.containsKey(selectedGroup.toLowerCase(Locale.ROOT))) {
            selectedGroup = ALL_GROUPS;
        }

        String normalizedQuery = query == null ? "" : query.trim();
        ArrayList<Channel> rows = new ArrayList<>();
        for (Channel channel : safe) {
            if (channel == null || channel.type != wantedType) continue;
            if (!ProviderLanguageCache.matches(channel, selectedLanguage)) continue;
            if (FAVORITES_GROUP.equals(selectedGroup)) {
                if (collections == null || !collections.isFavorite(channel)) continue;
            } else if (RECENT_GROUP.equals(selectedGroup)) {
                if (collections == null || !collections.isRecent(channel)) continue;
            } else if (!selectedGroup.isBlank()
                    && !canonicalGroup(channel.group, selectedFacet).equalsIgnoreCase(selectedGroup)) {
                continue;
            }
            if (!normalizedQuery.isBlank() && !matchesQuery(channel, normalizedQuery)) continue;
            rows.add(channel);
        }

        return new Snapshot(new ArrayList<>(languageMap.values()),
                new ArrayList<>(visibleGroups.values()), rows, selectedLanguage, selectedGroup);
    }

    private static boolean matchesQuery(Channel channel, String query) {
        return containsIgnoreCase(channel.name, query)
                || containsIgnoreCase(channel.group, query);
    }

    private static boolean containsIgnoreCase(String text, String needle) {
        if (text == null || needle == null) return false;
        int limit = text.length() - needle.length();
        for (int index = 0; index <= limit; index++) {
            if (text.regionMatches(true, index, needle, 0, needle.length())) return true;
        }
        return false;
    }

    private static String canonicalGroup(String value, ProviderLanguage.Facet facet) {
        String group = safeGroup(value);
        if (UNCATEGORIZED.equals(group)) return group;

        if (facet != null && !facet.id.isBlank()) {
            for (String prefix : languagePrefixes(facet)) {
                String stripped = stripExactPrefix(group, prefix);
                if (stripped != null) {
                    group = stripped.isBlank() ? UNCATEGORIZED : stripped;
                    break;
                }
            }
        }

        String mediaStripped = stripMediaPrefix(group);
        if (mediaStripped != null && !mediaStripped.isBlank()) group = mediaStripped;
        return prettyGroup(group);
    }

    private static String[] languagePrefixes(ProviderLanguage.Facet facet) {
        String id = facet.id == null ? "" : facet.id.toLowerCase(Locale.ROOT);
        switch (id) {
            case "de": return new String[]{facet.label, "DE", "GER", "DEU", "German", "Deutsch"};
            case "tr": return new String[]{facet.label, "TR", "TUR", "Turkish", "Türkisch", "Turkiye", "Türkiye"};
            case "el": return new String[]{facet.label, "GR", "EL", "GRE", "Greek", "Griechisch"};
            case "en": return new String[]{facet.label, "EN", "ENG", "UK", "US", "USA", "English", "Englisch"};
            case "ar": return new String[]{facet.label, "AR", "ARA", "Arabic", "Arabisch"};
            case "fr": return new String[]{facet.label, "FR", "FRA", "French", "Französisch"};
            case "it": return new String[]{facet.label, "IT", "ITA", "Italian", "Italienisch"};
            case "es": return new String[]{facet.label, "ES", "ESP", "Spanish", "Spanisch"};
            case "pt": return new String[]{facet.label, "PT", "POR", "BR", "Portuguese", "Portugiesisch"};
            case "nl": return new String[]{facet.label, "NL", "NLD", "Dutch", "Niederländisch"};
            case "pl": return new String[]{facet.label, "PL", "POL", "Polish", "Polnisch"};
            case "ro": return new String[]{facet.label, "RO", "RON", "Romanian", "Rumänisch"};
            case "bg": return new String[]{facet.label, "BG", "BUL", "Bulgarian", "Bulgarisch"};
            case "sq": return new String[]{facet.label, "AL", "SQ", "ALB", "Albanian", "Albanisch"};
            case "ru": return new String[]{facet.label, "RU", "RUS", "Russian", "Russisch"};
            case "uk": return new String[]{facet.label, "UA", "UKR", "Ukrainian", "Ukrainisch"};
            case "bs": return new String[]{facet.label, "BA", "BS", "BOS", "Bosnian", "Bosnisch"};
            case "hr": return new String[]{facet.label, "HR", "HRV", "Croatian", "Kroatisch"};
            case "sr": return new String[]{facet.label, "RS", "SR", "SRP", "Serbian", "Serbisch"};
            default: return new String[]{facet.label, facet.id.toUpperCase(Locale.ROOT), facet.id};
        }
    }

    private static String stripMediaPrefix(String value) {
        String[] prefixes = new String[]{
                "LIVE TV", "LIVE-TV", "LIVE",
                "FILME", "FILM", "MOVIES", "MOVIE", "VOD",
                "SERIEN", "SERIE", "SERIES"
        };
        for (String prefix : prefixes) {
            String stripped = stripExactPrefix(value, prefix);
            if (stripped != null) return stripped;
        }
        return null;
    }

    private static String stripExactPrefix(String value, String prefix) {
        if (value == null || prefix == null || prefix.isBlank()) return null;
        if (value.equalsIgnoreCase(prefix)) return "";
        if (value.length() <= prefix.length()
                || !value.regionMatches(true, 0, prefix, 0, prefix.length())) return null;
        char next = value.charAt(prefix.length());
        if (!Character.isWhitespace(next) && "|:;•/-–—".indexOf(next) < 0) return null;
        int index = prefix.length();
        while (index < value.length()) {
            char current = value.charAt(index);
            if (!Character.isWhitespace(current) && "|:;•/-–—".indexOf(current) < 0) break;
            index++;
        }
        return value.substring(index).trim();
    }

    private static boolean isRedundantLanguageGroup(String group,
                                                     ProviderLanguage.Facet facet) {
        if (facet == null) return isMediaRoot(group);
        return group.equalsIgnoreCase(facet.label)
                || group.equalsIgnoreCase(facet.id)
                || isMediaRoot(group);
    }

    private static boolean isMediaRoot(String group) {
        if (group == null) return false;
        String normalized = group.trim().toLowerCase(Locale.ROOT);
        return normalized.equals("live") || normalized.equals("live tv")
                || normalized.equals("live-tv") || normalized.equals("filme")
                || normalized.equals("film") || normalized.equals("movies")
                || normalized.equals("movie") || normalized.equals("vod")
                || normalized.equals("serien") || normalized.equals("serie")
                || normalized.equals("series");
    }

    private static boolean isDominantProviderRoot(String group, int count,
                                                   int languageRows, int providerGroupCount) {
        if (UNCATEGORIZED.equalsIgnoreCase(group)) return false;
        if (languageRows <= 0 || count <= 0) return false;
        if (providerGroupCount == 1 && count == languageRows) return true;
        if (count * 100 < languageRows * 90) return false;
        String normalized = group.toLowerCase(Locale.ROOT);
        return normalized.length() <= 18
                && !normalized.contains("news")
                && !normalized.contains("sport")
                && !normalized.contains("movie")
                && !normalized.contains("film")
                && !normalized.contains("series")
                && !normalized.contains("serie")
                && !normalized.contains("kids")
                && !normalized.contains("music")
                && !normalized.contains("doku");
    }

    private static String prettyGroup(String value) {
        String group = safeGroup(value);
        if (!group.equals(group.toUpperCase(Locale.ROOT))) return group;
        String normalized = group.toUpperCase(Locale.ROOT);
        if (normalized.equals("HD") || normalized.equals("FHD") || normalized.equals("UHD")
                || normalized.equals("SD") || normalized.equals("TV")
                || normalized.equals("4K") || normalized.equals("8K")) return normalized;
        String[] words = group.toLowerCase(Locale.ROOT).split("\\s+");
        StringBuilder result = new StringBuilder(group.length());
        for (String word : words) {
            if (word.isBlank()) continue;
            if (result.length() > 0) result.append(' ');
            result.append(Character.toUpperCase(word.charAt(0))).append(word.substring(1));
        }
        return result.toString();
    }

    private static String safeGroup(String value) {
        if (value == null || value.isBlank() || value.trim().equalsIgnoreCase("Weitere")) {
            return UNCATEGORIZED;
        }
        return value.trim().replaceAll("\\s{2,}", " ");
    }
}
