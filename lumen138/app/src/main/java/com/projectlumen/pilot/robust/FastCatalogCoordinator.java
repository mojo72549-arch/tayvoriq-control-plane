package com.projectlumen.pilot.robust;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.TextView;

import java.io.File;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.WeakHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Installs fast paths without changing the stable MainActivity import flow.
 * The first screen is painted from a bounded safe cache preview while the full
 * catalog continues loading, and blank-query switches use prepared buckets.
 */
final class FastCatalogCoordinator {
    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    private static final ExecutorService PREVIEW = Executors.newSingleThreadExecutor(r -> {
        Thread thread = new Thread(r, "lumen-instant-preview");
        thread.setDaemon(true);
        return thread;
    });
    private static final Map<Activity, State> STATES = new WeakHashMap<>();
    private static final Map<Activity, Integer> ADULT_REVISIONS = new WeakHashMap<>();
    private static final String ADULT_TOOLS_TAG = "lumen-adult-category-tools-v1";

    private FastCatalogCoordinator() { }

    static void install(MainActivity activity) {
        if (activity == null || activity.isFinishing() || activity.isDestroyed()) return;
        State state;
        synchronized (STATES) {
            state = STATES.get(activity);
            if (state == null) {
                state = new State();
                STATES.put(activity, state);
            }
            if (state.installed) return;
            state.installed = true;
        }

        try {
            hook(activity, state, "liveButton", "mode", "LIVE");
            hook(activity, state, "movieButton", "mode", "MOVIES");
            hook(activity, state, "seriesButton", "mode", "SERIES");
            hook(activity, state, "germanButton", "language", "DE");
            hook(activity, state, "turkishButton", "language", "TR");
            hook(activity, state, "allLanguageButton", "language", "ALL");
            showPreparedOrPreview(activity, state, "initial");
        } catch (Throwable failure) {
            DiagnosticLog.get(activity).exception("-", "FAST-CATALOG-INSTALL-ERROR", failure);
        }
    }

