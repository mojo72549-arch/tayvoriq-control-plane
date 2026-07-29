package com.projectlumen.pilot.robust;

import org.junit.After;
import org.junit.Before;
import org.junit.Test;

import java.io.ByteArrayInputStream;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.util.List;

import static org.junit.Assert.assertEquals;

public final class ProtectedCatalogRecoveryTest {
    @Before public void enableProtectionForRecoveryTests() {
        ParentalFeature.setEnabledForTests(true);
    }

    @After public void clearProtectionOverride() {
        ParentalFeature.setEnabledForTests(null);
    }

    @Test public void parserKeepsRestrictedRowsAndClassifiesVodAsMovies() throws Exception {
        ParentalControl.lock("test");
        String m3u = "#EXTM3U\n"
                + "#EXTINF:-1 group-title=\"18+ DE\",Restricted Feature 1\n"
                + "http://example.test/content/1001\n"
                + "#EXTINF:-1 group-title=\"Adult Movies\",Restricted Feature 2\n"
                + "http://example.test/content/1002.mp4\n"
                + "#EXTINF:-1 group-title=\"Adult Live\",Restricted TV Live\n"
                + "http://example.test/live/2001.ts\n"
                + "#EXTINF:-1 group-title=\"DE Live\",RTL\n"
                + "http://example.test/live/3001.ts\n";

        List<Channel> protectedList = M3uParser.parse(
                new ByteArrayInputStream(m3u.getBytes(StandardCharsets.UTF_8)),
                100, 10_000L, null);
        List<Channel> raw = AdultContentPolicy.raw(protectedList);

        assertEquals(1, protectedList.size());
        assertEquals(4, raw.size());
        assertEquals(Channel.Type.MOVIE, raw.get(0).type);
        assertEquals(Channel.Type.MOVIE, raw.get(1).type);
        assertEquals(Channel.Type.LIVE, raw.get(2).type);
        assertEquals(Channel.Type.LIVE, raw.get(3).type);
    }

    @Test public void cacheRoundTripNeverDropsLockedRestrictedRows() throws Exception {
        ParentalControl.lock("test");
        String m3u = "#EXTM3U\n"
                + "#EXTINF:-1 group-title=\"18+ DE\",Restricted Feature\n"
                + "http://example.test/content/1001\n"
                + "#EXTINF:-1 group-title=\"DE Live\",RTL\n"
                + "http://example.test/live/3001.ts\n";
        List<Channel> protectedList = M3uParser.parse(
                new ByteArrayInputStream(m3u.getBytes(StandardCharsets.UTF_8)),
                100, 10_000L, null);

        File file = File.createTempFile("lumen-protected-recovery", ".bin");
        try {
            CatalogCache.write(file, protectedList);
            List<Channel> restored = CatalogCache.read(file);
            assertEquals(1, restored.size());
            assertEquals(2, AdultContentPolicy.rawSize(restored));
            assertEquals(Channel.Type.MOVIE, AdultContentPolicy.raw(restored).get(0).type);
        } finally {
            file.delete();
        }
    }
}
