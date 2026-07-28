package com.projectlumen.pilot.robust;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/** Process-local catalog handoff with precomputed family and protected scopes. */
final class CatalogSession {
    private static final int LANGUAGE_COUNT = MediaLanguage.Code.values().length;

    private static volatile List<Channel> raw = Collections.emptyList();
    private static volatile List<Channel> family = Collections.emptyList();
    private static volatile List<Channel> protectedCatalog = Collections.emptyList();
    private static volatile List<List<Channel>> familyBuckets = Collections.emptyList();
    private static volatile List<Channel> adultLive = Collections.emptyList();
    private static volatile List<Channel> adultMovies = Collections.emptyList();
    private static volatile List<Channel> adultSeries = Collections.emptyList();
    private static volatile int publishedPolicyRevision = -1;

    private CatalogSession() { }

    static synchronized void publish(List<Channel> source) {
        List<Channel> next = AdultContentPolicy.raw(source);
        int revision = AdultGroupPolicy.revision();
        if (next == raw && revision == publishedPolicyRevision) return;
        if (!next.isEmpty() && next.get(0).policyRevision != revision) {
            next = AdultGroupPolicy.reapply(next);
        }
        publishInternal(next, revision);
    }

    static synchronized void rebuildPolicies() {
        publishInternal(AdultGroupPolicy.reapply(raw), AdultGroupPolicy.revision());
    }

    private static void publishInternal(List<Channel> next, int revision) {
        List<Channel> source = next == null ? Collections.emptyList() : next;
        ArrayList<Channel> rawCopy = new ArrayList<>(source.size());
        ArrayList<Channel> safeCopy = new ArrayList<>(source.size());
        ArrayList<Channel> liveAdult = new ArrayList<>();
        ArrayList<Channel> movieAdult = new ArrayList<>();
        ArrayList<Channel> seriesAdult = new ArrayList<>();

        int bucketCount = Channel.Type.values().length * LANGUAGE_COUNT;
        ArrayList<ArrayList<Channel>> mutableBuckets = new ArrayList<>(bucketCount);
        for (int index = 0; index < bucketCount; index++) mutableBuckets.add(new ArrayList<>());

        for (Channel channel : source) {
            if (channel == null) continue;
            rawCopy.add(channel);
            if (channel.adult) {
                if (channel.type == Channel.Type.LIVE) liveAdult.add(channel);
                else if (channel.type == Channel.Type.SERIES) seriesAdult.add(channel);
                else movieAdult.add(channel);
                continue;
            }

            safeCopy.add(channel);
            mutableBuckets.get(index(channel.type, MediaLanguage.Code.ALL)).add(channel);
            MediaLanguage.Code code = MediaLanguage.detect(channel);
            if (code == MediaLanguage.Code.ALL) code = MediaLanguage.Code.OTHER;
            mutableBuckets.get(index(channel.type, code)).add(channel);
        }

        ArrayList<List<Channel>> immutableBuckets = new ArrayList<>(bucketCount);
        for (ArrayList<Channel> bucket : mutableBuckets) {
            immutableBuckets.add(Collections.unmodifiableList(bucket));
        }

        raw = Collections.unmodifiableList(rawCopy);
        family = Collections.unmodifiableList(safeCopy);
        protectedCatalog = AdultContentPolicy.protectClassified(raw, family);
        familyBuckets = Collections.unmodifiableList(immutableBuckets);
        adultLive = Collections.unmodifiableList(liveAdult);
        adultMovies = Collections.unmodifiableList(movieAdult);
        adultSeries = Collections.unmodifiableList(seriesAdult);
        publishedPolicyRevision = revision;
    }

    static List<Channel> raw() { return raw; }
    static List<Channel> family() { return family; }
    static List<Channel> protectedCatalog() { return protectedCatalog; }
    static List<Channel> adultLive() { return adultLive; }
    static List<Channel> adultMovies() { return adultMovies; }
    static List<Channel> adultSeries() { return adultSeries; }

    static boolean ready() { return !raw.isEmpty() && !familyBuckets.isEmpty(); }

    static List<Channel> family(Channel.Type type, MediaLanguage.Code language) {
        List<List<Channel>> buckets = familyBuckets;
        if (buckets.isEmpty() || type == null) return Collections.emptyList();
        MediaLanguage.Code code = language == null ? MediaLanguage.Code.ALL : language;
        int index = index(type, code);
        return index >= 0 && index < buckets.size() ? buckets.get(index) : Collections.emptyList();
    }

    private static int index(Channel.Type type, MediaLanguage.Code language) {
        return type.ordinal() * LANGUAGE_COUNT + language.ordinal();
    }
}