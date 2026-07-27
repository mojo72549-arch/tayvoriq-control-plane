package com.projectlumen.pilot.robust;

import android.content.ContentResolver;
import android.content.Context;
import android.content.SharedPreferences;
import android.net.Uri;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.KeyStore;
import java.util.Collections;
import java.util.List;
import javax.crypto.Cipher;
import javax.crypto.CipherInputStream;
import javax.crypto.CipherOutputStream;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

final class PlaylistRepository {
    interface Progress { void update(String stage, String detail); }
    static final int MAX_BYTES = 256 * 1024 * 1024;
    static final int MAX_ENTRIES = 100_000;
    private static final String KEY_ALIAS = "lumen_playlist_key_v1";
    private final Context context;
    private final File current;
    private final File backup;
    private final File temp;
    private final SharedPreferences prefs;

    PlaylistRepository(Context context) {
        this.context = context.getApplicationContext();
        File dir = new File(this.context.getFilesDir(), "catalog");
        if (!dir.exists()) dir.mkdirs();
        current = new File(dir, "active.m3u.enc");
        backup = new File(dir, "backup.m3u.enc");
        temp = new File(dir, "candidate.m3u.enc");
        prefs = this.context.getSharedPreferences("lumen_catalog_state", Context.MODE_PRIVATE);
    }

    List<Channel> restore(Progress progress) throws Exception {
        if (!current.exists()) return Collections.emptyList();
        progress.update("RESTORE-DECRYPT-START", "Gespeicherte Quelle wird entschlüsselt und zeilenweise gelesen.");
        try {
            List<Channel> channels = parseEncrypted(current);
            progress.update("CATALOG-READY", "entries=" + channels.size());
            return channels;
        } catch (Exception primary) {
            if (!backup.exists()) throw primary;
            progress.update("RESTORE-ROLLBACK", "Aktive Generation defekt; letzte funktionierende Generation wird geprüft.");
            List<Channel> channels = parseEncrypted(backup);
            copyFile(backup, current);
            return channels;
        }
    }

    List<Channel> importUrl(String name, String sourceUrl, Progress progress) throws Exception {
        URL url = new URL(sourceUrl);
        String protocol = url.getProtocol().toLowerCase();
        if (!protocol.equals("http") && !protocol.equals("https")) throw new IllegalArgumentException("Nur HTTP und HTTPS werden unterstützt.");
        HttpURLConnection connection = (HttpURLConnection) url.openConnection();
        connection.setConnectTimeout(20_000);
        connection.setReadTimeout(60_000);
        connection.setInstanceFollowRedirects(true);
        connection.setRequestProperty("User-Agent", "ProjectLumen/13.1.38");
        connection.setRequestProperty("Accept", "*/*");
        try {
            progress.update("IMPORT-CONNECT", "Verbindung wird aufgebaut.");
            int status = connection.getResponseCode();
            if (status < 200 || status >= 300) throw new IllegalStateException("Server antwortet mit HTTP " + status + ".");
            long declared = connection.getContentLengthLong();
            progress.update("IMPORT-DOWNLOAD", declared > 0 ? "Server meldet " + declared + " Bytes; tatsächlicher Empfang wird gemessen." : "Download läuft; Server nennt keine Gesamtgröße.");
            try (InputStream input = new BufferedInputStream(connection.getInputStream(), 64 * 1024)) {
                return importStream(name, input, progress);
            }
        } finally {
            connection.disconnect();
        }
    }

    List<Channel> importUri(String name, ContentResolver resolver, Uri uri, Progress progress) throws Exception {
        try (InputStream input = resolver.openInputStream(uri)) {
            if (input == null) throw new IllegalArgumentException("Datei konnte nicht geöffnet werden.");
            return importStream(name, new BufferedInputStream(input, 64 * 1024), progress);
        }
    }

    String sourceName() { return prefs.getString("source_name", "Noch keine Quelle"); }

