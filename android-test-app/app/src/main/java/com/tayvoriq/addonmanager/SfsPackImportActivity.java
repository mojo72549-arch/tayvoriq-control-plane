package com.tayvoriq.addonmanager;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.DocumentsContract;
import android.provider.OpenableColumns;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import androidx.documentfile.provider.DocumentFile;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

/** Isolated Spaceflight Simulator custom-parts adapter. Minecraft code remains separate. */
public final class SfsPackImportActivity extends Activity {
    private static final String SFS_PACKAGE = "com.StefMorojna.SpaceflightSimulator";
    private static final int PICK_SFS_PARTS_FOLDER = 1701;
    private static final String PREFS = "universal_import";
    private static final String PREF_SFS_PARTS_TREE = "sfs_custom_parts_tree";

    private static final long MAX_ARCHIVE_BYTES = 750L * 1024L * 1024L;
    private static final long MAX_SINGLE_PACK_BYTES = 300L * 1024L * 1024L;
    private static final int MAX_ENTRIES = 10_000;
    private static final int MAX_PACKS = 250;

    private static final int BG = Color.rgb(5, 8, 18);
    private static final int SURFACE = Color.rgb(13, 19, 33);
    private static final int TEXT = Color.rgb(245, 248, 255);
    private static final int MUTED = Color.rgb(158, 169, 192);
    private static final int CYAN = Color.rgb(0, 222, 235);
    private static final int GREEN = Color.rgb(57, 221, 139);
    private static final int RED = Color.rgb(255, 82, 106);
    private static final int VIOLET = Color.rgb(124, 77, 255);

