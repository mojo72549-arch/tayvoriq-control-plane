package com.projectlumen.publicpreview;

import android.content.Context;
import android.content.SharedPreferences;

import java.io.BufferedInputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Properties;
import java.util.Set;
import java.util.UUID;

/**
 * Crash-safe two-generation storage for the active local library.
 *
 * A generation becomes visible only after playlist, catalog, manifest and READY marker
 * are fully written and the staging directory has been renamed atomically. The pointer
 * update happens last and retains the previous generation for recovery.
 */
final class LibraryGenerationStore {
    private static final String PREFS = "lumen-library-generations-v1";
    private static final String KEY_ACTIVE = "active_generation";
    private static final String KEY_PREVIOUS = "previous_generation";
    private static final String KEY_RESTORE_RUNNING = "restore_running";
    private static final String ROOT = "library-generations";
    private static final String PLAYLIST = "playlist.lumen";
    private static final String CATALOG = "catalog.lumen";
    private static final String MANIFEST = "manifest.properties";
    private static final String READY = "READY";
    private static final int MANIFEST_VERSION = 1;
    private static final int MAX_ENTRIES = 100_000;

    static final class Generation {
        final String id;
        final File directory;
        final File playlist;
        final File catalog;
        final boolean legacy;

        Generation(String id, File directory, File playlist, File catalog, boolean legacy) {
            this.id = id;
            this.directory = directory;
            this.playlist = playlist;
            this.catalog = catalog;
            this.legacy = legacy;
        }

        String relativePlaylistPath(Context context) {
            if (legacy) return playlist.getName();
            String rootPath = context.getFilesDir().getAbsolutePath() + File.separator;
            String absolute = playlist.getAbsolutePath();
            return absolute.startsWith(rootPath) ? absolute.substring(rootPath.length()) : absolute;
        }
    }

    static final class Stage {
        final String id;
        final File directory;
        final File playlist;
        final File catalog;

        Stage(String id, File directory) {
            this.id = id;
            this.directory = directory;
            this.playlist = new File(directory, PLAYLIST);
            this.catalog = new File(directory, CATALOG);
        }
    }

    private LibraryGenerationStore() {}

    static Stage begin(Context context) throws IOException {
        File root = root(context);
        if (!root.exists() && !root.mkdirs()) throw new IOException("Bibliotheksspeicher konnte nicht erstellt werden.");
        String id = "g-" + System.currentTimeMillis() + "-" + UUID.randomUUID().toString().replace("-", "").substring(0, 8);
        File directory = new File(root, ".stage-" + id);
        deleteRecursively(directory);
        if (!directory.mkdirs()) throw new IOException("Temporäre Bibliotheksgeneration konnte nicht erstellt werden.");
        return new Stage(id, directory);
    }

    static Generation commit(Context context, Stage stage, int entryCount) throws IOException {
        if (stage == null || !stage.playlist.isFile() || !stage.catalog.isFile()) {
            throw new IOException("Bibliotheksgeneration ist unvollständig.");
        }
        if (entryCount < 1 || entryCount > MAX_ENTRIES) throw new IOException("Ungültige Bibliotheksgröße.");
        syncFile(stage.playlist);
        syncFile(stage.catalog);

        Properties manifest = new Properties();
        manifest.setProperty("version", Integer.toString(MANIFEST_VERSION));
        manifest.setProperty("generation", stage.id);
        manifest.setProperty("entries", Integer.toString(entryCount));
        manifest.setProperty("playlist.length", Long.toString(stage.playlist.length()));
        manifest.setProperty("catalog.length", Long.toString(stage.catalog.length()));
        manifest.setProperty("playlist.sha256", sha256(stage.playlist));
        manifest.setProperty("catalog.sha256", sha256(stage.catalog));
        manifest.setProperty("createdAt", Long.toString(System.currentTimeMillis()));

        File manifestTemp = new File(stage.directory, MANIFEST + ".tmp");
        try (FileOutputStream output = new FileOutputStream(manifestTemp)) {
            manifest.store(output, "Project Lumen local library generation");
            output.flush();
            output.getFD().sync();
        }
        moveAtomically(manifestTemp, new File(stage.directory, MANIFEST));
        writeAndSync(new File(stage.directory, READY), stage.id + "\n");

        File finalDirectory = new File(root(context), stage.id);
        if (finalDirectory.exists()) deleteRecursively(finalDirectory);
        moveAtomically(stage.directory, finalDirectory);

        SharedPreferences preferences = preferences(context);
        String oldActive = preferences.getString(KEY_ACTIVE, "");
        SharedPreferences.Editor editor = preferences.edit().putString(KEY_ACTIVE, stage.id);
        if (!oldActive.isBlank() && !oldActive.equals(stage.id)) editor.putString(KEY_PREVIOUS, oldActive);
        if (!editor.commit()) {
            deleteRecursively(finalDirectory);
            throw new IOException("Aktive Bibliotheksgeneration konnte nicht dauerhaft markiert werden.");
        }
        cleanup(context);
        return generation(context, stage.id, false);
    }

