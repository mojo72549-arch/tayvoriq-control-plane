package com.projectlumen.pilot.robust;

import java.io.BufferedOutputStream;
import java.io.DataOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.nio.ByteBuffer;
import java.nio.BufferUnderflowException;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/** Fast, versioned catalog cache with persisted language and safety flags. */
final class CatalogCache {
    private static final int MAGIC = 0x4C554D34; // LUM4
    private static final int VERSION_LEGACY_LOGO = 2;
    private static final int VERSION_FAST_FLAGS = 3;
    private static final int MAX_ENTRIES = 100_000;
    private static final int MAX_STRING_BYTES = 4 * 1024 * 1024;
    private static final int BUFFER_BYTES = 4 * 1024 * 1024;
    private static final Object IO_LOCK = new Object();

    private static volatile MemorySnapshot memory;

    private CatalogCache() { }

    static void write(File file, List<Channel> channels) throws Exception {
        synchronized (IO_LOCK) {
            memory = null;
            List<Channel> raw = AdultContentPolicy.raw(
                    channels == null ? Collections.emptyList() : channels);
            writeInternal(file, raw);
            CatalogSession.publish(raw);
        }
    }

    static List<Channel> read(File file) throws Exception {
        synchronized (IO_LOCK) {
            validateFile(file);
            MemorySnapshot snapshot = memory;
            String path = canonicalPath(file);
            if (snapshot != null && snapshot.matches(path, file)) {
                CatalogSession.publish(AdultContentPolicy.raw(snapshot.channels));
                return snapshot.channels;
            }

            Parsed parsed = readMapped(file);
            if (parsed.version == VERSION_LEGACY_LOGO) {
                upgradeAtomically(file, parsed.raw);
            }

            List<Channel> protectedList = AdultContentPolicy.protectClassified(
                    parsed.raw, parsed.safe);
            CatalogSession.publish(parsed.raw);
            memory = new MemorySnapshot(path, file.length(), file.lastModified(), protectedList);
            return protectedList;
        }
    }

    static boolean usable(File file) {
        return file != null && file.exists() && file.length() >= 12;
    }

    private static Parsed readMapped(File file) throws Exception {
        try (FileInputStream input = new FileInputStream(file);
             FileChannel channel = input.getChannel()) {
            long size = channel.size();
            if (size < 12 || size > Integer.MAX_VALUE) {
                throw new IllegalStateException("Katalogcache hat eine ungültige Größe.");
            }
            ByteBuffer buffer = channel.map(FileChannel.MapMode.READ_ONLY, 0, size);
            int magic = buffer.getInt();
            int version = buffer.getInt();
            int count = buffer.getInt();
            if (magic != MAGIC) {
                throw new IllegalStateException("Katalogcache hat eine ungültige Kennung.");
            }
            if (version != VERSION_LEGACY_LOGO && version != VERSION_FAST_FLAGS) {
                throw new IllegalStateException(
                        "Schnellindex wird einmalig aus der verschlüsselten Playlist aufgebaut.");
            }
            if (count < 0 || count > MAX_ENTRIES) {
                throw new IllegalStateException("Katalogcache enthält eine ungültige Eintragszahl.");
            }

            ArrayList<Channel> raw = new ArrayList<>(count);
            ArrayList<Channel> safe = new ArrayList<>(count);
            Channel.Type[] types = Channel.Type.values();
            MediaLanguage.Code[] languages = MediaLanguage.Code.values();

            for (int index = 0; index < count; index++) {
                String id = readString(buffer);
                String name = readString(buffer);
                String group = readString(buffer);
                String url = readString(buffer);
                String logo = readString(buffer);
                int typeIndex = unsignedByte(buffer);
                if (typeIndex >= types.length) {
                    throw new IllegalStateException("Ungültiger Medientyp im Cache.");
                }

                Channel entry;
                if (version == VERSION_FAST_FLAGS) {
                    int languageIndex = unsignedByte(buffer);
                    byte adultClass = buffer.get();
                    if (languageIndex >= languages.length) {
                        throw new IllegalStateException("Ungültige Sprachkennung im Cache.");
                    }
                    if (adultClass < AdultContentPolicy.CLASS_SAFE
                            || adultClass > AdultContentPolicy.CLASS_ADULT_BRAND) {
                        throw new IllegalStateException("Ungültige Jugendschutzkennung im Cache.");
                    }
                    entry = new Channel(id, name, group, url, logo, types[typeIndex],
                            languages[languageIndex], adultClass);
                } else {
                    entry = new Channel(id, name, group, url, logo, types[typeIndex]);
                }
                raw.add(entry);
                if (!entry.adult) safe.add(entry);
            }
            return new Parsed(version, raw, safe);
        } catch (BufferUnderflowException incomplete) {
            throw new IllegalStateException("Katalogcache wurde unvollständig geschrieben.", incomplete);
        }
    }

