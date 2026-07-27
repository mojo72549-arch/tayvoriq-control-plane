package com.projectlumen.pilot.robust;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import org.junit.Test;

public final class M3uParserPerformanceTest {
    @Test
    public void parsesOneHundredThousandEntriesAndDrainsTail() throws Exception {
        int sourceEntries = 100_500;
        String padding = "x".repeat(220);
        StringBuilder playlist = new StringBuilder(sourceEntries * 360);
        playlist.append("#EXTM3U\n");
        for (int index = 0; index < sourceEntries; index++) {
            playlist.append("#EXTINF:-1 group-title=\"Group ")
                    .append(index % 50)
                    .append("\",Channel ")
                    .append(index)
                    .append(' ')
                    .append(padding)
                    .append('\n');
            playlist.append("http://example.invalid/live/user/pass/")
                    .append(index)
                    .append(".ts\n");
        }

        byte[] payload = playlist.toString().getBytes(StandardCharsets.UTF_8);
        AtomicInteger progressEvents = new AtomicInteger();
        AtomicLong finalLines = new AtomicLong();
        long started = System.nanoTime();

        List<Channel> channels = M3uParser.parse(
                new ByteArrayInputStream(payload),
                100_000,
                120_000L,
                (lines, entries, elapsedMs, limitReached) -> {
                    progressEvents.incrementAndGet();
                    finalLines.set(lines);
                });

        long elapsedMs = (System.nanoTime() - started) / 1_000_000L;
        assertEquals(100_000, channels.size());
        assertTrue("Parser must continue to EOF for GCM integrity verification",
                finalLines.get() >= 201_001L);
        assertTrue("Parser must emit progress events", progressEvents.get() >= 20);
        assertTrue("100k parser gate exceeded 30 seconds: " + elapsedMs + " ms",
                elapsedMs < 30_000L);
    }
}
