package com.projectlumen.pilot.robust;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotEquals;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public final class PinSecurityTest {
    @Test
    public void acceptsOnlyFourToEightDigits() {
        assertTrue(PinSecurity.validPin("1234"));
        assertTrue(PinSecurity.validPin("12345678"));
        assertFalse(PinSecurity.validPin("123"));
        assertFalse(PinSecurity.validPin("123456789"));
        assertFalse(PinSecurity.validPin("12a4"));
        assertFalse(PinSecurity.validPin(null));
    }

    @Test
    public void storesSaltedHashAndVerifiesConstantTimeComparisonPath() throws Exception {
        PinSecurity.Record first = PinSecurity.create("4826");
        PinSecurity.Record second = PinSecurity.create("4826");
        assertNotEquals(first.salt, second.salt);
        assertNotEquals(first.hash, second.hash);
        assertTrue(PinSecurity.verify("4826", first.salt, first.hash));
        assertFalse(PinSecurity.verify("1111", first.salt, first.hash));
    }
}
