package com.projectlumen.pilot.robust;

import android.app.Activity;
import android.app.Application;
import android.os.Bundle;
import android.widget.Toast;

public final class LumenApplication extends Application {
    @Override
    public void onCreate() {
        super.onCreate();
        registerActivityLifecycleCallbacks(new ActivityLifecycleCallbacks() {
            @Override
            public void onActivityCreated(Activity activity, Bundle state) {
                if (!(activity instanceof PlayerActivity)) return;
                boolean adult = activity.getIntent() != null
                        && activity.getIntent().getBooleanExtra(
                        ParentalControl.EXTRA_ADULT_CONTENT, false);
                if (adult && !ParentalControl.isSessionUnlocked()) {
                    DiagnosticLog.get(LumenApplication.this).event(
                            "-", "PARENTAL-PLAYER-BLOCKED",
                            "reason=adult-session-locked");
                    activity.finish();
                    Toast.makeText(LumenApplication.this,
                            "Erwachsenen-Inhalt gesperrt. Eltern-PIN erforderlich.",
                            Toast.LENGTH_LONG).show();
                }
            }

            @Override public void onActivityStarted(Activity activity) { }
            @Override public void onActivityResumed(Activity activity) { }
            @Override public void onActivityPaused(Activity activity) { }
            @Override public void onActivityStopped(Activity activity) { }
            @Override public void onActivitySaveInstanceState(Activity activity, Bundle state) { }
            @Override public void onActivityDestroyed(Activity activity) { }
        });
    }
}
