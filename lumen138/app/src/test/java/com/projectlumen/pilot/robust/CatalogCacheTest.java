package com.projectlumen.pilot.robust;

import org.junit.Test;

import java.io.File;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.List;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

public final class CatalogCacheTest {
    @Test
    public void writesAndReadsOneHundredThousandEntries() throws Exception {
        ArrayList<Channel> source = new ArrayList<>(100_000);
        for (int index = 0; index < 100_000; index++) {
            Channel.Type type = index % 11 == 0 ? Channel.Type.SERIES
                    : index % 5 == 0 ? Channel.Type.MOVIE : Channel.Type.LIVE;
            source.add(new Channel(
                    "id-" + index,
                    "Eintrag " + index,
                    "Gruppe " + (index % 120),
                    "https://example.test/stream/" + index + ".ts",
                    type));
        }

        File file = Files.createTempFile("lumen-catalog-", ".bin").toFile();
        long started = System.nanoTime();
        CatalogCache.write(file, source);
        List<Channel> restored = CatalogCache.read(file);
        long durationMs = (System.nanoTime() - started) / 1_000_000L;

        assertEquals(100_000, restored.size());
        assertEquals("Eintrag 0", restored.get(0).name);
        assertEquals("Eintrag 99999", restored.get(99_999).name);
        assertEquals(Channel.Type.MOVIE, restored.get(99_995).type);
        assertTrue("Cache roundtrip took " + durationMs + " ms", durationMs < 30_000L);
        assertTrue(file.length() > 1_000_000L);

        file.delete();
    }
}
