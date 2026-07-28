package com.projectlumen.pilot.robust;

import android.app.Activity;
import android.app.Application;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

/** Process-level parental lock and premium-shell installer. */
public final class LumenApplication extends Application
        implements Application.ActivityLifecycleCallbacks {
    static final String EXTRA_ADULT_CONTENT = "lumen_parental_adult_content";
    private static final String ACTIONS_TAG = "lumen-premium-actions-v4";

    private final Handler main = new Handler(Looper.getMainLooper());
    private int startedActivities;

    private final Runnable backgroundLock = () -> {
        if (startedActivities == 0 && ParentalControl.isUnlocked()) {
            ParentalControl.lock("app-background");
            DiagnosticLog.get(this).event("-", "PARENTAL-LOCK", "reason=app-background");
        }
    };

    @Override public void onCreate() {
        super.onCreate();
        ParentalControl.initialize(this);
        ParentalControl.setListener((unlocked, reason) ->
                DiagnosticLog.get(this).event("-",
                        unlocked ? "PARENTAL-UNLOCK" : "PARENTAL-LOCK",
                        "reason=" + safeReason(reason)));
        registerActivityLifecycleCallbacks(this);
    }

    @Override public void onActivityCreated(Activity activity, Bundle state) {
        blockAdultPlayerIfNeeded(activity);
    }

    @Override public void onActivityStarted(Activity activity) {
        startedActivities++;
        main.removeCallbacks(backgroundLock);
        blockAdultPlayerIfNeeded(activity);
    }

    @Override public void onActivityResumed(Activity activity) {
        if (activity instanceof MainActivity) {
            installPremiumShell(activity);
        } else if (activity instanceof ParentalControlActivity
                || activity instanceof AdultCatalogActivity
                || activity instanceof LanguageCatalogActivity) {
            installFlowBackground(activity);
        }
        blockAdultPlayerIfNeeded(activity);
    }

    @Override public void onActivityPaused(Activity activity) { }

    @Override public void onActivityStopped(Activity activity) {
        startedActivities = Math.max(0, startedActivities - 1);
        if (startedActivities == 0 && !activity.isChangingConfigurations()) {
            main.removeCallbacks(backgroundLock);
            main.postDelayed(backgroundLock, 600L);
        }
    }

    @Override public void onActivitySaveInstanceState(Activity activity, Bundle state) { }
    @Override public void onActivityDestroyed(Activity activity) { }

    private void blockAdultPlayerIfNeeded(Activity activity) {
        if (!(activity instanceof PlayerActivity)) return;
        boolean adult = activity.getIntent().getBooleanExtra(EXTRA_ADULT_CONTENT, false);
        if (!adult || ParentalControl.isUnlocked()) return;
        DiagnosticLog.get(this).event("-", "PARENTAL-BLOCK",
                "target=player reason=session-locked");
        activity.finish();
    }

    private void installPremiumShell(Activity activity) {
        installHeaderLogo(activity.getWindow().getDecorView());
        installFlowBackground(activity);
        ViewGroup root = findMainColumn(activity.findViewById(android.R.id.content));
        if (root == null || root.findViewWithTag(ACTIONS_TAG) != null) return;

        LinearLayout actions = new LinearLayout(activity);
        actions.setTag(ACTIONS_TAG);
        actions.setOrientation(LinearLayout.HORIZONTAL);
        actions.setGravity(Gravity.CENTER_VERTICAL);

        Button languages = actionButton(activity, "🌐 Sprachen", 0xFF17354A, Color.WHITE);
        languages.setOnClickListener(v -> {
            DiagnosticLog.get(activity).event("-", "LANGUAGE-HUB-OPEN", "source=main");
            activity.startActivity(new Intent(activity, LanguageCatalogActivity.class));
        });
        actions.addView(languages, weighted(activity, 0));

        Button parental = actionButton(activity, "🛡 Jugendschutz", 0xFF17354A, Color.WHITE);
        parental.setOnClickListener(v -> activity.startActivity(
                new Intent(activity, ParentalControlActivity.class)));
        actions.addView(parental, weighted(activity, dp(activity, 7)));

        if (ParentalControl.isUnlocked()) {
            Button adult = actionButton(activity, "18+ Bereich", 0xFFE94D5F, Color.WHITE);
            adult.setOnClickListener(v -> {
                DiagnosticLog.get(activity).event("-", "PARENTAL-ADULT-HUB-OPEN",
                        "source=main isolated=true");
                activity.startActivity(new Intent(activity, AdultCatalogActivity.class));
            });
            actions.addView(adult, weighted(activity, dp(activity, 7)));
        }

        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, dp(activity, 41));
        params.setMargins(0, dp(activity, 7), 0, dp(activity, 1));
        int index = Math.min(4, root.getChildCount());
        root.addView(actions, index, params);
    }

    private static void installFlowBackground(Activity activity) {
        ViewGroup content = activity.findViewById(android.R.id.content);
        if (content == null || content.getChildCount() == 0) return;
        View stage = content.getChildAt(0);
        if (!(stage.getBackground() instanceof LumenFlowDrawable)) {
            stage.setBackground(new LumenFlowDrawable());
        }
    }

    private static ViewGroup findMainColumn(View view) {
        if (view instanceof LinearLayout) {
            LinearLayout linear = (LinearLayout) view;
            if (linear.getOrientation() == LinearLayout.VERTICAL && linear.getChildCount() >= 6) {
                return linear;
            }
        }
        if (view instanceof ViewGroup) {
            ViewGroup group = (ViewGroup) view;
            for (int index = 0; index < group.getChildCount(); index++) {
                ViewGroup found = findMainColumn(group.getChildAt(index));
                if (found != null) return found;
            }
        }
        return null;
    }

    private static Button actionButton(Activity activity, String label, int fill, int textColor) {
        Button button = new Button(activity);
        button.setText(label);
        button.setAllCaps(false);
        button.setSingleLine(true);
        button.setEllipsize(TextUtils.TruncateAt.END);
        button.setTextSize(10);
        button.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        button.setTextColor(textColor);
        button.setMinWidth(0);
        button.setMinHeight(0);
        button.setPadding(dp(activity, 6), 0, dp(activity, 6), 0);
        GradientDrawable background = new GradientDrawable();
        background.setColor(fill);
        background.setCornerRadius(dp(activity, 13));
        background.setStroke(dp(activity, 1), fill == 0xFF17354A ? 0xFF2A5269 : fill);
        button.setBackground(background);
        return button;
    }

    private static LinearLayout.LayoutParams weighted(Activity activity, int leftMargin) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, -1, 1f);
        params.setMargins(leftMargin, 0, 0, 0);
        return params;
    }

    private static int dp(Activity activity, int value) {
        return Math.round(value * activity.getResources().getDisplayMetrics().density);
    }

    private static void installHeaderLogo(View view) {
        if (view instanceof TextView) {
            TextView text = (TextView) view;
            if ("✦".contentEquals(text.getText())) {
                text.setText("");
                text.setBackgroundResource(R.drawable.ic_lumen_mark_tile);
                text.setContentDescription("Project Lumen Logo");
                return;
            }
        }
        if (view instanceof ViewGroup) {
            ViewGroup group = (ViewGroup) view;
            for (int index = 0; index < group.getChildCount(); index++) {
                installHeaderLogo(group.getChildAt(index));
            }
        }
    }

    private static String safeReason(String reason) {
        if (reason == null || reason.isBlank()) return "state-change";
        StringBuilder safe = new StringBuilder(reason.length());
        for (int index = 0; index < reason.length(); index++) {
            char value = reason.charAt(index);
            boolean allowed = value >= 'a' && value <= 'z'
                    || value >= 'A' && value <= 'Z'
                    || value >= '0' && value <= '9'
                    || value == '_' || value == '-';
            safe.append(allowed ? value : '_');
        }
        return safe.toString();
    }
}