    private static void writeInternal(File file, List<Channel> raw) throws Exception {
        if (file == null) throw new IllegalArgumentException("Cache-Zieldatei fehlt.");
        if (raw.size() > MAX_ENTRIES) throw new IllegalArgumentException("Zu viele Katalogeinträge.");
        File parent = file.getParentFile();
        if (parent != null && !parent.exists() && !parent.mkdirs()) {
            throw new IllegalStateException("Cache-Verzeichnis konnte nicht erstellt werden.");
        }

        try (FileOutputStream rawFile = new FileOutputStream(file);
             BufferedOutputStream buffered = new BufferedOutputStream(rawFile, BUFFER_BYTES);
             DataOutputStream output = new DataOutputStream(buffered)) {
            output.writeInt(MAGIC);
            output.writeInt(VERSION_FAST_FLAGS);
            output.writeInt(raw.size());
            for (Channel entry : raw) {
                writeString(output, entry.id);
                writeString(output, entry.name);
                writeString(output, entry.group);
                writeString(output, entry.url);
                writeString(output, entry.logo);
                output.writeByte(entry.type.ordinal());
                output.writeByte(entry.language.ordinal());
                output.writeByte(entry.adultClass);
            }
            output.flush();
            buffered.flush();
            rawFile.getFD().sync();
        }
    }

    private static void upgradeAtomically(File current, List<Channel> raw) {
        File parent = current.getParentFile();
        File upgraded = new File(parent, current.getName() + ".v3.tmp");
        File backup = new File(parent, current.getName() + ".v2.bak");
        try {
            if (upgraded.exists()) upgraded.delete();
            if (backup.exists()) backup.delete();
            writeInternal(upgraded, raw);
            if (!current.renameTo(backup)) {
                upgraded.delete();
                return;
            }
            if (!upgraded.renameTo(current)) {
                backup.renameTo(current);
                upgraded.delete();
                return;
            }
            backup.delete();
        } catch (Throwable ignored) {
            upgraded.delete();
            if (!current.exists() && backup.exists()) backup.renameTo(current);
        }
    }

    private static void validateFile(File file) {
        if (file == null || !file.exists() || file.length() < 12) {
            throw new IllegalStateException("Katalogcache fehlt oder ist unvollständig.");
        }
    }

    private static int unsignedByte(ByteBuffer buffer) {
        return buffer.get() & 0xFF;
    }

    private static void writeString(DataOutputStream output, String value) throws Exception {
        byte[] bytes = (value == null ? "" : value).getBytes(StandardCharsets.UTF_8);
        if (bytes.length > MAX_STRING_BYTES) {
            throw new IllegalArgumentException("Katalogtext ist ungewöhnlich groß.");
        }
        output.writeInt(bytes.length);
        output.write(bytes);
    }

    private static String readString(ByteBuffer buffer) {
        int length = buffer.getInt();
        if (length < 0 || length > MAX_STRING_BYTES || length > buffer.remaining()) {
            throw new IllegalStateException("Ungültige Textlänge im Katalogcache.");
        }
        if (length == 0) return "";
        byte[] bytes = new byte[length];
        buffer.get(bytes);
        return new String(bytes, StandardCharsets.UTF_8);
    }

    private static String canonicalPath(File file) {
        try { return file.getCanonicalPath(); }
        catch (Exception ignored) { return file.getAbsolutePath(); }
    }

    private static final class Parsed {
        final int version;
        final List<Channel> raw;
        final List<Channel> safe;

        Parsed(int version, List<Channel> raw, List<Channel> safe) {
            this.version = version;
            this.raw = raw;
            this.safe = safe;
        }
    }

    private static final class MemorySnapshot {
        final String path;
        final long length;
        final long modified;
        final List<Channel> channels;

        MemorySnapshot(String path, long length, long modified, List<Channel> channels) {
            this.path = path;
            this.length = length;
            this.modified = modified;
            this.channels = channels;
        }

        boolean matches(String wantedPath, File file) {
            return path.equals(wantedPath) && length == file.length()
                    && modified == file.lastModified();
        }
    }
}
