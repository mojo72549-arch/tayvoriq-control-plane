package com.projectlumen.pilot.robust;

import android.app.Activity;
import android.app.Application;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.TextView;

import java.lang.ref.WeakReference;

/** Process-level security lifecycle and brand installer. */
public final class LumenApplication extends Application
        implements Application.ActivityLifecycleCallbacks {
    private final Handler main = new Handler(Looper.getMainLooper());
    private int startedActivities;
    private boolean pendingCatalogRefresh;
    private WeakReference<MainActivity> mainActivity = new WeakReference<>(null);
    private WeakReference<PlayerActivity> playerActivity = new WeakReference<>(null);

    private final Runnable backgroundLock = () -> {
        if (!ParentalFeature.enabled()) return;
        if (startedActivities == 0) {
            pendingCatalogRefresh = ParentalControl.isUnlocked();
            ParentalControl.lock("app-background");
            DiagnosticLog.get(this).event("-", "PARENTAL-LOCK", "reason=app-background");
        }
    };

    @Override public void onCreate() {
        super.onCreate();
        if (ParentalFeature.enabled()) {
            ParentalControl.initialize(this);
            ParentalControl.setListener((unlocked, reason) -> {
                DiagnosticLog.get(this).event("-",
                        unlocked ? "PARENTAL-UNLOCK" : "PARENTAL-LOCK",
                        "reason=" + safeReason(reason));
                if (!unlocked) finishActivePlayback();
                if (startedActivities == 0) {
                    pendingCatalogRefresh = true;
                    return;
                }
                refreshMainActivity();
            });
        }
        registerActivityLifecycleCallbacks(this);
    }

    @Override public void onActivityCreated(Activity activity, Bundle state) {
        if (activity instanceof MainActivity) {
            mainActivity = new WeakReference<>((MainActivity) activity);
        } else if (activity instanceof PlayerActivity) {
            playerActivity = new WeakReference<>((PlayerActivity) activity);
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
            installHeaderLogoAndReleaseControls(activity.getWindow().getDecorView());
            if (ParentalFeature.enabled() && pendingCatalogRefresh) {
                pendingCatalogRefresh = false;
                activity.recreate();
                return;
            }
        }
        blockAdultPlayerIfNeeded(activity);
    }

    @Override public void onActivityPaused(Activity activity) { }

    @Override public void onActivityStopped(Activity activity) {
        startedActivities = Math.max(0, startedActivities - 1);
        if (ParentalFeature.enabled() && startedActivities == 0
                && !activity.isChangingConfigurations()) {
            main.removeCallbacks(backgroundLock);
            main.postDelayed(backgroundLock, 600L);
        }
    }

    @Override public void onActivitySaveInstanceState(Activity activity, Bundle state) { }

    @Override public void onActivityDestroyed(Activity activity) {
        MainActivity currentMain = mainActivity.get();
        if (activity == currentMain) mainActivity.clear();
        PlayerActivity currentPlayer = playerActivity.get();
        if (activity == currentPlayer) playerActivity.clear();
    }

    private void refreshMainActivity() {
        MainActivity activity = mainActivity.get();
        if (activity != null && !activity.isFinishing() && !activity.isDestroyed()) {
            activity.recreate();
        } else {
            pendingCatalogRefresh = true;
        }
    }

    /**
     * Fail closed when an unlock session expires. The current pilot does not
     * persist a content rating on PlayerActivity, so stopping any playback that
     * is active at the lock transition is safer than allowing restricted media
     * to continue.
     */
    private void finishActivePlayback() {
        PlayerActivity activity = playerActivity.get();
        if (activity != null && !activity.isFinishing() && !activity.isDestroyed()) {
            DiagnosticLog.get(this).event("-", "PARENTAL-BLOCK",
                    "target=active-player reason=session-ended");
            activity.finish();
        }
    }

    private void blockAdultPlayerIfNeeded(Activity activity) {
        if (!ParentalFeature.enabled()) return;
        if (!(activity instanceof PlayerActivity) || ParentalControl.isUnlocked()) return;
        String name = activity.getIntent().getStringExtra(PlayerActivity.EXTRA_NAME);
        if (!AdultContentPolicy.isAdultText(name)) return;
        DiagnosticLog.get(this).event("-", "PARENTAL-BLOCK", "target=player");
        activity.finish();
    }

    private static void installHeaderLogoAndReleaseControls(View view) {
        if (view instanceof TextView) {
            TextView text = (TextView) view;
            if ("✦".contentEquals(text.getText())) {
                text.setText("");
                text.setBackgroundResource(R.drawable.ic_lumen_mark_tile);
                text.setContentDescription("Project Lumen Logo");
            } else if (!BuildConfig.DIAGNOSTICS_UI_ENABLED
                    && view instanceof Button
                    && "System".contentEquals(text.getText())) {
                text.setText("Mehr");
                text.setContentDescription("Mehr und Jugendschutz");
            }
        }
        if (view instanceof ViewGroup) {
            ViewGroup group = (ViewGroup) view;
            for (int i = 0; i < group.getChildCount(); i++) {
                installHeaderLogoAndReleaseControls(group.getChildAt(i));
            }
        }
    }

    private static String safeReason(String reason) {
        if (reason == null || reason.isBlank()) return "state-change";
        return reason.replaceAll("[^a-zA-Z0-9_-]", "_");
    }
}
