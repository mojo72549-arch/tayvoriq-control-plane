package com.projectlumen.pilot.robust;

import android.content.ContentResolver;
import android.content.Context;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.SystemClock;
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
    private static final long PARSE_TIMEOUT_MS = 180_000L;
    private static final long DOWNLOAD_REPORT_BYTES = 4L * 1024L * 1024L;
    private static final long DOWNLOAD_REPORT_INTERVAL_MS = 1_500L;
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
        if (temp.exists() && temp.length() > 32) {
            progress.update("RESTORE-CANDIDATE-FOUND",
                    "Ein vollständig geladener, noch nicht aktivierter Import wurde gefunden. Prüfung wird fortgesetzt.");
            try {
                List<Channel> recovered = parseEncrypted(temp, progress, "RESTORE-CANDIDATE-PARSE");
                if (recovered.isEmpty()) throw new IllegalArgumentException(
                        "Die wiederhergestellte Kandidatendatei enthält keine unterstützten Einträge.");
                commitCandidate();
                String pendingName = prefs.getString("pending_source_name", "Wiederhergestellte Playlist");
                long pendingBytes = prefs.getLong("pending_source_bytes", 0L);
                saveActiveMetadata(pendingName, pendingBytes, recovered.size());
                clearPendingMetadata();
                progress.update("RESTORE-CANDIDATE-COMMIT",
                        "Unterbrochener Import erfolgreich fortgesetzt: entries=" + recovered.size());
                return recovered;
            } catch (Exception candidateFailure) {
                progress.update("RESTORE-CANDIDATE-ERROR",
                        "Kandidatenprüfung fehlgeschlagen: " + safeMessage(candidateFailure));
                if (!current.exists()) throw candidateFailure;
            }
        }

        if (!current.exists()) return Collections.emptyList();
        progress.update("RESTORE-DECRYPT-START",
                "Gespeicherte Quelle wird entschlüsselt und zeilenweise gelesen.");
        try {
            List<Channel> channels = parseEncrypted(current, progress, "RESTORE-PARSE-PROGRESS");
            progress.update("CATALOG-READY", "entries=" + channels.size());
            return channels;
        } catch (Exception primary) {
            if (!backup.exists()) throw primary;
            progress.update("RESTORE-ROLLBACK",
                    "Aktive Generation defekt; letzte funktionierende Generation wird geprüft.");
            List<Channel> channels = parseEncrypted(backup, progress, "RESTORE-BACKUP-PROGRESS");
            copyFile(backup, current);
            return channels;
        }
    }

    List<Channel> importUrl(String name, String sourceUrl, Progress progress) throws Exception {
        URL url = new URL(sourceUrl);
        String protocol = url.getProtocol().toLowerCase();
        if (!protocol.equals("http") && !protocol.equals("https")) {
            throw new IllegalArgumentException("Nur HTTP und HTTPS werden unterstützt.");
        }

        rememberPendingName(name);
        HttpURLConnection connection = (HttpURLConnection) url.openConnection();
        connection.setConnectTimeout(20_000);
        connection.setReadTimeout(60_000);
        connection.setInstanceFollowRedirects(true);
        connection.setRequestProperty("User-Agent", "ProjectLumen/13.1.39");
        connection.setRequestProperty("Accept", "*/*");
        try {
            progress.update("IMPORT-CONNECT", "Verbindung wird aufgebaut.");
            int status = connection.getResponseCode();
            if (status < 200 || status >= 300) {
                throw new IllegalStateException("Server antwortet mit HTTP " + status + ".");
            }
            long declared = connection.getContentLengthLong();
            progress.update("IMPORT-DOWNLOAD", declared > 0
                    ? "Server meldet " + declared + " Bytes; tatsächlicher Empfang wird gemessen."
                    : "Download läuft; Server nennt keine Gesamtgröße.");
            try (InputStream input = new BufferedInputStream(connection.getInputStream(), 256 * 1024)) {
                return importStream(name, input, progress);
            }
        } finally {
            connection.disconnect();
        }
    }

    List<Channel> importUri(String name, ContentResolver resolver, Uri uri, Progress progress) throws Exception {
        rememberPendingName(name);
        try (InputStream input = resolver.openInputStream(uri)) {
            if (input == null) throw new IllegalArgumentException("Datei konnte nicht geöffnet werden.");
            return importStream(name, new BufferedInputStream(input, 256 * 1024), progress);
        }
    }

    String sourceName() { return prefs.getString("source_name", "Noch keine Quelle"); }
    boolean hasRecoverableCandidate() { return temp.exists() && temp.length() > 32; }

    private List<Channel> importStream(String name, InputStream input, Progress progress) throws Exception {
        if (temp.exists() && !temp.delete()) {
            throw new IllegalStateException("Alte Kandidatendatei konnte nicht ersetzt werden.");
        }

        long bytes;
        try {
            bytes = encryptToTemp(input, progress);
            prefs.edit().putLong("pending_source_bytes", bytes).apply();
        } catch (Exception downloadFailure) {
            temp.delete();
            clearPendingMetadata();
            throw downloadFailure;
        }

        progress.update("IMPORT-PARSE",
                "Download abgeschlossen; schnelle zeilenweise Kandidatenprüfung startet.");

        List<Channel> channels;
        try {
            channels = parseEncrypted(temp, progress, "IMPORT-PARSE-PROGRESS");
        } catch (Exception parseFailure) {
            progress.update("IMPORT-PAUSED",
                    "Kandidatenprüfung unterbrochen. Die verschlüsselte Datei bleibt für die Fortsetzung beim nächsten Start erhalten.");
            throw parseFailure;
        }

        if (channels.isEmpty()) {
            temp.delete();
            clearPendingMetadata();
            throw new IllegalArgumentException("Die Playlist enthält keine unterstützten Stream-Einträge.");
        }

        commitCandidate();
        saveActiveMetadata(name, bytes, channels.size());
        clearPendingMetadata();
        progress.update("IMPORT-DONE", "entries=" + channels.size() + " bytes=" + bytes);
        return channels;
    }

    private long encryptToTemp(InputStream input, Progress progress) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key());
        byte[] iv = cipher.getIV();
        long total = 0;
        long reportedBytes = 0;
        long lastReportAt = SystemClock.elapsedRealtime();

        try (FileOutputStream file = new FileOutputStream(temp);
             BufferedOutputStream raw = new BufferedOutputStream(file, 256 * 1024)) {
            raw.write(iv.length);
            raw.write(iv);
            try (CipherOutputStream encrypted = new CipherOutputStream(raw, cipher)) {
                byte[] buffer = new byte[256 * 1024];
                int count;
                while ((count = input.read(buffer)) >= 0) {
                    if (count == 0) continue;
                    total += count;
                    if (total > MAX_BYTES) {
                        throw new IllegalArgumentException(
                                "Playlist überschreitet das sichere Limit von 256 MB.");
                    }
                    encrypted.write(buffer, 0, count);
                    long now = SystemClock.elapsedRealtime();
                    if (total - reportedBytes >= DOWNLOAD_REPORT_BYTES
                            || now - lastReportAt >= DOWNLOAD_REPORT_INTERVAL_MS) {
                        reportedBytes = total;
                        lastReportAt = now;
                        progress.update("IMPORT-DOWNLOAD",
                                "Empfangen und verschlüsselt: " + total + " Bytes.");
                    }
                }
            }
        } catch (Exception failure) {
            temp.delete();
            throw failure;
        }

        progress.update("IMPORT-DOWNLOAD-END", "bytes=" + total);
        return total;
    }

    private List<Channel> parseEncrypted(File file, Progress progress, String progressStage) throws Exception {
        long encryptedBytes = file.length();
        try (InputStream input = decrypt(file)) {
            List<Channel> parsed = M3uParser.parse(input, MAX_ENTRIES, PARSE_TIMEOUT_MS,
                    (lines, entries, elapsedMs, limitReached) -> progress.update(progressStage,
                            "Zeilen=" + lines + " · Einträge=" + entries + " · Dauer=" + elapsedMs
                                    + " ms" + (limitReached ? " · Limit 100000 erreicht; Integrität wird bis Dateiende geprüft" : "")));
            return Collections.unmodifiableList(parsed);
        } catch (Exception failure) {
            progress.update(progressStage + "-ERROR",
                    "encryptedBytes=" + encryptedBytes + " · " + safeMessage(failure));
            throw failure;
        }
    }

    private InputStream decrypt(File file) throws Exception {
        FileInputStream raw = new FileInputStream(file);
        int ivLength = raw.read();
        if (ivLength < 12 || ivLength > 32) {
            raw.close();
            throw new IllegalStateException("Verschlüsselte Bibliothek ist beschädigt.");
        }
        byte[] iv = new byte[ivLength];
        int offset = 0;
        while (offset < ivLength) {
            int count = raw.read(iv, offset, ivLength - offset);
            if (count < 0) break;
            offset += count;
        }
        if (offset != ivLength) {
            raw.close();
            throw new IllegalStateException("Verschlüsselte Bibliothek ist unvollständig.");
        }
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, iv));
        return new CipherInputStream(new BufferedInputStream(raw, 256 * 1024), cipher);
    }

    private SecretKey key() throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        if (store.containsAlias(KEY_ALIAS)) return (SecretKey) store.getKey(KEY_ALIAS, null);
        KeyGenerator generator = KeyGenerator.getInstance(
                KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
        generator.init(new KeyGenParameterSpec.Builder(KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256).build());
        return generator.generateKey();
    }

    private void commitCandidate() throws Exception {
        if (backup.exists() && !backup.delete()) {
            throw new IllegalStateException("Alte Sicherung konnte nicht ersetzt werden.");
        }
        if (current.exists() && !current.renameTo(backup)) {
            throw new IllegalStateException(
                    "Letzte funktionierende Bibliothek konnte nicht gesichert werden.");
        }
        if (!temp.renameTo(current)) {
            if (backup.exists()) backup.renameTo(current);
            throw new IllegalStateException("Neue Bibliothek konnte nicht atomar aktiviert werden.");
        }
    }

    private void rememberPendingName(String name) {
        prefs.edit().putString("pending_source_name", safeName(name))
                .putLong("pending_started_at", System.currentTimeMillis()).apply();
    }

    private void saveActiveMetadata(String name, long bytes, int entries) {
        prefs.edit().putString("source_name", safeName(name))
                .putLong("source_bytes", bytes)
                .putInt("source_entries", entries)
                .putLong("source_activated_at", System.currentTimeMillis()).apply();
    }

    private void clearPendingMetadata() {
        prefs.edit().remove("pending_source_name")
                .remove("pending_source_bytes")
                .remove("pending_started_at").apply();
    }

    private static void copyFile(File source, File target) throws Exception {
        try (InputStream in = new BufferedInputStream(new FileInputStream(source), 256 * 1024);
             BufferedOutputStream out = new BufferedOutputStream(new FileOutputStream(target), 256 * 1024)) {
            byte[] buffer = new byte[256 * 1024];
            int count;
            while ((count = in.read(buffer)) >= 0) {
                if (count > 0) out.write(buffer, 0, count);
            }
        }
    }

    private static String safeName(String value) {
        String result = value == null ? "" : value.trim();
        if (result.isBlank()) result = "Meine Quelle";
        return result.replaceAll("[\\r\\n\\t]", " ").replaceAll("\\s{2,}", " ");
    }

    private static String safeMessage(Throwable failure) {
        if (failure == null || failure.getMessage() == null || failure.getMessage().isBlank()) {
            return failure == null ? "Unbekannter Fehler" : failure.getClass().getSimpleName();
        }
        return failure.getMessage();
    }
}
