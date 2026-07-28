package com.projectlumen.pilot.robust;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.ColorDrawable;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.Editable;
import android.text.TextUtils;
import android.text.TextWatcher;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

/** Dedicated parent-only movie catalog. It never mutates or recreates MainActivity. */
public final class AdultCatalogActivity extends Activity {
    private static final int BG = 0xFF050D18;
    private static final int CARD = 0xEE0B2030;
    private static final int STROKE = 0xFF2A5269;
    private static final int ACCENT = 0xFFE94D5F;
    private static final int TEXT_SECONDARY = 0xFF9DB6C8;

    private final Handler main = new Handler(Looper.getMainLooper());
    private final ExecutorService worker = Executors.newSingleThreadExecutor(r -> {
        Thread thread = new Thread(r, "lumen-adult-catalog");
        thread.setDaemon(true);
        return thread;
    });
    private final AtomicInteger filterGeneration = new AtomicInteger();

    private DiagnosticLog log;
    private CatalogAdapter adapter;
    private List<Channel> adultMovies = Collections.emptyList();
    private EditText search;
    private TextView count;
    private TextView empty;
    private TextView status;
    private ProgressBar progress;
    private volatile boolean destroyed;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(BG);
        getWindow().setNavigationBarColor(BG);
        log = DiagnosticLog.get(this);
        if (!ParentalControl.isUnlocked()) {
            Toast.makeText(this, "Elternzugang ist gesperrt.", Toast.LENGTH_LONG).show();
            finish();
            return;
        }
        buildUi();
        loadAdultCatalog();
    }

    @Override protected void onResume() {
        super.onResume();
        if (!ParentalControl.isUnlocked()) {
            Toast.makeText(this, "Der Elternzugang wurde wieder gesperrt.", Toast.LENGTH_LONG).show();
            finish();
        }
    }

    @Override protected void onDestroy() {
        destroyed = true;
        filterGeneration.incrementAndGet();
        main.removeCallbacksAndMessages(null);
        worker.shutdownNow();
        super.onDestroy();
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
        titles.addView(text("18+ FILME", 20, Color.WHITE, true));
        TextView subtitle = text("GESCHÜTZTER ELTERNBEREICH", 9, TEXT_SECONDARY, true);
        subtitle.setLetterSpacing(0.06f);
        titles.addView(subtitle);
        header.addView(titles, new LinearLayout.LayoutParams(0, -2, 1f));

        Button lock = button("Sperren", true);
        lock.setOnClickListener(v -> {
            ParentalControl.lock("adult-hub-manual");
            log.event("-", "PARENTAL-LOCK", "reason=adult-hub-manual");
            finish();
        });
        header.addView(lock, new LinearLayout.LayoutParams(dp(88), dp(39)));

        Button back = button("Zurück", false);
        back.setOnClickListener(v -> finish());
        LinearLayout.LayoutParams backParams = new LinearLayout.LayoutParams(dp(82), dp(39));
        backParams.setMargins(dp(7), 0, 0, 0);
        header.addView(back, backParams);
        root.addView(header);

        TextView notice = text("Nur eindeutig erkannte Erwachsenenfilme werden hier angezeigt. "
                + "Der normale Filmkatalog bleibt vollständig getrennt.",
                12, 0xFFBDD0DC, false);
        notice.setPadding(dp(12), dp(10), dp(12), dp(10));
        notice.setBackground(roundRect(CARD, 14, STROKE));
        LinearLayout.LayoutParams noticeParams = new LinearLayout.LayoutParams(-1, -2);
        noticeParams.setMargins(0, dp(11), 0, dp(8));
        root.addView(notice, noticeParams);

        LinearLayout searchRow = new LinearLayout(this);
        searchRow.setGravity(Gravity.CENTER_VERTICAL);
        search = new EditText(this);
        search.setSingleLine(true);
        search.setHint("Im geschützten Bereich suchen");
        search.setTextColor(Color.WHITE);
        search.setHintTextColor(0xFF7896AA);
        search.setTextSize(14);
        search.setPadding(dp(13), 0, dp(12), 0);
        search.setBackground(roundRect(CARD, 14, STROKE));
        search.addTextChangedListener(new TextWatcher() {
            @Override public void beforeTextChanged(CharSequence s, int start, int count, int after) { }
            @Override public void onTextChanged(CharSequence s, int start, int before, int count) { filterAsync(); }
            @Override public void afterTextChanged(Editable editable) { }
        });
        searchRow.addView(search, new LinearLayout.LayoutParams(0, dp(46), 1f));

        count = text("0", 12, Color.WHITE, true);
        count.setGravity(Gravity.CENTER);
        count.setMinWidth(dp(48));
        count.setBackground(roundRect(ACCENT, 18, ACCENT));
        LinearLayout.LayoutParams countParams = new LinearLayout.LayoutParams(-2, dp(40));
        countParams.setMargins(dp(8), 0, 0, 0);
        searchRow.addView(count, countParams);
        root.addView(searchRow);

        status = text("Geschützter Katalog wird vorbereitet …", 11, TEXT_SECONDARY, false);
        status.setSingleLine(true);
        status.setEllipsize(TextUtils.TruncateAt.END);
        LinearLayout.LayoutParams statusParams = new LinearLayout.LayoutParams(-1, -2);
        statusParams.setMargins(0, dp(7), 0, dp(4));
        root.addView(status, statusParams);

        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setIndeterminate(true);
        if (progress.getIndeterminateDrawable() != null) progress.getIndeterminateDrawable().setTint(ACCENT);
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
        list.setSelector(roundRect(0x33E94D5F, 16, ACCENT));
        adapter = new CatalogAdapter(this);
        list.setAdapter(adapter);
        list.setOnItemClickListener((parent, view, position, id) -> openMovie(adapter.item(position)));
        host.addView(list, new FrameLayout.LayoutParams(-1, -1));

        empty = text("Noch keine 18+-Filme geladen.", 15, TEXT_SECONDARY, false);
        empty.setGravity(Gravity.CENTER);
        empty.setPadding(dp(22), dp(22), dp(22), dp(22));
        host.addView(empty, new FrameLayout.LayoutParams(-1, -1));
        list.setEmptyView(empty);
    }

    private void loadAdultCatalog() {
        worker.execute(() -> {
            long started = android.os.SystemClock.elapsedRealtime();
            try {
                List<Channel> raw = CatalogSession.raw();
                boolean memoryHit = !raw.isEmpty();
                if (!memoryHit) {
                    PlaylistRepository repository = new PlaylistRepository(this);
                    List<Channel> restored = repository.restore((stage, detail) ->
                            log.event("-", "ADULT-" + stage, detail));
                    CatalogSession.publish(restored);
                    raw = CatalogSession.raw();
                }
                List<Channel> found = AdultContentPolicy.adultMovies(raw);
                long duration = android.os.SystemClock.elapsedRealtime() - started;
                log.event("-", "ADULT-CATALOG-READY", "rows=" + found.size()
                        + " raw=" + raw.size() + " memoryHit=" + memoryHit
                        + " durationMs=" + duration);
                main.post(() -> {
                    if (!alive()) return;
                    adultMovies = found;
                    progress.setVisibility(View.GONE);
                    status.setText(found.isEmpty()
                            ? "Keine eindeutig markierte 18+-Filmkategorie gefunden"
                            : found.size() + " geschützte Filme · Elternzugang aktiv");
                    empty.setText(found.isEmpty()
                            ? "Keine eindeutig markierte 18+-Filmkategorie erkannt.\n"
                            + "Der normale Filmkatalog wird aus Sicherheitsgründen nicht angezeigt."
                            : "Keine Treffer im geschützten Bereich.");
                    filterAsync();
                });
            } catch (Throwable failure) {
                log.exception("-", "ADULT-CATALOG-ERROR", failure);
                main.post(() -> {
                    if (!alive()) return;
                    progress.setVisibility(View.GONE);
                    status.setText("Geschützter Katalog konnte nicht geöffnet werden");
                    empty.setText("Der 18+-Bereich wurde sicher geschlossen.\nBitte Systemdiagnose öffnen.");
                    adapter.submit(Collections.emptyList());
                    count.setText("0");
                });
            }
        });
    }

    private void filterAsync() {
        if (search == null || adapter == null) return;
        int generation = filterGeneration.incrementAndGet();
        String query = search.getText().toString().trim().toLowerCase(Locale.ROOT);
        List<Channel> source = adultMovies;
        worker.execute(() -> {
            ArrayList<Channel> result = new ArrayList<>();
            for (Channel channel : source) {
                if (Thread.currentThread().isInterrupted()) return;
                if (query.isEmpty() || contains(channel.name, query) || contains(channel.group, query)) {
                    result.add(channel);
                }
            }
            main.post(() -> {
                if (!alive() || generation != filterGeneration.get()) return;
                adapter.submit(result);
                count.setText(String.valueOf(result.size()));
            });
        });
    }

    private void openMovie(Channel channel) {
        if (channel == null) return;
        if (!ParentalControl.isUnlocked()) {
            Toast.makeText(this, "Elternzugang ist gesperrt.", Toast.LENGTH_LONG).show();
            finish();
            return;
        }
        String interaction = log.newInteractionId();
        Intent player = new Intent(this, PlayerActivity.class);
        player.putExtra(PlayerActivity.EXTRA_URL, channel.url);
        player.putExtra(PlayerActivity.EXTRA_NAME, channel.name);
        player.putExtra(PlayerActivity.EXTRA_INTERACTION, interaction);
        player.putExtra(LumenApplication.EXTRA_ADULT_CONTENT, true);
        log.event(interaction, "PARENTAL-ADULT-PLAY", "authorized=true type=MOVIE");
        startActivity(player);
    }

    private boolean alive() {
        return !destroyed && !isFinishing() && !isDestroyed();
    }

    private static boolean contains(String value, String query) {
        return value != null && value.toLowerCase(Locale.ROOT).contains(query);
    }

    private Button button(String label, boolean danger) {
        Button button = new Button(this);
        button.setText(label);
        button.setAllCaps(false);
        button.setSingleLine(true);
        button.setTextSize(11);
        button.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        button.setTextColor(Color.WHITE);
        button.setMinHeight(0);
        button.setMinWidth(0);
        button.setPadding(dp(8), 0, dp(8), 0);
        button.setBackground(roundRect(danger ? ACCENT : 0xFF17354A,
                12, danger ? ACCENT : STROKE));
        return button;
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
