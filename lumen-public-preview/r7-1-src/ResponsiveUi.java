package com.projectlumen.publicpreview;

import android.app.UiModeManager;
import android.content.Context;
import android.content.res.Configuration;
import android.text.TextUtils;
import android.util.TypedValue;
import android.widget.TextView;

/** Responsive tokens for compact phones, normal phones, large phones/tablets and TV. */
public final class ResponsiveUi {
    public enum WidthClass { COMPACT, STANDARD, LARGE, TV }

    private ResponsiveUi() {}

    public static WidthClass widthClass(Context context) {
        if (isTelevision(context)) return WidthClass.TV;
        int widthDp = context.getResources().getConfiguration().screenWidthDp;
        if (widthDp > 0 && widthDp <= 360) return WidthClass.COMPACT;
        if (widthDp >= 412) return WidthClass.LARGE;
        return WidthClass.STANDARD;
    }

    public static boolean compact(Context context) {
        return widthClass(context) == WidthClass.COMPACT;
    }

    public static boolean large(Context context) {
        return widthClass(context) == WidthClass.LARGE;
    }

    public static boolean isTelevision(Context context) {
        int type = context.getResources().getConfiguration().uiMode & Configuration.UI_MODE_TYPE_MASK;
        if (type == Configuration.UI_MODE_TYPE_TELEVISION) return true;
        UiModeManager manager = (UiModeManager) context.getSystemService(Context.UI_MODE_SERVICE);
        return manager != null && manager.getCurrentModeType() == Configuration.UI_MODE_TYPE_TELEVISION;
    }

    public static int sp(Context context, int compact, int standard, int large, int television) {
        switch (widthClass(context)) {
            case COMPACT: return compact;
            case LARGE: return large;
            case TV: return television;
            default: return standard;
        }
    }

    public static int dp(Context context, int compact, int standard, int large, int television) {
        return Math.round(select(context, compact, standard, large, television)
                * context.getResources().getDisplayMetrics().density);
    }

    public static int value(Context context, int compact, int standard, int large, int television) {
        return select(context, compact, standard, large, television);
    }

    public static int sidePaddingDp(Context context) {
        return select(context, 12, 16, 22, 28);
    }

    public static int contentGapDp(Context context) {
        return select(context, 10, 12, 14, 18);
    }

    public static void polish(TextView view, int maxLines) {
        view.setIncludeFontPadding(false);
        view.setLineSpacing(0f, 1.08f);
        view.setMaxLines(Math.max(1, maxLines));
        view.setEllipsize(TextUtils.TruncateAt.END);
        if (android.os.Build.VERSION.SDK_INT >= 23) {
            view.setBreakStrategy(android.text.Layout.BREAK_STRATEGY_HIGH_QUALITY);
            view.setHyphenationFrequency(android.text.Layout.HYPHENATION_FREQUENCY_NONE);
        }
    }

    public static void singleLine(TextView view) {
        polish(view, 1);
        view.setSingleLine(true);
        view.setHorizontallyScrolling(false);
    }

    public static void setSp(TextView view, int compact, int standard, int large, int television) {
        view.setTextSize(TypedValue.COMPLEX_UNIT_SP,
                sp(view.getContext(), compact, standard, large, television));
    }

    private static int select(Context context, int compact, int standard, int large, int television) {
        switch (widthClass(context)) {
            case COMPACT: return compact;
            case LARGE: return large;
            case TV: return television;
            default: return standard;
        }
    }
}
