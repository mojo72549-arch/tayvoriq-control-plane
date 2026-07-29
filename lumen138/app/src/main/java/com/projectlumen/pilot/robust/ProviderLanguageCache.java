package com.projectlumen.pilot.robust;

import java.util.concurrent.ConcurrentHashMap;

/** Bounded process-local cache for immutable catalog rows. */
final class ProviderLanguageCache {
    private static final int MAX_ENTRIES = 150_000;
    private static final ProviderLanguage.Facet UNKNOWN =
            new ProviderLanguage.Facet("__unknown__", "", "");
    private static final ConcurrentHashMap<String, ProviderLanguage.Facet> CACHE =
            new ConcurrentHashMap<>();

    private ProviderLanguageCache() { }

    static ProviderLanguage.Facet detect(Channel channel) {
        if (channel == null) return null;
        String key = safe(channel.id) + '\u0000' + safe(channel.group) + '\u0000' + safe(channel.name);
        ProviderLanguage.Facet cached = CACHE.get(key);
        if (cached != null) return cached == UNKNOWN ? null : cached;

        ProviderLanguage.Facet detected = ProviderLanguage.detect(channel);
        if (CACHE.size() >= MAX_ENTRIES) CACHE.clear();
        CACHE.put(key, detected == null ? UNKNOWN : detected);
        return detected;
    }

    static boolean matches(Channel channel, String languageId) {
        if (languageId == null || languageId.isBlank()) return true;
        ProviderLanguage.Facet facet = detect(channel);
        return facet != null && languageId.equals(facet.id);
    }

    static void clear() {
        CACHE.clear();
    }

    private static String safe(String value) {
        return value == null ? "" : value;
    }
}