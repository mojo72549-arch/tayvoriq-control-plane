package com.projectlumen.publicpreview;

import android.content.Context;
import java.io.*;
import java.util.*;

/** Encrypted handoff for a selected series; avoids Binder limits and plaintext URLs. */
public final class SeriesSelectionStore {
    private static final int MAGIC = 0x4C535253, VERSION = 1, MAX_ITEMS = 2000, MAX_BYTES = 8 * 1024 * 1024;
    private static final String KEY_ALIAS = "project_lumen_series_handoff_v1";

    public static final class Item {
        public final String name, group, url, logo, language;
        public Item(String name, String group, String url, String logo, String language) {
            this.name = safe(name, 400); this.group = safe(group, 400); this.url = safe(url, 4096);
            this.logo = safe(logo, 4096); this.language = safe(language, 80);
        }
    }
    public static final class Selection {
        public final String title;
        public final List<Item> items;
        Selection(String title, List<Item> items) {
            this.title = title; this.items = Collections.unmodifiableList(new ArrayList<>(items));
        }
    }
    private SeriesSelectionStore() {}

    public static String save(Context context, String title, List<Item> items) throws IOException {
        if (items == null || items.isEmpty()) throw new IOException("Keine Episoden gefunden.");
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(bytes);
        int count = Math.min(MAX_ITEMS, items.size());
        out.writeInt(MAGIC); out.writeInt(VERSION); out.writeUTF(safe(title, 400)); out.writeInt(count);
        for (int i = 0; i < count; i++) {
            Item item = items.get(i);
            out.writeUTF(item.name); out.writeUTF(item.group); out.writeUTF(item.url);
            out.writeUTF(item.logo); out.writeUTF(item.language);
        }
        out.flush();
        String token = UUID.randomUUID().toString().replace("-", "");
        SecureBlobStore.write(context, file(context, token), KEY_ALIAS, bytes.toByteArray());
        cleanup(context, token);
        return token;
    }

    public static Selection load(Context context, String token) throws IOException {
        DataInputStream in = new DataInputStream(new ByteArrayInputStream(
                SecureBlobStore.read(context, file(context, token), KEY_ALIAS, MAX_BYTES)));
        if (in.readInt() != MAGIC || in.readInt() != VERSION) throw new IOException("Serienauswahl ist ungültig.");
        String title = in.readUTF();
        int count = in.readInt();
        if (count < 1 || count > MAX_ITEMS) throw new IOException("Ungültige Episodenanzahl.");
        List<Item> items = new ArrayList<>();
        for (int i = 0; i < count; i++) items.add(new Item(in.readUTF(), in.readUTF(), in.readUTF(), in.readUTF(), in.readUTF()));
        return new Selection(title, items);
    }

    private static File file(Context context, String token) throws IOException {
        String safe = token == null ? "" : token.replaceAll("[^A-Za-z0-9]", "");
        if (safe.length() < 12) throw new IOException("Serienauswahl fehlt.");
        File folder = new File(context.getCacheDir(), "series-handoff");
        if (!folder.exists() && !folder.mkdirs()) throw new IOException("Seriencache konnte nicht erstellt werden.");
        return new File(folder, safe + ".lumen");
    }
    private static void cleanup(Context context, String keep) {
        File[] files = new File(context.getCacheDir(), "series-handoff").listFiles();
        if (files == null) return;
        long now = System.currentTimeMillis();
        for (File file : files) if (!file.getName().startsWith(keep) && now - file.lastModified() > 86_400_000L) file.delete();
    }
    private static String safe(String value, int max) {
        String cleaned = value == null ? "" : value.replaceAll("[\\p{Cntrl}]", " ").trim();
        return cleaned.length() > max ? cleaned.substring(0, max) : cleaned;
    }
}
