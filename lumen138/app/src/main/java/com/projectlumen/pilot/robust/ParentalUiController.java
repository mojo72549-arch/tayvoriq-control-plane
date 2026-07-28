package com.projectlumen.pilot.robust;

import android.app.Activity;
import android.app.AlertDialog;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Handler;
import android.os.Looper;
import android.text.InputFilter;
import android.text.InputType;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

final class ParentalUiController {
    private static final int BG = 0xFF050D18;
    private static final int SAFE = 0xFF73E6A2;
    private static final int ADULT = 0xFFFF6B7A;
    private static final int SURFACE = 0xFF102A3A;
    private static final int STROKE = 0xFF2A5269;

    private final Activity activity;
    private final DiagnosticLog log;
    private final Button button;
    private final TextView hint;
    private final Runnable onVisibilityChanged;
    private final Handler main = new Handler(Looper.getMainLooper());
    private final Runnable relock = this::handleRelock;
    private boolean lastUnlocked;

    ParentalUiController(Activity activity, DiagnosticLog log, Button button,
                         TextView hint, Runnable onVisibilityChanged) {
        this.activity = activity;
        this.log = log;
        this.button = button;
        this.hint = hint;
        this.onVisibilityChanged = onVisibilityChanged;
        button.setOnClickListener(v -> showAccess());
        refresh(false);
    }

    void refresh(boolean triggerFilter) {
        boolean hasPin = ParentalControl.hasPin(activity);
        boolean unlocked = hasPin && ParentalControl.isSessionUnlocked();
        boolean changed = unlocked != lastUnlocked;
        lastUnlocked = unlocked;
        if (!hasPin) {
            hint.setText("Erwachsenen-Inhalte verborgen · Eltern-PIN einrichten");
            style("PIN einrichten", SAFE);
            main.removeCallbacks(relock);
        } else if (unlocked) {
            hint.setText("Erwachsenenmodus temporär freigeschaltet");
            style("🔓 Erwachsene", ADULT);
            scheduleRelock();
        } else {
            hint.setText("Erwachsenen-Inhalte verborgen");
            style("🔒 Kinderfilter", SAFE);
            main.removeCallbacks(relock);
        }
        if (triggerFilter && changed) onVisibilityChanged.run();
    }

    void onUserActivity() {
        if (!ParentalControl.isSessionUnlocked()) return;
        ParentalControl.touchSession();
        scheduleRelock();
    }

    void requestUnlock(Runnable afterUnlock) {
        if (!ParentalControl.hasPin(activity)) {
            setupPin(false);
            return;
        }
        long remaining = ParentalControl.lockRemainingMs(activity);
        if (remaining > 0) {
            Toast.makeText(activity, "Zu viele Fehlversuche. Bitte noch "
                    + Math.max(1, (remaining + 999) / 1000) + " Sekunden warten.",
                    Toast.LENGTH_LONG).show();
            return;
        }
        EditText pin = pinInput("Eltern-PIN");
        AlertDialog dialog = new AlertDialog.Builder(activity)
                .setTitle("Erwachsenenbereich entsperren")
                .setMessage("Die Freischaltung endet nach 5 Minuten Inaktivität.")
                .setView(form(pin))
                .setPositiveButton("Entsperren", null)
                .setNegativeButton("Abbrechen", null)
                .create();
        dialog.setOnShowListener(ignored -> dialog.getButton(AlertDialog.BUTTON_POSITIVE)
                .setOnClickListener(v -> {
                    ParentalControl.VerifyResult result = ParentalControl.verifyPin(
                            activity, pin.getText().toString().toCharArray());
                    pin.setText("");
                    if (result == ParentalControl.VerifyResult.OK) {
                        log.event("-", "PARENTAL-UNLOCKED", "sessionMinutes=5");
                        refresh(true);
                        dialog.dismiss();
                        if (afterUnlock != null) afterUnlock.run();
                    } else if (result == ParentalControl.VerifyResult.LOCKED
                            || ParentalControl.lockRemainingMs(activity) > 0) {
                        pin.setError("Zu viele Fehlversuche. Zugriff kurzzeitig gesperrt.");
                        log.event("-", "PARENTAL-PIN-LOCKOUT", "attemptLimitReached=true");
                    } else {
                        pin.setError("Falsche Eltern-PIN.");
                        log.event("-", "PARENTAL-PIN-REJECTED", "reason=wrong-pin");
                    }
                }));
        dialog.show();
    }

    void destroy() {
        main.removeCallbacks(relock);
    }

