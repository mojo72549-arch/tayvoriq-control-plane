package com.tayvoriq.addonmanager;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.res.AssetFileDescriptor;
import android.database.Cursor;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Bundle;
import android.provider.OpenableColumns;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import com.google.android.gms.ads.AdRequest;
import com.google.android.gms.ads.AdSize;
import com.google.android.gms.ads.AdView;
import com.google.android.gms.ads.MobileAds;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

public final class MainActivity extends Activity {
    private static final int PICK_ADDON = 1201;
    private static final long MAX_FILE_BYTES = 300L * 1024L * 1024L;
    private static final long MAX_UNPACKED_BYTES = 750L * 1024L * 1024L;
    private static final int MAX_ENTRIES = 10_000;
    private static final int MAX_MANIFEST_BYTES = 2 * 1024 * 1024;

    private static final int COLOR_BG = Color.rgb(246, 247, 251);
    private static final int COLOR_TEXT = Color.rgb(21, 25, 36);
    private static final int COLOR_MUTED = Color.rgb(91, 99, 116);
    private static final int COLOR_PRIMARY = Color.rgb(91, 66, 230);
    private static final int COLOR_OK = Color.rgb(20, 123, 82);
    private static final int COLOR_WARN = Color.rgb(176, 78, 16);
    private static final int COLOR_ERROR = Color.rgb(176, 36, 48);

