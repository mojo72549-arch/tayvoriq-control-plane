package com.projectlumen.pilot.robust;

import android.content.Context;
import android.content.SharedPreferences;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/** Parent-managed exact group overrides. Rules remain local to the device. */
final class AdultGroupPolicy {
    static final byte RULE_AUTO = -2;

    private static final String PREFS = "lumen_adult_group_policy";
    private static final String KEY_EXPLICIT = "explicit_groups";
    private static final String KEY_AGE18 = "age18_groups";
    private static final String KEY_SAFE = "safe_groups";
    private static final String KEY_REVISION = "revision";

    private static volatile SharedPreferences preferences;
    private static volatile Set<String> explicit = Collections.emptySet();
    private static volatile Set<String> age18 = Collections.emptySet();
    private static volatile Set<String> safe = Collections.emptySet();
    private static volatile int revision;

    private AdultGroupPolicy() { }

    static synchronized void initialize(Context context) {
        if (preferences != null || context == null) return;
        preferences = context.getApplicationContext().getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        reloadLocked();
    }

    static int revision() { return revision; }

    static byte resolve(String group, byte automaticClass) {
        String key = normalize(group);
        if (key.isEmpty()) return automaticClass;
        if (safe.contains(key)) return AdultContentPolicy.CLASS_SAFE;
        if (explicit.contains(key)) return AdultContentPolicy.CLASS_EXPLICIT;
        if (age18.contains(key)) return AdultContentPolicy.CLASS_AGE_18;
        return automaticClass;
    }

    static byte manualRule(String group) {
        String key = normalize(group);
        if (safe.contains(key)) return AdultContentPolicy.CLASS_SAFE;
        if (explicit.contains(key)) return AdultContentPolicy.CLASS_EXPLICIT;
        if (age18.contains(key)) return AdultContentPolicy.CLASS_AGE_18;
        return RULE_AUTO;
    }

    static synchronized void setRule(String group, byte rule) {
        ensureInitialized();
        String key = normalize(group);
        if (key.isEmpty()) return;

        HashSet<String> nextExplicit = new HashSet<>(explicit);
        HashSet<String> nextAge18 = new HashSet<>(age18);
        HashSet<String> nextSafe = new HashSet<>(safe);
        nextExplicit.remove(key);
        nextAge18.remove(key);
        nextSafe.remove(key);

        if (rule == AdultContentPolicy.CLASS_EXPLICIT || rule == AdultContentPolicy.CLASS_ADULT_BRAND) {
            nextExplicit.add(key);
        } else if (rule == AdultContentPolicy.CLASS_AGE_18) {
            nextAge18.add(key);
        } else if (rule == AdultContentPolicy.CLASS_SAFE) {
            nextSafe.add(key);
        }

        int nextRevision = revision + 1;
        preferences.edit()
                .putStringSet(KEY_EXPLICIT, nextExplicit)
                .putStringSet(KEY_AGE18, nextAge18)
                .putStringSet(KEY_SAFE, nextSafe)
                .putInt(KEY_REVISION, nextRevision)
                .apply();
        explicit = Collections.unmodifiableSet(nextExplicit);
        age18 = Collections.unmodifiableSet(nextAge18);
        safe = Collections.unmodifiableSet(nextSafe);
        revision = nextRevision;
    }

    static List<Channel> reapply(List<Channel> source) {
        List<Channel> raw = AdultContentPolicy.raw(source);
        if (raw.isEmpty()) return Collections.emptyList();
        ArrayList<Channel> result = new ArrayList<>(raw.size());
        int wantedRevision = revision;
        for (Channel channel : raw) {
            if (channel == null) continue;
            if (channel.policyRevision == wantedRevision) {
                result.add(channel);
            } else {
                result.add(new Channel(channel.id, channel.name, channel.group, channel.url,
                        channel.logo, channel.type, channel.language,
                        channel.automaticAdultClass));
            }
        }
        return Collections.unmodifiableList(result);
    }

    static String normalize(String value) {
        if (value == null) return "";
        String trimmed = value.trim().toLowerCase(Locale.ROOT);
        if (trimmed.isEmpty()) return "";
        StringBuilder out = new StringBuilder(trimmed.length());
        boolean space = false;
        for (int index = 0; index < trimmed.length(); index++) {
            char c = trimmed.charAt(index);
            if (Character.isWhitespace(c)) {
                space = out.length() > 0;
            } else {
                if (space) out.append(' ');
                out.append(c);
                space = false;
            }
        }
        return out.toString();
    }

    private static void ensureInitialized() {
        if (preferences == null) {
            throw new IllegalStateException("Jugendschutz-Gruppenverwaltung ist noch nicht initialisiert.");
        }
    }

    private static void reloadLocked() {
        explicit = immutableCopy(preferences.getStringSet(KEY_EXPLICIT, Collections.emptySet()));
        age18 = immutableCopy(preferences.getStringSet(KEY_AGE18, Collections.emptySet()));
        safe = immutableCopy(preferences.getStringSet(KEY_SAFE, Collections.emptySet()));
        revision = preferences.getInt(KEY_REVISION, 0);
    }

    private static Set<String> immutableCopy(Set<String> source) {
        return Collections.unmodifiableSet(new HashSet<>(
                source == null ? Collections.emptySet() : source));
    }
}