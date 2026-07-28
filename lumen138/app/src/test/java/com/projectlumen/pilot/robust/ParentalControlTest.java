package com.projectlumen.pilot.robust;

import org.junit.Test;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

public final class ParentalControlTest {
    @Test public void hidesExplicitAdultGroups() {
        assertTrue(ParentalControl.isAdultText("Film 1", "XXX Movies", "http://x/movie/1"));
        assertTrue(ParentalControl.isAdultText("Film 2", "Adults Only", "http://x/movie/2"));
        assertTrue(ParentalControl.isAdultText("Film 3", "Erotik 18+", "http://x/movie/3"));
        assertTrue(ParentalControl.isAdultText("Film 4", "Yetişkin", "http://x/movie/4"));
    }

    @Test public void hidesKnownAdultBrandsAndPaths() {
        assertTrue(ParentalControl.isAdultText("Brazzers TV", "Weitere", "http://x/live/1"));
        assertTrue(ParentalControl.isAdultText("Unbenannt", "Weitere", "http://x/adult/1.ts"));
        assertTrue(ParentalControl.isAdultText("Playboy", "Movies", "http://x/movie/2"));
    }

    @Test public void doesNotHideOrdinaryTitles() {
        assertFalse(ParentalControl.isAdultText("Sex and the City", "US Serien", "http://x/series/1"));
        assertFalse(ParentalControl.isAdultText("Hot Wheels", "Kinder", "http://x/movie/2"));
        assertFalse(ParentalControl.isAdultText("RTL", "Deutschland", "http://x/live/3.ts"));
        assertFalse(ParentalControl.isAdultText("Kanal D", "Türkiye", "http://x/live/4.ts"));
    }
}
