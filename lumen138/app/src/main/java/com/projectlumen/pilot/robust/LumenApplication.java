package com.projectlumen.pilot.robust;

import android.app.Activity;
import android.app.Application;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.widget.TextView;
import android.view.View;
import android.view.ViewGroup;

import java.lang.ref.WeakReference;

/** Process-level parental lock and brand installer. */
public final class LumenApplication extends Application
        implements Application.ActivityLifecycleCallbacks {
    private final Handler main = new Handler(Looper.getMainLooper());
    private int startedActivities;
    private WeakReference<MainActivity> mainActivity = new WeakReference<>(null);
    private final Runnable backgroundLock = () -> {
        if (startedActivities == 0) {
            ParentalControl.lock("app-background");
            DiagnosticLog.get(this).event("-", "PARENTAL-LOCK", "reason=app-background");
        }
    };

    @Override public void onCreate() {
        super.onCreate();
        ParentalControl.initialize(this);
        ParentalControl.setListener((unlocked, reason) -> {
            DiagnosticLog.get(this).event("-", unlocked ? "PARENTAL-UNLOCK" : "PARENTAL-LOCK",
                    "reason=" + safeReason(reason));
            MainActivity activity = mainActivity.get();
            if (activity != null && !activity.isFinishing() && !activity.isDestroyed()) {
                activity.recreate();
            }
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
        if (activity instanceof MainActivity) installHeaderLogo(activity.getWindow().getDecorView());
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

    private void blockAdultPlayerIfNeeded(Activity activity) {
        if (!(activity instanceof PlayerActivity) || ParentalControl.isUnlocked()) return;
        String name = activity.getIntent().getStringExtra(PlayerActivity.EXTRA_NAME);
        if (!AdultContentPolicy.isAdultText(name)) return;
        DiagnosticLog.get(this).event("-", "PARENTAL-BLOCK", "target=player");
        activity.finish();
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
            for (int i = 0; i < group.getChildCount(); i++) installHeaderLogo(group.getChildAt(i));
        }
    }

    private static String safeReason(String reason) {
        if (reason == null || reason.isBlank()) return "state-change";
        return reason.replaceAll("[^a-zA-Z0-9_-]", "_");
    }
}