    private Uri selectedUri;
    private TextView statusView;
    private TextView detailView;
    private Button openButton;
    private LinearLayout adHost;
    private AdView adView;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        MobileAds.initialize(this, ignored -> { });
        setContentView(buildScreen());
    }

    private View buildScreen() {
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setBackgroundColor(COLOR_BG);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(20), dp(24), dp(20), dp(32));
        scroll.addView(root, new ScrollView.LayoutParams(
                ScrollView.LayoutParams.MATCH_PARENT,
                ScrollView.LayoutParams.WRAP_CONTENT));

        LinearLayout brand = new LinearLayout(this);
        brand.setOrientation(LinearLayout.VERTICAL);
        brand.setPadding(dp(20), dp(20), dp(20), dp(20));
        brand.setBackground(rounded(Color.rgb(25, 27, 43), 24));
        root.addView(brand, matchWrap());

        TextView eyebrow = text("TAYVORIQ LABS · ANDROID TEST", 12, Color.rgb(190, 181, 255), true);
        brand.addView(eyebrow, matchWrap());

        TextView title = text("Add-on Manager", 30, Color.WHITE, true);
        title.setPadding(0, dp(8), 0, 0);
        brand.addView(title, matchWrap());

        TextView subtitle = text("Minecraft-Bedrock-Dateien lokal prüfen und anschließend regulär an Minecraft übergeben.", 15, Color.rgb(220, 222, 232), false);
        subtitle.setPadding(0, dp(8), 0, 0);
        brand.addView(subtitle, matchWrap());

        TextView testBadge = text("TESTVERSION · NUR GOOGLE-TESTWERBUNG", 12, COLOR_PRIMARY, true);
        testBadge.setGravity(Gravity.CENTER);
        testBadge.setPadding(dp(12), dp(10), dp(12), dp(10));
        testBadge.setBackground(rounded(Color.WHITE, 14));
        LinearLayout.LayoutParams badgeParams = matchWrap();
        badgeParams.topMargin = dp(14);
        brand.addView(testBadge, badgeParams);

        TextView stepTitle = text("1. Add-on auswählen", 20, COLOR_TEXT, true);
        LinearLayout.LayoutParams titleParams = matchWrap();
        titleParams.topMargin = dp(24);
        root.addView(stepTitle, titleParams);

        TextView supported = text("Unterstützt: .mcaddon, .mcpack und .mcworld · maximal 300 MB", 14, COLOR_MUTED, false);
        supported.setPadding(0, dp(5), 0, dp(12));
        root.addView(supported, matchWrap());

        Button chooseButton = primaryButton("DATEI AUSWÄHLEN UND PRÜFEN");
        chooseButton.setOnClickListener(v -> chooseAddon());
        root.addView(chooseButton, matchWrap());

        statusView = text("Noch keine Datei ausgewählt", 16, COLOR_MUTED, true);
        statusView.setPadding(dp(16), dp(15), dp(16), dp(15));
        statusView.setBackground(rounded(Color.WHITE, 18));
        LinearLayout.LayoutParams statusParams = matchWrap();
        statusParams.topMargin = dp(16);
        root.addView(statusView, statusParams);

        detailView = text("Die Prüfung sucht unter anderem nach manifest.json, Pakettyp, UUID-Struktur, Pfadmanipulationen, ausführbaren Dateien und ungewöhnlich großen Archiven.", 14, COLOR_MUTED, false);
        detailView.setPadding(dp(4), dp(12), dp(4), dp(8));
        root.addView(detailView, matchWrap());

        openButton = secondaryButton("MIT MINECRAFT ÖFFNEN");
        openButton.setEnabled(false);
        openButton.setAlpha(0.45f);
        openButton.setOnClickListener(v -> openWithMinecraft());
        LinearLayout.LayoutParams openParams = matchWrap();
        openParams.topMargin = dp(8);
        root.addView(openButton, openParams);

        Button infoButton = secondaryButton("TEST- UND DATENSCHUTZHINWEIS");
        infoButton.setOnClickListener(v -> showInfo());
        LinearLayout.LayoutParams infoParams = matchWrap();
        infoParams.topMargin = dp(10);
        root.addView(infoButton, infoParams);

        adHost = new LinearLayout(this);
        adHost.setOrientation(LinearLayout.VERTICAL);
        adHost.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams adParams = matchWrap();
        adParams.topMargin = dp(22);
        root.addView(adHost, adParams);

        TextView disclaimer = text("Unabhängiges Testprodukt. Nicht von Mojang oder Microsoft genehmigt oder mit diesen verbunden. Minecraft ist eine Marke von Microsoft.", 12, COLOR_MUTED, false);
        disclaimer.setGravity(Gravity.CENTER);
        disclaimer.setPadding(dp(8), dp(22), dp(8), 0);
        root.addView(disclaimer, matchWrap());

        return scroll;
    }

    private void chooseAddon() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("application/octet-stream");
        intent.putExtra(Intent.EXTRA_MIME_TYPES, new String[] {
                "application/octet-stream", "application/zip", "application/x-zip-compressed", "*/*"
        });
        startActivityForResult(Intent.createChooser(intent, "Minecraft-Add-on auswählen"), PICK_ADDON);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != PICK_ADDON || resultCode != RESULT_OK || data == null || data.getData() == null) {
            return;
        }
        selectedUri = data.getData();
        try {
            int flags = data.getFlags() & (Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
            getContentResolver().takePersistableUriPermission(selectedUri, flags);
        } catch (Exception ignored) {
            // Some document providers only grant temporary access; that is sufficient for this test.
        }
        startAnalysis(selectedUri);
    }

    private void startAnalysis(Uri uri) {
        setStatus("Datei wird lokal geprüft …", COLOR_PRIMARY, false);
        detailView.setText("Die Datei wird nicht hochgeladen. Je nach Paketgröße kann die vollständige Archivprüfung einige Sekunden dauern.");
        openButton.setEnabled(false);
        openButton.setAlpha(0.45f);

        new Thread(() -> {
            try {
                Analysis result = analyze(uri);
                runOnUiThread(() -> showResult(result));
            } catch (Exception error) {
                String message = error.getMessage() == null ? error.getClass().getSimpleName() : error.getMessage();
                runOnUiThread(() -> showResult(Analysis.blocked("Prüfung fehlgeschlagen", message)));
            }
        }, "addon-analysis").start();
    }

    private Analysis analyze(Uri uri) throws Exception {
        String fileName = queryDisplayName(uri);
        String lowerFile = fileName.toLowerCase(Locale.ROOT);
        if (!(lowerFile.endsWith(".mcaddon") || lowerFile.endsWith(".mcpack") || lowerFile.endsWith(".mcworld"))) {
            return Analysis.blocked("Nicht unterstützte Datei", "Erwartet wird eine Datei mit der Endung .mcaddon, .mcpack oder .mcworld. Ausgewählt: " + fileName);
        }

        try (AssetFileDescriptor descriptor = getContentResolver().openAssetFileDescriptor(uri, "r")) {
            if (descriptor != null && descriptor.getLength() > MAX_FILE_BYTES) {
                return Analysis.blocked("Datei zu groß", "Die Testversion akzeptiert höchstens 300 MB. Dateigröße: " + readableBytes(descriptor.getLength()));
            }
        }

        int entries = 0;
        long unpacked = 0;
        boolean foundManifest = false;
        boolean foundLevelDat = false;
        String packName = null;
        String version = null;
        List<String> moduleTypes = new ArrayList<>();

        try (InputStream raw = getContentResolver().openInputStream(uri);
             ZipInputStream zip = new ZipInputStream(raw)) {
            if (raw == null) {
                throw new IllegalStateException("Die Datei konnte nicht geöffnet werden.");
            }
            ZipEntry entry;
            byte[] buffer = new byte[32 * 1024];
            while ((entry = zip.getNextEntry()) != null) {
                entries++;
                if (entries > MAX_ENTRIES) {
                    return Analysis.blocked("Archiv blockiert", "Das Paket enthält mehr als " + MAX_ENTRIES + " Einträge.");
                }

                String entryName = entry.getName() == null ? "" : entry.getName().replace('\\', '/');
                String lowerEntry = entryName.toLowerCase(Locale.ROOT);
                if (entryName.startsWith("/") || entryName.contains("../") || entryName.equals("..")) {
                    return Analysis.blocked("Unsicherer Archivpfad", "Blockierter Eintrag: " + entryName);
                }
                if (isExecutable(lowerEntry)) {
                    return Analysis.blocked("Ausführbare Datei blockiert", "Minecraft-Add-ons dürfen keine ausführbaren Bestandteile enthalten: " + entryName);
                }
                if (lowerEntry.endsWith("level.dat")) {
                    foundLevelDat = true;
                }

                boolean manifestEntry = lowerEntry.equals("manifest.json") || lowerEntry.endsWith("/manifest.json");
                ByteArrayOutputStream manifestBytes = manifestEntry ? new ByteArrayOutputStream() : null;
                int read;
                while ((read = zip.read(buffer)) != -1) {
                    unpacked += read;
                    if (unpacked > MAX_UNPACKED_BYTES) {
                        return Analysis.blocked("Archiv zu groß entpackt", "Das Archiv überschreitet die Sicherheitsgrenze von " + readableBytes(MAX_UNPACKED_BYTES) + ".");
                    }
                    if (manifestBytes != null) {
                        if (manifestBytes.size() + read > MAX_MANIFEST_BYTES) {
                            return Analysis.blocked("Manifest zu groß", "Eine manifest.json überschreitet 2 MB.");
                        }
                        manifestBytes.write(buffer, 0, read);
                    }
                }

                if (manifestBytes != null) {
                    foundManifest = true;
                    JSONObject manifest = new JSONObject(manifestBytes.toString(StandardCharsets.UTF_8));
                    JSONObject header = manifest.optJSONObject("header");
                    if (header != null) {
                        packName = header.optString("name", packName);
                        JSONArray versionArray = header.optJSONArray("version");
                        if (versionArray != null) {
                            version = joinVersion(versionArray);
                        }
                        String uuid = header.optString("uuid", "");
                        if (!uuid.isEmpty() && uuid.length() < 20) {
                            return Analysis.blocked("Ungültige UUID", "Die UUID im Manifest ist ungewöhnlich kurz.");
                        }
                    }
                    JSONArray modules = manifest.optJSONArray("modules");
                    if (modules != null) {
                        for (int i = 0; i < modules.length(); i++) {
                            JSONObject module = modules.optJSONObject(i);
                            if (module != null) {
                                String type = module.optString("type", "");
                                if (!type.isEmpty() && !moduleTypes.contains(type)) {
                                    moduleTypes.add(type);
                                }
                            }
                        }
                    }
                }
                zip.closeEntry();
            }
        }

        if (entries == 0) {
            return Analysis.blocked("Leeres oder ungültiges Archiv", "Die Datei enthält keine lesbaren ZIP-Einträge.");
        }
        if (!foundManifest && !(lowerFile.endsWith(".mcworld") && foundLevelDat)) {
            return Analysis.blocked("Minecraft-Struktur nicht erkannt", "Es wurde weder eine manifest.json noch eine gültige Weltstruktur mit level.dat gefunden.");
        }

        String type;
        if (lowerFile.endsWith(".mcworld")) {
            type = "Minecraft-Welt";
        } else if (moduleTypes.contains("data") && moduleTypes.contains("resources")) {
            type = "Behavior- und Resource-Pack";
        } else if (moduleTypes.contains("data")) {
            type = "Behavior-Pack";
        } else if (moduleTypes.contains("resources")) {
            type = "Resource-Pack";
        } else {
            type = lowerFile.endsWith(".mcaddon") ? "Add-on-Bündel" : "Minecraft-Pack";
        }

        StringBuilder details = new StringBuilder();
        details.append("Datei: ").append(fileName)
                .append("\nTyp: ").append(type)
                .append("\nArchiveinträge: ").append(entries)
                .append("\nEntpackte Prüfmenge: ").append(readableBytes(unpacked));
        if (packName != null && !packName.isBlank()) {
            details.append("\nPaketname: ").append(packName);
        }
        if (version != null) {
            details.append("\nVersion: ").append(version);
        }
        if (!moduleTypes.isEmpty()) {
            details.append("\nModule: ").append(String.join(", ", moduleTypes));
        }
        details.append("\n\nErgebnis: Keine blockierten Pfade oder ausführbaren Dateien gefunden. Dies ist eine Strukturprüfung, kein vollständiger Virenscan.");
        return Analysis.ready("Bereit für Minecraft", details.toString());
    }

    private void showResult(Analysis result) {
        setStatus(result.title, result.ready ? COLOR_OK : COLOR_ERROR, result.ready);
        detailView.setText(result.details);
        openButton.setEnabled(result.ready);
        openButton.setAlpha(result.ready ? 1f : 0.45f);
        if (result.ready) {
            showTestBanner();
        }
    }

    private void openWithMinecraft() {
        if (selectedUri == null) {
            return;
        }
        Intent direct = new Intent(Intent.ACTION_VIEW);
        direct.setDataAndType(selectedUri, "application/octet-stream");
        direct.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        direct.setPackage("com.mojang.minecraftpe");
        try {
            startActivity(direct);
        } catch (ActivityNotFoundException noMinecraft) {
            Intent chooser = new Intent(Intent.ACTION_VIEW);
            chooser.setDataAndType(selectedUri, "application/octet-stream");
            chooser.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            try {
                startActivity(Intent.createChooser(chooser, "Mit App öffnen"));
            } catch (ActivityNotFoundException none) {
                Toast.makeText(this, "Keine passende App gefunden. Ist Minecraft Bedrock installiert?", Toast.LENGTH_LONG).show();
            }
        }
    }

    private void showTestBanner() {
        if (adView != null) {
            return;
        }
        TextView label = text("Google-Testanzeige · in der finalen Free-Version dezent nach der Prüfung", 11, COLOR_MUTED, false);
        label.setGravity(Gravity.CENTER);
        label.setPadding(0, 0, 0, dp(6));
        adHost.addView(label, matchWrap());

        adView = new AdView(this);
        adView.setAdSize(AdSize.BANNER);
        adView.setAdUnitId("ca-app-pub-3940256099942544/6300978111");
        adHost.addView(adView, new LinearLayout.LayoutParams(dp(320), dp(50)));
        adView.loadAd(new AdRequest.Builder().build());
    }

    private void showInfo() {
        new AlertDialog.Builder(this)
                .setTitle("Hinweis zur Testversion")
                .setMessage("Die ausgewählte Datei wird ausschließlich lokal auf diesem Gerät gelesen. Sie wird nicht an TAYVORIQ übertragen. Die eingeblendete Anzeige verwendet offizielle Google-Testkennungen und erzeugt keine Einnahmen. Diese APK ist nicht für die Veröffentlichung im Play Store bestimmt.")
                .setPositiveButton("Verstanden", null)
                .show();
    }

    private String queryDisplayName(Uri uri) {
        try (Cursor cursor = getContentResolver().query(uri, new String[] { OpenableColumns.DISPLAY_NAME }, null, null, null)) {
            if (cursor != null && cursor.moveToFirst()) {
                int index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME);
                if (index >= 0) {
                    String value = cursor.getString(index);
                    if (value != null && !value.isBlank()) {
                        return value;
                    }
                }
            }
        }
        String fallback = uri.getLastPathSegment();
        return fallback == null ? "ausgewählte Datei" : fallback;
    }

    private static boolean isExecutable(String name) {
        String[] blocked = { ".apk", ".exe", ".dex", ".so", ".jar", ".msi", ".bat", ".cmd", ".ps1", ".sh" };
        for (String extension : blocked) {
            if (name.endsWith(extension)) {
                return true;
            }
        }
        return false;
    }

    private static String joinVersion(JSONArray array) {
        List<String> values = new ArrayList<>();
        for (int i = 0; i < array.length(); i++) {
            values.add(String.valueOf(array.opt(i)));
        }
        return String.join(".", values);
    }

    private static String readableBytes(long bytes) {
        if (bytes < 1024) return bytes + " B";
        double value = bytes;
        String[] units = { "KB", "MB", "GB" };
        for (String unit : units) {
            value /= 1024d;
            if (value < 1024d || unit.equals("GB")) {
                return String.format(Locale.GERMANY, "%.1f %s", value, unit);
            }
        }
        return bytes + " B";
    }

    private void setStatus(String message, int color, boolean ready) {
        statusView.setText((ready ? "✓  " : "") + message);
        statusView.setTextColor(color);
        int fill = ready ? Color.rgb(231, 247, 239) : Color.WHITE;
        statusView.setBackground(rounded(fill, 18));
    }

    private TextView text(String value, int sizeSp, int color, boolean bold) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(sizeSp);
        view.setTextColor(color);
        view.setLineSpacing(0f, 1.15f);
        if (bold) view.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        return view;
    }

    private Button primaryButton(String value) {
        Button button = new Button(this);
        button.setText(value);
        button.setTextColor(Color.WHITE);
        button.setTextSize(14);
        button.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        button.setMinHeight(dp(54));
        button.setBackground(rounded(COLOR_PRIMARY, 16));
        return button;
    }

    private Button secondaryButton(String value) {
        Button button = new Button(this);
        button.setText(value);
        button.setTextColor(COLOR_TEXT);
        button.setTextSize(14);
        button.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        button.setMinHeight(dp(52));
        button.setBackground(rounded(Color.WHITE, 16));
        return button;
    }

    private GradientDrawable rounded(int color, int radiusDp) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(color);
        drawable.setCornerRadius(dp(radiusDp));
        return drawable;
    }

    private LinearLayout.LayoutParams matchWrap() {
        return new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    @Override
    protected void onDestroy() {
        if (adView != null) {
            adView.destroy();
        }
        super.onDestroy();
    }

    private record Analysis(boolean ready, String title, String details) {
        static Analysis ready(String title, String details) {
            return new Analysis(true, title, details);
        }

        static Analysis blocked(String title, String details) {
            return new Analysis(false, title, details);
        }
    }
}