    static List<Generation> restoreCandidates(Context context, String legacyFileName) {
        boolean verifyChecksum = markRestoreStarted(context);
        List<Generation> result = new ArrayList<>();
        SharedPreferences preferences = preferences(context);
        Set<String> seen = new HashSet<>();
        addCandidate(context, result, seen, preferences.getString(KEY_ACTIVE, ""), verifyChecksum);
        addCandidate(context, result, seen, preferences.getString(KEY_PREVIOUS, ""), verifyChecksum);

        if (legacyFileName != null && !legacyFileName.isBlank()) {
            File playlist = new File(context.getFilesDir(), legacyFileName);
            File catalog = new File(context.getFilesDir(), "active-catalog.lumen");
            if (playlist.isFile()) result.add(new Generation("legacy", context.getFilesDir(), playlist, catalog, true));
        }
        return result;
    }

    static Generation active(Context context) {
        String id = preferences(context).getString(KEY_ACTIVE, "");
        Generation generation = generation(context, id, false);
        return validate(generation, false) ? generation : null;
    }

    static void markActive(Context context, Generation generation) {
        if (generation == null || generation.legacy) return;
        SharedPreferences preferences = preferences(context);
        String oldActive = preferences.getString(KEY_ACTIVE, "");
        SharedPreferences.Editor editor = preferences.edit().putString(KEY_ACTIVE, generation.id);
        if (!oldActive.isBlank() && !oldActive.equals(generation.id)) editor.putString(KEY_PREVIOUS, oldActive);
        editor.commit();
    }

    static void markRestoreFinished(Context context) {
        preferences(context).edit().putBoolean(KEY_RESTORE_RUNNING, false).commit();
    }

    static void copyPlaylistToStage(File source, Stage stage) throws IOException {
        if (source == null || !source.isFile() || stage == null) throw new IOException("Gespeicherte Rohquelle fehlt.");
        copyAndSync(source, stage.playlist);
    }

    static Generation migrateLegacy(Context context, File legacyPlaylist, File legacyCatalog, int entryCount) throws IOException {
        if (legacyPlaylist == null || !legacyPlaylist.isFile() || legacyCatalog == null || !legacyCatalog.isFile()) return null;
        Stage stage = begin(context);
        try {
            copyAndSync(legacyPlaylist, stage.playlist);
            copyAndSync(legacyCatalog, stage.catalog);
            return commit(context, stage, entryCount);
        } catch (IOException failure) {
            deleteRecursively(stage.directory);
            throw failure;
        }
    }

    static void clear(Context context) {
        deleteRecursively(root(context));
        preferences(context).edit().clear().commit();
        new File(context.getFilesDir(), "active-playlist.lumen").delete();
        new File(context.getFilesDir(), "active-catalog.lumen").delete();
        new File(context.getFilesDir(), "active-playlist.lumen.tmp").delete();
        new File(context.getFilesDir(), "active-catalog.lumen.tmp").delete();
    }

    static void abandon(Stage stage) {
        if (stage != null) deleteRecursively(stage.directory);
    }

    private static boolean markRestoreStarted(Context context) {
        SharedPreferences preferences = preferences(context);
        boolean previousRunInterrupted = preferences.getBoolean(KEY_RESTORE_RUNNING, false);
        preferences.edit().putBoolean(KEY_RESTORE_RUNNING, true).commit();
        return previousRunInterrupted;
    }

    private static void addCandidate(Context context, List<Generation> result, Set<String> seen,
                                     String id, boolean verifyChecksum) {
        if (id == null || id.isBlank() || !seen.add(id)) return;
        Generation generation = generation(context, id, false);
        if (validate(generation, verifyChecksum)) result.add(generation);
    }

    private static Generation generation(Context context, String id, boolean legacy) {
        if (id == null || id.isBlank()) return null;
        File directory = new File(root(context), id);
        return new Generation(id, directory, new File(directory, PLAYLIST), new File(directory, CATALOG), legacy);
    }

