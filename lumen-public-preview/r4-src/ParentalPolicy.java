package com.projectlumen.publicpreview;

import android.content.Context;
import java.lang.reflect.Field;
import java.util.Locale;

/** Conservative local child-profile filter; no content metadata is uploaded. */
public final class ParentalPolicy {
    private static final String[] BLOCKED = {
            "adult", "adults", "xxx", "18+", "+18", "erotic", "erotik", "porn", "playboy", "redlight", "hot night"
    };

    private ParentalPolicy() {}

    public static boolean isAllowed(Context context, Object item) {
        if (!ProfileStore.isChildMode(context)) return true;
        StringBuilder text = new StringBuilder();
        if (item != null) {
            text.append(String.valueOf(item)).append(' ');
            for (Field field : item.getClass().getDeclaredFields()) {
                try {
                    field.setAccessible(true);
                    Object value = field.get(item);
                    if (value instanceof CharSequence || value instanceof Enum<?>) {
                        text.append(value).append(' ');
                    }
                } catch (Throwable ignored) {
                }
            }
        }
        String normalized = text.toString().toLowerCase(Locale.ROOT);
        for (String token : BLOCKED) {
            if (normalized.contains(token)) return false;
        }
        return true;
    }
}
