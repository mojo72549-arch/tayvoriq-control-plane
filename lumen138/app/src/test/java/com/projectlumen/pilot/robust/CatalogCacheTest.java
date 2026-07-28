package com.projectlumen.pilot.robust;

import org.junit.Test;

import java.io.BufferedOutputStream;
import java.io.DataOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.List;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertSame;
import static org.junit.Assert.assertTrue;

public final class CatalogCacheTest {
    @Test
    public void writesAndReadsOneHundredThousandEntriesWithCachedFlagsAndLogos() throws Exception {
        ArrayList<Channel> source = new ArrayList<>(100_000);
        for (int index = 0; index < 100_000; index++) {
            Channel.Type type = index % 11 == 0 ? Channel.Type.SERIES
                    : index % 5 == 0 ? Channel.Type.MOVIE : Channel.Type.LIVE;
            String group = index % 4 == 0 ? "DE | Gruppe " + (index % 120)
                    : index % 4 == 1 ? "TR | Gruppe " + (index % 120)
                    : index % 4 == 2 ? "UK | English" : "Italia";
            source.add(new Channel(
                    "id-" + index,
                    "Eintrag " + index,
                    group,
                    "https://example.test/stream/" + index + ".ts",
                    "https://img.example.test/logo/" + index + ".png",
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
        assertEquals("https://img.example.test/logo/0.png", restored.get(0).logo);
        assertEquals("https://img.example.test/logo/99999.png", restored.get(99_999).logo);
        assertEquals(Channel.Type.MOVIE, restored.get(99_995).type);
        assertEquals(MediaLanguage.Code.DE, restored.get(0).language);
        assertEquals(MediaLanguage.Code.TR, restored.get(1).language);
        assertEquals(MediaLanguage.Code.EN, restored.get(2).language);
        assertEquals(MediaLanguage.Code.OTHER, restored.get(3).language);
        assertFalse(restored.get(18).adult);
        assertTrue("Cache roundtrip took " + durationMs + " ms", durationMs < 30_000L);
        assertTrue(file.length() > 1_000_000L);

        long memoryStarted = System.nanoTime();
        List<Channel> memoryHit = CatalogCache.read(file);
        long memoryDurationMs = (System.nanoTime() - memoryStarted) / 1_000_000L;
        assertSame(restored, memoryHit);
        assertTrue("Process memory hit took " + memoryDurationMs + " ms", memoryDurationMs < 250L);

        file.delete();
    }

    @Test
    public void versionThreeCacheRecomputesFormerWickedFalsePositive() throws Exception {
        File file = Files.createTempFile("lumen-v3-stale-", ".bin").toFile();
        try (DataOutputStream output = new DataOutputStream(new BufferedOutputStream(
                new FileOutputStream(file)))) {
            output.writeInt(0x4C554D34);
            output.writeInt(3);
            output.writeInt(1);
            writeString(output, "wicked-id");
            writeString(output, "Wicked - 2024");
            writeString(output, "TR Drama Filmleri");
            writeString(output, "https://provider/movie/wicked-2024.mp4");
            writeString(output, "https://images/wicked.jpg");
            output.writeByte(Channel.Type.MOVIE.ordinal());
            output.writeByte(MediaLanguage.Code.TR.ordinal());
            output.writeByte(AdultContentPolicy.CLASS_ADULT_BRAND);
        }

        List<Channel> restored = CatalogCache.read(file);
        assertEquals(1, restored.size());
        assertEquals("Wicked - 2024", restored.get(0).name);
        assertFalse(restored.get(0).adult);
        assertEquals(AdultContentPolicy.CLASS_SAFE, restored.get(0).adultClass);
        assertEquals(1, AdultContentPolicy.raw(restored).size());
    }

    private static void writeString(DataOutputStream output, String value) throws Exception {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        output.writeInt(bytes.length);
        output.write(bytes);
    }
}
