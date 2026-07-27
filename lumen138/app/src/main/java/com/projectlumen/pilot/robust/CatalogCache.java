package com.projectlumen.pilot.robust;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/** Compact, versioned catalog cache used for sub-second app restore. */
final class CatalogCache {
    private static final int MAGIC = 0x4C554D34; // LUM4
    private static final int VERSION = 1;
    private static final int MAX_ENTRIES = 100_000;
    private static final int MAX_STRING_BYTES = 4 * 1024 * 1024;
    private static final int BUFFER_BYTES = 1024 * 1024;

    private CatalogCache() { }

    static void write(File file, List<Channel> channels) throws Exception {
        if (file == null) throw new IllegalArgumentException("Cache-Zieldatei fehlt.");
        List<Channel> safe = channels == null ? Collections.emptyList() : channels;
        if (safe.size() > MAX_ENTRIES) throw new IllegalArgumentException("Zu viele Katalogeinträge.");
        File parent = file.getParentFile();
        if (parent != null && !parent.exists() && !parent.mkdirs()) {
            throw new IllegalStateException("Cache-Verzeichnis konnte nicht erstellt werden.");
        }

        try (FileOutputStream rawFile = new FileOutputStream(file);
             BufferedOutputStream buffered = new BufferedOutputStream(rawFile, BUFFER_BYTES);
             DataOutputStream output = new DataOutputStream(buffered)) {
            output.writeInt(MAGIC);
            output.writeInt(VERSION);
            output.writeInt(safe.size());
            for (Channel channel : safe) {
                writeString(output, channel.id);
                writeString(output, channel.name);
                writeString(output, channel.group);
                writeString(output, channel.url);
                output.writeByte(channel.type.ordinal());
            }
            output.flush();
            buffered.flush();
            rawFile.getFD().sync();
        }
    }

    static List<Channel> read(File file) throws Exception {
        if (file == null || !file.exists() || file.length() < 12) {
            throw new IllegalStateException("Katalogcache fehlt oder ist unvollständig.");
        }
        try (DataInputStream input = new DataInputStream(new BufferedInputStream(
                new FileInputStream(file), BUFFER_BYTES))) {
            int magic = input.readInt();
            int version = input.readInt();
            int count = input.readInt();
            if (magic != MAGIC) throw new IllegalStateException("Katalogcache hat eine ungültige Kennung.");
            if (version != VERSION) throw new IllegalStateException("Katalogcache-Version wird nicht unterstützt.");
            if (count < 0 || count > MAX_ENTRIES) {
                throw new IllegalStateException("Katalogcache enthält eine ungültige Eintragszahl.");
            }
            ArrayList<Channel> result = new ArrayList<>(count);
            Channel.Type[] types = Channel.Type.values();
            for (int index = 0; index < count; index++) {
                String id = readString(input);
                String name = readString(input);
                String group = readString(input);
                String url = readString(input);
                int typeIndex = input.readUnsignedByte();
                if (typeIndex >= types.length) throw new IllegalStateException("Ungültiger Medientyp im Cache.");
                result.add(new Channel(id, name, group, url, types[typeIndex]));
            }
            return Collections.unmodifiableList(result);
        } catch (EOFException incomplete) {
            throw new IllegalStateException("Katalogcache wurde unvollständig geschrieben.", incomplete);
        }
    }

    static boolean usable(File file) {
        return file != null && file.exists() && file.length() >= 12;
    }

    private static void writeString(DataOutputStream output, String value) throws Exception {
        byte[] bytes = (value == null ? "" : value).getBytes(StandardCharsets.UTF_8);
        if (bytes.length > MAX_STRING_BYTES) throw new IllegalArgumentException("Katalogtext ist ungewöhnlich groß.");
        output.writeInt(bytes.length);
        output.write(bytes);
    }

    private static String readString(DataInputStream input) throws Exception {
        int length = input.readInt();
        if (length < 0 || length > MAX_STRING_BYTES) {
            throw new IllegalStateException("Ungültige Textlänge im Katalogcache.");
        }
        byte[] bytes = new byte[length];
        input.readFully(bytes);
        return new String(bytes, StandardCharsets.UTF_8);
    }
}
