package com.projectlumen.pilot.robust;

import org.junit.Test;

import java.util.Arrays;
import java.util.List;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

/** Release invariant: store candidates must fail closed for adult content. */
public final class ReleaseParentalPolicyTest {
    @Test public void releaseCandidateEnablesParentalProtection() {
        assertTrue(BuildConfig.PARENTAL_PROTECTION_ENABLED);
    }

    @Test public void lockedCatalogHidesRestrictedRows() {
        ParentalFeature.setEnabledForTests(true);
        try {
            ParentalControl.lock("test");
            List<Channel> source = Arrays.asList(
                    new Channel("1", "RTL", "DE Live",
                            "http://example.test/1", Channel.Type.LIVE),
                    new Channel("2", "Film", "XXX Movies",
                            "http://example.test/2", Channel.Type.MOVIE));

            List<Channel> visible = AdultContentPolicy.protect(source);

            assertEquals(1, visible.size());
            assertEquals("RTL", visible.get(0).name);
        } finally {
            ParentalFeature.setEnabledForTests(null);
        }
    }
}
