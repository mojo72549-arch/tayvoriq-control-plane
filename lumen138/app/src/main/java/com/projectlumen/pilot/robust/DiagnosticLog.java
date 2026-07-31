package com.projectlumen.pilot.robust;

import android.content.Context;
import android.os.Build;

import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.regex.Pattern;

final class DiagnosticLog {
    private static final int MAX_BYTES = 2 * 1024 * 1024;
    private static final Pattern SECRET = Pattern.compile("(?i)(username|password|token|auth|key)=([^&\\s]+)");
    private static final ExecutorService WRITER = Executors.newSingleThreadExecutor(runnable -> {
        Thread thread = new Thread(runnable, "lumen-diagnostic-writer");
        thread.setDaemon(true);
        return thread;
    });
    private static DiagnosticLog instance;

    private final File file;
    private final Object fileLock = new Object();
    private final String session = UUID.randomUUID().toString().substring(0, 8).toUpperCase(Locale.ROOT);
    private int writesSinceTrim;

    static synchronized DiagnosticLog get(Context context) {
        if (instance == null) instance = new DiagnosticLog(context.getApplicationContext());
        return instance;
    }

    private DiagnosticLog(Context context) {
        file = new File(context.getFilesDir(), "lumen-diagnostics.log");
        event("-", "SESSION", "app=" + BuildConfig.VERSION_NAME + " android=" + Build.VERSION.SDK_INT
                + " device=" + Build.MANUFACTURER + " " + Build.MODEL);
    }

    void event(String interaction, String type, String detail) {
        long timestamp = System.currentTimeMillis();
        String safeInteraction = safe(interaction);
        String safeType = safe(type);
        String rawDetail = detail;
        try {
            WRITER.execute(() -> append(formatLine(timestamp, safeInteraction, safeType, rawDetail)));
        } catch (Throwable ignored) {
            append(formatLine(timestamp, safeInteraction, safeType, rawDetail));
        }
    }

    void exception(String interaction, String type, Throwable failure) {
        event(interaction, type, failure == null ? "unknown"
                : failure.getClass().getSimpleName() + ": " + failure.getMessage());
    }

    String read() {
        flushQueuedWrites();
        synchronized (fileLock) {
            try {
                return "Project Lumen Diagnose\nSession=" + session + "\nApp=" + BuildConfig.VERSION_NAME
                        + "\nAndroid=" + Build.VERSION.SDK_INT + "\nGerät=" + Build.MANUFACTURER + " " + Build.MODEL
                        + "\n\n" + (file.exists()
                        ? new String(java.nio.file.Files.readAllBytes(file.toPath()), StandardCharsets.UTF_8)
                        : "Keine Ereignisse.");
            } catch (Exception failure) {
                return "Diagnose konnte nicht gelesen werden: " + failure.getMessage();
            }
        }
    }

    void clear() {
        Future<?> task = WRITER.submit(() -> {
            synchronized (fileLock) {
                if (file.exists()) file.delete();
                writesSinceTrim = 0;
                appendLocked(formatLine(System.currentTimeMillis(), "-",
                        "DIAGNOSTICS-CLEARED", "ok=true"));
            }
        });
        await(task);
    }

    String newInteractionId() {
        return UUID.randomUUID().toString().substring(0, 8).toUpperCase(Locale.ROOT);
    }

    String anonymousId(String value) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(safe(value).getBytes(StandardCharsets.UTF_8));
            StringBuilder out = new StringBuilder();
            for (int i = 0; i < 6; i++) {
                out.append(String.format(Locale.ROOT, "%02x", digest[i]));
            }
            return out.toString();
        } catch (Exception ignored) {
            return Integer.toHexString(safe(value).hashCode());
        }
    }

    private void append(String line) {
        synchronized (fileLock) {
            appendLocked(line);
        }
    }

    private void appendLocked(String line) {
        try (FileOutputStream out = new FileOutputStream(file, true)) {
            out.write(line.getBytes(StandardCharsets.UTF_8));
        } catch (Exception ignored) { }

        writesSinceTrim++;
        if (writesSinceTrim >= 128 || file.length() > MAX_BYTES) {
            writesSinceTrim = 0;
            trimLocked();
        }
    }

    private void flushQueuedWrites() {
        try {
            await(WRITER.submit(() -> { }));
        } catch (Throwable ignored) { }
    }

    private static void await(Future<?> task) {
        try {
            task.get(3, TimeUnit.SECONDS);
        } catch (Exception ignored) { }
    }

    private void trimLocked() {
        if (!file.exists() || file.length() <= MAX_BYTES) return;
        try {
            byte[] all = java.nio.file.Files.readAllBytes(file.toPath());
            int keep = Math.min(all.length, MAX_BYTES / 2);
            try (FileOutputStream out = new FileOutputStream(file, false)) {
                out.write(all, all.length - keep, keep);
            }
        } catch (Exception ignored) { }
    }

    private static String formatLine(long timestamp, String interaction,
                                     String type, String detail) {
        String stamp = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSSZ", Locale.GERMANY)
                .format(new Date(timestamp));
        return stamp + " | " + safe(interaction) + " | " + safe(type)
                + " | " + redact(detail) + "\n";
    }

    static String redact(String raw) {
        if (raw == null) return "";
        String cleaned = SECRET.matcher(raw).replaceAll("$1=***");
        cleaned = cleaned.replaceAll("(?i)https?://[^\\s]+", "[Adresse ausgeblendet]");
        return cleaned;
    }

    private static String safe(String value) {
        return value == null ? "-" : value.replace('\n', ' ').replace('\r', ' ');
    }
}
