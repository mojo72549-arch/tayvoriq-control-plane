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
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.KeyStore;
import java.util.Collections;
import java.util.List;

import javax.crypto.Cipher;
import javax.crypto.CipherOutputStream;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

final class PlaylistRepository {
    interface Progress { void update(String stage, String detail); }

    static final int MAX_BYTES = 256 * 1024 * 1024;
    static final int MAX_ENTRIES = 100_000;

    private static final long RESTORE_PARSE_TIMEOUT_MS = 180_000L;
    private static final long IMPORT_STREAM_TIMEOUT_MS = 900_000L;
    private static final long DOWNLOAD_REPORT_BYTES = 4L * 1024L * 1024L;
    private static final long DOWNLOAD_REPORT_INTERVAL_MS = 1_500L;
    private static final String KEY_ALIAS = "lumen_playlist_key_v1";
    private static final String PREF_BLOCKED_CANDIDATE_BYTES = "blocked_candidate_bytes";

    private final File current;
    private final File backup;
    private final File temp;
    private final File cacheCurrent;
    private final File cacheBackup;
    private final File cacheTemp;
    private final SharedPreferences prefs;

    PlaylistRepository(Context context) {
        Context app = context.getApplicationContext();
        File dir = new File(app.getFilesDir(), "catalog");
        if (!dir.exists()) dir.mkdirs();
        current = new File(dir, "active.m3u.enc");
        backup = new File(dir, "backup.m3u.enc");
        temp = new File(dir, "candidate.m3u.enc");
        cacheCurrent = new File(dir, "active.catalog.bin");
        cacheBackup = new File(dir, "backup.catalog.bin");
        cacheTemp = new File(dir, "candidate.catalog.bin");
        prefs = app.getSharedPreferences("lumen_catalog_state", Context.MODE_PRIVATE);
    }

