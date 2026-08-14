package com.tayvoriq.addonmanager;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.ComponentName;
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
import android.provider.OpenableColumns;
import android.view.Gravity;
import android.view.ViewGroup;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import androidx.core.content.FileProvider;
import androidx.documentfile.provider.DocumentFile;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.Locale;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

/** Receives Minecraft Bedrock files and safe ZIP packages for Spaceflight Simulator. */
public final class FileImportActivity extends Activity {
    private static final String MINECRAFT_PACKAGE = "com.mojang.minecraftpe";
    private static final String MINECRAFT_MAIN_ACTIVITY = "com.mojang.minecraftpe.MainActivity";
    private static final String SPACEFLIGHT_PACKAGE = "com.StefMorojna.SpaceflightSimulator";

    private static final int PICK_SPACEFLIGHT_TARGET_FOLDER = 1601;
    private static final String PREFS = "universal_import";
    private static final String PREF_SFS_BLUEPRINT_TREE = "spaceflight_blueprints_tree";

    private static final long MAX_UNPACKED_BYTES = 750L * 1024L * 1024L;
    private static final long MAX_STAGED_FILE_BYTES = 300L * 1024L * 1024L;
    private static final int MAX_ENTRIES = 10_000;
    private static final int MAX_BLUEPRINT_BYTES = 32 * 1024 * 1024;

    private static final int BG = Color.rgb(5, 8, 18);
    private static final int SURFACE = Color.rgb(13, 19, 33);
    private static final int TEXT = Color.rgb(245, 248, 255);
    private static final int MUTED = Color.rgb(158, 169, 192);
    private static final int CYAN = Color.rgb(0, 222, 235);
    private static final int RED = Color.rgb(255, 82, 106);

