package com.projectlumen.pilot.robust;

import org.junit.After;
import org.junit.Before;
import org.junit.Test;

import java.util.Arrays;
import java.util.List;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

public final class AdultContentPolicyTest {
    @Before public void enableProtectionForPolicyTests() {
        ParentalFeature.setEnabledForTests(true);
    }

    @After public void clearProtectionOverride() {
        ParentalFeature.setEnabledForTests(null);
    }

    @Test public void detectsCommonAdultCategoryLabels() {
        assertTrue(AdultContentPolicy.isAdultText("XXX Germany"));
        assertTrue(AdultContentPolicy.isAdultText("Adult Movies"));
        assertTrue(AdultContentPolicy.isAdultText("18+ VOD"));
        assertTrue(AdultContentPolicy.isAdultText("Erotik Filme"));
        assertTrue(AdultContentPolicy.isAdultText("Yetişkin Porno"));
        assertTrue(AdultContentPolicy.isAdultText("Adults Only"));
        assertTrue(AdultContentPolicy.isAdultText("Dorcel HD"));
        assertTrue(AdultContentPolicy.isAdultText("Penthouse Live"));
        assertTrue(AdultContentPolicy.isAdultText("Seks TV"));
        assertTrue(AdultContentPolicy.isAdultText("Nur für Erwachsene"));
    }

    @Test public void doesNotHideHarmlessTitlesBySubstring() {
        assertFalse(AdultContentPolicy.isAdultText("Essex County News"));
        assertFalse(AdultContentPolicy.isAdultText("Hotbird International"));
        assertFalse(AdultContentPolicy.isAdultText("RTL Zwei"));
        assertFalse(AdultContentPolicy.isAdultText("Kanal D Dizileri"));
        assertFalse(AdultContentPolicy.isAdultText("Sex Education Documentary"));
        assertFalse(AdultContentPolicy.isAdultText("Private Practice"));
        assertFalse(AdultContentPolicy.isAdultText("Venus – Planetendokumentation"));
    }

    @Test public void lockedProjectionRemovesRowsButRawCatalogRemainsComplete() {
        ParentalControl.lock("test");
        List<Channel> raw = Arrays.asList(
                new Channel("1", "RTL", "DE Live", "http://example/1", Channel.Type.LIVE),
                new Channel("2", "Hidden", "XXX Movies", "http://example/2", Channel.Type.MOVIE),
                new Channel("3", "TRT 1", "TR Live", "http://example/3", Channel.Type.LIVE));
        List<Channel> protectedList = AdultContentPolicy.protect(raw);
        assertEquals(2, protectedList.size());
        assertEquals(3, AdultContentPolicy.rawSize(protectedList));
        assertEquals("RTL", protectedList.get(0).name);
        assertEquals("TRT 1", protectedList.get(1).name);
    }
}
