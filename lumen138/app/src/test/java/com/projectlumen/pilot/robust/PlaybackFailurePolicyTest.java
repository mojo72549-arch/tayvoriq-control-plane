package com.projectlumen.pilot.robust;

import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

public final class PlaybackFailurePolicyTest {
    @Test public void http509RetriesOnceWithoutTransportFallback() {
        PlaybackFailurePolicy.Decision first = PlaybackFailurePolicy.decide(
                "ERROR_CODE_IO_BAD_HTTP_STATUS", 509, 0, false,
                "http://provider/movie/user/pass/12345.mp4");
        assertEquals("HTTP_509", first.code);
        assertTrue(first.automaticRetry);
        assertFalse(first.transportStreamFallback);
        assertTrue(first.message.contains("kein defektes Videoformat"));

        PlaybackFailurePolicy.Decision second = PlaybackFailurePolicy.decide(
                "ERROR_CODE_IO_BAD_HTTP_STATUS", 509, 1, false,
                "http://provider/movie/user/pass/12345.mp4");
        assertFalse(second.automaticRetry);
        assertFalse(second.transportStreamFallback);
        assertTrue(second.message.contains("weiterhin"));
    }

    @Test public void authorizationFailuresDoNotRetry() {
        PlaybackFailurePolicy.Decision decision = PlaybackFailurePolicy.decide(
                "ERROR_CODE_IO_BAD_HTTP_STATUS", 403, 0, false,
                "http://provider/movie/1.mp4");
        assertEquals("HTTP_403", decision.code);
        assertFalse(decision.automaticRetry);
        assertFalse(decision.transportStreamFallback);
    }

    @Test public void malformedLiveTransportStreamUsesOneFormatFallback() {
        PlaybackFailurePolicy.Decision decision = PlaybackFailurePolicy.decide(
                "ERROR_CODE_PARSING_CONTAINER_MALFORMED", -1, 0, false,
                "http://provider/live/user/pass/123.ts");
        assertTrue(decision.transportStreamFallback);
        assertFalse(decision.automaticRetry);

        PlaybackFailurePolicy.Decision forced = PlaybackFailurePolicy.decide(
                "ERROR_CODE_PARSING_CONTAINER_MALFORMED", -1, 0, true,
                "http://provider/live/user/pass/123.ts");
        assertFalse(forced.transportStreamFallback);
    }

    @Test public void server503UsesOneControlledRetry() {
        PlaybackFailurePolicy.Decision decision = PlaybackFailurePolicy.decide(
                "ERROR_CODE_IO_BAD_HTTP_STATUS", 503, 0, false,
                "http://provider/movie/1.mp4");
        assertTrue(decision.automaticRetry);
        assertEquals(2_500L, decision.retryDelayMs);
    }
}
