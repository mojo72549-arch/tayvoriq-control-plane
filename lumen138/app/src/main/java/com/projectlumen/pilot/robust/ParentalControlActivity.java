package com.projectlumen.pilot.robust;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.text.InputFilter;
import android.text.InputType;
import android.view.Gravity;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

/** Parent-only PIN setup and temporary adult-content unlock screen. */
public final class ParentalControlActivity extends Activity {
    private static final int BG = 0xFF050D18;
    private static final int CARD = 0xFF0D2435;
    private static final int STROKE = 0xFF2A5269;
    private static final int ACCENT = 0xFF62E7D3;
    private static final int DANGER = 0xFFE94D5F;

    private LinearLayout root;
    private DiagnosticLog log;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(BG);
        getWindow().setNavigationBarColor(BG);
        log = DiagnosticLog.get(this);
        build();
    }

    @Override protected void onResume() {
        super.onResume();
        render();
    }

    private void build() {
        root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(18), dp(18), dp(18), dp(18));
        root.setBackground(new LumenFlowDrawable());
        setContentView(root);
    }

    private void render() {
        root.removeAllViews();

        LinearLayout header = new LinearLayout(this);
        header.setGravity(Gravity.CENTER_VERTICAL);
        TextView logo = text("", 18, Color.WHITE, true);
        logo.setBackgroundResource(R.drawable.ic_lumen_mark_tile);
        logo.setContentDescription("Project Lumen Logo");
        header.addView(logo, new LinearLayout.LayoutParams(dp(46), dp(46)));
        LinearLayout brand = new LinearLayout(this);
        brand.setOrientation(LinearLayout.VERTICAL);
        brand.setPadding(dp(10), 0, 0, 0);
        brand.addView(text("PROJECT LUMEN", 21, Color.WHITE, true));
        brand.addView(text("JUGENDSCHUTZ UND ERWACHSENENBEREICH", 10, 0xFF9DB6C8, true));
        header.addView(brand, new LinearLayout.LayoutParams(0, -2, 1f));
        root.addView(header);

        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(16), dp(16), dp(16), dp(16));
        card.setBackground(roundRect(CARD, 17, STROKE));
        LinearLayout.LayoutParams cardParams = new LinearLayout.LayoutParams(-1, -2);
        cardParams.setMargins(0, dp(18), 0, 0);
        root.addView(card, cardParams);

        boolean hasPin = ParentalControl.hasPin();
        boolean unlocked = ParentalControl.isUnlocked();
        TextView status = text(unlocked ? "Elternzugang ist vorübergehend entsperrt"
                : "Erwachsenenbereiche sind vollständig verborgen",
                17, unlocked ? ACCENT : Color.WHITE, true);
        status.setGravity(Gravity.CENTER_HORIZONTAL);
        card.addView(status);

        TextView detail = text(unlocked
                        ? "Der getrennte 18+-Bereich für Filme, Serien und Live-Sender kann jetzt geöffnet werden. Der Familienkatalog bleibt unverändert und geschützt."
                        : "Hier wird die 6-stellige Eltern-PIN festgelegt. Titel, Kategorien, Logos, Suche und Trefferzahlen bleiben vorher unsichtbar.",
                13, 0xFFB6CAD7, false);
        detail.setGravity(Gravity.CENTER_HORIZONTAL);
        detail.setPadding(0, dp(7), 0, dp(14));
        card.addView(detail);

        if (!hasPin) renderSetup(card);
        else if (!unlocked) renderUnlock(card);
        else renderUnlocked(card);

        Button back = button("Zurück", false);
        back.setOnClickListener(v -> finish());
        LinearLayout.LayoutParams backParams = new LinearLayout.LayoutParams(-1, dp(48));
        backParams.setMargins(0, dp(14), 0, 0);
        root.addView(back, backParams);
    }

    private void renderSetup(LinearLayout card) {
        card.addView(text("Eltern-PIN einrichten", 15, Color.WHITE, true));
        EditText pin = pinInput("Neue 6-stellige PIN");
        EditText repeat = pinInput("PIN wiederholen");
        card.addView(pin, inputParams());
        card.addView(repeat, inputParams());
        Button save = button("PIN sicher festlegen", true);
        save.setOnClickListener(v -> {
            String first = pin.getText().toString();
            String second = repeat.getText().toString();
            if (!first.equals(second)) {
                toast("Die beiden PIN-Eingaben stimmen nicht überein.");
                return;
            }
            try {
                ParentalControl.setInitialPin(first);
                log.event("-", "PARENTAL-PIN-CREATED", "keystore=true digits=6");
                toast("Eltern-PIN wurde sicher eingerichtet.");
                render();
            } catch (Throwable failure) {
                log.exception("-", "PARENTAL-PIN-SET-ERROR", failure);
                toast(message(failure));
            }
        });
        card.addView(save, buttonParams());
    }

    private void renderUnlock(LinearLayout card) {
        long lockout = ParentalControl.lockoutRemainingMs();
        if (lockout > 0) {
            TextView wait = text("Nach mehreren Fehlversuchen noch "
                    + Math.max(1, (lockout + 999) / 1000) + " Sekunden gesperrt.",
                    13, DANGER, true);
            wait.setGravity(Gravity.CENTER);
            card.addView(wait);
        }
        EditText pin = pinInput("Eltern-PIN");
        card.addView(pin, inputParams());
        Button unlock = button("Für 10 Minuten entsperren", true);
        unlock.setEnabled(lockout <= 0);
        unlock.setAlpha(lockout <= 0 ? 1f : 0.55f);
        unlock.setOnClickListener(v -> {
            try {
                if (ParentalControl.unlock(pin.getText().toString())) {
                    log.event("-", "PARENTAL-UNLOCK-APPROVED", "durationMinutes=10");
                    toast("Elternzugang wurde vorübergehend entsperrt.");
                    render();
                } else {
                    log.event("-", "PARENTAL-UNLOCK-DENIED", "reason=invalid-pin");
                    toast("Die Eltern-PIN ist falsch.");
                    pin.setText("");
                    render();
                }
            } catch (Throwable failure) {
                log.event("-", "PARENTAL-UNLOCK-DENIED", "reason=locked-or-invalid");
                toast(message(failure));
                render();
            }
        });
        card.addView(unlock, buttonParams());
    }

    private void renderUnlocked(LinearLayout card) {
        long minutes = Math.max(1, (ParentalControl.unlockRemainingMs() + 59_999) / 60_000);
        TextView remaining = text("Verbleibende Freigabe: etwa " + minutes + " Minuten",
                13, 0xFFB6CAD7, false);
        remaining.setGravity(Gravity.CENTER);
        card.addView(remaining);

        Button openAdult = button("18+ Bereich sicher öffnen", true);
        openAdult.setOnClickListener(v -> openAdultArea());
        card.addView(openAdult, buttonParams());

        Button lock = button("Jetzt wieder sperren", false);
        lock.setOnClickListener(v -> {
            ParentalControl.lock("manual");
            log.event("-", "PARENTAL-LOCK", "reason=manual");
            render();
        });
        card.addView(lock, buttonParams());

        TextView changeTitle = text("PIN ändern", 14, Color.WHITE, true);
        changeTitle.setPadding(0, dp(14), 0, 0);
        card.addView(changeTitle);
        EditText current = pinInput("Aktuelle PIN");
        EditText next = pinInput("Neue 6-stellige PIN");
        card.addView(current, inputParams());
        card.addView(next, inputParams());
        Button change = button("PIN ändern", false);
        change.setOnClickListener(v -> {
            try {
                ParentalControl.changePin(current.getText().toString(), next.getText().toString());
                log.event("-", "PARENTAL-PIN-CHANGED", "keystore=true digits=6");
                toast("Eltern-PIN wurde geändert.");
                render();
            } catch (Throwable failure) {
                log.event("-", "PARENTAL-PIN-CHANGE-DENIED", "reason=verification");
                toast(message(failure));
            }
        });
        card.addView(change, buttonParams());
    }

    private void openAdultArea() {
        if (!ParentalControl.isUnlocked()) {
            toast("Elternzugang ist nicht mehr freigegeben.");
            render();
            return;
        }
        log.event("-", "PARENTAL-ADULT-HUB-OPEN", "isolated=true mainRestart=false scopes=3");
        startActivity(new Intent(this, AdultCatalogActivity.class));
    }

    private EditText pinInput(String hint) {
        EditText input = new EditText(this);
        input.setSingleLine(true);
        input.setHint(hint);
        input.setTextColor(Color.WHITE);
        input.setHintTextColor(0xFF7896AA);
        input.setTextSize(16);
        input.setGravity(Gravity.CENTER);
        input.setInputType(InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_VARIATION_PASSWORD);
        input.setFilters(new InputFilter[]{new InputFilter.LengthFilter(6)});
        input.setBackground(roundRect(0xFF091B29, 13, STROKE));
        return input;
    }

    private LinearLayout.LayoutParams inputParams() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, dp(52));
        params.setMargins(0, dp(8), 0, 0);
        return params;
    }

    private LinearLayout.LayoutParams buttonParams() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, dp(48));
        params.setMargins(0, dp(10), 0, 0);
        return params;
    }

    private Button button(String value, boolean primary) {
        Button button = new Button(this);
        button.setText(value);
        button.setAllCaps(false);
        button.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        button.setTextColor(primary ? BG : Color.WHITE);
        button.setBackground(roundRect(primary ? ACCENT : 0xFF17354A,
                13, primary ? ACCENT : STROKE));
        return button;
    }

    private TextView text(String value, float size, int color, boolean bold) {
        TextView text = new TextView(this);
        text.setText(value);
        text.setTextSize(size);
        text.setTextColor(color);
        if (bold) text.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        return text;
    }

    private GradientDrawable roundRect(int color, int radius, int stroke) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(color);
        drawable.setCornerRadius(dp(radius));
        drawable.setStroke(dp(1), stroke);
        return drawable;
    }

    private void toast(String value) { Toast.makeText(this, value, Toast.LENGTH_LONG).show(); }

    private static String message(Throwable failure) {
        return failure == null || failure.getMessage() == null || failure.getMessage().isBlank()
                ? "Vorgang konnte nicht abgeschlossen werden." : failure.getMessage();
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
