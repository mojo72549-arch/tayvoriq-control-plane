package com.projectlumen.pilot.robust;

import android.app.Activity;
import android.app.ActivityManager;
import android.app.AlertDialog;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.view.Gravity;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

public final class DiagnosticsActivity extends Activity {
    private DiagnosticLog log;
    private TextView body;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        log = DiagnosticLog.get(this);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(14), dp(14), dp(14), dp(14));
        root.setBackground(new GradientDrawable(
                GradientDrawable.Orientation.TL_BR,
                new int[]{0xFF040A14, 0xFF071D2D, 0xFF211B3D}));

        LinearLayout titleRow = new LinearLayout(this);
        titleRow.setGravity(Gravity.CENTER_VERTICAL);
        TextView logo = new TextView(this);
        logo.setBackgroundResource(R.drawable.ic_lumen_mark_tile);
        logo.setContentDescription("Project Lumen Logo");
        titleRow.addView(logo, new LinearLayout.LayoutParams(dp(44), dp(44)));
        TextView title = new TextView(this);
        title.setText(BuildConfig.DIAGNOSTICS_UI_ENABLED
                ? "Project Lumen System" : "Project Lumen Mehr");
        title.setTextColor(Color.WHITE);
        title.setTextSize(21);
        title.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        title.setPadding(dp(10), 0, 0, 0);
        titleRow.addView(title, new LinearLayout.LayoutParams(0, dp(48), 1f));
        root.addView(titleRow);

        Button parental = button(ParentalControl.isUnlocked()
                ? "Jugendschutz · entsperrt" : "Jugendschutz · aktiv", true);
        parental.setOnClickListener(v -> startActivity(
                new Intent(this, ParentalControlActivity.class)));
        LinearLayout.LayoutParams parentalParams = new LinearLayout.LayoutParams(-1, dp(48));
        parentalParams.setMargins(0, dp(12), 0, dp(8));
        root.addView(parental, parentalParams);

        Button delete = button("Lokale App-Daten vollständig löschen", false);
        delete.setOnClickListener(v -> confirmDeleteAllData());
        LinearLayout.LayoutParams deleteParams = new LinearLayout.LayoutParams(-1, dp(48));
        deleteParams.setMargins(0, 0, 0, dp(8));
        root.addView(delete, deleteParams);

        if (BuildConfig.DIAGNOSTICS_UI_ENABLED) {
            addDiagnosticControls(root);
        } else {
            TextView privacy = new TextView(this);
            privacy.setText("Playlists, Zugangsdaten, Schnellindex, Verlauf und Eltern-PIN "
                    + "werden ausschließlich lokal verwaltet. Über die Löschfunktion werden "
                    + "alle App-Daten des Geräts entfernt.");
            privacy.setTextColor(0xFFB6CAD7);
            privacy.setTextSize(13);
            privacy.setLineSpacing(0, 1.18f);
            privacy.setPadding(dp(2), dp(8), dp(2), dp(8));
            root.addView(privacy);
        }

        setContentView(root);
        refresh();
    }

    @Override protected void onResume() {
        super.onResume();
        if (body != null) refresh();
    }

    private void addDiagnosticControls(LinearLayout root) {
        LinearLayout actions = new LinearLayout(this);
        actions.setOrientation(LinearLayout.HORIZONTAL);
        Button copy = button("Kopieren", false);
        copy.setOnClickListener(v -> copy());
        actions.addView(copy, new LinearLayout.LayoutParams(0, dp(48), 1f));
        Button share = button("Teilen", false);
        share.setOnClickListener(v -> share());
        actions.addView(share, new LinearLayout.LayoutParams(0, dp(48), 1f));
        Button clear = button("Leeren", false);
        clear.setOnClickListener(v -> { log.clear(); refresh(); });
        actions.addView(clear, new LinearLayout.LayoutParams(0, dp(48), 1f));
        LinearLayout.LayoutParams actionsParams = new LinearLayout.LayoutParams(-1, dp(48));
        actionsParams.setMargins(0, dp(4), 0, dp(8));
        root.addView(actions, actionsParams);

        ScrollView scroll = new ScrollView(this);
        body = new TextView(this);
        body.setTextColor(0xFFD7E8F3);
        body.setTextSize(12);
        body.setTextIsSelectable(true);
        body.setPadding(0, dp(10), 0, dp(10));
        scroll.addView(body);
        root.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1f));
    }

    private void refresh() {
        if (body != null) body.setText(log.read());
    }

    private void confirmDeleteAllData() {
        new AlertDialog.Builder(this)
                .setTitle("Alle lokalen App-Daten löschen?")
                .setMessage("Dadurch werden Playlists, Bibliothek, Zugangsdaten, Favoriten, "
                        + "Profile, Verlauf, Diagnose und Eltern-PIN dieses Geräts dauerhaft entfernt.")
                .setNegativeButton("Abbrechen", null)
                .setPositiveButton("Alle Daten löschen", (dialog, which) -> {
                    ActivityManager manager =
                            (ActivityManager) getSystemService(Context.ACTIVITY_SERVICE);
                    if (manager == null || !manager.clearApplicationUserData()) {
                        Toast.makeText(this,
                                "Die lokalen App-Daten konnten nicht vollständig gelöscht werden.",
                                Toast.LENGTH_LONG).show();
                    }
                })
                .show();
    }

    private void copy() {
        ((ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE))
                .setPrimaryClip(ClipData.newPlainText("Project Lumen Diagnose", log.read()));
        Toast.makeText(this, "Diagnose kopiert.", Toast.LENGTH_SHORT).show();
    }

    private void share() {
        Intent intent = new Intent(Intent.ACTION_SEND);
        intent.setType("text/plain");
        intent.putExtra(Intent.EXTRA_SUBJECT, "Project Lumen Diagnose");
        intent.putExtra(Intent.EXTRA_TEXT, log.read());
        startActivity(Intent.createChooser(intent, "Diagnose teilen"));
    }

    private Button button(String text, boolean primary) {
        Button button = new Button(this);
        button.setText(text);
        button.setAllCaps(false);
        button.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        button.setTextColor(primary ? 0xFF050D18 : Color.WHITE);
        GradientDrawable background = new GradientDrawable();
        background.setColor(primary ? 0xFF62E7D3 : 0xFF17354A);
        background.setCornerRadius(dp(12));
        background.setStroke(dp(1), primary ? 0xFF62E7D3 : 0xFF2A5269);
        button.setBackground(background);
        return button;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
