package com.projectlumen.publicpreview;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.pm.ApplicationInfo;
import android.os.Bundle;
import android.view.Gravity;
import android.widget.*;
import java.text.DateFormat;
import java.util.Date;

/** Commercial-readiness UI; real purchase adapters are injected in store-specific builds. */
public final class ActivationActivity extends Activity {
    private static final int BG = 0xFF05070B, SURFACE = 0xFF141A24, TEXT = 0xFFF7F9FC, MUTED = 0xFFA7B0BE;
    private EntitlementStore store;

    @Override protected void onCreate(Bundle state) { super.onCreate(state); store = new EntitlementStore(this); render(); }
    private void render() {
        ScrollView scroll = new ScrollView(this); scroll.setFillViewport(true);
        LinearLayout root = new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(28), dp(24), dp(28), dp(40)); root.setBackgroundColor(BG);
        scroll.addView(root, new ScrollView.LayoutParams(-1, -2));
        root.addView(text("Aktivierung & Softwarelizenz", 30, TEXT, true));
        root.addView(text("Verkauft wird ausschließlich die Player-Software. Inhalte, Playlists und Zugangsdaten sind niemals Bestandteil der Lizenz.",
                15, MUTED, false), margin(0, 7, 0, 18));
        EntitlementStore.Status status = store.status();
        root.addView(info("Gerätecode", DeviceIdentity.shortCode(this)));
        root.addView(info("Lizenzstatus", statusText(status)), margin(0, 10, 0, 0));
        root.addView(info("Supportcode", status.supportCode), margin(0, 10, 0, 0));
        Button restore = button("Kauf wiederherstellen");
        restore.setOnClickListener(v -> BillingGateway.forPilot(this).restorePurchases((success, code, token) -> {
            if (success && token != null && !token.isBlank()) {
                Toast.makeText(this, store.importToken(token).supportCode, Toast.LENGTH_LONG).show(); render();
            } else Toast.makeText(this, "Store-Billing ist im Pilot-Build noch nicht konfiguriert. Code " + code, Toast.LENGTH_LONG).show();
        }));
        root.addView(restore, margin(0, 16, 0, 0));
        Button purchase = button("Jahreslizenz anzeigen");
        purchase.setOnClickListener(v -> BillingGateway.forPilot(this).startYearlyPurchase((success, code, token) ->
                Toast.makeText(this, "Store-Konfiguration ausstehend. Code " + code, Toast.LENGTH_LONG).show()));
        root.addView(purchase, margin(0, 10, 0, 0));
        if (isDebuggable()) {
            Button importToken = button("Test-Entitlement importieren");
            importToken.setOnClickListener(v -> importToken()); root.addView(importToken, margin(0, 10, 0, 0));
        }
        root.addView(text("Produktionsgrenze: Ein Store-Kauf darf erst nach serverseitiger Prüfung des Store-Belegs ein kurzlebiges, signiertes Entitlement erzeugen. Der Backend-Vertrag akzeptiert keine Playlistdateien, Stream-URLs oder EPG-Daten.",
                14, MUTED, false), margin(0, 22, 0, 0));
        setContentView(scroll); restore.requestFocus();
    }
    private boolean isDebuggable() {
        return (getApplicationInfo().flags & ApplicationInfo.FLAG_DEBUGGABLE) != 0;
    }
    private void importToken() {
        EditText field = new EditText(this); field.setHint("Signiertes Entitlement-Token"); field.setMinLines(4);
        new AlertDialog.Builder(this).setTitle("Nur für Testumgebung").setView(field)
                .setPositiveButton("Prüfen", (d, w) -> { Toast.makeText(this,
                        store.importToken(field.getText().toString()).supportCode, Toast.LENGTH_LONG).show(); render(); })
                .setNegativeButton("Abbrechen", null).show();
    }
    private String statusText(EntitlementStore.Status status) {
        switch (status.state) {
            case VALID: return "Premium aktiv · " + status.plan + " · Offline bis " + date(status.offlineUntilMs);
            case EXPIRED: return "Lizenz oder Offline-Fenster abgelaufen";
            case DEVICE_MISMATCH: return "Lizenz gehört zu einem anderen Gerät";
            case INVALID: return "Lizenzdaten ungültig";
            case NONE: return "Keine Lizenz gespeichert";
            default: return "Pilot-Build · Store-/Backend-Schlüssel noch nicht konfiguriert";
        }
    }
    private LinearLayout info(String label, String value) {
        LinearLayout card = new LinearLayout(this); card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(18), dp(14), dp(18), dp(14)); card.setBackgroundColor(SURFACE);
        card.addView(text(label, 16, TEXT, true)); card.addView(text(value, 14, MUTED, false), margin(0, 4, 0, 0)); return card;
    }
    private Button button(String label) { Button b = new Button(this); b.setText(label); b.setTextSize(16); b.setAllCaps(false); b.setFocusable(true); b.setMinHeight(dp(54)); return b; }
    private TextView text(String value, int size, int color, boolean bold) { TextView v = new TextView(this); v.setText(value); v.setTextSize(size); v.setTextColor(color); v.setGravity(Gravity.START); if (bold) v.setTypeface(null, 1); return v; }
    private LinearLayout.LayoutParams margin(int l, int t, int r, int b) { LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(-1, -2); p.setMargins(dp(l), dp(t), dp(r), dp(b)); return p; }
    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
    private static String date(long millis) { return millis <= 0 ? "–" : DateFormat.getDateTimeInstance(DateFormat.MEDIUM, DateFormat.SHORT).format(new Date(millis)); }
}
