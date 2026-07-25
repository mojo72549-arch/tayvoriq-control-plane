package com.projectlumen.publicpreview;

import android.animation.ValueAnimator;
import android.app.UiModeManager;
import android.content.Context;
import android.content.res.Configuration;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.RadialGradient;
import android.graphics.Shader;
import android.os.PowerManager;
import android.util.AttributeSet;
import android.view.View;
import android.view.animation.LinearInterpolator;

/**
 * Rubu-inspired dark premium background with subtle cyan/petrol/violet light.
 * Motion is intentionally slow and is disabled on televisions and in power-save mode.
 */
public final class PremiumBackgroundView extends View {
    private final Paint base = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint glow = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint grain = new Paint(Paint.ANTI_ALIAS_FLAG);
    private ValueAnimator animator;
    private float phase;
    private boolean motionAllowed;

    public PremiumBackgroundView(Context context) { this(context, null); }
    public PremiumBackgroundView(Context context, AttributeSet attrs) {
        super(context, attrs);
        setWillNotDraw(false);
        grain.setColor(0x0FFFFFFF);
        motionAllowed = !isTelevision(context) && !isPowerSave(context);
    }

    @Override protected void onAttachedToWindow() {
        super.onAttachedToWindow();
        if (!motionAllowed || animator != null) return;
        animator = ValueAnimator.ofFloat(0f, 1f);
        animator.setDuration(20_000L);
        animator.setRepeatCount(ValueAnimator.INFINITE);
        animator.setRepeatMode(ValueAnimator.REVERSE);
        animator.setInterpolator(new LinearInterpolator());
        animator.addUpdateListener(value -> {
            phase = (float) value.getAnimatedValue();
            invalidate();
        });
        animator.start();
    }

    @Override protected void onDetachedFromWindow() {
        if (animator != null) animator.cancel();
        animator = null;
        super.onDetachedFromWindow();
    }

    @Override protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        int width = Math.max(1, getWidth());
        int height = Math.max(1, getHeight());
        base.setShader(new LinearGradient(0, 0, width, height,
                new int[]{0xFF040A12, 0xFF071521, 0xFF07101C, 0xFF03070D},
                new float[]{0f, 0.36f, 0.72f, 1f}, Shader.TileMode.CLAMP));
        canvas.drawRect(0, 0, width, height, base);

        float drift = motionAllowed ? phase : 0.35f;
        drawGlow(canvas, width * (0.08f + 0.10f * drift), height * 0.10f,
                Math.max(width, height) * 0.70f, 0x5032D8D0, 0x0032D8D0);
        drawGlow(canvas, width * (0.91f - 0.08f * drift), height * 0.82f,
                Math.max(width, height) * 0.62f, 0x3D6252F4, 0x006252F4);
        drawGlow(canvas, width * 0.62f, height * (0.16f + 0.04f * drift),
                Math.max(width, height) * 0.42f, 0x263A86FF, 0x003A86FF);

        int step = Math.max(56, Math.min(width, height) / 12);
        for (int y = step / 2; y < height; y += step) {
            for (int x = step / 2; x < width; x += step) {
                int hash = (x * 31 + y * 17) & 7;
                if (hash == 0 || hash == 3) canvas.drawCircle(x, y, 0.75f, grain);
            }
        }
    }

    private void drawGlow(Canvas canvas, float x, float y, float radius, int center, int edge) {
        glow.setShader(new RadialGradient(x, y, radius,
                new int[]{center, Color.argb(18, Color.red(center), Color.green(center), Color.blue(center)), edge},
                new float[]{0f, 0.42f, 1f}, Shader.TileMode.CLAMP));
        canvas.drawCircle(x, y, radius, glow);
    }

    private static boolean isTelevision(Context context) {
        UiModeManager manager = (UiModeManager) context.getSystemService(Context.UI_MODE_SERVICE);
        return manager != null && manager.getCurrentModeType() == Configuration.UI_MODE_TYPE_TELEVISION;
    }

    private static boolean isPowerSave(Context context) {
        PowerManager manager = (PowerManager) context.getSystemService(Context.POWER_SERVICE);
        return manager != null && manager.isPowerSaveMode();
    }
}
