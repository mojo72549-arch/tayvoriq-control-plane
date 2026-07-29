package com.projectlumen.pilot.robust;

import android.graphics.Canvas;
import android.graphics.ColorFilter;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.PixelFormat;
import android.graphics.Shader;
import android.graphics.drawable.Drawable;
import android.os.SystemClock;

/** Low-frequency animated navy/petrol/violet gradient used by the premium shell. */
final class LumenFlowDrawable extends Drawable implements Runnable {
    private static final long FRAME_MS = 70L;
    private static final long CYCLE_MS = 18_000L;
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private boolean running = true;

    @Override public void draw(Canvas canvas) {
        float width = Math.max(1f, getBounds().width());
        float height = Math.max(1f, getBounds().height());
        float phase = (SystemClock.uptimeMillis() % CYCLE_MS) / (float) CYCLE_MS;
        double angle = phase * Math.PI * 2.0;
        float swayX = (float) Math.sin(angle) * width * 0.18f;
        float swayY = (float) Math.cos(angle * 0.7) * height * 0.12f;
        float p1 = 0.23f + (float) Math.sin(angle) * 0.045f;
        float p2 = 0.60f + (float) Math.cos(angle * 0.8) * 0.055f;
        int[] colors = new int[]{0xFF030914, 0xFF082234, 0xFF0D4350, 0xFF211B3D};
        float[] positions = new float[]{0f, p1, p2, 1f};
        paint.setShader(new LinearGradient(
                -swayX, -swayY, width + swayX, height + swayY,
                colors, positions, Shader.TileMode.CLAMP));
        canvas.drawRect(getBounds(), paint);
        if (running) scheduleSelf(this, SystemClock.uptimeMillis() + FRAME_MS);
    }

    @Override public void run() { invalidateSelf(); }

    @Override public boolean setVisible(boolean visible, boolean restart) {
        running = visible;
        if (visible) {
            unscheduleSelf(this);
            scheduleSelf(this, SystemClock.uptimeMillis() + FRAME_MS);
        } else {
            unscheduleSelf(this);
        }
        return super.setVisible(visible, restart);
    }

    @Override public void setAlpha(int alpha) { paint.setAlpha(alpha); }
    @Override public void setColorFilter(ColorFilter filter) { paint.setColorFilter(filter); }
    @Override public int getOpacity() { return PixelFormat.OPAQUE; }
}
