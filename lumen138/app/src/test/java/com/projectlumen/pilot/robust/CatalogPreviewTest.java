package com.projectlumen.pilot.robust;

import org.junit.Test;

import java.io.File;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.List;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

public final class CatalogPreviewTest {
    @Test public void readsBoundedSafeTurkishMoviePreviewWithoutFullProjection() throws Exception {
        ArrayList<Channel> source = new ArrayList<>(100_000);
        for (int index = 0; index < 100_000; index++) {
            boolean movie = index % 3 == 0;
            boolean turkish = index % 2 == 0;
            boolean adult = index % 997 == 0;
            source.add(new Channel("id-" + index, "Entry " + index,
                    adult ? "XXX Movies" : turkish ? "TR | Filmler" : "DE | Filme",
                    "https://example.test/stream/" + index,
                    "https://img.example.test/" + index + ".png",
                    movie ? Channel.Type.MOVIE : Channel.Type.LIVE));
        }

        File file = Files.createTempFile("lumen-preview-", ".bin").toFile();
        CatalogCache.write(file, source);

        long started = System.nanoTime();
        List<Channel> preview = CatalogCache.readPreview(file, Channel.Type.MOVIE,
                MediaLanguage.Code.TR, 180);
        long durationMs = (System.nanoTime() - started) / 1_000_000L;

        assertEquals(180, preview.size());
        for (Channel channel : preview) {
            assertEquals(Channel.Type.MOVIE, channel.type);
            assertEquals(MediaLanguage.Code.TR, channel.language);
            assertFalse(channel.adult);
        }
        assertTrue("Preview took " + durationMs + " ms", durationMs < 2_000L);
        file.delete();
    }
}