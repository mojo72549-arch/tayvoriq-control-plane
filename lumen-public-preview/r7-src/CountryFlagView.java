package com.projectlumen.publicpreview;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RectF;
import android.view.View;

/** Lightweight vector flags so presentation is consistent across Android vendors. */
public final class CountryFlagView extends View {
    private final String code;
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Path path = new Path();

    public CountryFlagView(Context context, String code) {
        super(context);
        this.code = code == null ? "WORLD" : code.toUpperCase(java.util.Locale.ROOT);
        setLayerType(LAYER_TYPE_SOFTWARE, null);
    }

    @Override protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        float width = getWidth();
        float height = getHeight();
        RectF rect = new RectF(1, 1, width - 1, height - 1);
        canvas.save();
        path.reset();
        path.addRoundRect(rect, height * 0.18f, height * 0.18f, Path.Direction.CW);
        canvas.clipPath(path);
        switch (code) {
            case "DE" -> germany(canvas, rect);
            case "TR" -> turkey(canvas, rect);
            case "GB" -> unitedKingdom(canvas, rect);
            default -> world(canvas, rect);
        }
        canvas.restore();
        paint.setStyle(Paint.Style.STROKE);
        paint.setStrokeWidth(Math.max(1f, height * 0.025f));
        paint.setColor(0x669FC7DF);
        canvas.drawRoundRect(rect, height * 0.18f, height * 0.18f, paint);
        paint.setStyle(Paint.Style.FILL);
    }

    private void germany(Canvas canvas, RectF r) {
        float third = r.height() / 3f;
        fill(canvas, Color.BLACK, r.left, r.top, r.right, r.top + third);
        fill(canvas, 0xFFDD0000, r.left, r.top + third, r.right, r.top + third * 2f);
        fill(canvas, 0xFFFFCE00, r.left, r.top + third * 2f, r.right, r.bottom);
    }

    private void turkey(Canvas canvas, RectF r) {
        fill(canvas, 0xFFE30A17, r.left, r.top, r.right, r.bottom);
        float cx = r.left + r.width() * 0.42f;
        float cy = r.centerY();
        paint.setColor(Color.WHITE);
        canvas.drawCircle(cx, cy, r.height() * 0.28f, paint);
        paint.setColor(0xFFE30A17);
        canvas.drawCircle(cx + r.height() * 0.10f, cy, r.height() * 0.225f, paint);
        paint.setColor(Color.WHITE);
        star(canvas, cx + r.height() * 0.34f, cy, r.height() * 0.105f, -90f);
    }

    private void unitedKingdom(Canvas canvas, RectF r) {
        fill(canvas, 0xFF21468B, r.left, r.top, r.right, r.bottom);
        paint.setStrokeCap(Paint.Cap.SQUARE);
        paint.setColor(Color.WHITE); paint.setStrokeWidth(r.height() * 0.22f);
        canvas.drawLine(r.left, r.top, r.right, r.bottom, paint);
        canvas.drawLine(r.right, r.top, r.left, r.bottom, paint);
        paint.setColor(0xFFCF142B); paint.setStrokeWidth(r.height() * 0.10f);
        canvas.drawLine(r.left, r.top, r.right, r.bottom, paint);
        canvas.drawLine(r.right, r.top, r.left, r.bottom, paint);
        paint.setColor(Color.WHITE);
        canvas.drawRect(r.left, r.centerY() - r.height() * 0.16f, r.right, r.centerY() + r.height() * 0.16f, paint);
        canvas.drawRect(r.centerX() - r.height() * 0.16f, r.top, r.centerX() + r.height() * 0.16f, r.bottom, paint);
        paint.setColor(0xFFCF142B);
        canvas.drawRect(r.left, r.centerY() - r.height() * 0.09f, r.right, r.centerY() + r.height() * 0.09f, paint);
        canvas.drawRect(r.centerX() - r.height() * 0.09f, r.top, r.centerX() + r.height() * 0.09f, r.bottom, paint);
        paint.setStrokeCap(Paint.Cap.BUTT);
    }

    private void world(Canvas canvas, RectF r) {
        fill(canvas, 0xFF123D54, r.left, r.top, r.right, r.bottom);
        paint.setStyle(Paint.Style.STROKE);
        paint.setStrokeWidth(Math.max(2f, r.height() * 0.045f));
        paint.setColor(0xFF57E3D1);
        float radius = r.height() * 0.31f;
        canvas.drawCircle(r.centerX(), r.centerY(), radius, paint);
        canvas.drawOval(new RectF(r.centerX() - radius * 0.48f, r.centerY() - radius,
                r.centerX() + radius * 0.48f, r.centerY() + radius), paint);
        canvas.drawLine(r.centerX() - radius, r.centerY(), r.centerX() + radius, r.centerY(), paint);
        paint.setStyle(Paint.Style.FILL);
    }

    private void star(Canvas canvas, float cx, float cy, float radius, float rotation) {
        Path star = new Path();
        for (int i = 0; i < 10; i++) {
            double angle = Math.toRadians(rotation + i * 36f);
            float length = (i & 1) == 0 ? radius : radius * 0.42f;
            float x = cx + (float) Math.cos(angle) * length;
            float y = cy + (float) Math.sin(angle) * length;
            if (i == 0) star.moveTo(x, y); else star.lineTo(x, y);
        }
        star.close();
        canvas.drawPath(star, paint);
    }

    private void fill(Canvas canvas, int color, float left, float top, float right, float bottom) {
        paint.setStyle(Paint.Style.FILL); paint.setColor(color); canvas.drawRect(left, top, right, bottom, paint);
    }
}
