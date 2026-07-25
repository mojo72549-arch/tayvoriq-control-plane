package com.projectlumen.publicpreview;

import android.app.Activity;
import android.content.Context;
import android.graphics.drawable.GradientDrawable;
import android.view.View;
import android.view.ViewGroup;
import android.widget.FrameLayout;

/** Shared R7 palette, surfaces and focus behaviour. */
public final class PremiumUi {
    public static final int BG = 0xFF040A12;
    public static final int SURFACE = 0xD91A2737;
    public static final int SURFACE_ALT = 0xE0223348;
    public static final int GLASS = 0xB8142333;
    public static final int PRIMARY = 0xFF54E5D1;
    public static final int PRIMARY_BLUE = 0xFF4BA7FF;
    public static final int ACCENT = 0xFF806BFF;
    public static final int TEXT = 0xFFF7FAFD;
    public static final int MUTED = 0xFF9EACBC;
    public static final int BORDER = 0x665C7592;
    public static final int BORDER_FOCUS = 0xFF65E6D6;

    private PremiumUi() {}

    public static FrameLayout frame(Activity activity, View content) {
        FrameLayout frame = new FrameLayout(activity);
        PremiumBackgroundView background = new PremiumBackgroundView(activity);
        frame.addView(background, match());
        content.setBackgroundColor(0x00000000);
        frame.addView(content, match());
        return frame;
    }

    public static GradientDrawable surface(Context context, boolean elevated) {
        GradientDrawable drawable = new GradientDrawable(
                GradientDrawable.Orientation.TL_BR,
                elevated
                        ? new int[]{0xF0253548, 0xE8172638}
                        : new int[]{0xD91A293B, 0xD9132130});
        drawable.setCornerRadius(dp(context, elevated ? 24 : 19));
        drawable.setStroke(dp(context, 1), BORDER);
        return drawable;
    }

    public static GradientDrawable hero(Context context) {
        GradientDrawable drawable = new GradientDrawable(
                GradientDrawable.Orientation.TL_BR,
                new int[]{0xF0163B4A, 0xED173147, 0xE7261F4C});
        drawable.setCornerRadius(dp(context, 28));
        drawable.setStroke(dp(context, 1), 0x8871E8DA);
        return drawable;
    }

    public static GradientDrawable button(Context context, boolean primary, boolean focused) {
        int[] colors;
        if (primary) colors = focused
                ? new int[]{0xFF78F0DF, 0xFF54BFFF}
                : new int[]{0xFF55E3D0, 0xFF4BA7FF};
        else colors = focused
                ? new int[]{0xFF294A5F, 0xFF33445D}
                : new int[]{0xE31C3345, 0xE3202C42};
        GradientDrawable drawable = new GradientDrawable(GradientDrawable.Orientation.LEFT_RIGHT, colors);
        drawable.setCornerRadius(dp(context, 17));
        drawable.setStroke(dp(context, focused ? 2 : 1), focused ? BORDER_FOCUS : BORDER);
        return drawable;
    }

    public static GradientDrawable chip(Context context, boolean selected, boolean focused) {
        GradientDrawable drawable = new GradientDrawable(
                GradientDrawable.Orientation.LEFT_RIGHT,
                selected
                        ? new int[]{0xFF54E5D1, 0xFF4BA7FF}
                        : new int[]{0xC21B2B3B, 0xC21B2638});
        drawable.setCornerRadius(dp(context, 22));
        drawable.setStroke(dp(context, focused ? 2 : 1), focused ? BORDER_FOCUS : BORDER);
        return drawable;
    }

    public static void focus(View view, boolean primary) {
        view.setFocusable(true);
        view.setOnFocusChangeListener((target, focused) -> {
            target.animate()
                    .scaleX(focused ? 1.045f : 1f)
                    .scaleY(focused ? 1.045f : 1f)
                    .translationZ(focused ? dp(target.getContext(), 10) : 0)
                    .setDuration(135L)
                    .start();
            target.setBackground(button(target.getContext(), primary, focused));
        });
    }

    public static int dp(Context context, int value) {
        return Math.round(value * context.getResources().getDisplayMetrics().density);
    }

    private static FrameLayout.LayoutParams match() {
        return new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT);
    }
}