    private void showAccess() {
        if (!ParentalControl.hasPin(activity)) {
            setupPin(false);
        } else if (!ParentalControl.isSessionUnlocked()) {
            requestUnlock(null);
        } else {
            new AlertDialog.Builder(activity)
                    .setTitle("Elternbereich")
                    .setItems(new String[]{"Kinderfilter jetzt aktivieren", "Eltern-PIN ändern"},
                            (dialog, which) -> {
                                if (which == 0) lockNow("manual");
                                else setupPin(true);
                            })
                    .setNegativeButton("Schließen", null)
                    .show();
        }
    }

    private void setupPin(boolean changing) {
        EditText first = pinInput("Neue Eltern-PIN (4–8 Ziffern)");
        EditText second = pinInput("Eltern-PIN wiederholen");
        AlertDialog dialog = new AlertDialog.Builder(activity)
                .setTitle(changing ? "Eltern-PIN ändern" : "Jugendschutz einrichten")
                .setMessage("Erwachsenen-Inhalte bleiben standardmäßig verborgen. "
                        + "Die PIN wird nicht im Klartext gespeichert.")
                .setView(form(first, second))
                .setPositiveButton("PIN speichern", null)
                .setNegativeButton("Abbrechen", null)
                .create();
        dialog.setOnShowListener(ignored -> dialog.getButton(AlertDialog.BUTTON_POSITIVE)
                .setOnClickListener(v -> {
                    String a = first.getText().toString();
                    String b = second.getText().toString();
                    if (!a.equals(b)) {
                        second.setError("Die PINs stimmen nicht überein.");
                        return;
                    }
                    try {
                        ParentalControl.setPin(activity, a.toCharArray());
                        first.setText("");
                        second.setText("");
                        log.event("-", changing ? "PARENTAL-PIN-CHANGED"
                                : "PARENTAL-PIN-SET", "stored=pbkdf2");
                        refresh(true);
                        Toast.makeText(activity,
                                "Eltern-PIN gespeichert. Kinderfilter ist aktiv.",
                                Toast.LENGTH_LONG).show();
                        dialog.dismiss();
                    } catch (Throwable failure) {
                        first.setError(failure.getMessage());
                    }
                }));
        dialog.show();
    }

    private void lockNow(String reason) {
        boolean wasUnlocked = ParentalControl.isSessionUnlocked();
        ParentalControl.lockSession();
        refresh(true);
        if (wasUnlocked) log.event("-", "PARENTAL-LOCKED", "reason=" + reason);
    }

    private void handleRelock() {
        if (ParentalControl.isSessionUnlocked()) {
            scheduleRelock();
            return;
        }
        boolean wasUnlocked = lastUnlocked;
        refresh(true);
        if (wasUnlocked) {
            log.event("-", "PARENTAL-LOCKED", "reason=inactivity-timeout");
            Toast.makeText(activity, "Kinderfilter wurde automatisch aktiviert.",
                    Toast.LENGTH_SHORT).show();
        }
    }

    private void scheduleRelock() {
        main.removeCallbacks(relock);
        long delay = ParentalControl.sessionRemainingMs();
        if (delay > 0) main.postDelayed(relock, delay + 100L);
    }

    private void style(String label, int color) {
        button.setText(label);
        button.setTextColor(BG);
        button.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        button.setBackground(roundRect(color, 12, color));
    }

    private EditText pinInput(String hintText) {
        EditText value = new EditText(activity);
        value.setSingleLine(true);
        value.setHint(hintText);
        value.setTextColor(Color.WHITE);
        value.setHintTextColor(0xFF7893A7);
        value.setInputType(InputType.TYPE_CLASS_NUMBER
                | InputType.TYPE_NUMBER_VARIATION_PASSWORD);
        value.setFilters(new InputFilter[]{new InputFilter.LengthFilter(8)});
        value.setPadding(dp(12), dp(10), dp(12), dp(10));
        value.setBackground(roundRect(SURFACE, 12, STROKE));
        return value;
    }

    private LinearLayout form(EditText... fields) {
        LinearLayout form = new LinearLayout(activity);
        form.setOrientation(LinearLayout.VERTICAL);
        form.setPadding(dp(18), dp(8), dp(18), 0);
        for (EditText field : fields) {
            LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2);
            params.setMargins(0, dp(5), 0, dp(5));
            form.addView(field, params);
        }
        return form;
    }

    private GradientDrawable roundRect(int color, int radius, int stroke) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(color);
        drawable.setCornerRadius(dp(radius));
        drawable.setStroke(dp(1), stroke);
        return drawable;
    }

    private int dp(int value) {
        return Math.round(value * activity.getResources().getDisplayMetrics().density);
    }
}
