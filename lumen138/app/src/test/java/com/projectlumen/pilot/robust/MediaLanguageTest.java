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

    @Test public void detectsEnglishAndKeepsOtherCountriesSeparate() {
        assertEquals(MediaLanguage.Code.EN, MediaLanguage.detect(channel("BBC One", "UK")));
        assertEquals(MediaLanguage.Code.EN, MediaLanguage.detect(channel("NBC News", "US English")));
        assertEquals(MediaLanguage.Code.EN, MediaLanguage.detect(channel("Channel 4", "Entertainment")));
        assertEquals(MediaLanguage.Code.OTHER, MediaLanguage.detect(channel("Rai Uno", "Italia")));
        assertEquals(MediaLanguage.Code.OTHER, MediaLanguage.detect(channel("France 2", "France")));
    }

    @Test public void explicitPlaylistGroupWinsOverAmbiguousBrand() {
        assertEquals(MediaLanguage.Code.TR, MediaLanguage.detect(channel("RTL International", "TR | Avrupa")));
        assertEquals(MediaLanguage.Code.DE, MediaLanguage.detect(channel("Kanal D Europe", "DE | International")));
        assertEquals(MediaLanguage.Code.EN, MediaLanguage.detect(channel("RTL World", "UK | English")));
    }

    @Test public void cachedLanguageIsReturnedWithoutReclassification() {
        Channel channel = new Channel("id", "Ambiguous", "Unknown", "http://example.test/live.ts", "",
                Channel.Type.LIVE, MediaLanguage.Code.EN, AdultContentPolicy.CLASS_SAFE);
        assertEquals(MediaLanguage.Code.EN, MediaLanguage.detect(channel));
    }

    private static Channel channel(String name, String group) {
        return new Channel("id", name, group, "http://example.test/live.ts", Channel.Type.LIVE);
    }
}
