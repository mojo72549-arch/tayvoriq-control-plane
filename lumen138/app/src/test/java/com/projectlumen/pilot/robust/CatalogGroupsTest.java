package com.projectlumen.pilot.robust;

import org.junit.Test;

import java.util.Arrays;
import java.util.List;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

public final class CatalogGroupsTest {
    @Test public void allLanguageShowsEveryPlaylistGroup() {
        List<Channel> channels = Arrays.asList(
                channel("RTL", "DE | Fernsehen"),
                channel("TRT 1", "TR | Ulusal"),
                channel("BBC One", "UK | Entertainment"),
                channel("Al Jazeera", "AR | News"));

        CatalogGroups.Snapshot snapshot = CatalogGroups.build(
                channels, Channel.Type.LIVE, MediaLanguage.Code.ALL, "", "");

        assertEquals(4, snapshot.rows.size());
        assertEquals(4, snapshot.groups.size());
        assertTrue(snapshot.groups.contains("DE | Fernsehen"));
        assertTrue(snapshot.groups.contains("TR | Ulusal"));
        assertTrue(snapshot.groups.contains("UK | Entertainment"));
        assertTrue(snapshot.groups.contains("AR | News"));
    }

    @Test public void otherLanguageShowsNonGermanAndNonTurkishGroups() {
        List<Channel> channels = Arrays.asList(
                channel("RTL", "DE | Fernsehen"),
                channel("TRT 1", "TR | Ulusal"),
                channel("BBC One", "UK | Entertainment"),
                channel("Al Jazeera", "AR | News"));

        CatalogGroups.Snapshot snapshot = CatalogGroups.build(
                channels, Channel.Type.LIVE, MediaLanguage.Code.OTHER, "", "");

        assertEquals(2, snapshot.rows.size());
        assertEquals(2, snapshot.groups.size());
        assertTrue(snapshot.groups.contains("UK | Entertainment"));
        assertTrue(snapshot.groups.contains("AR | News"));
        assertFalse(snapshot.groups.contains("DE | Fernsehen"));
        assertFalse(snapshot.groups.contains("TR | Ulusal"));
    }

    @Test public void selectedGroupFiltersExactlyAndCaseInsensitively() {
        List<Channel> channels = Arrays.asList(
                channel("BBC One", "UK | Entertainment"),
                channel("BBC Two", "UK | Entertainment"),
                channel("Sky News", "UK | News"));

        CatalogGroups.Snapshot snapshot = CatalogGroups.build(
                channels, Channel.Type.LIVE, MediaLanguage.Code.ALL,
                "uk | entertainment", "");

        assertEquals("UK | Entertainment", snapshot.selectedGroup);
        assertEquals(2, snapshot.rows.size());
    }

    @Test public void unavailablePersistedGroupFallsBackToAllGroups() {
        List<Channel> channels = Arrays.asList(
                channel("BBC One", "UK | Entertainment"),
                channel("Sky News", "UK | News"));

        CatalogGroups.Snapshot snapshot = CatalogGroups.build(
                channels, Channel.Type.LIVE, MediaLanguage.Code.ALL,
                "Nicht mehr vorhanden", "");

        assertEquals(CatalogGroups.ALL, snapshot.selectedGroup);
        assertEquals(2, snapshot.rows.size());
    }

    @Test public void lockedAdultProjectionDoesNotLeakRestrictedGroupName() {
        ParentalControl.lock("test");
        List<Channel> raw = Arrays.asList(
                channel("RTL", "DE | Fernsehen"),
                new Channel("adult", "Restricted VOD", "XXX Movies",
                        "http://example/adult", Channel.Type.LIVE));
        List<Channel> protectedCatalog = AdultContentPolicy.protect(raw);

        CatalogGroups.Snapshot snapshot = CatalogGroups.build(
                protectedCatalog, Channel.Type.LIVE, MediaLanguage.Code.ALL, "", "");

        assertEquals(1, snapshot.rows.size());
        assertEquals(1, snapshot.groups.size());
        assertFalse(snapshot.groups.contains("XXX Movies"));
        assertEquals(2, AdultContentPolicy.raw(protectedCatalog).size());
    }

    private static Channel channel(String name, String group) {
        return new Channel(name, name, group, "http://example/" + name,
                Channel.Type.LIVE);
    }
}
