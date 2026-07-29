package com.projectlumen.pilot.robust;

import android.os.SystemClock;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/**
 * Migrates the legacy 13.1.38/13.1.39 single-record AES-GCM candidate.
 *
 * Some Android Keystore providers buffer CipherInputStream output until the
 * authentication tag is verified. This class deliberately avoids
 * CipherInputStream, processes large blocks directly and enforces an outer
 * timeout so a device-specific provider can never trap the UI indefinitely.
 */
final class LegacyCandidateMigrator {
    interface Progress { void update(String stage, String detail); }

    private static final int BUFFER_BYTES = 1024 * 1024;
    private static final long REPORT_BYTES = 4L * 1024L * 1024L;
    private static final long REPORT_INTERVAL_MS = 1_000L;
    private static final long HARD_TIMEOUT_SECONDS = 90L;

    private LegacyCandidateMigrator() { }

    static List<Channel> migrate(File encrypted,
                                 File plaintext,
                                 SecretKey key,
                                 int maxEntries,
                                 long parseTimeoutMs,
                                 Progress progress) throws Exception {
        if (encrypted == null || !encrypted.exists() || encrypted.length() <= 32) {
            throw new IllegalStateException("Alte Kandidatendatei fehlt oder ist unvollständig.");
        }
        if (plaintext.exists() && !plaintext.delete()) {
            throw new IllegalStateException("Alte temporäre Migrationsdatei konnte nicht entfernt werden.");
        }

        ExecutorService executor = Executors.newSingleThreadExecutor(r -> {
            Thread thread = new Thread(r, "lumen-legacy-gcm-migration");
            thread.setDaemon(true);
            return thread;
        });
        Future<?> decryptTask = executor.submit(() -> {
            try {
                decryptToFile(encrypted, plaintext, key, progress);
                return null;
            } catch (Exception failure) {
                throw new RuntimeException(failure);
            }
        });

        try {
            progress.update("RESTORE-LEGACY-DECRYPT-START",
                    "Altimport wird blockweise entschlüsselt · " + encrypted.length() + " Bytes.");
            decryptTask.get(HARD_TIMEOUT_SECONDS, TimeUnit.SECONDS);
        } catch (TimeoutException timeout) {
            decryptTask.cancel(true);
            deleteQuietly(plaintext);
            throw new IllegalStateException(
                    "Die Altimport-Entschlüsselung wurde nach 90 Sekunden beendet. "
                            + "Bitte den Playlist-Link einmal neu laden; neue Importe laufen ohne diesen Altpfad.",
                    timeout);
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            decryptTask.cancel(true);
            deleteQuietly(plaintext);
            throw new IllegalStateException("Altimport-Migration wurde unterbrochen.", interrupted);
        } catch (ExecutionException wrapped) {
            deleteQuietly(plaintext);
            Throwable cause = wrapped.getCause();
            if (cause instanceof RuntimeException && cause.getCause() != null) {
                cause = cause.getCause();
            }
            if (cause instanceof Exception) throw (Exception) cause;
            throw new IllegalStateException("Altimport konnte nicht entschlüsselt werden.", cause);
        } finally {
            executor.shutdownNow();
        }

        try {
            progress.update("RESTORE-LEGACY-PARSE-START",
                    "Entschlüsselung abgeschlossen · schneller Katalogaufbau startet.");
            try (InputStream input = new BufferedInputStream(
                    new FileInputStream(plaintext), BUFFER_BYTES)) {
                List<Channel> parsed = M3uParser.parse(input, maxEntries, parseTimeoutMs,
                        (lines, entries, elapsedMs, limitReached) -> progress.update(
                                "RESTORE-LEGACY-PARSE-PROGRESS",
                                "Zeilen=" + lines + " · Einträge=" + entries
                                        + " · Dauer=" + elapsedMs + " ms"
                                        + (limitReached
                                        ? " · Limit erreicht; Datei wird vollständig geprüft"
                                        : "")));
                progress.update("RESTORE-LEGACY-PARSE-END",
                        "entries=" + parsed.size());
                return Collections.unmodifiableList(parsed);
            }
        } finally {
            deleteQuietly(plaintext);
        }
    }

    private static void decryptToFile(File encrypted,
                                      File plaintext,
                                      SecretKey key,
                                      Progress progress) throws Exception {
        long started = SystemClock.elapsedRealtime();
        long processed = 0L;
        long reported = 0L;
        long lastReportAt = started;

        try (FileInputStream fileInput = new FileInputStream(encrypted);
             BufferedInputStream raw = new BufferedInputStream(fileInput, BUFFER_BYTES)) {
            int ivLength = raw.read();
            if (ivLength < 12 || ivLength > 32) {
                throw new IllegalStateException("Altimport besitzt eine ungültige Verschlüsselungskennung.");
            }
            byte[] iv = new byte[ivLength];
            int offset = 0;
            while (offset < ivLength) {
                int count = raw.read(iv, offset, ivLength - offset);
                if (count < 0) break;
                offset += count;
            }
            if (offset != ivLength) {
                throw new IllegalStateException("Altimport enthält keinen vollständigen Initialisierungsvektor.");
            }

            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(128, iv));

            try (FileOutputStream fileOutput = new FileOutputStream(plaintext);
                 BufferedOutputStream output = new BufferedOutputStream(fileOutput, BUFFER_BYTES)) {
                byte[] encryptedBuffer = new byte[BUFFER_BYTES];
                int count;
                while ((count = raw.read(encryptedBuffer)) >= 0) {
                    if (Thread.currentThread().isInterrupted()) {
                        throw new InterruptedException("Altimport-Migration wurde abgebrochen.");
                    }
                    if (count == 0) continue;
                    byte[] clear = cipher.update(encryptedBuffer, 0, count);
                    if (clear != null && clear.length > 0) output.write(clear);
                    processed += count;
                    long now = SystemClock.elapsedRealtime();
                    if (processed - reported >= REPORT_BYTES
                            || now - lastReportAt >= REPORT_INTERVAL_MS) {
                        reported = processed;
                        lastReportAt = now;
                        progress.update("RESTORE-LEGACY-DECRYPT-PROGRESS",
                                "Verschlüsselte Daten geprüft: " + processed + " / "
                                        + Math.max(1L, encrypted.length()) + " Bytes · "
                                        + (now - started) + " ms");
                    }
                }
                byte[] finalClear = cipher.doFinal();
                if (finalClear != null && finalClear.length > 0) output.write(finalClear);
                output.flush();
                fileOutput.getFD().sync();
            }
        } catch (Exception failure) {
            deleteQuietly(plaintext);
            throw failure;
        }

        progress.update("RESTORE-LEGACY-DECRYPT-END",
                "bytes=" + processed + " durationMs="
                        + (SystemClock.elapsedRealtime() - started));
    }

    private static void deleteQuietly(File file) {
        if (file != null && file.exists()) file.delete();
    }
}
