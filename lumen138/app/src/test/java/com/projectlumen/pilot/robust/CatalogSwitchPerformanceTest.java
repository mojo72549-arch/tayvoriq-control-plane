package com.projectlumen.pilot.robust;

import org.junit.Test;

import java.util.ArrayList;
import java.util.List;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

public final class CatalogSwitchPerformanceTest {
    @Test public void repeatedLanguageSwitchesUseCachedFlags() {
        ArrayList<Channel> channels = new ArrayList<>(100_000);
        for (int index = 0; index < 100_000; index++) {
            String group;
            String name;
            switch (index % 4) {
                case 0:
                    group = "DE | Unterhaltung";
                    name = "RTL " + index;
                    break;
                case 1:
                    group = "TR | Türkiye";
                    name = "TRT " + index;
                    break;
                case 2:
                    group = "UK | English";
                    name = "BBC " + index;
                    break;
                default:
                    group = "Italia";
                    name = "Rai " + index;
                    break;
            }
            channels.add(new Channel("id-" + index, name, group,
                    "http://example.test/" + index + ".ts", Channel.Type.LIVE));
        }

        long started = System.nanoTime();
        int total = 0;
        for (int round = 0; round < 20; round++) {
            MediaLanguage.Code wanted = round % 4 == 0 ? MediaLanguage.Code.DE
                    : round % 4 == 1 ? MediaLanguage.Code.TR
                    : round % 4 == 2 ? MediaLanguage.Code.EN : MediaLanguage.Code.OTHER;
            for (Channel channel : channels) {
                if (MediaLanguage.detect(channel) == wanted) total++;
            }
        }
        long durationMs = (System.nanoTime() - started) / 1_000_000L;

        assertEquals(500_000, total);
        assertTrue("20 cached switches over 100k rows took " + durationMs + " ms",
                durationMs < 2_500L);
    }

    @Test public void cachedAdultProjectionIsLinearAndStable() {
        List<Channel> channels = new ArrayList<>();
        for (int index = 0; index < 100_000; index++) {
            boolean protectedRow = index % 100 == 0;
            channels.add(new Channel("id-" + index, "Movie " + index,
                    protectedRow ? "FSK 18 Filme" : "DE Filme",
                    "http://example.test/movie/" + index, Channel.Type.MOVIE));
        }
        long started = System.nanoTime();
        List<Channel> protectedList = AdultContentPolicy.protect(channels);
        long durationMs = (System.nanoTime() - started) / 1_000_000L;
        assertEquals(99_000, protectedList.size());
        assertEquals(1_000, AdultContentPolicy.adultMovies(protectedList).size());
        assertTrue("Cached safety projection took " + durationMs + " ms", durationMs < 2_500L);
    }
}
