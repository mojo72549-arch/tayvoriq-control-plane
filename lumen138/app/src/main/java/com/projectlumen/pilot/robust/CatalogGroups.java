package com.projectlumen.pilot.robust;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;

/** Builds a dynamic, safe group index from the currently visible catalog projection. */
final class CatalogGroups {
    static final String ALL = "";

    static final class Snapshot {
        final List<Channel> rows;
        final List<String> groups;
        final String selectedGroup;

        Snapshot(List<Channel> rows, List<String> groups, String selectedGroup) {
            this.rows = rows;
            this.groups = groups;
            this.selectedGroup = selectedGroup;
        }
    }

    private CatalogGroups() { }

    static Snapshot build(List<Channel> source,
                          Channel.Type type,
                          MediaLanguage.Code language,
                          String requestedGroup,
                          String query) {
        List<Channel> safeSource = source == null ? Collections.emptyList() : source;
        MediaLanguage.Code safeLanguage = language == null ? MediaLanguage.Code.ALL : language;
        String safeQuery = query == null ? "" : query.trim();

        ArrayList<Channel> candidates = new ArrayList<>();
        Map<String, String> canonicalGroups = new TreeMap<>();
        for (Channel channel : safeSource) {
            if (channel == null || channel.type != type) continue;
            if (safeLanguage != MediaLanguage.Code.ALL
                    && MediaLanguage.detect(channel) != safeLanguage) continue;
            candidates.add(channel);
            String group = safeGroup(channel.group);
            canonicalGroups.putIfAbsent(normalize(group), group);
        }

        ArrayList<String> groups = new ArrayList<>(canonicalGroups.values());
        groups.sort(String.CASE_INSENSITIVE_ORDER);

        String wanted = requestedGroup == null ? ALL : requestedGroup.trim();
        String effectiveGroup = wanted.isEmpty()
                ? ALL : canonicalGroups.getOrDefault(normalize(wanted), ALL);

        ArrayList<Channel> rows = new ArrayList<>();
        for (Channel channel : candidates) {
            if (!effectiveGroup.isEmpty()
                    && !safeGroup(channel.group).equalsIgnoreCase(effectiveGroup)) continue;
            if (!safeQuery.isEmpty() && !matches(channel, safeQuery)) continue;
            rows.add(channel);
        }

        return new Snapshot(
                Collections.unmodifiableList(rows),
                Collections.unmodifiableList(groups),
                effectiveGroup);
    }

    private static boolean matches(Channel channel, String query) {
        return containsIgnoreCase(channel.name, query)
                || containsIgnoreCase(channel.group, query);
    }

    private static boolean containsIgnoreCase(String value, String query) {
        if (value == null || query == null || query.length() > value.length()) return false;
        int limit = value.length() - query.length();
        for (int index = 0; index <= limit; index++) {
            if (value.regionMatches(true, index, query, 0, query.length())) return true;
        }
        return false;
    }

    private static String safeGroup(String value) {
        String group = value == null ? "" : value.trim();
        return group.isEmpty() ? "Weitere" : group;
    }

    private static String normalize(String value) {
        return safeGroup(value).toLowerCase(Locale.ROOT);
    }
}
