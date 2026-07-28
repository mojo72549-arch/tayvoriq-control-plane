package com.projectlumen.pilot.robust;

import java.util.Collections;
import java.util.List;

/** Process-local catalog handoff and cached protected scopes. */
final class CatalogSession {
    private static volatile List<Channel> raw = Collections.emptyList();
    private static volatile List<Channel> adultLive = Collections.emptyList();
    private static volatile List<Channel> adultMovies = Collections.emptyList();
    private static volatile List<Channel> adultSeries = Collections.emptyList();

    private CatalogSession() { }

    static synchronized void publish(List<Channel> source) {
        List<Channel> next = AdultContentPolicy.raw(source);
        if (next == raw) return;
        raw = next;
        adultLive = AdultContentPolicy.adultContent(next, Channel.Type.LIVE);
        adultMovies = AdultContentPolicy.adultContent(next, Channel.Type.MOVIE);
        adultSeries = AdultContentPolicy.adultContent(next, Channel.Type.SERIES);
    }

    static List<Channel> raw() { return raw; }
    static List<Channel> adultLive() { return adultLive; }
    static List<Channel> adultMovies() { return adultMovies; }
    static List<Channel> adultSeries() { return adultSeries; }
}
