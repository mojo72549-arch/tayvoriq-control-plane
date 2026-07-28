package com.projectlumen.pilot.robust;

import static org.junit.Assert.assertEquals;

import org.junit.Test;

public final class MediaLanguageTest {
    @Test public void detectsKnownGermanChannels() {
        assertEquals(MediaLanguage.Code.DE, MediaLanguage.detect(channel("RTL HD", "DE: Unterhaltung")));
        assertEquals(MediaLanguage.Code.DE, MediaLanguage.detect(channel("ZDF", "Germany")));
        assertEquals(MediaLanguage.Code.DE, MediaLanguage.detect(channel("N-TV HD", "News")));
        assertEquals(MediaLanguage.Code.DE, MediaLanguage.detect(channel("ProSieben", "DE | Free TV")));
    }

    @Test public void detectsKnownTurkishChannelsAndMedia() {
        assertEquals(MediaLanguage.Code.TR, MediaLanguage.detect(channel("Kanal D HD", "Türkiye Ulusal")));
        assertEquals(MediaLanguage.Code.TR, MediaLanguage.detect(channel("Eine Serie", "TR Dizi")));
        assertEquals(MediaLanguage.Code.TR, MediaLanguage.detect(channel("NTV HD", "Türkiye Haber")));
        assertEquals(MediaLanguage.Code.TR, MediaLanguage.detect(channel("TRT 1", "Ulusal")));
    }

    @Test public void explicitPlaylistGroupWinsOverAmbiguousBrand() {
        assertEquals(MediaLanguage.Code.TR, MediaLanguage.detect(channel("RTL International", "TR | Avrupa")));
        assertEquals(MediaLanguage.Code.DE, MediaLanguage.detect(channel("Kanal D Europe", "DE | International")));
    }

    @Test public void keepsUnknownContentSeparate() {
        assertEquals(MediaLanguage.Code.OTHER, MediaLanguage.detect(channel("BBC One", "UK")));
    }

    private static Channel channel(String name, String group) {
        return new Channel("id", name, group, "http://example.test/live.ts", Channel.Type.LIVE);
    }
}
