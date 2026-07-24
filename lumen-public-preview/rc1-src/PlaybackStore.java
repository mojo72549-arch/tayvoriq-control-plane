package com.projectlumen.publicpreview;

import android.content.Context;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;

/** Per-profile encrypted playback history and continue-watching state. */
public final class PlaybackStore {
    private static final int MAGIC = 0x4C505342;
    private static final int VERSION = 1;
    private static final int MAX_ENTRIES = 500;
    private static final int MAX_FILE_BYTES = 2 * 1024 * 1024;
    private static final String KEY_ALIAS = "project_lumen_playback_state_v1";

    public static final class Entry {
        public final String key, title, group, mediaType;
        public final long positionMs, durationMs, updatedAtMs;
        public final boolean completed;
        Entry(String key, String title, String group, String mediaType, long positionMs,
              long durationMs, long updatedAtMs, boolean completed) {
            this.key = key; this.title = title; this.group = group; this.mediaType = mediaType;
            this.positionMs = Math.max(0, positionMs); this.durationMs = Math.max(0, durationMs);
            this.updatedAtMs = updatedAtMs; this.completed = completed;
        }
        public int progressPercent() {
            if (durationMs <= 0) return 0;
            return (int) Math.max(0, Math.min(100, positionMs * 100L / durationMs));
        }
        public boolean isContinueWatching() {
            return !completed && durationMs > 0 && positionMs >= 30_000L && positionMs < durationMs - 60_000L;
        }
    }

    private final Context context;
    public PlaybackStore(Context context) { this.context = context.getApplicationContext(); }

    public synchronized Entry getByUrl(String url) { return loadMap().get(keyForUrl(url)); }
    public synchronized List<Entry> recent(int limit) {
        List<Entry> values = new ArrayList<>(loadMap().values());
        values.sort(Comparator.comparingLong((Entry e) -> e.updatedAtMs).reversed());
        return values.size() > limit ? new ArrayList<>(values.subList(0, limit)) : values;
    }
    public synchronized List<Entry> continueWatching(int limit) {
        List<Entry> result = new ArrayList<>();
        for (Entry entry : recent(MAX_ENTRIES)) {
            if (entry.isContinueWatching()) result.add(entry);
            if (result.size() >= limit) break;
        }
        return result;
    }
    public synchronized void record(String url, String title, String group, String mediaType,
                                    long positionMs, long durationMs, boolean completed) {
        if (url == null || url.isBlank()) return;
        Map<String, Entry> map = loadMap();
        String key = keyForUrl(url);
        boolean finished = completed || (durationMs > 0 && positionMs >= Math.max(0, durationMs - 30_000L));
        map.put(key, new Entry(key, safe(title, 240), safe(group, 240), safe(mediaType, 32),
                finished ? 0 : Math.max(0, positionMs), Math.max(0, durationMs),
                System.currentTimeMillis(), finished));
        if (map.size() > MAX_ENTRIES) {
            List<Entry> ordered = new ArrayList<>(map.values());
            ordered.sort(Comparator.comparingLong(e -> e.updatedAtMs));
            for (int i = 0; i < map.size() - MAX_ENTRIES; i++) map.remove(ordered.get(i).key);
        }
        saveMap(map);
    }
    public synchronized void clear() { File file = file(); if (file.exists()) file.delete(); }

    public static String keyForUrl(String url) {
        String value = url == null ? "" : url.trim();
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8));
            StringBuilder out = new StringBuilder();
            for (byte item : digest) out.append(String.format(Locale.ROOT, "%02x", item & 0xff));
            return out.toString();
        } catch (Exception failure) { return Integer.toHexString(value.hashCode()); }
    }

    private Map<String, Entry> loadMap() {
        File file = file();
        if (!file.isFile()) return new LinkedHashMap<>();
        try {
            DataInputStream in = new DataInputStream(new ByteArrayInputStream(
                    SecureBlobStore.read(context, file, KEY_ALIAS, MAX_FILE_BYTES)));
            if (in.readInt() != MAGIC || in.readInt() != VERSION) return new LinkedHashMap<>();
            int count = in.readInt();
            if (count < 0 || count > MAX_ENTRIES) return new LinkedHashMap<>();
            Map<String, Entry> map = new LinkedHashMap<>();
            for (int i = 0; i < count; i++) {
                Entry e = new Entry(in.readUTF(), in.readUTF(), in.readUTF(), in.readUTF(),
                        in.readLong(), in.readLong(), in.readLong(), in.readBoolean());
                map.put(e.key, e);
            }
            return map;
        } catch (Exception ignored) { return new LinkedHashMap<>(); }
    }
    private void saveMap(Map<String, Entry> map) {
        try {
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            DataOutputStream out = new DataOutputStream(bytes);
            out.writeInt(MAGIC); out.writeInt(VERSION); out.writeInt(map.size());
            for (Entry e : map.values()) {
                out.writeUTF(e.key); out.writeUTF(safe(e.title, 240)); out.writeUTF(safe(e.group, 240));
                out.writeUTF(safe(e.mediaType, 32)); out.writeLong(e.positionMs); out.writeLong(e.durationMs);
                out.writeLong(e.updatedAtMs); out.writeBoolean(e.completed);
            }
            out.flush();
            SecureBlobStore.write(context, file(), KEY_ALIAS, bytes.toByteArray());
        } catch (IOException ignored) {}
    }
    private File file() {
        return new File(context.getFilesDir(), "playback-" + ProfileStore.activeId(context).replaceAll("[^A-Za-z0-9_-]", "_") + ".lumen");
    }
    private static String safe(String value, int max) {
        String cleaned = value == null ? "" : value.replaceAll("[\\p{Cntrl}]", " ").trim();
        return cleaned.length() > max ? cleaned.substring(0, max) : cleaned;
    }
}
