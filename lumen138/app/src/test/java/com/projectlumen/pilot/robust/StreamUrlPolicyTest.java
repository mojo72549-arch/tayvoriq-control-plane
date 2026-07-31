package com.projectlumen.pilot.robust;

import org.junit.Test;

import javax.net.ssl.SSLException;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

public final class StreamUrlPolicyTest {
    @Test public void extensionlessXtreamLiveIsOpenedAsMpegTsImmediately() {
        assertTrue(StreamUrlPolicy.shouldForceMpegTs(
                "http://provider.example:8080/live/user/pass/12345"));
        assertTrue(StreamUrlPolicy.shouldForceMpegTs(
                "http://provider.example:8080/live/user/pass/12345.ts"));
        assertFalse(StreamUrlPolicy.shouldForceMpegTs(
                "http://provider.example/live/user/pass/channel.m3u8"));
    }

    @Test public void tlsMismatchOnCustomPortFallsBackToHttp() {
        String result = StreamUrlPolicy.httpCompatibilityUrl(
                "https://provider.example:8080/live/u/p/123",
                new SSLException("Unable to parse TLS packet header"));
        assertEquals("http://provider.example:8080/live/u/p/123", result);
    }

    @Test public void standardHttpsAndUnrelatedErrorsNeverDowngrade() {
        assertNull(StreamUrlPolicy.httpCompatibilityUrl(
                "https://provider.example/live/u/p/123",
                new SSLException("Unable to parse TLS packet header")));
        assertNull(StreamUrlPolicy.httpCompatibilityUrl(
                "https://provider.example:8080/live/u/p/123",
                new IllegalStateException("HTTP 404")));
    }
}