    static void installAdultTools(Activity activity) {
        if (!(activity instanceof AdultCatalogActivity)
                || !ParentalControl.isUnlocked()) return;
        refreshAdultCatalogIfPolicyChanged(activity);

        ViewGroup root = findVerticalRoot(activity.findViewById(android.R.id.content));
        if (root == null || root.findViewWithTag(ADULT_TOOLS_TAG) != null) return;

        Button manage = new Button(activity);
        manage.setTag(ADULT_TOOLS_TAG);
        manage.setText("Kategorien prüfen & zuordnen");
        manage.setAllCaps(false);
        manage.setSingleLine(true);
        manage.setTextSize(11);
        manage.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        manage.setTextColor(Color.WHITE);
        manage.setMinHeight(0);
        manage.setMinWidth(0);
        manage.setGravity(Gravity.CENTER);
        manage.setBackground(roundRect(activity, 0xFF5B3DB8, 13, 0xFF8D75E8));
        manage.setOnClickListener(v -> activity.startActivity(
                new Intent(activity, AdultCategoryManagerActivity.class)));

        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, dp(activity, 43));
        params.setMargins(0, dp(activity, 8), 0, dp(activity, 6));
        int index = Math.min(1, root.getChildCount());
        root.addView(manage, index, params);
    }

    private static void refreshAdultCatalogIfPolicyChanged(Activity activity) {
        int revision = AdultGroupPolicy.revision();
        Integer previous;
        synchronized (ADULT_REVISIONS) {
            previous = ADULT_REVISIONS.put(activity, revision);
        }
        if (previous == null || previous == revision) return;
        try {
            View progress = (View) readField(activity, "progress");
            TextView status = (TextView) readField(activity, "status");
            if (progress != null) progress.setVisibility(View.VISIBLE);
            if (status != null) status.setText("Neue Kategoriezuordnung wird übernommen …");
            invoke(activity, "loadProtectedCatalog");
            DiagnosticLog.get(activity).event("-", "ADULT-CATALOG-POLICY-REFRESH",
                    "fromRevision=" + previous + " toRevision=" + revision);
        } catch (Throwable failure) {
            DiagnosticLog.get(activity).exception("-", "ADULT-CATALOG-POLICY-REFRESH-ERROR",
                    failure);
        }
    }

    private static void hook(MainActivity activity, State state, String buttonField,
                             String stateField, String enumName) throws Exception {
        Button button = (Button) readField(activity, buttonField);
        if (button == null) return;
        button.setOnClickListener(v -> {
            try {
                Field target = declaredField(activity.getClass(), stateField);
                Object value = enumValue(target.getType(), enumName);
                target.set(activity, value);

                EditText search = (EditText) readField(activity, "search");
                boolean cleared = search != null && search.length() > 0;
                if (cleared) search.setText("");
                invoke(activity, "saveViewState");
                invoke(activity, "updateSelectionStyles");
                showPreparedOrPreview(activity, state, "selection");
                if (cleared) {
                    MAIN.postDelayed(() -> showPreparedOrPreview(activity, state,
                            "selection-after-search-clear"), 240L);
                }
            } catch (Throwable failure) {
                DiagnosticLog.get(activity).exception("-", "FAST-SWITCH-ERROR", failure);
            }
        });
    }

    private static void showPreparedOrPreview(MainActivity activity, State state, String reason) {
        if (activity.isFinishing() || activity.isDestroyed()) return;
        Selection selection;
        try {
            selection = currentSelection(activity);
        } catch (Throwable failure) {
            DiagnosticLog.get(activity).exception("-", "FAST-SELECTION-READ-ERROR", failure);
            return;
        }

        int generation = state.generation.incrementAndGet();
        if (CatalogSession.ready()) {
            List<Channel> rows = CatalogSession.family(selection.type, selection.language);
            submit(activity, state, generation, selection, rows,
                    "FAST-SWITCH-READY", reason, 0L);
            return;
        }

        File cache = new File(new File(activity.getFilesDir(), "catalog"), "active.catalog.bin");
        if (!CatalogCache.usable(cache)) return;
        long started = SystemClock.elapsedRealtime();
        DiagnosticLog.get(activity).event("-", "FAST-PREVIEW-START",
                "type=" + selection.type + " language=" + selection.language);
        PREVIEW.execute(() -> {
            try {
                List<Channel> rows = CatalogCache.readPreview(
                        cache, selection.type, selection.language, 180);
                long duration = SystemClock.elapsedRealtime() - started;
                MAIN.post(() -> submit(activity, state, generation, selection, rows,
                        "FAST-PREVIEW-READY", reason, duration));
            } catch (Throwable failure) {
                DiagnosticLog.get(activity).exception("-", "FAST-PREVIEW-ERROR", failure);
            }
        });
    }

    private static void submit(MainActivity activity, State state, int generation,
                               Selection selection, List<Channel> rows, String event,
                               String reason, long durationMs) {
        if (activity.isFinishing() || activity.isDestroyed()
                || generation != state.generation.get()) return;
        try {
            Selection current = currentSelection(activity);
            if (current.type != selection.type || current.language != selection.language) return;
            EditText search = (EditText) readField(activity, "search");
            if (search != null && search.length() > 0) return;

            CatalogAdapter adapter = (CatalogAdapter) readField(activity, "adapter");
            TextView count = (TextView) readField(activity, "count");
            TextView footer = (TextView) readField(activity, "footerStatus");
            View loading = (View) readField(activity, "loadingCard");
            ListView list = (ListView) readField(activity, "list");
            if (adapter == null || count == null) return;

            List<Channel> safeRows = rows == null ? Collections.emptyList() : rows;
            adapter.submit(safeRows);
            count.setText(String.valueOf(safeRows.size()));
            if (loading != null && !safeRows.isEmpty()) loading.setVisibility(View.GONE);
            if (footer != null) {
                footer.setText(event.equals("FAST-PREVIEW-READY")
                        ? "Sofortansicht bereit · Vollständiger Katalog lädt im Hintergrund"
                        : typeLabel(selection.type) + " · "
                        + MediaLanguage.label(selection.language) + " · "
                        + safeRows.size() + " Treffer");
            }
            DiagnosticLog.get(activity).event("-", event,
                    "type=" + selection.type + " language=" + selection.language
                            + " rows=" + safeRows.size() + " durationMs=" + durationMs
                            + " reason=" + reason);
            if (list != null) list.post(() -> DiagnosticLog.get(activity).event("-",
                    "FAST-FIRST-FRAME", "visibleChildren=" + list.getChildCount()));
        } catch (Throwable failure) {
            DiagnosticLog.get(activity).exception("-", "FAST-SUBMIT-ERROR", failure);
        }
    }

    private static Selection currentSelection(MainActivity activity) throws Exception {
        Object mode = readField(activity, "mode");
        MediaLanguage.Code language = (MediaLanguage.Code) readField(activity, "language");
        String modeName = mode == null ? "LIVE" : ((Enum<?>) mode).name();
        Channel.Type type = modeName.equals("MOVIES") ? Channel.Type.MOVIE
                : modeName.equals("SERIES") ? Channel.Type.SERIES : Channel.Type.LIVE;
        return new Selection(type, language == null ? MediaLanguage.Code.ALL : language);
    }

    private static Object readField(Object target, String name) throws Exception {
        Field field = declaredField(target.getClass(), name);
        return field.get(target);
    }

    private static Field declaredField(Class<?> type, String name) throws Exception {
        Field field = type.getDeclaredField(name);
        field.setAccessible(true);
        return field;
    }

    private static void invoke(Object target, String methodName) throws Exception {
        Method method = target.getClass().getDeclaredMethod(methodName);
        method.setAccessible(true);
        method.invoke(target);
    }

    @SuppressWarnings({"unchecked", "rawtypes"})
    private static Object enumValue(Class<?> enumType, String name) {
        return Enum.valueOf((Class<? extends Enum>) enumType, name);
    }

    private static ViewGroup findVerticalRoot(View view) {
        if (view instanceof LinearLayout) {
            LinearLayout linear = (LinearLayout) view;
            if (linear.getOrientation() == LinearLayout.VERTICAL && linear.getChildCount() >= 4) {
                return linear;
            }
        }
        if (view instanceof ViewGroup) {
            ViewGroup group = (ViewGroup) view;
            for (int index = 0; index < group.getChildCount(); index++) {
                ViewGroup found = findVerticalRoot(group.getChildAt(index));
                if (found != null) return found;
            }
        }
        return null;
    }

    private static GradientDrawable roundRect(Activity activity, int fill, int radius, int stroke) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(fill);
        drawable.setCornerRadius(dp(activity, radius));
        drawable.setStroke(dp(activity, 1), stroke);
        return drawable;
    }

    private static int dp(Activity activity, int value) {
        return Math.round(value * activity.getResources().getDisplayMetrics().density);
    }

    private static String typeLabel(Channel.Type type) {
        return type == Channel.Type.MOVIE ? "Filme"
                : type == Channel.Type.SERIES ? "Serien" : "Live-TV";
    }

    private static final class State {
        final AtomicInteger generation = new AtomicInteger();
        boolean installed;
    }

    private static final class Selection {
        final Channel.Type type;
        final MediaLanguage.Code language;

        Selection(Channel.Type type, MediaLanguage.Code language) {
            this.type = type;
            this.language = language;
        }
    }
}