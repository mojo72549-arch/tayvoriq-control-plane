package com.projectlumen.pilot.robust;

import org.junit.Test;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.List;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

public final class M3uParser100kTest {
    @Test
    public void parsesOneHundredThousandEntriesAndDrainsInput() throws Exception {
        ByteArrayOutputStream output = new ByteArrayOutputStream(32 * 1024 * 1024);
        output.write("#EXTM3U\n".getBytes(StandardCharsets.UTF_8));
        for (int index = 0; index < 100_500; index++) {
            String group = index % 9 == 0 ? "Serien" : index % 4 == 0 ? "Filme" : "Live DE";
            String item = "#EXTINF:-1 group-title=\"" + group + "\",Test " + index + "\n"
                    + "https://example.test/" + (group.equals("Serien") ? "series" : group.equals("Filme") ? "movie" : "live")
                    + "/" + index + ".ts\n";
            output.write(item.getBytes(StandardCharsets.UTF_8));
        }

        ByteArrayInputStream input = new ByteArrayInputStream(output.toByteArray());
        long started = System.nanoTime();
        List<Channel> channels = M3uParser.parse(input, 100_000, 30_000L,
                (lines, entries, elapsedMs, limitReached) -> { });
        long durationMs = (System.nanoTime() - started) / 1_000_000L;

        assertEquals(100_000, channels.size());
        assertEquals(0, input.available());
        assertEquals(Channel.Type.SERIES, channels.get(0).type);
        assertTrue("Parser took " + durationMs + " ms", durationMs < 30_000L);
    }
}
