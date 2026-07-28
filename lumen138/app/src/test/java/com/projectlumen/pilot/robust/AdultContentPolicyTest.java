package com.projectlumen.pilot.robust;

import org.junit.Test;

import java.util.Arrays;
import java.util.List;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

public final class AdultContentPolicyTest {
    @Test public void detectsCommonAdultCategoryLabels() {
        assertTrue(AdultContentPolicy.isAdultText("XXX Germany"));
        assertTrue(AdultContentPolicy.isAdultText("Adult Movies"));
        assertTrue(AdultContentPolicy.isAdultText("18+ VOD"));
        assertTrue(AdultContentPolicy.isAdultText("Erotik Filme"));
        assertTrue(AdultContentPolicy.isAdultText("Yetişkin Porno"));
        assertTrue(AdultContentPolicy.isAdultText("Adults Only"));
        assertTrue(AdultContentPolicy.isAdultText("VIP HOT"));
    }

    @Test public void doesNotHideHarmlessTitlesBySubstring() {
        assertFalse(AdultContentPolicy.isAdultText("Essex County News"));
        assertFalse(AdultContentPolicy.isAdultText("Hotbird International"));
        assertFalse(AdultContentPolicy.isAdultText("RTL Zwei"));
        assertFalse(AdultContentPolicy.isAdultText("Kanal D Dizileri"));
        assertFalse(AdultContentPolicy.isAdultText("Sex Education Documentary"));
    }

    @Test public void familyProjectionAlwaysRemovesAdultRowsButRawCatalogRemainsComplete() {
        List<Channel> raw = Arrays.asList(
                new Channel("1", "RTL", "DE Live", "http://example/1", Channel.Type.LIVE),
                new Channel("2", "Hidden", "XXX Movies", "http://example/2", Channel.Type.MOVIE),
                new Channel("3", "TRT 1", "TR Live", "http://example/3", Channel.Type.LIVE));
        List<Channel> protectedList = AdultContentPolicy.protect(raw);
        assertEquals(2, protectedList.size());
        assertEquals(3, AdultContentPolicy.raw(protectedList).size());
        assertEquals("RTL", protectedList.get(0).name);
        assertEquals("TRT 1", protectedList.get(1).name);
    }

    @Test public void adultProjectionContainsOnlyExplicitAdultMovies() {
        List<Channel> raw = Arrays.asList(
                new Channel("1", "Normal", "DE Filme", "http://example/1", Channel.Type.MOVIE),
                new Channel("2", "Protected Movie", "XXX Movies", "http://example/2", Channel.Type.MOVIE),
                new Channel("3", "Protected Live", "Adult Live", "http://example/3", Channel.Type.LIVE),
                new Channel("4", "Sex Education Documentary", "Dokumentation", "http://example/4", Channel.Type.MOVIE));
        List<Channel> adult = AdultContentPolicy.adultMovies(raw);
        assertEquals(1, adult.size());
        assertEquals("Protected Movie", adult.get(0).name);
    }
}