    private TextView status;
    private TextView details;
    private Button primaryButton;
    private Button openGameButton;
    private Uri sourceUri;
    private String sourceName;
    private final List<File> stagedPacks = new ArrayList<>();
    private DocumentFile resolvedPartsFolder;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().setStatusBarColor(BG);
        getWindow().setNavigationBarColor(BG);
        setContentView(buildScreen());
        receive(getIntent());
    }

    private View buildScreen() {
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setBackgroundColor(BG);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER_HORIZONTAL);
        root.setPadding(dp(22), dp(28), dp(22), dp(30));
        scroll.addView(root, new ScrollView.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setGravity(Gravity.CENTER_HORIZONTAL);
        card.setPadding(dp(22), dp(24), dp(22), dp(24));
        card.setBackground(rounded(SURFACE, 24));
        root.addView(card, matchWrap());

        ImageView logo = new ImageView(this);
        logo.setImageResource(R.drawable.ic_launcher_foreground);
        logo.setScaleType(ImageView.ScaleType.CENTER_INSIDE);
        card.addView(logo, new LinearLayout.LayoutParams(dp(132), dp(132)));

        TextView brand = text("TAYVORIQ", 28, TEXT, true);
        brand.setGravity(Gravity.CENTER);
        card.addView(brand, matchWrap());
        TextView sub = text("SPACEFLIGHT IMPORT", 12, CYAN, true);
        sub.setGravity(Gravity.CENTER);
        sub.setPadding(0, dp(3), 0, dp(16));
        card.addView(sub, matchWrap());

        status = text("🚀 Spaceflight Simulator", 19, TEXT, true);
        status.setGravity(Gravity.CENTER);
        status.setPadding(0, dp(6), 0, dp(10));
        card.addView(status, matchWrap());
        details = text("Datei wird sicher geprüft …", 14, MUTED, false);
        details.setGravity(Gravity.CENTER);
        details.setPadding(dp(4), dp(4), dp(4), dp(16));
        card.addView(details, matchWrap());

        primaryButton = button("MOD INSTALLIEREN", VIOLET);
        primaryButton.setVisibility(View.GONE);
        primaryButton.setOnClickListener(v -> installRequested());
        card.addView(primaryButton, matchWrap());

        openGameButton = button("SPACEFLIGHT SIMULATOR ÖFFNEN", Color.rgb(25, 44, 59));
        openGameButton.setVisibility(View.GONE);
        openGameButton.setOnClickListener(v -> launchSpaceflight());
        LinearLayout.LayoutParams gp = matchWrap();
        gp.topMargin = dp(10);
        card.addView(openGameButton, gp);

        TextView footer = text(
                "Installationsziel: Spaceflight Simulator → Mods → Custom Assets → Parts\n\n"
                        + "Dateien werden zuerst temporär geprüft. Vorhandene Mods werden nicht still überschrieben.",
                12, MUTED, false);
        footer.setGravity(Gravity.CENTER);
        footer.setPadding(dp(6), dp(18), dp(6), 0);
        card.addView(footer, matchWrap());
        return scroll;
    }

    private void receive(Intent intent) {
        if (intent == null) { fail("Keine Datei empfangen."); return; }
        sourceUri = intent.getData();
        if (sourceUri == null && Intent.ACTION_SEND.equals(intent.getAction())) {
            if (Build.VERSION.SDK_INT >= 33) sourceUri = intent.getParcelableExtra(Intent.EXTRA_STREAM, Uri.class);
            else {
                @SuppressWarnings("deprecation") Uri legacy = intent.getParcelableExtra(Intent.EXTRA_STREAM);
                sourceUri = legacy;
            }
        }
        if (sourceUri == null) { fail("Die Datei konnte nicht gelesen werden."); return; }
        sourceName = queryDisplayName(sourceUri);
        String lower = sourceName.toLowerCase(Locale.ROOT);
        if (!lower.endsWith(".pack") && !lower.endsWith(".zip")) {
            fail("Kein Spaceflight-Custom-Part-Paket: " + sourceName); return;
        }
        if (!isAppInstalled(SFS_PACKAGE)) { fail("Spaceflight Simulator ist auf diesem Android-Gerät nicht installiert."); return; }
        new Thread(this::stageAndAnalyze, "sfs-pack-stage").start();
    }

    private void stageAndAnalyze() {
        try {
            clearStage();
            if (sourceName.toLowerCase(Locale.ROOT).endsWith(".pack")) stagedPacks.add(copyUriToStage(sourceUri, sanitizeFileName(sourceName)));
            else extractPacksFromZip(sourceUri);
            if (stagedPacks.isEmpty()) { runOnUiThread(() -> fail("Kein .pack-Custom-Part-Paket gefunden.")); return; }
            StringBuilder list = new StringBuilder();
            for (File file : stagedPacks) list.append("\n✓ ").append(file.getName()).append(" · ").append(readableBytes(file.length()));
            runOnUiThread(() -> {
                status.setTextColor(GREEN);
                status.setText("🚀 Spaceflight Simulator Mod erkannt");
                details.setText("Typ: Custom Part Pack\nQuelle: " + sourceName
                        + "\n✓ SFS installiert\n✓ Mobile-Custom-Part-Format erkannt\n✓ Sicherheitsprüfung bestanden"
                        + "\n\n" + stagedPacks.size() + " Paket(e) gefunden:" + list);
                primaryButton.setVisibility(View.VISIBLE);
            });
        } catch (Exception error) {
            String message = error.getMessage() == null ? error.getClass().getSimpleName() : error.getMessage();
            runOnUiThread(() -> fail("SFS-Paketprüfung fehlgeschlagen: " + message));
        }
    }

    private void extractPacksFromZip(Uri uri) throws Exception {
        InputStream raw = getContentResolver().openInputStream(uri);
        if (raw == null) throw new IllegalStateException("ZIP konnte nicht geöffnet werden.");
        long unpacked = 0; int entries = 0; byte[] buffer = new byte[32 * 1024];
        try (raw; ZipInputStream zip = new ZipInputStream(raw)) {
            ZipEntry entry;
            while ((entry = zip.getNextEntry()) != null) {
                entries++;
                if (entries > MAX_ENTRIES) throw new IllegalStateException("Zu viele Dateien im ZIP.");
                String name = safeEntryName(entry.getName());
                String lower = name.toLowerCase(Locale.ROOT);
                if (isPcOnlyExecutable(lower)) throw new IllegalStateException("PC-/ausführbarer Mod-Bestandteil erkannt: " + name + ". Dieses Paket wird auf Android nicht installiert.");
                if (entry.isDirectory()) { zip.closeEntry(); continue; }
                if (lower.endsWith(".pack")) {
                    if (stagedPacks.size() >= MAX_PACKS) throw new IllegalStateException("Zu viele .pack-Dateien im ZIP.");
                    File target = uniqueStageFile(leafName(name)); long written = 0;
                    try (OutputStream out = new FileOutputStream(target)) {
                        int read;
                        while ((read = zip.read(buffer)) != -1) {
                            written += read; unpacked += read;
                            if (written > MAX_SINGLE_PACK_BYTES) throw new IllegalStateException("Ein .pack ist größer als 300 MB.");
                            if (unpacked > MAX_ARCHIVE_BYTES) throw new IllegalStateException("ZIP ist entpackt größer als 750 MB.");
                            out.write(buffer, 0, read);
                        }
                    }
                    stagedPacks.add(target);
                } else {
                    int read;
                    while ((read = zip.read(buffer)) != -1) {
                        unpacked += read;
                        if (unpacked > MAX_ARCHIVE_BYTES) throw new IllegalStateException("ZIP ist entpackt größer als 750 MB.");
                    }
                }
                zip.closeEntry();
            }
        }
    }

    private void installRequested() {
        primaryButton.setEnabled(false);
        status.setTextColor(TEXT);
        status.setText("Installationsziel wird geprüft …");
        DocumentFile parts = resolveSavedPartsFolder();
        if (parts != null) { resolvedPartsFolder = parts; inspectConflictsAndInstall(); return; }
        details.setText("Einmalige Einrichtung:\nBitte bestätige den Spaceflight-Simulator-Ordner unter\n"
                + "Android/media/com.StefMorojna.SpaceflightSimulator/Mods/Custom_Assets/Parts.\n\n"
                + "TAYVORIQ merkt sich diese Freigabe für weitere Installationen.");
        openPartsFolderPicker();
    }

    private void openPartsFolderPicker() {
        Intent picker = new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE);
        picker.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION
                | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION | Intent.FLAG_GRANT_PREFIX_URI_PERMISSION);
        if (Build.VERSION.SDK_INT >= 26) {
            try {
                String documentId = "primary:Android/media/com.StefMorojna.SpaceflightSimulator/Mods/Custom_Assets/Parts";
                Uri initial = DocumentsContract.buildDocumentUri("com.android.externalstorage.documents", documentId);
                picker.putExtra(DocumentsContract.EXTRA_INITIAL_URI, initial);
            } catch (RuntimeException ignored) { }
        }
        startActivityForResult(picker, PICK_SFS_PARTS_FOLDER);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != PICK_SFS_PARTS_FOLDER) return;
        if (resultCode != RESULT_OK || data == null || data.getData() == null) {
            primaryButton.setEnabled(true); fail("Spaceflight-Zielordner wurde nicht bestätigt."); return;
        }
        Uri treeUri = data.getData();
        try {
            int flags = data.getFlags() & (Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
            getContentResolver().takePersistableUriPermission(treeUri, flags);
            DocumentFile selected = DocumentFile.fromTreeUri(this, treeUri);
            if (selected == null || !selected.canWrite()) throw new IllegalStateException("Der gewählte Ordner ist nicht beschreibbar.");
            String treeId = "";
            try { treeId = DocumentsContract.getTreeDocumentId(treeUri).toLowerCase(Locale.ROOT); } catch (RuntimeException ignored) { }
            if (!treeId.contains("android/media/com.stefmorojna.spaceflightsimulator")) throw new IllegalStateException("Bitte den Spaceflight-Simulator-Ordner unter Android/media auswählen.");
            DocumentFile parts = resolvePartsFolderFromSelection(selected, treeId);
            if (parts == null || !parts.canWrite()) throw new IllegalStateException("Mods/Custom_Assets/Parts konnte nicht verwendet werden.");
            resolvedPartsFolder = parts;
            getSharedPreferences(PREFS, MODE_PRIVATE).edit().putString(PREF_SFS_PARTS_TREE, treeUri.toString()).apply();
            inspectConflictsAndInstall();
        } catch (Exception error) {
            primaryButton.setEnabled(true); fail("Spaceflight-Ordner konnte nicht verwendet werden: " + error.getMessage());
        }
    }

    private DocumentFile resolveSavedPartsFolder() {
        String saved = getSharedPreferences(PREFS, MODE_PRIVATE).getString(PREF_SFS_PARTS_TREE, null);
        if (saved == null) return null;
        try {
            Uri uri = Uri.parse(saved); DocumentFile selected = DocumentFile.fromTreeUri(this, uri);
            if (selected == null || !selected.canWrite()) return null;
            String treeId = DocumentsContract.getTreeDocumentId(uri).toLowerCase(Locale.ROOT);
            return resolvePartsFolderFromSelection(selected, treeId);
        } catch (Exception ignored) { return null; }
    }

    private DocumentFile resolvePartsFolderFromSelection(DocumentFile selected, String treeId) {
        String normalized = treeId.replace('\\', '/').toLowerCase(Locale.ROOT);
        if (normalized.endsWith("/mods/custom_assets/parts")) return selected;
        DocumentFile current = selected;
        if (!normalized.endsWith("/mods/custom_assets")) {
            if (!normalized.endsWith("/mods")) current = findOrCreateDirectory(current, "Mods");
            current = findOrCreateDirectory(current, "Custom_Assets");
        }
        return findOrCreateDirectory(current, "Parts");
    }

    private DocumentFile findOrCreateDirectory(DocumentFile parent, String name) {
        DocumentFile found = parent.findFile(name);
        if (found != null && found.isDirectory()) return found;
        DocumentFile created = parent.createDirectory(name);
        if (created == null) throw new IllegalStateException("Ordner konnte nicht erstellt werden: " + name);
        return created;
    }

    private void inspectConflictsAndInstall() {
        status.setText("Vorhandene Mods werden verglichen …");
        new Thread(() -> {
            try {
                Map<String, File> conflicts = new HashMap<>(); int identical = 0;
                for (File pack : stagedPacks) {
                    DocumentFile existing = resolvedPartsFolder.findFile(pack.getName());
                    if (existing == null || existing.isDirectory()) continue;
                    if (sha256(pack).equals(sha256(existing))) identical++; else conflicts.put(pack.getName(), pack);
                }
                final int identicalCount = identical;
                runOnUiThread(() -> {
                    if (conflicts.isEmpty()) performInstall(false, identicalCount);
                    else {
                        StringBuilder names = new StringBuilder(); for (String name : conflicts.keySet()) names.append("\n• ").append(name);
                        new AlertDialog.Builder(this)
                                .setTitle("Vorhandene Mods gefunden")
                                .setMessage(conflicts.size() + " Paket(e) haben denselben Dateinamen, aber anderen Inhalt:" + names
                                        + "\n\nAktualisieren ersetzt diese Pakete transaktional. Überspringen lässt die vorhandenen Dateien unverändert.")
                                .setPositiveButton("AKTUALISIEREN", (d, w) -> performInstall(true, identicalCount))
                                .setNegativeButton("ÜBERSPRINGEN", (d, w) -> performInstall(false, identicalCount))
                                .setCancelable(false).show();
                    }
                });
            } catch (Exception error) {
                runOnUiThread(() -> { primaryButton.setEnabled(true); fail("Konfliktprüfung fehlgeschlagen: " + error.getMessage()); });
            }
        }, "sfs-conflict-check").start();
    }

    private void performInstall(boolean updateConflicts, int identicalCount) {
        status.setTextColor(TEXT); status.setText("Mods werden sicher installiert …");
        details.setText("Temporäres Schreiben → SHA-256 prüfen → atomar übernehmen → Rollback bei Fehler");
        new Thread(() -> {
            int installed = 0, updated = 0, skipped = identicalCount;
            try {
                for (File pack : stagedPacks) {
                    DocumentFile existing = resolvedPartsFolder.findFile(pack.getName());
                    if (existing != null && !existing.isDirectory()) {
                        if (sha256(pack).equals(sha256(existing))) continue;
                        if (!updateConflicts) { skipped++; continue; }
                        transactionalWrite(pack, resolvedPartsFolder, existing); updated++;
                    } else { transactionalWrite(pack, resolvedPartsFolder, null); installed++; }
                }
                final int a = installed, b = updated, c = skipped;
                runOnUiThread(() -> installationSuccess(a, b, c));
            } catch (Exception error) {
                runOnUiThread(() -> { primaryButton.setEnabled(true); fail("Installation abgebrochen. Rollback wurde ausgeführt: " + error.getMessage()); });
            }
        }, "sfs-pack-install").start();
    }

    private void transactionalWrite(File source, DocumentFile partsRoot, DocumentFile existing) throws Exception {
        String expectedHash = sha256(source); String safeName = source.getName(); String token = Long.toHexString(System.nanoTime());
        String tempName = "." + safeName + ".tayvoriq-" + token + ".tmp";
        String backupName = "." + safeName + ".tayvoriq-" + token + ".bak";
        DocumentFile temp = partsRoot.createFile("application/octet-stream", tempName);
        if (temp == null) throw new IllegalStateException("Temporäre Datei konnte nicht erstellt werden: " + safeName);
        DocumentFile backup = null; boolean existingRenamed = false;
        try {
            copyFileToDocument(source, temp);
            if (!expectedHash.equals(sha256(temp))) throw new IllegalStateException("SHA-256-Prüfung fehlgeschlagen: " + safeName);
            if (existing != null) {
                if (!existing.renameTo(backupName)) throw new IllegalStateException("Backup konnte nicht angelegt werden: " + safeName);
                existingRenamed = true; backup = partsRoot.findFile(backupName);
            }
            if (!temp.renameTo(safeName)) throw new IllegalStateException("Neue Datei konnte nicht aktiviert werden: " + safeName);
            DocumentFile finalFile = partsRoot.findFile(safeName);
            if (finalFile == null || !expectedHash.equals(sha256(finalFile))) throw new IllegalStateException("Endprüfung fehlgeschlagen: " + safeName);
            if (backup != null) backup.delete();
        } catch (Exception error) {
            DocumentFile currentFinal = partsRoot.findFile(safeName);
            if (currentFinal != null && (existing == null || existingRenamed)) currentFinal.delete();
            DocumentFile tempLeft = partsRoot.findFile(tempName); if (tempLeft != null) tempLeft.delete();
            if (backup == null && existingRenamed) backup = partsRoot.findFile(backupName);
            if (backup != null) backup.renameTo(safeName);
            throw error;
        }
    }

    private void copyFileToDocument(File source, DocumentFile target) throws Exception {
        long written = 0; byte[] buffer = new byte[32 * 1024];
        try (InputStream in = new FileInputStream(source); OutputStream out = getContentResolver().openOutputStream(target.getUri(), "w")) {
            if (out == null) throw new IllegalStateException("Zieldatei konnte nicht beschrieben werden.");
            int read; while ((read = in.read(buffer)) != -1) { written += read; if (written > MAX_SINGLE_PACK_BYTES) throw new IllegalStateException("Paket größer als 300 MB."); out.write(buffer, 0, read); }
            out.flush();
        }
        if (written != source.length()) throw new IllegalStateException("Bytevergleich fehlgeschlagen: " + source.getName());
    }

    private String sha256(File file) throws Exception { try (InputStream in = new FileInputStream(file)) { return sha256(in); } }
    private String sha256(DocumentFile file) throws Exception {
        try (InputStream in = getContentResolver().openInputStream(file.getUri())) {
            if (in == null) throw new IllegalStateException("Datei konnte für SHA-256 nicht gelesen werden."); return sha256(in);
        }
    }
    private String sha256(InputStream in) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256"); byte[] buffer = new byte[32 * 1024]; int read;
        while ((read = in.read(buffer)) != -1) digest.update(buffer, 0, read);
        byte[] hash = digest.digest(); StringBuilder hex = new StringBuilder(hash.length * 2);
        for (byte b : hash) hex.append(String.format(Locale.ROOT, "%02x", b)); return hex.toString();
    }

    private void installationSuccess(int installed, int updated, int skipped) {
        primaryButton.setVisibility(View.GONE); openGameButton.setVisibility(View.VISIBLE);
        status.setTextColor(GREEN); status.setText("✓ Mod erfolgreich installiert");
        details.setText(sourceName + "\n\n✓ " + stagedPacks.size() + " Datei(en) geprüft"
                + "\n✓ " + installed + " neu installiert\n✓ " + updated + " aktualisiert\n✓ " + skipped + " unverändert/übersprungen"
                + "\n✓ SHA-256-Endprüfung bestanden\n\nSpaceflight Simulator → Mods → Custom Assets → Parts");
        new Handler(Looper.getMainLooper()).postDelayed(this::launchSpaceflight, 700);
    }

    private void launchSpaceflight() {
        Intent launch = getPackageManager().getLaunchIntentForPackage(SFS_PACKAGE);
        if (launch != null) try { startActivity(launch); return; } catch (RuntimeException ignored) { }
        Toast.makeText(this, "Spaceflight Simulator konnte nicht automatisch geöffnet werden.", Toast.LENGTH_LONG).show();
    }

    private File copyUriToStage(Uri uri, String name) throws Exception {
        File outFile = uniqueStageFile(name); long written = 0; byte[] buffer = new byte[32 * 1024];
        try (InputStream in = getContentResolver().openInputStream(uri); OutputStream out = new FileOutputStream(outFile)) {
            if (in == null) throw new IllegalStateException("Datei konnte nicht geöffnet werden.");
            int read; while ((read = in.read(buffer)) != -1) { written += read; if (written > MAX_SINGLE_PACK_BYTES) throw new IllegalStateException("Paket größer als 300 MB."); out.write(buffer, 0, read); }
        }
        return outFile;
    }

    private File uniqueStageFile(String requested) {
        File dir = stageDir(); String safe = sanitizeFileName(requested); File candidate = new File(dir, safe); int index = 2;
        while (candidate.exists()) {
            int dot = safe.lastIndexOf('.'); String base = dot > 0 ? safe.substring(0, dot) : safe; String ext = dot > 0 ? safe.substring(dot) : "";
            candidate = new File(dir, base + " (" + index++ + ")" + ext);
        }
        return candidate;
    }

    private File stageDir() {
        File dir = new File(getCacheDir(), "sfs-pack-stage");
        if (!dir.exists() && !dir.mkdirs()) throw new IllegalStateException("Temporärer Ordner konnte nicht erstellt werden."); return dir;
    }
    private void clearStage() { stagedPacks.clear(); File[] files = stageDir().listFiles(); if (files != null) for (File file : files) file.delete(); }

    private boolean isAppInstalled(String packageName) {
        try {
            ApplicationInfo info;
            if (Build.VERSION.SDK_INT >= 33) info = getPackageManager().getApplicationInfo(packageName, PackageManager.ApplicationInfoFlags.of(0));
            else { @SuppressWarnings("deprecation") ApplicationInfo legacy = getPackageManager().getApplicationInfo(packageName, 0); info = legacy; }
            return info.enabled;
        } catch (PackageManager.NameNotFoundException error) { return false; }
    }

    private String queryDisplayName(Uri uri) {
        try (Cursor cursor = getContentResolver().query(uri, new String[] {OpenableColumns.DISPLAY_NAME}, null, null, null)) {
            if (cursor != null && cursor.moveToFirst()) { int index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME); if (index >= 0) { String value = cursor.getString(index); if (value != null && !value.isBlank()) return value; } }
        } catch (Exception ignored) { }
        String fallback = uri.getLastPathSegment(); return fallback == null ? "Spaceflight-Mod.pack" : fallback;
    }

    private static String safeEntryName(String raw) {
        String name = raw == null ? "" : raw.replace('\\', '/');
        if (name.startsWith("/") || name.contains("../") || name.equals("..") || name.matches("^[A-Za-z]:.*")) throw new IllegalStateException("Unsicherer ZIP-Pfad blockiert: " + name);
        return name;
    }
    private static boolean isPcOnlyExecutable(String lower) {
        String[] blocked = {".apk", ".aab", ".exe", ".dll", ".dex", ".so", ".jar", ".class", ".msi", ".bat", ".cmd", ".ps1", ".sh", ".scr", ".com"};
        for (String ext : blocked) if (lower.endsWith(ext)) return true; return false;
    }
    private static String leafName(String path) { int slash = path.lastIndexOf('/'); return sanitizeFileName(slash >= 0 ? path.substring(slash + 1) : path); }
    private static String sanitizeFileName(String value) {
        String safe = value.replaceAll("[^A-Za-z0-9._() -]", "_").trim();
        if (safe.isEmpty()) safe = "TAYVORIQ.pack";
        if (!safe.toLowerCase(Locale.ROOT).endsWith(".pack")) safe += ".pack";
        return safe;
    }
    private static String readableBytes(long bytes) {
        if (bytes < 1024) return bytes + " B"; double kb = bytes / 1024.0;
        if (kb < 1024) return String.format(Locale.GERMANY, "%.1f KB", kb); return String.format(Locale.GERMANY, "%.1f MB", kb / 1024.0);
    }

    private void fail(String message) {
        status.setTextColor(RED); status.setText("Installation nicht möglich"); details.setText(message); openGameButton.setVisibility(View.GONE);
        Toast.makeText(this, message, Toast.LENGTH_LONG).show();
    }
    private TextView text(String value, int sizeSp, int color, boolean bold) {
        TextView view = new TextView(this); view.setText(value); view.setTextSize(sizeSp); view.setTextColor(color); view.setLineSpacing(0f, 1.14f);
        if (bold) view.setTypeface(Typeface.DEFAULT, Typeface.BOLD); return view;
    }
    private Button button(String value, int color) {
        Button button = new Button(this); button.setText(value); button.setTextColor(Color.WHITE); button.setTextSize(14); button.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        button.setMinHeight(dp(54)); button.setBackground(rounded(color, 16)); return button;
    }
    private GradientDrawable rounded(int color, int radiusDp) {
        GradientDrawable drawable = new GradientDrawable(); drawable.setColor(color); drawable.setCornerRadius(dp(radiusDp)); drawable.setStroke(dp(1), Color.rgb(45, 62, 91)); return drawable;
    }
    private LinearLayout.LayoutParams matchWrap() { return new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT); }
    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
}
