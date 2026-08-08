package com.tayvoriq.addonmanager;

import android.app.Activity;
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

import java.util.Locale;

/** Receives a supported add-on from Downloads/My Files and immediately opens Minecraft. */
public final class FileImportActivity extends Activity {
    private static final String MINECRAFT_PACKAGE = "com.mojang.minecraftpe";
    private static final String MINECRAFT_MAIN_ACTIVITY = "com.mojang.minecraftpe.MainActivity";

    private static final int BG = Color.rgb(5, 8, 18);
    private static final int SURFACE = Color.rgb(13, 19, 33);
    private static final int TEXT = Color.rgb(245, 248, 255);
    private static final int MUTED = Color.rgb(158, 169, 192);
    private static final int CYAN = Color.rgb(0, 222, 235);
    private static final int RED = Color.rgb(255, 82, 106);

    private Uri fileUri;
    private TextView status;

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
        card.addView(logo, new LinearLayout.LayoutParams(dp(170), dp(170)));

        TextView brand = text("TAYVORIQ", 28, TEXT, true);
        brand.setGravity(Gravity.CENTER);
        card.addView(brand, matchWrap());

        TextView subtitle = text("ADD-ON MANAGER", 12, CYAN, true);
        subtitle.setGravity(Gravity.CENTER);
        subtitle.setPadding(0, dp(3), 0, dp(18));
        card.addView(subtitle, matchWrap());

        status = text("Add-on wird vorbereitet …", 17, TEXT, true);
        status.setGravity(Gravity.CENTER);
        status.setPadding(dp(10), dp(12), dp(10), dp(12));
        card.addView(status, matchWrap());

        TextView info = text(
                "Die Datei bleibt lokal. TAYVORIQ übergibt sie direkt an Minecraft.",
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
        String name = queryDisplayName(uri);
        String lower = name.toLowerCase(Locale.ROOT);
        if (!(lower.endsWith(".mcaddon") || lower.endsWith(".mcpack") || lower.endsWith(".mcworld"))) {
            fail("Nicht unterstützt: " + name);
            return;
        }

        status.setText(name + "\n\nMinecraft wird geöffnet und der Import gestartet …");
        new Handler(Looper.getMainLooper()).postDelayed(() -> openMinecraft(name), 250);
    }

    private void openMinecraft(String fileName) {
        if (!isMinecraftInstalled()) {
            fail("Minecraft Bedrock ist auf diesem Gerät nicht installiert oder für Android nicht sichtbar.");
            return;
        }

        try {
            grantUriPermission(
                    MINECRAFT_PACKAGE,
                    fileUri,
                    Intent.FLAG_GRANT_READ_URI_PERMISSION);
        } catch (Exception ignored) { }

        // 1) Strongest path: explicit MainActivity launch. This bypasses Minecraft's
        // MIME intent-filter matching while still delivering ACTION_VIEW + the file URI.
        Intent explicit = legacyViewIntent();
        explicit.setComponent(new ComponentName(MINECRAFT_PACKAGE, MINECRAFT_MAIN_ACTIVITY));
        if (tryStart(explicit)) {
            finish();
            return;
        }

        // 2) Restore the exact hand-off style used by the first working app version.
        Intent legacyPackageIntent = legacyViewIntent();
        legacyPackageIntent.setPackage(MINECRAFT_PACKAGE);
        if (tryStart(legacyPackageIntent)) {
            finish();
            return;
        }

        // 3) Fallback MIME variants for Minecraft builds that publish a stricter filter.
        for (String mime : preferredMimes(fileName)) {
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

        // 4) Last-resort: open Minecraft itself. This confirms the app is installed,
        // while avoiding the false "Minecraft not found" message from v1.4.
        Intent launch = getPackageManager().getLaunchIntentForPackage(MINECRAFT_PACKAGE);
        if (launch != null && tryStart(launch)) {
            fail("Minecraft wurde geöffnet, aber diese Minecraft-Version hat den Datei-Import-Intent nicht angenommen. Bitte die Add-on-Datei erneut antippen.");
            return;
        }

        fail("Minecraft wurde gefunden, konnte die Add-on-Datei aber nicht übernehmen.");
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

    private boolean isMinecraftInstalled() {
        try {
            ApplicationInfo info;
            if (Build.VERSION.SDK_INT >= 33) {
                info = getPackageManager().getApplicationInfo(
                        MINECRAFT_PACKAGE,
                        PackageManager.ApplicationInfoFlags.of(0));
            } else {
                @SuppressWarnings("deprecation")
                ApplicationInfo legacy = getPackageManager().getApplicationInfo(MINECRAFT_PACKAGE, 0);
                info = legacy;
            }
            return info.enabled;
        } catch (PackageManager.NameNotFoundException error) {
            return false;
        }
    }

    private static String[] preferredMimes(String fileName) {
        String lower = fileName.toLowerCase(Locale.ROOT);
        if (lower.endsWith(".mcaddon")) {
            return new String[] {
                    "application/octet-stream",
                    "application/mcaddon",
                    "application/zip"
            };
        }
        if (lower.endsWith(".mcpack")) {
            return new String[] {
                    "application/octet-stream",
                    "application/mcpack",
                    "application/zip"
            };
        }
        return new String[] {
                "application/octet-stream",
                "application/mcworld",
                "application/zip"
        };
    }

    private String queryDisplayName(Uri uri) {
        try (Cursor cursor = getContentResolver().query(
                uri,
                new String[] {OpenableColumns.DISPLAY_NAME},
                null,
                null,
                null)) {
            if (cursor != null && cursor.moveToFirst()) {
                int index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME);
                if (index >= 0) {
                    String value = cursor.getString(index);
                    if (value != null && !value.isBlank()) return value;
                }
            }
        } catch (Exception ignored) { }
        String fallback = uri.getLastPathSegment();
        return fallback == null ? "Minecraft-Add-on" : fallback;
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
}
