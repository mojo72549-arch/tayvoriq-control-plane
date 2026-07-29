package com.projectlumen.pilot.robust;

import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

public final class PlaybackFailurePolicyTest {
    @Test public void http509IsProviderLimitNotParsingFailure() {
        String details = "causeChain=ExoPlaybackException>InvalidResponseCodeException httpStatus=509";
        assertEquals(509, PlaybackFailurePolicy.httpStatus(details));
        assertTrue(PlaybackFailurePolicy.isHttpFailure("ERROR_CODE_IO_BAD_HTTP_STATUS", 509));
        assertTrue(PlaybackFailurePolicy.shouldAutoRetry(509, 0));
        assertFalse(PlaybackFailurePolicy.shouldAutoRetry(509, 1));
        assertEquals(5_000L, PlaybackFailurePolicy.retryDelayMs(509));
        assertEquals("HTTP_509_PROVIDER_LIMIT",
                PlaybackFailurePolicy.diagnosticCode("ERROR_CODE_IO_BAD_HTTP_STATUS", 509));
        String message = PlaybackFailurePolicy.message("ERROR_CODE_IO_BAD_HTTP_STATUS", details);
        assertTrue(message.contains("HTTP 509"));
        assertTrue(message.contains("Verbindungslimit"));
        assertFalse(message.contains("Medienformat"));
    }

    @Test public void parsingFailureRemainsAFormatFailureWithoutHttpStatus() {
        String name = "ERROR_CODE_PARSING_CONTAINER_MALFORMED";
        assertEquals(PlaybackFailurePolicy.NO_HTTP_STATUS,
                PlaybackFailurePolicy.httpStatus("causeChain=ParserException"));
        assertFalse(PlaybackFailurePolicy.isHttpFailure(name,
                PlaybackFailurePolicy.NO_HTTP_STATUS));
        assertTrue(PlaybackFailurePolicy.message(name, "causeChain=ParserException")
                .contains("Medienformat"));
    }

    @Test public void transientServerStatusesRetryOnlyOnce() {
        int[] statuses = {408, 425, 429, 500, 502, 503, 504, 509};
        for (int status : statuses) {
            assertTrue("status=" + status,
                    PlaybackFailurePolicy.shouldAutoRetry(status, 0));
            assertFalse("status=" + status,
                    PlaybackFailurePolicy.shouldAutoRetry(status, 1));
        }
        assertFalse(PlaybackFailurePolicy.shouldAutoRetry(401, 0));
        assertFalse(PlaybackFailurePolicy.shouldAutoRetry(404, 0));
    }
}
