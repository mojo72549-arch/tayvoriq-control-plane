package com.projectlumen.pilot.robust;

import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.FilterOutputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

import javax.crypto.Cipher;
import javax.crypto.CipherInputStream;
import javax.crypto.CipherOutputStream;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/**
 * Compact, versioned catalog cache used for sub-second app restore.
 *
 * Android production files are encrypted in full with AES-256-GCM using the
 * same non-exportable Keystore key as the encrypted playlist. Plain encoding is
 * retained only for host-JVM unit tests where AndroidKeyStore does not exist.
 */
final class CatalogCache {
    private static final int ENCRYPTED_MAGIC = 0x4C434531; // LCE1
    private static final int PAYLOAD_MAGIC = 0x4C554D34; // LUM4
    private static final int VERSION = 3;
    private static final int MAX_ENTRIES = 100_000;
    private static final int MAX_STRING_BYTES = 4 * 1024 * 1024;
    private static final int BUFFER_BYTES = 1024 * 1024;
    private static final String KEY_ALIAS = "lumen_playlist_key_v1";

    private CatalogCache() { }

    static void write(File file, List<Channel> channels) throws Exception {
        if (file == null) throw new IllegalArgumentException("Cache-Zieldatei fehlt.");
        List<Channel> raw = AdultContentPolicy.raw(channels);
        if (raw.size() > MAX_ENTRIES) throw new IllegalArgumentException("Zu viele Katalogeinträge.");
        File parent = file.getParentFile();
        if (parent != null && !parent.exists() && !parent.mkdirs()) {
            throw new IllegalStateException("Cache-Verzeichnis konnte nicht erstellt werden.");
        }

        try (FileOutputStream rawFile = new FileOutputStream(file);
             BufferedOutputStream buffered = new BufferedOutputStream(rawFile, BUFFER_BYTES)) {
            OutputStream payload = buffered;
            if (isAndroidRuntime()) {
                Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
                cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey());
                byte[] iv = cipher.getIV();
                DataOutputStream envelope = new DataOutputStream(buffered);
                envelope.writeInt(ENCRYPTED_MAGIC);
                envelope.writeByte(iv.length);
                envelope.write(iv);
                envelope.flush();
                payload = new CipherOutputStream(nonClosing(buffered), cipher);
            }

            try (DataOutputStream output = new DataOutputStream(payload)) {
                output.writeInt(PAYLOAD_MAGIC);
                output.writeInt(VERSION);
                output.writeInt(raw.size());
                for (Channel channel : raw) {
                    writeString(output, channel.id);
                    writeString(output, channel.name);
                    writeString(output, channel.group);
                    writeString(output, channel.url);
                    output.writeByte(channel.type.ordinal());
                }
                output.flush();
            }
            buffered.flush();
            if (isAndroidRuntime()) rawFile.getFD().sync();
        } catch (Exception failure) {
            if (file.exists()) file.delete();
            throw failure;
        }
    }

    static List<Channel> read(File file) throws Exception {
        if (file == null || !file.exists() || file.length() < 12) {
            throw new IllegalStateException("Katalogcache fehlt oder ist unvollständig.");
        }

        try (FileInputStream rawFile = new FileInputStream(file);
             BufferedInputStream buffered = new BufferedInputStream(rawFile, BUFFER_BYTES);
             DataInputStream envelope = new DataInputStream(buffered)) {
            int firstMagic = envelope.readInt();
            if (!isAndroidRuntime()) {
                return readPayload(envelope, firstMagic);
            }
            if (firstMagic != ENCRYPTED_MAGIC) {
                throw new IllegalStateException(
                        "Veralteter Klartext-Schnellindex wird sicher neu aufgebaut.");
            }
            int ivLength = envelope.readUnsignedByte();
            if (ivLength < 12 || ivLength > 32) {
                throw new IllegalStateException("Schnellindex besitzt eine ungültige Verschlüsselungskennung.");
            }
            byte[] iv = new byte[ivLength];
            envelope.readFully(iv);

            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, getOrCreateKey(), new GCMParameterSpec(128, iv));
            try (DataInputStream input = new DataInputStream(
                    new CipherInputStream(envelope, cipher))) {
                return readPayload(input, input.readInt());
            }
        } catch (EOFException incomplete) {
            throw new IllegalStateException("Katalogcache wurde unvollständig geschrieben.", incomplete);
        }
    }

    static boolean usable(File file) {
        return file != null && file.exists() && file.length() >= 12;
    }

    private static List<Channel> readPayload(DataInputStream input, int magic) throws Exception {
        int version = input.readInt();
        int count = input.readInt();
        if (magic != PAYLOAD_MAGIC) {
            throw new IllegalStateException("Katalogcache hat eine ungültige Kennung.");
        }
        if (version != VERSION) {
            throw new IllegalStateException("Katalogcache-Version wird nicht unterstützt.");
        }
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
            if (typeIndex >= types.length) {
                throw new IllegalStateException("Ungültiger Medientyp im Cache.");
            }
            result.add(new Channel(id, name, group, url, types[typeIndex]));
        }
        if (input.read() != -1) {
            throw new IllegalStateException("Katalogcache enthält unerwartete Zusatzdaten.");
        }
        return AdultContentPolicy.protect(result);
    }

    private static SecretKey getOrCreateKey() throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        if (store.containsAlias(KEY_ALIAS)) {
            return (SecretKey) store.getKey(KEY_ALIAS, null);
        }
        KeyGenerator generator = KeyGenerator.getInstance(
                KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
        generator.init(new KeyGenParameterSpec.Builder(KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build());
        return generator.generateKey();
    }

    private static boolean isAndroidRuntime() {
        String name = System.getProperty("java.vm.name", "").toLowerCase(Locale.ROOT);
        return name.contains("dalvik") || name.contains("art");
    }

    private static OutputStream nonClosing(OutputStream output) {
        return new FilterOutputStream(output) {
            @Override public void close() throws java.io.IOException { flush(); }
        };
    }

    private static void writeString(DataOutputStream output, String value) throws Exception {
        byte[] bytes = (value == null ? "" : value).getBytes(StandardCharsets.UTF_8);
        if (bytes.length > MAX_STRING_BYTES) {
            throw new IllegalArgumentException("Katalogtext ist ungewöhnlich groß.");
        }
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
