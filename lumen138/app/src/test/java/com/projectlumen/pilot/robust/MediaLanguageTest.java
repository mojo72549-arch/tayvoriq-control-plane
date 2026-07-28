package com.projectlumen.pilot.robust;

import static org.junit.Assert.assertEquals;

import org.junit.Test;

public final class MediaLanguageTest {
    @Test public void detectsKnownGermanChannels() {
        assertEquals(MediaLanguage.Code.DE, MediaLanguage.detect(channel("RTL HD", "DE: Unterhaltung")));
        assertEquals(MediaLanguage.Code.DE, MediaLanguage.detect(channel("ZDF", "Germany")));
    }

    @Test public void detectsKnownTurkishChannelsAndMedia() {
        assertEquals(MediaLanguage.Code.TR, MediaLanguage.detect(channel("Kanal D HD", "Türkiye Ulusal")));
        assertEquals(MediaLanguage.Code.TR, MediaLanguage.detect(channel("Eine Serie", "TR Dizi")));
    }

    @Test public void keepsUnknownContentSeparate() {
        assertEquals(MediaLanguage.Code.OTHER, MediaLanguage.detect(channel("BBC One", "UK")));
    }

    private static Channel channel(String name, String group) {
        return new Channel("id", name, group, "http://example.test/live.ts", Channel.Type.LIVE);
    }
}
