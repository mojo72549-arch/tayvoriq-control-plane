package com.projectlumen.pilot.robust;

import java.util.Collections;
import java.util.List;

/** Process-local catalog handoff so the parent hub never reloads or mutates MainActivity. */
final class CatalogSession {
    private static volatile List<Channel> raw = Collections.emptyList();

    private CatalogSession() { }

    static void publish(List<Channel> source) {
        raw = AdultContentPolicy.raw(source);
    }

    static List<Channel> raw() {
        return raw;
    }

    static List<Channel> adultMovies() {
        return AdultContentPolicy.adultMovies(raw);
    }
}
