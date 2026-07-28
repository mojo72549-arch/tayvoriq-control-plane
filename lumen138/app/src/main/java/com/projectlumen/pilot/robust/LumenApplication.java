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
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.lang.ref.WeakReference;

/** Process-level parental lock, dedicated adult hub and brand installer. */
public final class LumenApplication extends Application
        implements Application.ActivityLifecycleCallbacks {
    private static final String ACTIONS_TAG = "lumen-parental-actions-v2";
    private final Handler main = new Handler(Looper.getMainLooper());
    private int startedActivities;
    private boolean pendingCatalogRefresh;
    private WeakReference<MainActivity> mainActivity = new WeakReference<>(null);

    private final Runnable backgroundLock = () -> {
        if (startedActivities == 0) {
            pendingCatalogRefresh = ParentalControl.isUnlocked() || AdultContentPolicy.isAdultMode();
            AdultContentPolicy.setAdultMode(false);
            ParentalControl.lock("app-background");
            DiagnosticLog.get(this).event("-", "PARENTAL-LOCK", "reason=app-background");
        }
    };

    @Override public void onCreate() {
        super.onCreate();
        ParentalControl.initialize(this);
        ParentalControl.setListener((unlocked, reason) -> {
            if (!unlocked) AdultContentPolicy.setAdultMode(false);
            DiagnosticLog.get(this).event("-",
                    unlocked ? "PARENTAL-UNLOCK" : "PARENTAL-LOCK",
                    "reason=" + safeReason(reason));
            if (startedActivities == 0) {
                pendingCatalogRefresh = true;
                return;
            }
            refreshMainActivity();
        });
        registerActivityLifecycleCallbacks(this);
    }

    @Override public void onActivityCreated(Activity activity, Bundle state) {
        if (activity instanceof MainActivity) {
            mainActivity = new WeakReference<>((MainActivity) activity);
        }
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
            if (pendingCatalogRefresh) {
                pendingCatalogRefresh = false;
                activity.recreate();
                return;
            }
        } else if (activity instanceof ParentalControlActivity) {
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

    @Override public void onActivityDestroyed(Activity activity) {
        MainActivity current = mainActivity.get();
        if (activity == current) mainActivity.clear();
    }

    private void refreshMainActivity() {
        MainActivity activity = mainActivity.get();
        if (activity != null && !activity.isFinishing() && !activity.isDestroyed()) {
            activity.recreate();
        } else {
            pendingCatalogRefresh = true;
        }
    }

    private void blockAdultPlayerIfNeeded(Activity activity) {
        if (!(activity instanceof PlayerActivity) || ParentalControl.isUnlocked()) return;
        String name = activity.getIntent().getStringExtra(PlayerActivity.EXTRA_NAME);
        if (!AdultContentPolicy.isAdultText(name)) return;
        DiagnosticLog.get(this).event("-", "PARENTAL-BLOCK", "target=player");
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

        Button parental = actionButton(activity, "🛡  Jugendschutz", 0xFF17354A, Color.WHITE);
        parental.setOnClickListener(v -> activity.startActivity(
                new Intent(activity, ParentalControlActivity.class)));
        actions.addView(parental, weighted(activity, 0));

        if (ParentalControl.isUnlocked()) {
            boolean adult = AdultContentPolicy.isAdultMode();
            Button scope = actionButton(activity,
                    adult ? "Familienbereich" : "18+ Filme öffnen",
                    adult ? 0xFF62E7D3 : 0xFFE94D5F,
                    adult ? 0xFF050D18 : Color.WHITE);
            scope.setOnClickListener(v -> {
                boolean next = !AdultContentPolicy.isAdultMode();
                AdultContentPolicy.setAdultMode(next);
                if (next) {
                    activity.getSharedPreferences("lumen_premium_view_state", MODE_PRIVATE)
                            .edit().putString("mode", "MOVIES")
                            .putString("language", "ALL").apply();
                }
                DiagnosticLog.get(activity).event("-", "PARENTAL-SCOPE",
                        "adultMode=" + next);
                activity.recreate();
            });
            LinearLayout.LayoutParams scopeParams = weighted(activity, dp(activity, 7));
            actions.addView(scope, scopeParams);
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
            for (int i = 0; i < group.getChildCount(); i++) {
                ViewGroup found = findMainColumn(group.getChildAt(i));
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
        button.setTextSize(11);
        button.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        button.setTextColor(textColor);
        button.setMinWidth(0);
        button.setMinHeight(0);
        button.setPadding(dp(activity, 8), 0, dp(activity, 8), 0);
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
            for (int i = 0; i < group.getChildCount(); i++) {
                installHeaderLogo(group.getChildAt(i));
            }
        }
    }

    private static String safeReason(String reason) {
        if (reason == null || reason.isBlank()) return "state-change";
        return reason.replaceAll("[^a-zA-Z0-9_-]", "_");
    }
}