    List<Channel> restore(Progress progress) throws Exception {
        if (hasRecoverableCandidate()) {
            if (legacyRecoveryRequiresReimport()) {
                progress.update("RESTORE-CANDIDATE-REIMPORT-REQUIRED",
                        "Dieser Altimport wurde auf dem Gerät bereits sicher beendet. "
                                + "Bitte den Playlist-Link einmal neu laden.");
                if (!current.exists()) {
                    throw new IllegalStateException(
                            "Der alte 13.1.38-Import kann auf diesem Samsung nicht zuverlässig "
                                    + "entschlüsselt werden. Bitte über + Quelle den Playlist-Link "
                                    + "einmal neu laden; 13.1.41 verarbeitet ihn anschließend in einem Durchlauf.");
                }
            } else {
                progress.update("RESTORE-CANDIDATE-FOUND",
                        "Vollständig geladener Altimport gefunden. Blockmigration und Indexaufbau starten.");
                try {
                    long started = SystemClock.elapsedRealtime();
                    List<Channel> recovered = parseEncrypted(
                            temp, progress, "RESTORE-CANDIDATE-PARSE");
                    if (recovered.isEmpty()) {
                        throw new IllegalArgumentException(
                                "Die wiederhergestellte Playlist enthält keine unterstützten Einträge.");
                    }
                    writeCandidateCache(recovered, progress);
                    commitCandidate();
                    String pendingName = prefs.getString(
                            "pending_source_name", "Wiederhergestellte Playlist");
                    long pendingBytes = prefs.getLong("pending_source_bytes", 0L);
                    saveActiveMetadata(pendingName, pendingBytes, recovered.size());
                    clearPendingMetadata();
                    clearCandidateBlock();
                    progress.update("RESTORE-CANDIDATE-COMMIT",
                            "entries=" + recovered.size() + " durationMs="
                                    + (SystemClock.elapsedRealtime() - started));
                    return recovered;
                } catch (Exception candidateFailure) {
                    markCandidateBlocked();
                    progress.update("RESTORE-CANDIDATE-ERROR",
                            safeMessage(candidateFailure)
                                    + " · weiterer automatischer Endlosversuch wurde gesperrt");
                    if (!current.exists()) {
                        throw new IllegalStateException(
                                safeMessage(candidateFailure)
                                        + " Bitte den Playlist-Link einmal neu laden; "
                                        + "die neue Ein-Durchlauf-Verarbeitung umgeht diesen Altpfad.",
                                candidateFailure);
                    }
                }
            }
        }

        if (!current.exists()) return Collections.emptyList();

        if (CatalogCache.usable(cacheCurrent)) {
            long started = SystemClock.elapsedRealtime();
            progress.update("RESTORE-CACHE-START", "Gespeicherter Schnellindex wird geladen.");
            try {
                List<Channel> channels = CatalogCache.read(cacheCurrent);
                progress.update("RESTORE-CACHE-END",
                        "entries=" + channels.size() + " durationMs="
                                + (SystemClock.elapsedRealtime() - started));
                return channels;
            } catch (Exception cacheFailure) {
                progress.update("RESTORE-CACHE-INVALID",
                        "Schnellindex wird neu aufgebaut: " + safeMessage(cacheFailure));
                cacheCurrent.delete();
            }
        }

        progress.update("RESTORE-DECRYPT-START",
                "Einmaliger blockweiser Indexaufbau aus der verschlüsselten Bibliothek.");
        try {
            List<Channel> channels = parseEncrypted(
                    current, progress, "RESTORE-PARSE-PROGRESS");
            activateRebuiltCache(channels, progress);
            progress.update("CATALOG-READY", "entries=" + channels.size());
            return channels;
        } catch (Exception primary) {
            if (!backup.exists()) throw primary;
            progress.update("RESTORE-ROLLBACK",
                    "Aktive Generation defekt; letzte funktionierende Generation wird geladen.");
            List<Channel> channels;
            if (CatalogCache.usable(cacheBackup)) {
                channels = CatalogCache.read(cacheBackup);
            } else {
                channels = parseEncrypted(
                        backup, progress, "RESTORE-BACKUP-PROGRESS");
            }
            copyFile(backup, current);
            activateRebuiltCache(channels, progress);
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
        connection.setRequestProperty("User-Agent", "ProjectLumen/13.1.41");
        connection.setRequestProperty("Accept", "*/*");
        try {
            progress.update("IMPORT-CONNECT", "Verbindung wird aufgebaut.");
            int status = connection.getResponseCode();
            if (status < 200 || status >= 300) {
                throw new IllegalStateException("Server antwortet mit HTTP " + status + ".");
            }
            long declared = connection.getContentLengthLong();
            progress.update("IMPORT-DOWNLOAD", declared > 0
                    ? "Gesamtgröße " + declared
                            + " Bytes · Download und Indexaufbau laufen parallel."
                    : "Download und Indexaufbau laufen parallel.");
            try (InputStream input = new BufferedInputStream(
                    connection.getInputStream(), 1024 * 1024)) {
                return importStream(name, input, progress);
            }
        } finally {
            connection.disconnect();
        }
    }

    List<Channel> importUri(String name, ContentResolver resolver, Uri uri,
                            Progress progress) throws Exception {
        rememberPendingName(name);
        try (InputStream input = resolver.openInputStream(uri)) {
            if (input == null) {
                throw new IllegalArgumentException("Datei konnte nicht geöffnet werden.");
            }
            return importStream(name,
                    new BufferedInputStream(input, 1024 * 1024), progress);
        }
    }

    String sourceName() {
        return prefs.getString("source_name", "Noch keine Quelle");
    }

    boolean hasRecoverableCandidate() {
        return temp.exists() && temp.length() > 32;
    }

    boolean legacyRecoveryRequiresReimport() {
        return hasRecoverableCandidate()
                && prefs.getLong(PREF_BLOCKED_CANDIDATE_BYTES, -1L) == temp.length();
    }

    private List<Channel> importStream(String name, InputStream input,
                                       Progress progress) throws Exception {
        deleteCandidateFiles();
        EncryptingInputStream securedInput = null;
        try {
            progress.update("IMPORT-ONE-PASS-START",
                    "Download, Verschlüsselung und Katalogisierung wurden zusammengeführt.");
            securedInput = new EncryptingInputStream(input, progress);
            List<Channel> channels = M3uParser.parse(
                    securedInput, MAX_ENTRIES, IMPORT_STREAM_TIMEOUT_MS,
                    (lines, entries, elapsedMs, limitReached) -> progress.update(
                            "IMPORT-INDEX-PROGRESS",
                            "Zeilen=" + lines + " · Einträge=" + entries
                                    + " · Dauer=" + elapsedMs + " ms"
                                    + (limitReached
                                    ? " · Limit erreicht; Integrität wird abgeschlossen"
                                    : "")));

            if (!securedInput.reachedEof()) {
                throw new IllegalStateException("Playlist wurde nicht vollständig empfangen.");
            }
            securedInput.finishEncryption();
            long bytes = securedInput.totalBytes();
            prefs.edit().putLong("pending_source_bytes", bytes).apply();
            if (channels.isEmpty()) {
                throw new IllegalArgumentException(
                        "Die Playlist enthält keine unterstützten Stream-Einträge.");
            }

            writeCandidateCache(channels, progress);
            commitCandidate();
            saveActiveMetadata(name, bytes, channels.size());
            clearPendingMetadata();
            clearCandidateBlock();
            progress.update("IMPORT-DONE",
                    "entries=" + channels.size() + " bytes=" + bytes
                            + " onePass=true cache=true");
            return channels;
        } catch (Exception failure) {
            boolean complete = securedInput != null
                    && securedInput.reachedEof()
                    && securedInput.encryptionFinalized();
            if (!complete) {
                deleteCandidateFiles();
                clearPendingMetadata();
            } else {
                cacheTemp.delete();
                prefs.edit().putLong("pending_source_bytes",
                        securedInput.totalBytes()).apply();
                progress.update("IMPORT-PAUSED",
                        "Download ist vollständig. Kandidat bleibt für die Fortsetzung gespeichert.");
            }
            throw failure;
        } finally {
            if (securedInput != null) {
                try { securedInput.close(); } catch (Exception ignored) { }
            }
        }
    }

    private void writeCandidateCache(List<Channel> channels,
                                     Progress progress) throws Exception {
        if (cacheTemp.exists() && !cacheTemp.delete()) {
            throw new IllegalStateException(
                    "Alter Kandidatenindex konnte nicht ersetzt werden.");
        }
        long started = SystemClock.elapsedRealtime();
        progress.update("IMPORT-CACHE-WRITE-START",
                "Kompakter Schnellindex wird atomar geschrieben.");
        CatalogCache.write(cacheTemp, channels);
        progress.update("IMPORT-CACHE-WRITE-END",
                "entries=" + channels.size() + " durationMs="
                        + (SystemClock.elapsedRealtime() - started));
    }

    private void activateRebuiltCache(List<Channel> channels,
                                      Progress progress) throws Exception {
        if (cacheTemp.exists()) cacheTemp.delete();
        long started = SystemClock.elapsedRealtime();
        CatalogCache.write(cacheTemp, channels);
        if (cacheCurrent.exists() && !cacheCurrent.delete()) {
            cacheTemp.delete();
            throw new IllegalStateException(
                    "Alter Schnellindex konnte nicht ersetzt werden.");
        }
        if (!cacheTemp.renameTo(cacheCurrent)) {
            cacheTemp.delete();
            throw new IllegalStateException(
                    "Neuer Schnellindex konnte nicht aktiviert werden.");
        }
        progress.update("RESTORE-CACHE-BUILT",
                "entries=" + channels.size() + " durationMs="
                        + (SystemClock.elapsedRealtime() - started));
    }

    private List<Channel> parseEncrypted(File file, Progress progress,
                                         String progressStage) throws Exception {
        long encryptedBytes = file.length();
        File clearTemp = new File(file.getParentFile(),
                file.getName() + ".recovery.tmp");
        try {
            return LegacyCandidateMigrator.migrate(
                    file,
                    clearTemp,
                    key(),
                    MAX_ENTRIES,
                    RESTORE_PARSE_TIMEOUT_MS,
                    (stage, detail) -> progress.update(
                            progressStage + "-" + stage, detail));
        } catch (Exception failure) {
            progress.update(progressStage + "-ERROR",
                    "encryptedBytes=" + encryptedBytes + " · "
                            + safeMessage(failure));
            throw failure;
        } finally {
            if (clearTemp.exists()) clearTemp.delete();
        }
    }

    private SecretKey key() throws Exception {
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

    private void commitCandidate() throws Exception {
        deleteRequired(backup,
                "Alte Playlist-Sicherung konnte nicht ersetzt werden.");
        deleteRequired(cacheBackup,
                "Alter Index-Backup konnte nicht ersetzt werden.");

        boolean previousPlaylistMoved = false;
        boolean previousCacheMoved = false;
        if (current.exists()) {
            previousPlaylistMoved = current.renameTo(backup);
            if (!previousPlaylistMoved) {
                throw new IllegalStateException(
                        "Letzte funktionierende Bibliothek konnte nicht gesichert werden.");
            }
        }
        if (cacheCurrent.exists()) {
            previousCacheMoved = cacheCurrent.renameTo(cacheBackup);
            if (!previousCacheMoved) {
                if (previousPlaylistMoved) backup.renameTo(current);
                throw new IllegalStateException(
                        "Letzter funktionierender Schnellindex konnte nicht gesichert werden.");
            }
        }

        if (!temp.renameTo(current)) {
            restorePrevious(previousPlaylistMoved, previousCacheMoved);
            throw new IllegalStateException(
                    "Neue Bibliothek konnte nicht aktiviert werden.");
        }
        if (!cacheTemp.renameTo(cacheCurrent)) {
            current.renameTo(temp);
            restorePrevious(previousPlaylistMoved, previousCacheMoved);
            throw new IllegalStateException(
                    "Neuer Schnellindex konnte nicht aktiviert werden.");
        }
    }

    private void restorePrevious(boolean playlistMoved, boolean cacheMoved) {
        if (current.exists()) current.delete();
        if (cacheCurrent.exists()) cacheCurrent.delete();
        if (playlistMoved && backup.exists()) backup.renameTo(current);
        if (cacheMoved && cacheBackup.exists()) cacheBackup.renameTo(cacheCurrent);
    }

    private void rememberPendingName(String name) {
        prefs.edit()
                .putString("pending_source_name", safeName(name))
                .putLong("pending_started_at", System.currentTimeMillis())
                .apply();
    }

    private void saveActiveMetadata(String name, long bytes, int entries) {
        prefs.edit()
                .putString("source_name", safeName(name))
                .putLong("source_bytes", bytes)
                .putInt("source_entries", entries)
                .putLong("source_activated_at", System.currentTimeMillis())
                .apply();
    }

    private void clearPendingMetadata() {
        prefs.edit()
                .remove("pending_source_name")
                .remove("pending_source_bytes")
                .remove("pending_started_at")
                .apply();
    }

    private void markCandidateBlocked() {
        if (temp.exists()) {
            prefs.edit()
                    .putLong(PREF_BLOCKED_CANDIDATE_BYTES, temp.length())
                    .apply();
        }
    }

    private void clearCandidateBlock() {
        prefs.edit().remove(PREF_BLOCKED_CANDIDATE_BYTES).apply();
    }

    private void deleteCandidateFiles() throws Exception {
        deleteRequired(temp,
                "Alte Kandidatendatei konnte nicht ersetzt werden.");
        deleteRequired(cacheTemp,
                "Alter Kandidatenindex konnte nicht ersetzt werden.");
        clearCandidateBlock();
        File clearTemp = new File(temp.getParentFile(),
                temp.getName() + ".recovery.tmp");
        if (clearTemp.exists()) clearTemp.delete();
    }

    private static void deleteRequired(File file, String message)
            throws Exception {
        if (file.exists() && !file.delete()) {
            throw new IllegalStateException(message);
        }
    }

    private static void copyFile(File source, File target) throws Exception {
        try (InputStream in = new BufferedInputStream(
                new FileInputStream(source), 1024 * 1024);
             BufferedOutputStream out = new BufferedOutputStream(
                     new FileOutputStream(target), 1024 * 1024)) {
            byte[] buffer = new byte[1024 * 1024];
            int count;
            while ((count = in.read(buffer)) >= 0) {
                if (count > 0) out.write(buffer, 0, count);
            }
        }
    }

    private static String safeName(String value) {
        String result = value == null ? "" : value.trim();
        if (result.isBlank()) result = "Meine Quelle";
        return result.replaceAll("[\\r\\n\\t]", " ")
                .replaceAll("\\s{2,}", " ");
    }

    private static String safeMessage(Throwable failure) {
        if (failure == null || failure.getMessage() == null
                || failure.getMessage().isBlank()) {
            return failure == null ? "Unbekannter Fehler"
                    : failure.getClass().getSimpleName();
        }
        return failure.getMessage();
    }

    private final class EncryptingInputStream extends FilterInputStream {
        private final CipherOutputStream encryptedOutput;
        private final Progress progress;
        private long total;
        private long reportedBytes;
        private long lastReportAt;
        private boolean eof;
        private boolean encryptionFinalized;
        private boolean closed;

        EncryptingInputStream(InputStream source, Progress progress)
                throws Exception {
            super(source);
            this.progress = progress;
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, key());
            byte[] iv = cipher.getIV();
            FileOutputStream file = new FileOutputStream(temp);
            BufferedOutputStream raw = new BufferedOutputStream(
                    file, 1024 * 1024);
            raw.write(iv.length);
            raw.write(iv);
            encryptedOutput = new CipherOutputStream(raw, cipher);
            lastReportAt = SystemClock.elapsedRealtime();
        }

        @Override
        public int read() throws IOException {
            int value = super.read();
            if (value < 0) {
                eof = true;
                return -1;
            }
            encryptedOutput.write(value);
            record(1);
            return value;
        }

        @Override
        public int read(byte[] buffer, int offset, int length)
                throws IOException {
            int count = super.read(buffer, offset, length);
            if (count < 0) {
                eof = true;
                return -1;
            }
            if (count == 0) return 0;
            encryptedOutput.write(buffer, offset, count);
            record(count);
            return count;
        }

        private void record(int count) throws IOException {
            total += count;
            if (total > MAX_BYTES) {
                throw new IOException(
                        "Playlist überschreitet das sichere Limit von 256 MB.");
            }
            long now = SystemClock.elapsedRealtime();
            if (total - reportedBytes >= DOWNLOAD_REPORT_BYTES
                    || now - lastReportAt >= DOWNLOAD_REPORT_INTERVAL_MS) {
                reportedBytes = total;
                lastReportAt = now;
                progress.update("IMPORT-DOWNLOAD",
                        "Empfangen, verschlüsselt und indexiert: "
                                + total + " Bytes.");
            }
        }

        void finishEncryption() throws IOException {
            if (encryptionFinalized) return;
            encryptedOutput.close();
            encryptionFinalized = true;
        }

        long totalBytes() { return total; }
        boolean reachedEof() { return eof; }
        boolean encryptionFinalized() { return encryptionFinalized; }

        @Override
        public void close() throws IOException {
            if (closed) return;
            closed = true;
            IOException failure = null;
            if (!encryptionFinalized) {
                try {
                    finishEncryption();
                } catch (IOException closeFailure) {
                    failure = closeFailure;
                }
            }
            try {
                super.close();
            } catch (IOException closeFailure) {
                if (failure == null) failure = closeFailure;
            }
            if (failure != null) throw failure;
        }
    }
}
