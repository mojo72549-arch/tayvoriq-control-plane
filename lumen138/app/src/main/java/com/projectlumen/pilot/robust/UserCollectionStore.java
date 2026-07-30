package com.projectlumen.pilot.robust;

import android.content.Context;
import android.content.SharedPreferences;

import java.util.LinkedHashSet;
import java.util.Set;

/** Lightweight local favorites and recently viewed store; no cloud or account dependency. */
final class UserCollectionStore {
    private static final String PREFS = "lumen_user_collections";
    private static final String FAVORITES = "favorites";
    private static final String RECENT = "recent";
    private static final int MAX_RECENT = 100;
    private static volatile UserCollectionStore active;

    private final SharedPreferences preferences;
    private final LinkedHashSet<String> favorites;
    private final LinkedHashSet<String> recent;

    private UserCollectionStore(Context context) {
        preferences = context.getApplicationContext().getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        favorites = new LinkedHashSet<>(preferences.getStringSet(FAVORITES, Set.of()));
        recent = decodeRecent(preferences.getString(RECENT, ""));
    }

    static UserCollectionStore init(Context context) {
        UserCollectionStore current = active;
        if (current != null) return current;
        synchronized (UserCollectionStore.class) {
            current = active;
            if (current == null) {
                current = new UserCollectionStore(context);
                active = current;
            }
            return current;
        }
    }

    static UserCollectionStore current() { return active; }

    synchronized boolean isFavorite(Channel channel) {
        return channel != null && favorites.contains(channel.id);
    }

    synchronized boolean isRecent(Channel channel) {
        return channel != null && recent.contains(channel.id);
    }

    synchronized boolean hasFavorites(Channel.Type type, Iterable<Channel> channels) {
        for (Channel channel : channels) {
            if (channel != null && channel.type == type && favorites.contains(channel.id)) return true;
        }
        return false;
    }

    synchronized boolean hasRecent(Channel.Type type, Iterable<Channel> channels) {
        for (Channel channel : channels) {
            if (channel != null && channel.type == type && recent.contains(channel.id)) return true;
        }
        return false;
    }

    synchronized boolean toggleFavorite(Channel channel) {
        if (channel == null || channel.id.isBlank()) return false;
        boolean nowFavorite;
        if (favorites.remove(channel.id)) nowFavorite = false;
        else {
            favorites.add(channel.id);
            nowFavorite = true;
        }
        preferences.edit().putStringSet(FAVORITES, new LinkedHashSet<>(favorites)).apply();
        return nowFavorite;
    }

    synchronized void markRecent(Channel channel) {
        if (channel == null || channel.id.isBlank()) return;
        recent.remove(channel.id);
        recent.add(channel.id);
        while (recent.size() > MAX_RECENT) recent.remove(recent.iterator().next());
        preferences.edit().putString(RECENT, encodeRecent(recent)).apply();
    }

    private static String encodeRecent(LinkedHashSet<String> values) {
        StringBuilder out = new StringBuilder();
        for (String value : values) {
            if (value == null || value.isBlank()) continue;
            if (out.length() > 0) out.append('\u001f');
            out.append(value.replace("\u001f", ""));
        }
        return out.toString();
    }

    private static LinkedHashSet<String> decodeRecent(String value) {
        LinkedHashSet<String> out = new LinkedHashSet<>();
        if (value == null || value.isBlank()) return out;
        for (String item : value.split("\u001f", -1)) if (!item.isBlank()) out.add(item);
        return out;
    }
}