    private List<Channel> importStream(String name, InputStream input, Progress progress) throws Exception {
        if (temp.exists()) temp.delete();
        long bytes = encryptToTemp(input, progress);
        progress.update("IMPORT-PARSE", "Download abgeschlossen; verschlüsselte Kandidatengeneration wird geprüft.");
        List<Channel> channels = parseEncrypted(temp);
        if (channels.isEmpty()) {
            temp.delete();
            throw new IllegalArgumentException("Die Playlist enthält keine unterstützten Stream-Einträge.");
        }
        commitCandidate();
        prefs.edit().putString("source_name", safeName(name)).putLong("source_bytes", bytes)
                .putInt("source_entries", channels.size()).apply();
        progress.update("IMPORT-DONE", "entries=" + channels.size() + " bytes=" + bytes);
        return channels;
    }

    private long encryptToTemp(InputStream input, Progress progress) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key());
        byte[] iv = cipher.getIV();
        long total = 0;
        long reported = 0;
        try (FileOutputStream file = new FileOutputStream(temp);
             BufferedOutputStream raw = new BufferedOutputStream(file, 64 * 1024)) {
            raw.write(iv.length);
            raw.write(iv);
            try (CipherOutputStream encrypted = new CipherOutputStream(raw, cipher)) {
                byte[] buffer = new byte[64 * 1024];
                int count;
                while ((count = input.read(buffer)) >= 0) {
                    total += count;
                    if (total > MAX_BYTES) throw new IllegalArgumentException("Playlist überschreitet das sichere Limit von 256 MB.");
                    encrypted.write(buffer, 0, count);
                    if (total - reported >= 1024 * 1024) {
                        reported = total;
                        progress.update("IMPORT-DOWNLOAD", "Empfangen und verschlüsselt: " + total + " Bytes.");
                    }
                }
            }
        } catch (Exception failure) {
            temp.delete();
            throw failure;
        }
        return total;
    }

    private List<Channel> parseEncrypted(File file) throws Exception {
        try (InputStream input = decrypt(file)) {
            return Collections.unmodifiableList(M3uParser.parse(input, MAX_ENTRIES));
        }
    }

    private InputStream decrypt(File file) throws Exception {
        FileInputStream raw = new FileInputStream(file);
        int ivLength = raw.read();
        if (ivLength < 12 || ivLength > 32) { raw.close(); throw new IllegalStateException("Verschlüsselte Bibliothek ist beschädigt."); }
        byte[] iv = new byte[ivLength];
        int offset = 0;
        while (offset < ivLength) {
            int count = raw.read(iv, offset, ivLength - offset);
            if (count < 0) break;
            offset += count;
        }
        if (offset != ivLength) { raw.close(); throw new IllegalStateException("Verschlüsselte Bibliothek ist unvollständig."); }
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, iv));
        return new CipherInputStream(new BufferedInputStream(raw, 64 * 1024), cipher);
    }

    private SecretKey key() throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        if (store.containsAlias(KEY_ALIAS)) return (SecretKey) store.getKey(KEY_ALIAS, null);
        KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
        generator.init(new KeyGenParameterSpec.Builder(KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256).build());
        return generator.generateKey();
    }

    private void commitCandidate() throws Exception {
        if (backup.exists() && !backup.delete()) throw new IllegalStateException("Alte Sicherung konnte nicht ersetzt werden.");
        if (current.exists() && !current.renameTo(backup)) throw new IllegalStateException("Letzte funktionierende Bibliothek konnte nicht gesichert werden.");
        if (!temp.renameTo(current)) {
            if (backup.exists()) backup.renameTo(current);
            throw new IllegalStateException("Neue Bibliothek konnte nicht atomar aktiviert werden.");
        }
    }

    private static void copyFile(File source, File target) throws Exception {
        try (InputStream in = new FileInputStream(source); FileOutputStream out = new FileOutputStream(target)) {
            byte[] buffer = new byte[64 * 1024];
            int count;
            while ((count = in.read(buffer)) >= 0) out.write(buffer, 0, count);
        }
    }

    private static String safeName(String value) {
        String result = value == null ? "" : value.trim();
        if (result.isBlank()) result = "Meine Quelle";
        return result.replaceAll("[\\r\\n\\t]", " ").replaceAll("\\s{2,}", " ");
    }
}
