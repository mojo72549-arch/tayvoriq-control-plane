package com.projectlumen.pilot.robust;

import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.ColorDrawable;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.text.Editable;
import android.text.TextUtils;
import android.text.TextWatcher;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

/** Fast language hub backed by precomputed DE/TR/EN/OTHER catalog buckets. */
public final class LanguageCatalogActivity extends Activity {
    private static final int BG = 0xFF050D18;
    private static final int CARD = 0xEE0B2030;
    private static final int STROKE = 0xFF2A5269;
    private static final int ACCENT = 0xFF62E7D3;
    private static final int ACCENT_BLUE = 0xFF57B7F2;
    private static final int TEXT_SECONDARY = 0xFF9DB6C8;
    private static final String PREFS = "lumen_language_hub_state";
    private static final int LANGUAGE_COUNT = MediaLanguage.Code.values().length;

    private final Handler main = new Handler(Looper.getMainLooper());
    private final ExecutorService worker = Executors.newSingleThreadExecutor(r -> {
        Thread thread = new Thread(r, "lumen-language-hub");
        thread.setDaemon(true);
        return thread;
    });
    private final AtomicInteger filterGeneration = new AtomicInteger();
    private final List<List<Channel>> buckets = new ArrayList<>();

    private DiagnosticLog log;
    private SharedPreferences preferences;
    private CatalogAdapter adapter;
    private Channel.Type type = Channel.Type.LIVE;
    private MediaLanguage.Code language = MediaLanguage.Code.ALL;
    private Button liveButton;
    private Button movieButton;
    private Button seriesButton;
    private final Button[] languageButtons = new Button[LANGUAGE_COUNT];
    private EditText search;
    private TextView count;
    private TextView status;
    private TextView empty;
    private ProgressBar progress;
    private volatile boolean ready;
    private volatile boolean destroyed;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(BG);
        getWindow().setNavigationBarColor(BG);
        log = DiagnosticLog.get(this);
        preferences = getSharedPreferences(PREFS, MODE_PRIVATE);
        restoreState();
        buildUi();
        loadAndIndex();
    }

    @Override protected void onDestroy() {
        destroyed = true;
        filterGeneration.incrementAndGet();
        main.removeCallbacksAndMessages(null);
        worker.shutdownNow();
        super.onDestroy();
    }

    private void restoreState() {
        try {
            type = Channel.Type.valueOf(preferences.getString("type", Channel.Type.LIVE.name()));
        } catch (Exception ignored) {
            type = Channel.Type.LIVE;
        }
        try {
            language = MediaLanguage.Code.valueOf(
                    preferences.getString("language", MediaLanguage.Code.ALL.name()));
        } catch (Exception ignored) {
            language = MediaLanguage.Code.ALL;
        }
    }

    private void saveState() {
        preferences.edit().putString("type", type.name())
                .putString("language", language.name()).apply();
    }

    private void buildUi() {
        FrameLayout stage = new FrameLayout(this);
        stage.setBackground(new LumenFlowDrawable());
        setContentView(stage);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(14), dp(12), dp(14), dp(10));
        stage.addView(root, new FrameLayout.LayoutParams(-1, -1));

        LinearLayout header = new LinearLayout(this);
        header.setGravity(Gravity.CENTER_VERTICAL);
        TextView logo = new TextView(this);
        logo.setBackgroundResource(R.drawable.ic_lumen_mark_tile);
        logo.setContentDescription("Project Lumen Logo");
        header.addView(logo, new LinearLayout.LayoutParams(dp(42), dp(42)));

        LinearLayout titles = new LinearLayout(this);
        titles.setOrientation(LinearLayout.VERTICAL);
        titles.setPadding(dp(10), 0, dp(6), 0);
        titles.addView(text("SPRACHEN & KATALOGE", 20, Color.WHITE, true));
        TextView subtitle = text("SOFORTINDEX FÜR DE · TR · EN · WEITERE", 9,
                TEXT_SECONDARY, true);
        subtitle.setLetterSpacing(0.05f);
        titles.addView(subtitle);
        header.addView(titles, new LinearLayout.LayoutParams(0, -2, 1f));

        Button back = button("Zurück", false);
        back.setOnClickListener(v -> finish());
        header.addView(back, new LinearLayout.LayoutParams(dp(86), dp(40)));
        root.addView(header);

        LinearLayout modes = new LinearLayout(this);
        modes.setOrientation(LinearLayout.HORIZONTAL);
        liveButton = modeButton("Live-TV", Channel.Type.LIVE);
        movieButton = modeButton("Filme", Channel.Type.MOVIE);
        seriesButton = modeButton("Serien", Channel.Type.SERIES);
        modes.addView(liveButton, weighted(0));
        modes.addView(movieButton, weighted(dp(6)));
        modes.addView(seriesButton, weighted(dp(6)));
        LinearLayout.LayoutParams modeParams = new LinearLayout.LayoutParams(-1, dp(42));
        modeParams.setMargins(0, dp(12), 0, dp(7));
        root.addView(modes, modeParams);

        HorizontalScrollView scroll = new HorizontalScrollView(this);
        scroll.setHorizontalScrollBarEnabled(false);
        LinearLayout languages = new LinearLayout(this);
        languages.setOrientation(LinearLayout.HORIZONTAL);
        MediaLanguage.Code[] codes = MediaLanguage.Code.values();
        for (MediaLanguage.Code code : codes) {
            Button chip = languageButton(languageLabel(code), code);
            languageButtons[code.ordinal()] = chip;
            LinearLayout.LayoutParams chipParams = new LinearLayout.LayoutParams(dp(104), dp(40));
            chipParams.setMargins(code == MediaLanguage.Code.ALL ? 0 : dp(6), 0, 0, 0);
            languages.addView(chip, chipParams);
        }
        scroll.addView(languages, new HorizontalScrollView.LayoutParams(-2, -1));
        root.addView(scroll, new LinearLayout.LayoutParams(-1, dp(40)));

        LinearLayout searchRow = new LinearLayout(this);
        searchRow.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout.LayoutParams searchParams = new LinearLayout.LayoutParams(-1, -2);
        searchParams.setMargins(0, dp(8), 0, 0);
        root.addView(searchRow, searchParams);

        search = new EditText(this);
        search.setSingleLine(true);
        search.setHint("Im ausgewählten Katalog suchen");
        search.setTextColor(Color.WHITE);
        search.setHintTextColor(0xFF7896AA);
        search.setTextSize(14);
        search.setPadding(dp(13), 0, dp(12), 0);
        search.setBackground(roundRect(CARD, 14, STROKE));
        search.addTextChangedListener(new TextWatcher() {
            @Override public void beforeTextChanged(CharSequence s, int start, int count, int after) { }
            @Override public void onTextChanged(CharSequence s, int start, int before, int count) {
                renderSelection();
            }
            @Override public void afterTextChanged(Editable editable) { }
        });
        searchRow.addView(search, new LinearLayout.LayoutParams(0, dp(46), 1f));

        count = text("0", 12, BG, true);
        count.setGravity(Gravity.CENTER);
        count.setMinWidth(dp(50));
        count.setBackground(roundRect(ACCENT, 18, ACCENT));
        LinearLayout.LayoutParams countParams = new LinearLayout.LayoutParams(-2, dp(40));
        countParams.setMargins(dp(8), 0, 0, 0);
        searchRow.addView(count, countParams);

        status = text("Schnellindex wird geöffnet …", 11, TEXT_SECONDARY, false);
        status.setSingleLine(true);
        status.setEllipsize(TextUtils.TruncateAt.END);
        LinearLayout.LayoutParams statusParams = new LinearLayout.LayoutParams(-1, -2);
        statusParams.setMargins(0, dp(7), 0, dp(4));
        root.addView(status, statusParams);

        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setIndeterminate(true);
        if (progress.getIndeterminateDrawable() != null) {
            progress.getIndeterminateDrawable().setTint(ACCENT);
        }
        root.addView(progress, new LinearLayout.LayoutParams(-1, dp(3)));

        FrameLayout host = new FrameLayout(this);
        LinearLayout.LayoutParams hostParams = new LinearLayout.LayoutParams(-1, 0, 1f);
        hostParams.setMargins(0, dp(8), 0, 0);
        root.addView(host, hostParams);

        ListView list = new ListView(this);
        list.setDivider(new ColorDrawable(Color.TRANSPARENT));
        list.setDividerHeight(dp(7));
        list.setFastScrollEnabled(true);
        list.setCacheColorHint(Color.TRANSPARENT);
        list.setSelector(roundRect(0x335EEAD4, 16, ACCENT));
        adapter = new CatalogAdapter(this);
        list.setAdapter(adapter);
        list.setOnItemClickListener((parent, view, position, id) -> open(adapter.item(position)));
        host.addView(list, new FrameLayout.LayoutParams(-1, -1));

        empty = text("Katalog wird geladen.", 15, TEXT_SECONDARY, false);
        empty.setGravity(Gravity.CENTER);
        empty.setPadding(dp(22), dp(22), dp(22), dp(22));
        host.addView(empty, new FrameLayout.LayoutParams(-1, -1));
        list.setEmptyView(empty);
        updateStyles();
    }

    private void loadAndIndex() {
        worker.execute(() -> {
            long started = SystemClock.elapsedRealtime();
            try {
                PlaylistRepository repository = new PlaylistRepository(this);
                List<Channel> safe = repository.restore((stage, detail) ->
                        log.event("-", "LANGUAGE-" + stage, detail));
                buildBuckets(safe);
                CatalogSession.publish(safe);
                long duration = SystemClock.elapsedRealtime() - started;
                log.event("-", "LANGUAGE-INDEX-READY", "safe=" + safe.size()
                        + " durationMs=" + duration + " buckets=" + buckets.size());
                main.post(() -> {
                    if (!alive()) return;
                    ready = true;
                    progress.setVisibility(View.GONE);
                    renderSelection();
                });
            } catch (Throwable failure) {
                log.exception("-", "LANGUAGE-INDEX-ERROR", failure);
                main.post(() -> {
                    if (!alive()) return;
                    progress.setVisibility(View.GONE);
                    status.setText("Sprachkatalog konnte nicht geöffnet werden");
                    empty.setText("Bibliothek konnte nicht geöffnet werden.\nBitte Systemdiagnose prüfen.");
                });
            }
        });
    }

    private void buildBuckets(List<Channel> safe) {
        buckets.clear();
        int total = Channel.Type.values().length * LANGUAGE_COUNT;
        for (int index = 0; index < total; index++) buckets.add(new ArrayList<>());
        for (Channel channel : safe) {
            if (channel == null || channel.adult) continue;
            mutableBucket(channel.type, MediaLanguage.Code.ALL).add(channel);
            MediaLanguage.Code code = MediaLanguage.detect(channel);
            if (code == MediaLanguage.Code.ALL) code = MediaLanguage.Code.OTHER;
            mutableBucket(channel.type, code).add(channel);
        }
        for (int index = 0; index < buckets.size(); index++) {
            buckets.set(index, Collections.unmodifiableList(buckets.get(index)));
        }
    }

    @SuppressWarnings("unchecked")
    private ArrayList<Channel> mutableBucket(Channel.Type wantedType, MediaLanguage.Code code) {
        return (ArrayList<Channel>) buckets.get(bucketIndex(wantedType, code));
    }

    private List<Channel> bucket(Channel.Type wantedType, MediaLanguage.Code code) {
        if (buckets.isEmpty()) return Collections.emptyList();
        return buckets.get(bucketIndex(wantedType, code));
    }

    private static int bucketIndex(Channel.Type wantedType, MediaLanguage.Code code) {
        return wantedType.ordinal() * LANGUAGE_COUNT + code.ordinal();
    }

    private Button modeButton(String label, Channel.Type target) {
        Button button = button(label, false);
        button.setOnClickListener(v -> {
            type = target;
            switchSelection();
        });
        return button;
    }

    private Button languageButton(String label, MediaLanguage.Code target) {
        Button button = button(label, false);
        button.setTextSize(10);
        button.setOnClickListener(v -> {
            language = target;
            switchSelection();
        });
        return button;
    }

    private void switchSelection() {
        saveState();
        updateStyles();
        if (search != null && search.length() > 0) search.setText("");
        else renderSelection();
    }

    private void renderSelection() {
        if (!ready || adapter == null || search == null) return;
        int generation = filterGeneration.incrementAndGet();
        Channel.Type wantedType = type;
        MediaLanguage.Code wantedLanguage = language;
        List<Channel> source = bucket(wantedType, wantedLanguage);
        String query = search.getText().toString().trim();
        long started = SystemClock.elapsedRealtime();

        if (query.isEmpty()) {
            adapter.submit(source);
            count.setText(String.valueOf(source.size()));
            status.setText(typeLabel(wantedType) + " · " + MediaLanguage.label(wantedLanguage)
                    + " · " + source.size() + " Treffer");
            empty.setText("Keine Inhalte in diesem Sprachbereich.");
            log.event("-", "LANGUAGE-SWITCH-READY", "type=" + wantedType
                    + " language=" + wantedLanguage + " rows=" + source.size()
                    + " durationMs=" + (SystemClock.elapsedRealtime() - started));
            return;
        }

        worker.execute(() -> {
            ArrayList<Channel> result = new ArrayList<>();
            for (Channel channel : source) {
                if (Thread.currentThread().isInterrupted()) return;
                if (containsIgnoreCase(channel.name, query)
                        || containsIgnoreCase(channel.group, query)) result.add(channel);
            }
            main.post(() -> {
                if (!alive() || generation != filterGeneration.get()
                        || wantedType != type || wantedLanguage != language) return;
                adapter.submit(Collections.unmodifiableList(result));
                count.setText(String.valueOf(result.size()));
                status.setText(typeLabel(wantedType) + " · " + MediaLanguage.label(wantedLanguage)
                        + " · " + result.size() + " Treffer");
                empty.setText("Keine Treffer in diesem Sprachbereich.");
            });
        });
    }

    private void updateStyles() {
        style(liveButton, type == Channel.Type.LIVE, ACCENT);
        style(movieButton, type == Channel.Type.MOVIE, ACCENT);
        style(seriesButton, type == Channel.Type.SERIES, ACCENT);
        for (MediaLanguage.Code code : MediaLanguage.Code.values()) {
            int selected = code == MediaLanguage.Code.DE ? 0xFFF4D35E
                    : code == MediaLanguage.Code.TR ? 0xFFE94D5F
                    : code == MediaLanguage.Code.EN ? ACCENT_BLUE
                    : code == MediaLanguage.Code.OTHER ? 0xFFB99AF7 : ACCENT;
            style(languageButtons[code.ordinal()], language == code, selected);
        }
    }

    private void style(Button button, boolean selected, int selectedColor) {
        if (button == null) return;
        button.setTextColor(selected ? BG : 0xFFDCE8EF);
        button.setBackground(roundRect(selected ? selectedColor : 0xFF17354A,
                12, selected ? selectedColor : STROKE));
    }

    private void open(Channel channel) {
        if (channel == null || channel.url.isBlank()) return;
        String interaction = log.newInteractionId();
        Intent player = new Intent(this, PlayerActivity.class);
        player.putExtra(PlayerActivity.EXTRA_URL, channel.url);
        player.putExtra(PlayerActivity.EXTRA_NAME, channel.name);
        player.putExtra(PlayerActivity.EXTRA_INTERACTION, interaction);
        log.event(interaction, "LANGUAGE-CONTENT-OPEN", "type=" + channel.type
                + " language=" + MediaLanguage.detect(channel));
        startActivity(player);
    }

    private boolean alive() {
        return !destroyed && !isFinishing() && !isDestroyed();
    }

    private static String languageLabel(MediaLanguage.Code code) {
        if (code == MediaLanguage.Code.DE) return "🇩🇪 Deutsch";
        if (code == MediaLanguage.Code.TR) return "🇹🇷 Türkçe";
        if (code == MediaLanguage.Code.EN) return "🇬🇧 English";
        if (code == MediaLanguage.Code.OTHER) return "🌍 Weitere";
        return "Alle";
    }

    private static String typeLabel(Channel.Type value) {
        if (value == Channel.Type.MOVIE) return "Filme";
        if (value == Channel.Type.SERIES) return "Serien";
        return "Live-TV";
    }

    private static boolean containsIgnoreCase(String value, String query) {
        if (value == null || query == null) return false;
        int limit = value.length() - query.length();
        for (int index = 0; index <= limit; index++) {
            if (value.regionMatches(true, index, query, 0, query.length())) return true;
        }
        return false;
    }

    private Button button(String label, boolean primary) {
        Button button = new Button(this);
        button.setText(label);
        button.setAllCaps(false);
        button.setSingleLine(true);
        button.setEllipsize(TextUtils.TruncateAt.END);
        button.setTextSize(11);
        button.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        button.setTextColor(primary ? BG : Color.WHITE);
        button.setMinWidth(0);
        button.setMinHeight(0);
        button.setPadding(dp(7), 0, dp(7), 0);
        button.setBackground(roundRect(primary ? ACCENT : 0xFF17354A,
                12, primary ? ACCENT : STROKE));
        return button;
    }

    private LinearLayout.LayoutParams weighted(int leftMargin) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, -1, 1f);
        params.setMargins(leftMargin, 0, 0, 0);
        return params;
    }

    private TextView text(String value, float size, int color, boolean bold) {
        TextView text = new TextView(this);
        text.setText(value);
        text.setTextSize(size);
        text.setTextColor(color);
        if (bold) text.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        return text;
    }

    private GradientDrawable roundRect(int color, int radius, int stroke) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(color);
        drawable.setCornerRadius(dp(radius));
        drawable.setStroke(dp(1), stroke);
        return drawable;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