    private static boolean validate(Generation generation, boolean verifyChecksum) {
        if (generation == null || generation.legacy) return generation != null && generation.playlist.isFile();
        try {
            File manifestFile = new File(generation.directory, MANIFEST);
            File readyFile = new File(generation.directory, READY);
            if (!generation.directory.isDirectory() || !manifestFile.isFile() || !readyFile.isFile()
                    || !generation.playlist.isFile() || !generation.catalog.isFile()) return false;
            Properties manifest = new Properties();
            try (FileInputStream input = new FileInputStream(manifestFile)) { manifest.load(input); }
            if (Integer.parseInt(manifest.getProperty("version", "0")) != MANIFEST_VERSION) return false;
            if (!generation.id.equals(manifest.getProperty("generation", ""))) return false;
            int entries = Integer.parseInt(manifest.getProperty("entries", "-1"));
            if (entries < 1 || entries > MAX_ENTRIES) return false;
            if (generation.playlist.length() != Long.parseLong(manifest.getProperty("playlist.length", "-1"))) return false;
            if (generation.catalog.length() != Long.parseLong(manifest.getProperty("catalog.length", "-1"))) return false;
            if (verifyChecksum) {
                if (!sha256(generation.playlist).equalsIgnoreCase(manifest.getProperty("playlist.sha256", ""))) return false;
                if (!sha256(generation.catalog).equalsIgnoreCase(manifest.getProperty("catalog.sha256", ""))) return false;
            }
            return true;
        } catch (Exception failure) {
            return false;
        }
    }

    private static void cleanup(Context context) {
        File root = root(context);
        File[] children = root.listFiles();
        if (children == null) return;
        SharedPreferences preferences = preferences(context);
        String active = preferences.getString(KEY_ACTIVE, "");
        String previous = preferences.getString(KEY_PREVIOUS, "");
        long staleBefore = System.currentTimeMillis() - 24L * 60L * 60L * 1000L;
        for (File child : children) {
            String name = child.getName();
            if (name.equals(active) || name.equals(previous)) continue;
            if (name.startsWith(".stage-") || child.lastModified() < staleBefore) deleteRecursively(child);
        }
    }

    private static File root(Context context) { return new File(context.getFilesDir(), ROOT); }
    private static SharedPreferences preferences(Context context) {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    private static void copyAndSync(File source, File target) throws IOException {
        File parent = target.getParentFile();
        if (parent != null && !parent.exists() && !parent.mkdirs()) throw new IOException("Zielordner konnte nicht erstellt werden.");
        try (BufferedInputStream input = new BufferedInputStream(new FileInputStream(source), 256 * 1024);
             FileOutputStream output = new FileOutputStream(target)) {
            byte[] buffer = new byte[256 * 1024];
            int read;
            while ((read = input.read(buffer)) >= 0) output.write(buffer, 0, read);
            output.flush();
            output.getFD().sync();
        }
    }

    private static void writeAndSync(File file, String value) throws IOException {
        try (FileOutputStream output = new FileOutputStream(file)) {
            output.write(value.getBytes(StandardCharsets.UTF_8));
            output.flush();
            output.getFD().sync();
        }
    }

    private static void syncFile(File file) throws IOException {
        try (FileOutputStream output = new FileOutputStream(file, true)) { output.getFD().sync(); }
    }

    private static void moveAtomically(File source, File target) throws IOException {
        try {
            Files.move(source.toPath(), target.toPath(), StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
        } catch (AtomicMoveNotSupportedException unsupported) {
            Files.move(source.toPath(), target.toPath(), StandardCopyOption.REPLACE_EXISTING);
        }
    }

    private static String sha256(File file) throws IOException {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            try (BufferedInputStream input = new BufferedInputStream(new FileInputStream(file), 256 * 1024)) {
                byte[] buffer = new byte[256 * 1024];
                int read;
                while ((read = input.read(buffer)) >= 0) digest.update(buffer, 0, read);
            }
            StringBuilder result = new StringBuilder(64);
            for (byte value : digest.digest()) result.append(String.format(Locale.ROOT, "%02x", value & 0xff));
            return result.toString();
        } catch (java.security.NoSuchAlgorithmException impossible) {
            throw new IOException("SHA-256 ist nicht verfügbar.", impossible);
        }
    }

    private static void deleteRecursively(File file) {
        if (file == null || !file.exists()) return;
        if (file.isDirectory()) {
            File[] children = file.listFiles();
            if (children != null) for (File child : children) deleteRecursively(child);
        }
        file.delete();
    }
}
