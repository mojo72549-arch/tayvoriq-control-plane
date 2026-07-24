package com.projectlumen.publicpreview;

import android.content.Context;
import java.lang.reflect.Field;
import java.util.*;

/** Central, local-only content guard for child profiles. */
public final class ParentalPolicy {
    private static final String[] BLOCKED = {
            "adult", "adults", "xxx", "18+", "+18", "erotic", "erotik",
            "porn", "playboy", "redlight", "hot night", "blue movie"
    };
    private static Object cachedSource;
    private static List<?> cachedResult;
    private ParentalPolicy() {}

    public static boolean isAllowed(Context context, Object item) {
        if (!ProfileStore.isChildMode(context)) return true;
        if (item == null) return false;
        StringBuilder text = new StringBuilder(String.valueOf(item));
        for (Field field : item.getClass().getDeclaredFields()) {
            try {
                field.setAccessible(true);
                Object value = field.get(item);
                if (value instanceof CharSequence || value instanceof Enum<?>) text.append(' ').append(value);
            } catch (Throwable ignored) {}
        }
        String normalized = text.toString().toLowerCase(Locale.ROOT);
        for (String token : BLOCKED) if (normalized.contains(token)) return false;
        return true;
    }

    @SuppressWarnings("unchecked")
    public static synchronized <T> List<T> filter(Context context, List<T> source) {
        if (source == null || source.isEmpty()) return Collections.emptyList();
        if (!ProfileStore.isChildMode(context)) return source;
        if (source == cachedSource && cachedResult != null) return (List<T>) cachedResult;
        List<T> result = new ArrayList<>();
        for (T item : source) if (isAllowed(context, item)) result.add(item);
        cachedSource = source;
        cachedResult = Collections.unmodifiableList(result);
        return (List<T>) cachedResult;
    }
    public static synchronized void invalidate() { cachedSource = null; cachedResult = null; }
}
