package com.projectlumen.pilot.robust;

import org.junit.After;
import org.junit.Before;
import org.junit.Test;

import java.util.Arrays;
import java.util.List;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

public final class ProviderCatalogTest {
    @Before public void enableProtectionForProviderTests() {
        ParentalFeature.setEnabledForTests(true);
    }

    @After public void clearProtectionOverride() {
        ParentalFeature.setEnabledForTests(null);
    }

    @Test public void exposesOnlyLanguagesActuallyProvidedInPlaylistOrder() {
        List<Channel> source = Arrays.asList(
                channel("1", "ERT 1", "GR | LIVE", Channel.Type.LIVE),
                channel("2", "Al Jazeera", "AR | NEWS", Channel.Type.LIVE),
                channel("3", "BBC One", "UK | LIVE", Channel.Type.LIVE));

        ProviderCatalog.Snapshot snapshot = ProviderCatalog.build(
                source, Channel.Type.LIVE, ProviderLanguage.ALL,
                ProviderCatalog.ALL_GROUPS, "");

        assertEquals(3, snapshot.languages.size());
        assertEquals("el", snapshot.languages.get(0).id);
        assertEquals("ar", snapshot.languages.get(1).id);
        assertEquals("en", snapshot.languages.get(2).id);
        assertEquals("el", snapshot.selectedLanguage);
        assertFalse(hasLanguage(snapshot, ProviderLanguage.ALL));
        assertFalse(hasLanguage(snapshot, "tr"));
        assertFalse(hasLanguage(snapshot, "de"));
    }

    @Test public void selectingGreekReturnsOnlyGreekRowsAndGroups() {
        List<Channel> source = Arrays.asList(
                channel("1", "ERT 1", "GR | LIVE", Channel.Type.LIVE),
                channel("2", "Mega", "Greek Entertainment", Channel.Type.LIVE),
                channel("3", "BBC One", "UK | LIVE", Channel.Type.LIVE));

        ProviderCatalog.Snapshot snapshot = ProviderCatalog.build(
                source, Channel.Type.LIVE, "el", ProviderCatalog.ALL_GROUPS, "");

        assertEquals("el", snapshot.selectedLanguage);
        assertEquals(2, snapshot.rows.size());
        assertEquals(2, snapshot.groups.size());
        assertTrue(snapshot.rows.stream().allMatch(channel ->
                "el".equals(ProviderLanguage.detect(channel).id)));
    }

    @Test public void unavailablePersistedLanguageFallsBackToFirstActualLanguage() {
        List<Channel> source = Arrays.asList(
                channel("1", "ERT 1", "GR | LIVE", Channel.Type.LIVE),
                channel("2", "BBC One", "UK | LIVE", Channel.Type.LIVE));

        ProviderCatalog.Snapshot snapshot = ProviderCatalog.build(
                source, Channel.Type.LIVE, "tr", ProviderCatalog.ALL_GROUPS, "");

        assertEquals("el", snapshot.selectedLanguage);
        assertEquals(1, snapshot.rows.size());
        assertEquals("ERT 1", snapshot.rows.get(0).name);
    }

    @Test public void adultOnlyLanguageDoesNotLeakWhileLocked() {
        ParentalControl.lock("test");
        List<Channel> protectedSource = AdultContentPolicy.protect(Arrays.asList(
                channel("1", "ERT 1", "GR | LIVE", Channel.Type.LIVE),
                channel("2", "Protected", "AR | XXX", Channel.Type.LIVE)));

        ProviderCatalog.Snapshot snapshot = ProviderCatalog.build(
                protectedSource, Channel.Type.LIVE, ProviderLanguage.ALL,
                ProviderCatalog.ALL_GROUPS, "");

        assertTrue(hasLanguage(snapshot, "el"));
        assertFalse(hasLanguage(snapshot, "ar"));
        assertEquals(1, snapshot.rows.size());
    }

    @Test public void groupFilteringRemainsExactInsideLanguage() {
        List<Channel> source = Arrays.asList(
                channel("1", "ERT 1", "GR | NEWS", Channel.Type.LIVE),
                channel("2", "Mega", "GR | ENTERTAINMENT", Channel.Type.LIVE),
                channel("3", "BBC One", "UK | NEWS", Channel.Type.LIVE));

        ProviderCatalog.Snapshot snapshot = ProviderCatalog.build(
                source, Channel.Type.LIVE, "el", "GR | NEWS", "");

        assertEquals(1, snapshot.rows.size());
        assertEquals("ERT 1", snapshot.rows.get(0).name);
        assertEquals("News", snapshot.selectedGroup);
    }

    @Test public void hidesSoleProviderRootBelowLanguageFacet() {
        List<Channel> source = Arrays.asList(
                channel("1", "TRT World HD", "TRT", Channel.Type.LIVE),
                channel("2", "Kanal D", "TRT", Channel.Type.LIVE),
                channel("3", "Show TV", "TRT", Channel.Type.LIVE));

        ProviderCatalog.Snapshot snapshot = ProviderCatalog.build(
                source, Channel.Type.LIVE, "tr", ProviderCatalog.ALL_GROUPS, "");

        assertEquals("tr", snapshot.selectedLanguage);
        assertEquals(3, snapshot.rows.size());
        assertTrue(snapshot.groups.isEmpty());
    }

    @Test public void stripsLanguagePrefixAndKeepsMeaningfulCategories() {
        List<Channel> source = Arrays.asList(
                channel("1", "TRT Haber", "TR | NEWS", Channel.Type.LIVE),
                channel("2", "A Spor", "TR | SPORTS", Channel.Type.LIVE),
                channel("3", "Kanal D", "TR | ENTERTAINMENT", Channel.Type.LIVE));

        ProviderCatalog.Snapshot snapshot = ProviderCatalog.build(
                source, Channel.Type.LIVE, "tr", ProviderCatalog.ALL_GROUPS, "");

        assertEquals(Arrays.asList("News", "Sports", "Entertainment"), snapshot.groups);
    }

    private static boolean hasLanguage(ProviderCatalog.Snapshot snapshot, String id) {
        return snapshot.languages.stream().anyMatch(facet -> id.equals(facet.id));
    }

    private static Channel channel(String id, String name, String group, Channel.Type type) {
        return new Channel(id, name, group, "http://example/" + id, type);
    }
}
