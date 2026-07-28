package com.projectlumen.pilot.robust;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public final class AdultContentClassifierTest {
    @Test
    public void detectsExplicitAdultLabelsAcrossLanguages() {
        assertTrue(AdultContentClassifier.isAdult("XXX Cinema", "Movies", "http://x/live/1.ts"));
        assertTrue(AdultContentClassifier.isAdult("Film 1", "Adult Movies 18+", "http://x/movie/1.ts"));
        assertTrue(AdultContentClassifier.isAdult("Erotik Film", "Deutsch", "http://x/movie/2.ts"));
        assertTrue(AdultContentClassifier.isAdult("Yetişkin", "Türkçe", "http://x/movie/3.ts"));
        assertTrue(AdultContentClassifier.isAdult("Film", "Movies", "http://x/adult/4.ts"));
    }

    @Test
    public void avoidsCommonFalsePositives() {
        assertFalse(AdultContentClassifier.isAdult("Adult Swim", "US Entertainment", "http://x/live/1.ts"));
        assertFalse(AdultContentClassifier.isAdult("Essex County", "Series", "http://x/series/2.ts"));
        assertFalse(AdultContentClassifier.isAdult("Hot Bird News", "Satellite", "http://x/live/3.ts"));
        assertFalse(AdultContentClassifier.isAdult("Kanal D", "Türkiye", "http://x/live/4.ts"));
    }

    @Test
    public void channelOverloadUsesNameGroupAndUrl() {
        Channel protectedChannel = new Channel("1", "Movie", "XXX 18+",
                "http://x/movie/1.ts", Channel.Type.MOVIE);
        Channel normalChannel = new Channel("2", "RTL", "Deutsch",
                "http://x/live/2.ts", Channel.Type.LIVE);
        assertTrue(AdultContentClassifier.isAdult(protectedChannel));
        assertFalse(AdultContentClassifier.isAdult(normalChannel));
    }
}
