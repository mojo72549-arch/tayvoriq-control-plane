package com.projectlumen.pilot.robust;

import org.junit.After;
import org.junit.Test;

import java.util.Arrays;
import java.util.List;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;

public final class ParentalFeatureDisabledTest {
    @After public void clearOverride() {
        ParentalFeature.setEnabledForTests(null);
    }

    @Test public void disabledBuildReturnsCompleteCatalogEvenWhenLocked() {
        ParentalFeature.setEnabledForTests(false);
        ParentalControl.lock("test");
        List<Channel> source = Arrays.asList(
                new Channel("1", "RTL", "DE Live", "http://example/1", Channel.Type.LIVE),
                new Channel("2", "Adult Movie", "XXX Movies", "http://example/2", Channel.Type.MOVIE));

        List<Channel> visible = AdultContentPolicy.protect(source);

        assertFalse(ParentalFeature.enabled());
        assertEquals(2, visible.size());
        assertEquals("XXX Movies", visible.get(1).group);
    }
}
