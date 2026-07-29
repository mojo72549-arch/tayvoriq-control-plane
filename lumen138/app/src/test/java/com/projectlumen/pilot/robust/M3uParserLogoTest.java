package com.projectlumen.pilot.robust;

import static org.junit.Assert.assertEquals;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.junit.Test;

public final class M3uParserLogoTest {
    @Test public void parsesHttpLogoMetadataAndRejectsLocalSchemes() throws Exception {
        String playlist = "#EXTM3U\n"
                + "#EXTINF:-1 tvg-id=\"rtl.de\" tvg-logo=\"https://img.example/rtl.png\" group-title=\"DE | Live\",RTL HD\n"
                + "http://example.test/rtl.ts\n"
                + "#EXTINF:-1 tvg-logo=\"file:///secret/logo.png\" group-title=\"TR | Live\",TRT 1\n"
                + "http://example.test/trt.ts\n";
        List<Channel> channels = M3uParser.parse(
                new ByteArrayInputStream(playlist.getBytes(StandardCharsets.UTF_8)),
                100, 5_000L, null);
        assertEquals(2, channels.size());
        assertEquals("https://img.example/rtl.png", channels.get(0).logo);
        assertEquals("", channels.get(1).logo);
    }
}
