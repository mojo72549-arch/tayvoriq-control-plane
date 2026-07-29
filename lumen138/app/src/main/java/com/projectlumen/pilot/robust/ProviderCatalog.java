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
        languageMap.put(ProviderLanguage.ALL, ProviderLanguage.allFacet());
        for (Channel channel : safe) {
            if (channel == null || channel.type != wantedType) continue;
            ProviderLanguage.Facet facet = ProviderLanguage.detect(channel);
            if (facet != null && !facet.id.isBlank()) languageMap.putIfAbsent(facet.id, facet);
        }

        String selectedLanguage = wantedLanguage == null ? ProviderLanguage.ALL : wantedLanguage;
        if (!selectedLanguage.isBlank() && !languageMap.containsKey(selectedLanguage)) {
            selectedLanguage = ProviderLanguage.ALL;
        }

        LinkedHashMap<String, String> groupMap = new LinkedHashMap<>();
        for (Channel channel : safe) {
            if (channel == null || channel.type != wantedType) continue;
            if (!ProviderLanguage.matches(channel, selectedLanguage)) continue;
            String group = safeGroup(channel.group);
            groupMap.putIfAbsent(group.toLowerCase(Locale.ROOT), group);
        }

        String selectedGroup = wantedGroup == null ? ALL_GROUPS : wantedGroup.trim();
        if (!selectedGroup.isBlank()
                && !groupMap.containsKey(selectedGroup.toLowerCase(Locale.ROOT))) {
            selectedGroup = ALL_GROUPS;
        }

        String normalizedQuery = query == null ? "" : query.trim();
        ArrayList<Channel> rows = new ArrayList<>();
        for (Channel channel : safe) {
            if (channel == null || channel.type != wantedType) continue;
            if (!ProviderLanguage.matches(channel, selectedLanguage)) continue;
            if (!selectedGroup.isBlank() && !safeGroup(channel.group).equalsIgnoreCase(selectedGroup)) {
                continue;
            }
            if (!normalizedQuery.isBlank() && !matchesQuery(channel, normalizedQuery)) continue;
            rows.add(channel);
        }

        return new Snapshot(new ArrayList<>(languageMap.values()),
                new ArrayList<>(groupMap.values()), rows, selectedLanguage, selectedGroup);
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

    private static String safeGroup(String value) {
        return value == null || value.isBlank() ? "Weitere" : value.trim();
    }
}