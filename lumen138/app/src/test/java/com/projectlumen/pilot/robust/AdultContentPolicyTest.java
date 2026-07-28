package com.projectlumen.pilot.robust;

import org.junit.Test;

import java.util.Arrays;
import java.util.List;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

public final class AdultContentPolicyTest {
    @Test public void detectsExplicitFsk18AndInternationalAdultLabels() {
        assertTrue(AdultContentPolicy.isAdultText("XXX Germany"));
        assertTrue(AdultContentPolicy.isAdultText("Adult Movies"));
        assertTrue(AdultContentPolicy.isAdultText("18+ VOD"));
        assertTrue(AdultContentPolicy.isAdultText("FSK 18 Film"));
        assertTrue(AdultContentPolicy.isAdultText("FSK18 Uncut"));
        assertTrue(AdultContentPolicy.isAdultText("AB 18"));
        assertTrue(AdultContentPolicy.isAdultText("R18 Cinema"));
        assertTrue(AdultContentPolicy.isAdultText("Erotik Filme"));
        assertTrue(AdultContentPolicy.isAdultText("Yetişkin Porno"));
        assertTrue(AdultContentPolicy.isAdultText("Adults Only"));
        assertTrue(AdultContentPolicy.isAdultText("Brazzers Collection"));
        assertTrue(AdultContentPolicy.isAdultText("Penthouse TV"));
        assertTrue(AdultContentPolicy.isAdult(new Channel(
                "hot", "Protected Movie", "VIP HOT", "http://example/hot", Channel.Type.MOVIE)));
    }

    @Test public void doesNotHideHarmlessTitlesOrNumberedGroups() {
        assertFalse(AdultContentPolicy.isAdultText("Essex County News"));
        assertFalse(AdultContentPolicy.isAdultText("Hotbird International"));
        assertFalse(AdultContentPolicy.isAdultText("RTL Zwei"));
        assertFalse(AdultContentPolicy.isAdultText("Kanal D Dizileri"));
        assertFalse(AdultContentPolicy.isAdultText("Sex Education Documentary"));
        assertFalse(AdultContentPolicy.isAdultText("Group 18"));
        assertFalse(AdultContentPolicy.isAdultText("Gruppe 18"));
        assertFalse(AdultContentPolicy.isAdultText("Channel 18 News"));
    }

    @Test public void familyProjectionAlwaysRemovesProtectedRowsButRawCatalogRemainsComplete() {
        List<Channel> raw = Arrays.asList(
                new Channel("1", "RTL", "DE Live", "http://example/1", Channel.Type.LIVE),
                new Channel("2", "Hidden", "XXX Movies", "http://example/2", Channel.Type.MOVIE),
                new Channel("3", "FSK 18 Thriller", "DE Filme", "http://example/3", Channel.Type.MOVIE),
                new Channel("4", "TRT 1", "TR Live", "http://example/4", Channel.Type.LIVE));
        List<Channel> protectedList = AdultContentPolicy.protect(raw);
        assertEquals(2, protectedList.size());
        assertEquals(4, AdultContentPolicy.raw(protectedList).size());
        assertEquals("RTL", protectedList.get(0).name);
        assertEquals("TRT 1", protectedList.get(1).name);
    }

    @Test public void protectedScopesStaySeparatedByMediaType() {
        List<Channel> raw = Arrays.asList(
                new Channel("1", "Normal", "DE Filme", "http://example/1", Channel.Type.MOVIE),
                new Channel("2", "Protected Movie", "XXX Movies", "http://example/2", Channel.Type.MOVIE),
                new Channel("3", "Protected Live", "Adult Live", "http://example/3", Channel.Type.LIVE),
                new Channel("4", "Protected Series", "FSK 18 Serien", "http://example/4", Channel.Type.SERIES),
                new Channel("5", "Sex Education Documentary", "Dokumentation", "http://example/5", Channel.Type.MOVIE));
        assertEquals(1, AdultContentPolicy.adultContent(raw, Channel.Type.MOVIE).size());
        assertEquals(1, AdultContentPolicy.adultContent(raw, Channel.Type.SERIES).size());
        assertEquals(1, AdultContentPolicy.adultContent(raw, Channel.Type.LIVE).size());
    }

    @Test public void cachedSafetyClassBypassesRepeatedTextClassification() {
        Channel cached = new Channel("id", "Normal title", "Normal group", "http://example/1", "",
                Channel.Type.MOVIE, MediaLanguage.Code.EN, AdultContentPolicy.CLASS_AGE_18);
        assertTrue(cached.adult);
        assertEquals("FSK 18", AdultContentPolicy.classLabel(cached.adultClass));
    }
}
