package com.projectlumen.pilot.robust;

import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;

import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

final class UiStallWatchdog {
    private final Handler main = new Handler(Looper.getMainLooper());
    private final ScheduledExecutorService timer = Executors.newSingleThreadScheduledExecutor(r -> {
        Thread t = new Thread(r, "lumen-ui-watchdog");
        t.setDaemon(true);
        return t;
    });
    private final DiagnosticLog log;
    private volatile long lastAck = SystemClock.uptimeMillis();
    private volatile boolean stalled;

    UiStallWatchdog(DiagnosticLog log) {
        this.log = log;
        timer.scheduleAtFixedRate(this::tick, 1, 1, TimeUnit.SECONDS);
    }

    private void tick() {
        long sent = SystemClock.uptimeMillis();
        main.post(() -> {
            long delay = SystemClock.uptimeMillis() - sent;
            lastAck = SystemClock.uptimeMillis();
            if (stalled) {
                stalled = false;
                log.event("-", "UI-STALL-RECOVERED", "deliveryDelayMs=" + delay);
            }
        });
        long silence = SystemClock.uptimeMillis() - lastAck;
        if (silence >= 2000 && !stalled) {
            stalled = true;
            Thread mainThread = Looper.getMainLooper().getThread();
            StackTraceElement[] stack = mainThread.getStackTrace();
            String top = stack.length == 0 ? "unknown" : stack[0].toString();
            log.event("-", "UI-STALL-DETECTED", "durationMs=" + silence + " mainTop=" + top);
        }
    }

    void stop() { timer.shutdownNow(); }
}
