package com.projectlumen.pilot.robust;

import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

public final class ProviderLanguageTest {
    @Test public void detectsProviderLanguagesFromNamesAndCodes() {
        assertEquals("el", detect("GR | LIVE", "ERT 1"));
        assertEquals("el", detect("Greek Cinema", "Movie"));
        assertEquals("ar", detect("AR | NEWS", "Al Jazeera"));
        assertEquals("fr", detect("France - Films", "Film"));
        assertEquals("it", detect("Italia | TV", "RAI 1"));
        assertEquals("sq", detect("AL | Shqip", "Top Channel"));
    }

    @Test public void doesNotTurnGenresIntoLanguages() {
        assertNull(ProviderLanguage.detect(channel("Sports", "Football")));
        assertNull(ProviderLanguage.detect(channel("News", "World News")));
        assertNull(ProviderLanguage.detect(channel("Kids", "Cartoon")));
        assertNull(ProviderLanguage.detect(channel("VIP Sports", "Premium Match")));
        assertNull(ProviderLanguage.detect(channel("XXX", "Protected")));
    }

    @Test public void unknownProviderLanguagePrefixStaysSeparate() {
        ProviderLanguage.Facet facet = ProviderLanguage.detect(
                channel("Català | Live", "Canal Local"));
        assertTrue(facet != null);
        assertTrue(facet.id.startsWith("provider:"));
        assertEquals("Català", facet.label);
    }

    private static String detect(String group, String name) {
        ProviderLanguage.Facet facet = ProviderLanguage.detect(channel(group, name));
        return facet == null ? null : facet.id;
    }

    private static Channel channel(String group, String name) {
        return new Channel("id", name, group, "http://example/stream", Channel.Type.LIVE);
    }
}