    private Uri fileUri;
    private String fileName;
    private TextView status;
    private SpaceflightPayload pendingSpaceflight;
    private Uri pendingGenericSpaceflightZipUri;
    private String pendingGenericSpaceflightZipName;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().setStatusBarColor(BG);
        getWindow().setNavigationBarColor(BG);
        setContentView(buildScreen());
        receive(getIntent());
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        receive(intent);
    }

    private LinearLayout buildScreen() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER);
        root.setPadding(dp(28), dp(32), dp(28), dp(32));
        root.setBackgroundColor(BG);

        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setGravity(Gravity.CENTER);
        card.setPadding(dp(22), dp(24), dp(22), dp(24));
        card.setBackground(rounded(SURFACE, 24));
        root.addView(card, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT));

        ImageView logo = new ImageView(this);
        logo.setImageResource(R.drawable.ic_launcher_foreground);
        logo.setScaleType(ImageView.ScaleType.CENTER_INSIDE);
        card.addView(logo, new LinearLayout.LayoutParams(dp(160), dp(160)));

        TextView brand = text("TAYVORIQ", 28, TEXT, true);
        brand.setGravity(Gravity.CENTER);
        card.addView(brand, matchWrap());

        TextView subtitle = text("UNIVERSAL IMPORT", 12, CYAN, true);
        subtitle.setGravity(Gravity.CENTER);
        subtitle.setPadding(0, dp(3), 0, dp(18));
        card.addView(subtitle, matchWrap());

        status = text("Datei wird vorbereitet …", 17, TEXT, true);
        status.setGravity(Gravity.CENTER);
        status.setPadding(dp(10), dp(12), dp(10), dp(12));
        card.addView(status, matchWrap());

        TextView info = text(
                "Alles bleibt lokal. ZIPs werden sicher geprüft. Eindeutige Pakete werden automatisch erkannt; bei anderen ZIPs wählst du das Zielspiel selbst.",
                13, MUTED, false);
        info.setGravity(Gravity.CENTER);
        info.setPadding(dp(8), dp(8), dp(8), 0);
        card.addView(info, matchWrap());
        return root;
    }

    private void receive(Intent intent) {
        if (intent == null) {
            fail("Keine Datei empfangen.");
            return;
        }

        Uri uri = null;
        if (Intent.ACTION_VIEW.equals(intent.getAction())) {
            uri = intent.getData();
        } else if (Intent.ACTION_SEND.equals(intent.getAction())) {
            if (Build.VERSION.SDK_INT >= 33) {
                uri = intent.getParcelableExtra(Intent.EXTRA_STREAM, Uri.class);
            } else {
                @SuppressWarnings("deprecation")
                Uri legacy = intent.getParcelableExtra(Intent.EXTRA_STREAM);
                uri = legacy;
            }
        }

        if (uri == null) {
            fail("Die Datei konnte nicht gelesen werden.");
            return;
        }

        fileUri = uri;
        fileName = queryDisplayName(uri);
        String lower = fileName.toLowerCase(Locale.ROOT);
        status.setTextColor(TEXT);

        if (isMinecraftExtension(lower)) {
            status.setText(fileName + "\n\nMinecraft Bedrock wird geöffnet …");
            new Handler(Looper.getMainLooper()).postDelayed(() -> openMinecraft(fileName), 200);
            return;
        }

        if (lower.endsWith(".zip")) {
            status.setText(fileName + "\n\nZIP wird lokal geprüft …");
            final Uri zipUri = uri;
            final String zipName = fileName;
            new Thread(() -> analyzeZip(zipUri, zipName), "universal-zip-analysis").start();
            return;
        }

        fail("Nicht unterstützt: " + fileName + "\nErlaubt sind .mcaddon, .mcpack, .mcworld und .zip.");
    }

    private void analyzeZip(Uri source, String originalName) {
        try {
            ZipInspection inspection = inspectZip(source);
            if (inspection.nestedMinecraftEntry != null) {
                File staged = extractEntryToCache(source, inspection.nestedMinecraftEntry);
                Uri stagedUri = shareUri(staged);
                runOnUiThread(() -> {
                    status.setTextColor(TEXT);
                    fileUri = stagedUri;
                    fileName = staged.getName();
                    status.setText("Minecraft Bedrock erkannt\n\n" + staged.getName() + " wird importiert …");
                    openMinecraft(fileName);
                });
                return;
            }

            if (inspection.minecraftManifestCount > 0 || inspection.minecraftLevelDat) {
                String extension = inspection.minecraftLevelDat
                        ? ".mcworld"
                        : (inspection.minecraftManifestCount > 1 ? ".mcaddon" : ".mcpack");
                File staged = copyUriToCache(source, stripExtension(originalName) + extension);
                Uri stagedUri = shareUri(staged);
                runOnUiThread(() -> {
                    status.setTextColor(TEXT);
                    fileUri = stagedUri;
                    fileName = staged.getName();
                    status.setText("Minecraft Bedrock ZIP erkannt\n\nPaket wird als " + extension + " übergeben …");
                    openMinecraft(fileName);
                });
                return;
            }

            if (inspection.spaceflightBlueprintEntry != null) {
                SpaceflightPayload payload = extractSpaceflightPayload(source, inspection, originalName);
                runOnUiThread(() -> prepareSpaceflightBlueprintImport(payload));
                return;
            }

            runOnUiThread(() -> showUnknownZipOptions(source, originalName, inspection.entries, inspection.unpackedBytes));
        } catch (Exception error) {
            String message = error.getMessage() == null ? error.getClass().getSimpleName() : error.getMessage();
            runOnUiThread(() -> fail("ZIP-Prüfung fehlgeschlagen: " + message));
        }
    }

    private void showUnknownZipOptions(Uri source, String originalName, int entries, long unpackedBytes) {
        status.setTextColor(CYAN);
        status.setText(
                "ZIP sicher geprüft\n\n" + originalName
                        + "\n" + entries + " Einträge · " + readableBytes(unpackedBytes)
                        + "\n\nDer Inhalt ist sicher lesbar, aber nicht eindeutig einem bekannten Pakettyp zuzuordnen.");

        new AlertDialog.Builder(this)
                .setTitle("ZIP-Ziel auswählen")
                .setMessage("Die Datei wird nicht mehr pauschal abgelehnt. Wähle, wofür du dieses ZIP verwenden möchtest.")
                .setPositiveButton("SPACEFLIGHT SIMULATOR", (dialog, which) -> prepareGenericSpaceflightZipImport(source, originalName))
                .setNeutralButton("MINECRAFT VERSUCHEN", (dialog, which) -> stageUnknownZipAsMinecraft(source, originalName))
                .setNegativeButton("ABBRECHEN", null)
                .show();
    }

    private void stageUnknownZipAsMinecraft(Uri source, String originalName) {
        status.setTextColor(TEXT);
        status.setText("Minecraft-Versuch wird vorbereitet …");
        new Thread(() -> {
            try {
                File staged = copyUriToCache(source, stripExtension(originalName) + ".mcpack");
                Uri stagedUri = shareUri(staged);
                runOnUiThread(() -> {
                    fileUri = stagedUri;
                    fileName = staged.getName();
                    status.setText("ZIP wird testweise als Minecraft-Pack übergeben …");
                    openMinecraft(fileName);
                });
            } catch (Exception error) {
                runOnUiThread(() -> fail("Minecraft-Versuch fehlgeschlagen: " + error.getMessage()));
            }
        }, "minecraft-zip-fallback").start();
    }

    private void prepareGenericSpaceflightZipImport(Uri source, String originalName) {
        if (!isAppInstalled(SPACEFLIGHT_PACKAGE)) {
            fail("Spaceflight Simulator ist auf diesem Android-Gerät nicht installiert.");
            return;
        }
        pendingSpaceflight = null;
        pendingGenericSpaceflightZipUri = source;
        pendingGenericSpaceflightZipName = originalName;
        status.setTextColor(TEXT);
        status.setText(
                "Spaceflight Simulator gewählt.\n\nWähle jetzt den Zielordner innerhalb von Spaceflight Simulator aus. TAYVORIQ entpackt das ZIP dort sicher und behält die enthaltene Ordnerstruktur bei.");
        openSpaceflightFolderPicker();
    }

    private ZipInspection inspectZip(Uri source) throws Exception {
        InputStream raw = getContentResolver().openInputStream(source);
        if (raw == null) throw new IllegalStateException("ZIP konnte nicht geöffnet werden.");

        int entries = 0;
        long unpacked = 0;
        int manifests = 0;
        boolean levelDat = false;
        String nestedMinecraft = null;
        String blueprint = null;
        String version = null;
        String blueprintParent = null;
        byte[] buffer = new byte[32 * 1024];

        try (raw; ZipInputStream zip = new ZipInputStream(raw)) {
            ZipEntry entry;
            while ((entry = zip.getNextEntry()) != null) {
                entries++;
                if (entries > MAX_ENTRIES) throw new IllegalStateException("Zu viele Dateien im ZIP.");
                String name = safeEntryName(entry.getName());
                String lower = name.toLowerCase(Locale.ROOT);

                if (isBlockedExecutable(lower)) {
                    throw new IllegalStateException("Ausführbare Datei im ZIP blockiert: " + name);
                }
                if (isMinecraftExtension(lower) && nestedMinecraft == null) {
                    nestedMinecraft = name;
                }
                if (lower.equals("manifest.json") || lower.endsWith("/manifest.json")) manifests++;
                if (lower.equals("level.dat") || lower.endsWith("/level.dat")) levelDat = true;
                if ((lower.equals("blueprint.txt") || lower.endsWith("/blueprint.txt")) && blueprint == null) {
                    blueprint = name;
                    int slash = name.lastIndexOf('/');
                    blueprintParent = slash >= 0 ? name.substring(0, slash + 1) : "";
                }
                if (lower.equals("version.txt") || lower.endsWith("/version.txt")) {
                    if (version == null) version = name;
                    if (blueprintParent != null && name.startsWith(blueprintParent)) version = name;
                }

                int read;
                while ((read = zip.read(buffer)) != -1) {
                    unpacked += read;
                    if (unpacked > MAX_UNPACKED_BYTES) {
                        throw new IllegalStateException("ZIP ist entpackt größer als 750 MB.");
                    }
                }
                zip.closeEntry();
            }
        }

        if (entries == 0) throw new IllegalStateException("Leeres oder ungültiges ZIP.");
        return new ZipInspection(nestedMinecraft, manifests, levelDat, blueprint, version, entries, unpacked);
    }

    private File extractEntryToCache(Uri source, String wantedEntry) throws Exception {
        InputStream raw = getContentResolver().openInputStream(source);
        if (raw == null) throw new IllegalStateException("ZIP konnte nicht geöffnet werden.");
        File folder = importsFolder();
        File destination = new File(folder, leafName(wantedEntry));
        long written = 0;
        byte[] buffer = new byte[32 * 1024];

        try (raw; ZipInputStream zip = new ZipInputStream(raw)) {
            ZipEntry entry;
            while ((entry = zip.getNextEntry()) != null) {
                String name = safeEntryName(entry.getName());
                if (!name.equals(wantedEntry)) continue;
                try (OutputStream out = new FileOutputStream(destination)) {
                    int read;
                    while ((read = zip.read(buffer)) != -1) {
                        written += read;
                        if (written > MAX_STAGED_FILE_BYTES) throw new IllegalStateException("Paket größer als 300 MB.");
                        out.write(buffer, 0, read);
                    }
                }
                return destination;
            }
        }
        throw new IllegalStateException("Enthaltenes Minecraft-Paket wurde nicht wiedergefunden.");
    }

    private File copyUriToCache(Uri source, String targetName) throws Exception {
        File destination = new File(importsFolder(), sanitizeFileName(targetName));
        InputStream in = getContentResolver().openInputStream(source);
        if (in == null) throw new IllegalStateException("Datei konnte nicht geöffnet werden.");
        long written = 0;
        byte[] buffer = new byte[32 * 1024];
        try (in; OutputStream out = new FileOutputStream(destination)) {
            int read;
            while ((read = in.read(buffer)) != -1) {
                written += read;
                if (written > MAX_STAGED_FILE_BYTES) throw new IllegalStateException("Paket größer als 300 MB.");
                out.write(buffer, 0, read);
            }
        }
        return destination;
    }

    private SpaceflightPayload extractSpaceflightPayload(Uri source, ZipInspection inspection, String originalName) throws Exception {
        byte[] blueprint = null;
        byte[] version = null;
        InputStream raw = getContentResolver().openInputStream(source);
        if (raw == null) throw new IllegalStateException("ZIP konnte nicht geöffnet werden.");

        try (raw; ZipInputStream zip = new ZipInputStream(raw)) {
            ZipEntry entry;
            while ((entry = zip.getNextEntry()) != null) {
                String name = safeEntryName(entry.getName());
                if (name.equals(inspection.spaceflightBlueprintEntry)) {
                    blueprint = readSmallEntry(zip, MAX_BLUEPRINT_BYTES);
                } else if (inspection.spaceflightVersionEntry != null && name.equals(inspection.spaceflightVersionEntry)) {
                    version = readSmallEntry(zip, 1024 * 1024);
                }
                zip.closeEntry();
            }
        }

        if (blueprint == null) throw new IllegalStateException("Blueprint.txt konnte nicht extrahiert werden.");
        return new SpaceflightPayload(stripExtension(originalName), blueprint, version);
    }

    private byte[] readSmallEntry(ZipInputStream zip, int maxBytes) throws Exception {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buffer = new byte[16 * 1024];
        int read;
        while ((read = zip.read(buffer)) != -1) {
            if (out.size() + read > maxBytes) throw new IllegalStateException("Blueprint-Datei ungewöhnlich groß.");
            out.write(buffer, 0, read);
        }
        return out.toByteArray();
    }

    private void prepareSpaceflightBlueprintImport(SpaceflightPayload payload) {
        pendingGenericSpaceflightZipUri = null;
        pendingGenericSpaceflightZipName = null;
        pendingSpaceflight = payload;
        if (!isAppInstalled(SPACEFLIGHT_PACKAGE)) {
            fail("Spaceflight Simulator ist auf diesem Android-Gerät nicht installiert.");
            return;
        }

        String saved = getSharedPreferences(PREFS, MODE_PRIVATE).getString(PREF_SFS_BLUEPRINT_TREE, null);
        if (saved != null) {
            try {
                Uri treeUri = Uri.parse(saved);
                DocumentFile root = DocumentFile.fromTreeUri(this, treeUri);
                if (root != null && root.canWrite()) {
                    importSpaceflightBlueprintInto(root);
                    return;
                }
            } catch (Exception ignored) { }
        }

        status.setTextColor(TEXT);
        status.setText(
                "Spaceflight Simulator Blueprint erkannt.\n\nEinmalige Einrichtung: Wähle jetzt den Blueprints-Ordner von Spaceflight Simulator.");
        openSpaceflightFolderPicker();
    }

    private void openSpaceflightFolderPicker() {
        Intent picker = new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE);
        picker.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION
                | Intent.FLAG_GRANT_WRITE_URI_PERMISSION
                | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION
                | Intent.FLAG_GRANT_PREFIX_URI_PERMISSION);
        startActivityForResult(picker, PICK_SPACEFLIGHT_TARGET_FOLDER);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != PICK_SPACEFLIGHT_TARGET_FOLDER) return;
        if (resultCode != RESULT_OK || data == null || data.getData() == null) {
            fail("Spaceflight-Zielordner wurde nicht ausgewählt.");
            return;
        }
        Uri treeUri = data.getData();
        try {
            int flags = data.getFlags() & (Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
            getContentResolver().takePersistableUriPermission(treeUri, flags);
            DocumentFile root = DocumentFile.fromTreeUri(this, treeUri);
            if (root == null || !root.canWrite()) throw new IllegalStateException("Ordner ist nicht beschreibbar.");

            if (pendingGenericSpaceflightZipUri != null) {
                importGenericSpaceflightZipInto(root);
            } else if (pendingSpaceflight != null) {
                getSharedPreferences(PREFS, MODE_PRIVATE).edit().putString(PREF_SFS_BLUEPRINT_TREE, treeUri.toString()).apply();
                importSpaceflightBlueprintInto(root);
            } else {
                throw new IllegalStateException("Kein Spaceflight-Import vorbereitet.");
            }
        } catch (Exception error) {
            fail("Spaceflight-Ordner konnte nicht verwendet werden: " + error.getMessage());
        }
    }

    private void importSpaceflightBlueprintInto(DocumentFile blueprintsRoot) throws Exception {
        if (pendingSpaceflight == null) throw new IllegalStateException("Kein Blueprint vorbereitet.");
        String folderName = sanitizeFolderName(pendingSpaceflight.name);
        DocumentFile target = blueprintsRoot.findFile(folderName);
        if (target == null || !target.isDirectory()) target = blueprintsRoot.createDirectory(folderName);
        if (target == null) throw new IllegalStateException("Blueprint-Unterordner konnte nicht erstellt werden.");

        writeDocument(target, "Blueprint.txt", pendingSpaceflight.blueprint, "text/plain");
        if (pendingSpaceflight.version != null) {
            writeDocument(target, "Version.txt", pendingSpaceflight.version, "text/plain");
        }

        status.setTextColor(TEXT);
        status.setText(
                "Spaceflight Blueprint installiert\n\n" + folderName + " wurde im gewählten Blueprints-Ordner abgelegt. Spaceflight Simulator wird geöffnet …");
        pendingSpaceflight = null;
        launchSpaceflight();
    }

    private void importGenericSpaceflightZipInto(DocumentFile targetRoot) throws Exception {
        Uri source = pendingGenericSpaceflightZipUri;
        String originalName = pendingGenericSpaceflightZipName;
        if (source == null) throw new IllegalStateException("Kein Spaceflight-ZIP vorbereitet.");

        InputStream raw = getContentResolver().openInputStream(source);
        if (raw == null) throw new IllegalStateException("ZIP konnte nicht geöffnet werden.");
        byte[] buffer = new byte[32 * 1024];
        long unpacked = 0;
        int entries = 0;

        try (raw; ZipInputStream zip = new ZipInputStream(raw)) {
            ZipEntry entry;
            while ((entry = zip.getNextEntry()) != null) {
                entries++;
                if (entries > MAX_ENTRIES) throw new IllegalStateException("Zu viele Dateien im ZIP.");
                String name = safeEntryName(entry.getName());
                String lower = name.toLowerCase(Locale.ROOT);
                if (isBlockedExecutable(lower)) {
                    throw new IllegalStateException("Ausführbare Datei im ZIP blockiert: " + name);
                }

                if (entry.isDirectory() || name.endsWith("/")) {
                    ensureDirectory(targetRoot, trimTrailingSlash(name));
                    zip.closeEntry();
                    continue;
                }

                int slash = name.lastIndexOf('/');
                String parentPath = slash >= 0 ? name.substring(0, slash) : "";
                String leaf = slash >= 0 ? name.substring(slash + 1) : name;
                DocumentFile parent = ensureDirectory(targetRoot, parentPath);
                DocumentFile existing = parent.findFile(leaf);
                if (existing != null) existing.delete();
                DocumentFile output = parent.createFile("application/octet-stream", leaf);
                if (output == null) throw new IllegalStateException("Datei konnte nicht erstellt werden: " + name);

                try (OutputStream out = getContentResolver().openOutputStream(output.getUri(), "w")) {
                    if (out == null) throw new IllegalStateException("Datei konnte nicht geschrieben werden: " + name);
                    int read;
                    while ((read = zip.read(buffer)) != -1) {
                        unpacked += read;
                        if (unpacked > MAX_UNPACKED_BYTES) {
                            throw new IllegalStateException("ZIP ist entpackt größer als 750 MB.");
                        }
                        out.write(buffer, 0, read);
                    }
                }
                zip.closeEntry();
            }
        }

        pendingGenericSpaceflightZipUri = null;
        pendingGenericSpaceflightZipName = null;
        status.setTextColor(TEXT);
        status.setText(
                "Spaceflight ZIP importiert\n\n" + originalName + " wurde mit " + entries + " Einträgen in den gewählten Zielordner entpackt. Spaceflight Simulator wird geöffnet …");
        launchSpaceflight();
    }

    private DocumentFile ensureDirectory(DocumentFile root, String path) {
        if (path == null || path.isBlank()) return root;
        DocumentFile current = root;
        String[] parts = path.split("/");
        for (String part : parts) {
            if (part == null || part.isBlank()) continue;
            String safe = sanitizeFolderName(part);
            DocumentFile next = current.findFile(safe);
            if (next == null || !next.isDirectory()) {
                next = current.createDirectory(safe);
            }
            if (next == null) throw new IllegalStateException("Ordner konnte nicht erstellt werden: " + safe);
            current = next;
        }
        return current;
    }

    private void writeDocument(DocumentFile folder, String name, byte[] data, String mime) throws Exception {
        DocumentFile existing = folder.findFile(name);
        if (existing != null) existing.delete();
        DocumentFile file = folder.createFile(mime, name);
        if (file == null) throw new IllegalStateException(name + " konnte nicht erstellt werden.");
        try (OutputStream out = getContentResolver().openOutputStream(file.getUri(), "w")) {
            if (out == null) throw new IllegalStateException(name + " konnte nicht beschrieben werden.");
            out.write(data);
        }
    }

    private void launchSpaceflight() {
        Intent launch = getPackageManager().getLaunchIntentForPackage(SPACEFLIGHT_PACKAGE);
        if (launch != null && tryStart(launch)) return;
        fail("Dateien wurden abgelegt, Spaceflight Simulator konnte aber nicht automatisch gestartet werden.");
    }

    private void openMinecraft(String currentFileName) {
        if (!isAppInstalled(MINECRAFT_PACKAGE)) {
            fail("Minecraft Bedrock ist auf diesem Gerät nicht installiert oder für Android nicht sichtbar.");
            return;
        }

        try {
            grantUriPermission(MINECRAFT_PACKAGE, fileUri, Intent.FLAG_GRANT_READ_URI_PERMISSION);
        } catch (Exception ignored) { }

        Intent explicit = legacyViewIntent();
        explicit.setComponent(new ComponentName(MINECRAFT_PACKAGE, MINECRAFT_MAIN_ACTIVITY));
        if (tryStart(explicit)) {
            finish();
            return;
        }

        Intent legacyPackageIntent = legacyViewIntent();
        legacyPackageIntent.setPackage(MINECRAFT_PACKAGE);
        if (tryStart(legacyPackageIntent)) {
            finish();
            return;
        }

        for (String mime : preferredMimes(currentFileName)) {
            if ("application/octet-stream".equals(mime)) continue;
            Intent alternate = new Intent(Intent.ACTION_VIEW);
            alternate.setDataAndType(fileUri, mime);
            alternate.setPackage(MINECRAFT_PACKAGE);
            alternate.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NO_HISTORY);
            if (tryStart(alternate)) {
                finish();
                return;
            }
        }

        Intent launch = getPackageManager().getLaunchIntentForPackage(MINECRAFT_PACKAGE);
        if (launch != null && tryStart(launch)) {
            fail("Minecraft wurde geöffnet, hat den Datei-Import aber nicht angenommen. Bitte die Datei erneut antippen.");
            return;
        }
        fail("Minecraft wurde gefunden, konnte die Datei aber nicht übernehmen.");
    }

    private Intent legacyViewIntent() {
        Intent intent = new Intent(Intent.ACTION_VIEW);
        intent.setDataAndType(fileUri, "application/octet-stream");
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NO_HISTORY);
        return intent;
    }

    private boolean tryStart(Intent intent) {
        try {
            startActivity(intent);
            return true;
        } catch (ActivityNotFoundException | SecurityException ignored) {
            return false;
        } catch (RuntimeException ignored) {
            return false;
        }
    }

    private boolean isAppInstalled(String packageName) {
        try {
            ApplicationInfo info;
            if (Build.VERSION.SDK_INT >= 33) {
                info = getPackageManager().getApplicationInfo(
                        packageName,
                        PackageManager.ApplicationInfoFlags.of(0));
            } else {
                @SuppressWarnings("deprecation")
                ApplicationInfo legacy = getPackageManager().getApplicationInfo(packageName, 0);
                info = legacy;
            }
            return info.enabled;
        } catch (PackageManager.NameNotFoundException error) {
            return false;
        }
    }

    private Uri shareUri(File file) {
        return FileProvider.getUriForFile(this, getPackageName() + ".files", file);
    }

    private File importsFolder() {
        File folder = new File(getCacheDir(), "imports");
        if (!folder.exists() && !folder.mkdirs()) {
            throw new IllegalStateException("Import-Cache konnte nicht erstellt werden.");
        }
        return folder;
    }

    private static String safeEntryName(String raw) {
        String name = raw == null ? "" : raw.replace('\\', '/');
        if (name.startsWith("/") || name.contains("../") || name.equals("..") || name.matches("^[A-Za-z]:.*")) {
            throw new IllegalStateException("Unsicherer ZIP-Pfad blockiert: " + name);
        }
        return name;
    }

    private static boolean isBlockedExecutable(String lower) {
        String[] blocked = {".apk", ".aab", ".exe", ".dll", ".dex", ".so", ".jar", ".class", ".msi", ".bat", ".cmd", ".ps1", ".sh", ".scr", ".com"};
        for (String ext : blocked) if (lower.endsWith(ext)) return true;
        return false;
    }

    private static boolean isMinecraftExtension(String lower) {
        return lower.endsWith(".mcaddon") || lower.endsWith(".mcpack") || lower.endsWith(".mcworld");
    }

    private static String[] preferredMimes(String currentFileName) {
        String lower = currentFileName.toLowerCase(Locale.ROOT);
        if (lower.endsWith(".mcaddon")) return new String[] {"application/octet-stream", "application/mcaddon", "application/zip"};
        if (lower.endsWith(".mcpack")) return new String[] {"application/octet-stream", "application/mcpack", "application/zip"};
        return new String[] {"application/octet-stream", "application/mcworld", "application/zip"};
    }

    private String queryDisplayName(Uri uri) {
        try (Cursor cursor = getContentResolver().query(
                uri, new String[] {OpenableColumns.DISPLAY_NAME}, null, null, null)) {
            if (cursor != null && cursor.moveToFirst()) {
                int index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME);
                if (index >= 0) {
                    String value = cursor.getString(index);
                    if (value != null && !value.isBlank()) return value;
                }
            }
        } catch (Exception ignored) { }
        String fallback = uri.getLastPathSegment();
        return fallback == null ? "Import-Datei" : fallback;
    }

    private static String stripExtension(String name) {
        int dot = name.lastIndexOf('.');
        return dot > 0 ? name.substring(0, dot) : name;
    }

    private static String leafName(String path) {
        int slash = path.lastIndexOf('/');
        return sanitizeFileName(slash >= 0 ? path.substring(slash + 1) : path);
    }

    private static String trimTrailingSlash(String value) {
        String result = value;
        while (result.endsWith("/")) result = result.substring(0, result.length() - 1);
        return result;
    }

    private static String sanitizeFileName(String value) {
        String safe = value.replaceAll("[^A-Za-z0-9._ -]", "_").trim();
        return safe.isEmpty() ? "import.bin" : safe;
    }

    private static String sanitizeFolderName(String value) {
        String safe = stripExtension(value).replaceAll("[^A-Za-z0-9._ -]", "_").trim();
        return safe.isEmpty() ? "TAYVORIQ Import" : safe;
    }

    private static String readableBytes(long bytes) {
        if (bytes < 1024) return bytes + " B";
        double kb = bytes / 1024.0;
        if (kb < 1024) return String.format(Locale.GERMANY, "%.1f KB", kb);
        double mb = kb / 1024.0;
        return String.format(Locale.GERMANY, "%.1f MB", mb);
    }

    private void fail(String message) {
        status.setText(message);
        status.setTextColor(RED);
        Toast.makeText(this, message, Toast.LENGTH_LONG).show();
    }

    private TextView text(String value, int sizeSp, int color, boolean bold) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(sizeSp);
        view.setTextColor(color);
        view.setLineSpacing(0f, 1.12f);
        if (bold) view.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        return view;
    }

    private GradientDrawable rounded(int color, int radiusDp) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(color);
        drawable.setCornerRadius(dp(radiusDp));
        drawable.setStroke(dp(1), Color.rgb(45, 62, 91));
        return drawable;
    }

    private LinearLayout.LayoutParams matchWrap() {
        return new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT);
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private record ZipInspection(
            String nestedMinecraftEntry,
            int minecraftManifestCount,
            boolean minecraftLevelDat,
            String spaceflightBlueprintEntry,
            String spaceflightVersionEntry,
            int entries,
            long unpackedBytes) { }

    private record SpaceflightPayload(String name, byte[] blueprint, byte[] version) { }
}
