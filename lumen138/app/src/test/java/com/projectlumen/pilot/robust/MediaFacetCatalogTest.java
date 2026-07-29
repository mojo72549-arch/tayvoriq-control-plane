package com.projectlumen.pilot.robust;

import org.junit.Test;

import java.util.Arrays;
import java.util.List;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

public final class MediaFacetCatalogTest {
    @Test public void moviesExposeOnlyMovieCategoriesForSelectedLanguage() {
        List<Channel> source = Arrays.asList(
                channel("m1", "Action One", "DE | FILME ACTION", Channel.Type.MOVIE),
                channel("m2", "Comedy One", "DE | FILME KOMÖDIE", Channel.Type.MOVIE),
                channel("m3", "Greek Drama", "GR | MOVIES DRAMA", Channel.Type.MOVIE),
                channel("s1", "Crime Episode", "DE | SERIEN KRIMI", Channel.Type.SERIES),
                channel("l1", "Sport Live", "DE | LIVE SPORT", Channel.Type.LIVE));

        ProviderCatalog.Snapshot snapshot = ProviderCatalog.build(
                source, Channel.Type.MOVIE, "de", ProviderCatalog.ALL_GROUPS, "");

        assertEquals(2, snapshot.rows.size());
        assertEquals(2, snapshot.groups.size());
        assertTrue(snapshot.groups.contains("DE | FILME ACTION"));
        assertTrue(snapshot.groups.contains("DE | FILME KOMÖDIE"));
        assertFalse(snapshot.groups.contains("DE | SERIEN KRIMI"));
        assertFalse(snapshot.groups.contains("DE | LIVE SPORT"));
    }

    @Test public void seriesExposeOnlySeriesCategoriesForSelectedLanguage() {
        List<Channel> source = Arrays.asList(
                channel("s1", "Crime S01E01", "DE | SERIEN KRIMI", Channel.Type.SERIES),
                channel("s2", "Drama S01E01", "DE | SERIEN DRAMA", Channel.Type.SERIES),
                channel("s3", "Greek Show S01E01", "GR | SERIES", Channel.Type.SERIES),
                channel("m1", "Crime Movie", "DE | FILME KRIMI", Channel.Type.MOVIE));

        ProviderCatalog.Snapshot snapshot = ProviderCatalog.build(
                source, Channel.Type.SERIES, "de", ProviderCatalog.ALL_GROUPS, "");

        assertEquals(2, snapshot.rows.size());
        assertEquals(2, snapshot.groups.size());
        assertTrue(snapshot.groups.contains("DE | SERIEN KRIMI"));
        assertTrue(snapshot.groups.contains("DE | SERIEN DRAMA"));
        assertFalse(snapshot.groups.contains("DE | FILME KRIMI"));
    }

    @Test public void exactMovieCategorySelectionDoesNotLeakOtherCategories() {
        List<Channel> source = Arrays.asList(
                channel("m1", "Action One", "DE | FILME ACTION", Channel.Type.MOVIE),
                channel("m2", "Action Two", "DE | FILME ACTION", Channel.Type.MOVIE),
                channel("m3", "Comedy One", "DE | FILME KOMÖDIE", Channel.Type.MOVIE));

        ProviderCatalog.Snapshot snapshot = ProviderCatalog.build(
                source, Channel.Type.MOVIE, "de", "DE | FILME ACTION", "");

        assertEquals(2, snapshot.rows.size());
        assertTrue(snapshot.rows.stream().allMatch(row ->
                "DE | FILME ACTION".equals(row.group)));
    }

    @Test public void blankProviderGroupUsesClearUncategorizedLabel() {
        Channel uncategorized = new Channel(
                "x", "Unsorted Movie", "Weitere", "http://example/x", Channel.Type.MOVIE);

        ProviderCatalog.Snapshot snapshot = ProviderCatalog.build(
                Arrays.asList(uncategorized), Channel.Type.MOVIE,
                ProviderLanguage.ALL, ProviderCatalog.ALL_GROUPS, "");

        assertEquals(1, snapshot.groups.size());
        assertEquals("Ohne Kategorie", snapshot.groups.get(0));
    }

    private static Channel channel(String id, String name, String group, Channel.Type type) {
        return new Channel(id, name, group, "http://example/" + id, type);
    }
}
