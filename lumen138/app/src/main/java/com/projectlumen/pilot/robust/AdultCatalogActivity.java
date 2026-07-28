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
import android.os.SystemClock;
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
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

/** Dedicated parent-only catalog. It never mutates or recreates MainActivity. */
public final class AdultCatalogActivity extends Activity {
    private static final int BG = 0xFF050D18;
    private static final int CARD = 0xEE0B2030;
    private static final int STROKE = 0xFF2A5269;
    private static final int ACCENT = 0xFFE94D5F;
    private static final int AGE_ACCENT = 0xFFF4A340;
    private static final int TEXT_SECONDARY = 0xFF9DB6C8;

    private enum Scope {
        MOVIES("Filme", Channel.Type.MOVIE),
        SERIES("Serien", Channel.Type.SERIES),
        LIVE("Live-TV", Channel.Type.LIVE);

        final String label;
        final Channel.Type type;

        Scope(String label, Channel.Type type) {
            this.label = label;
            this.type = type;
        }
    }

    private enum Protection {
        EXPLICIT("XXX / Erotik"),
        AGE_18("FSK 18"),
        ALL("Alle geschützt");

        final String label;

        Protection(String label) {
            this.label = label;
        }
    }

    private final Handler main = new Handler(Looper.getMainLooper());
    private final ExecutorService worker = Executors.newSingleThreadExecutor(r -> {
        Thread thread = new Thread(r, "lumen-adult-catalog");
        thread.setDaemon(true);
        return thread;
    });
    private final AtomicInteger filterGeneration = new AtomicInteger();

    private DiagnosticLog log;
    private CatalogAdapter adapter;
    private List<Channel> movies = Collections.emptyList();
    private List<Channel> series = Collections.emptyList();
    private List<Channel> live = Collections.emptyList();
    private Scope scope = Scope.MOVIES;
    private Protection protection = Protection.EXPLICIT;
    private EditText search;
    private TextView count;
    private TextView empty;
    private TextView status;
    private ProgressBar progress;
    private Button moviesButton;
    private Button seriesButton;
    private Button liveButton;
    private Button explicitButton;
    private Button ageButton;
    private Button allProtectedButton;
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
        loadProtectedCatalog();
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
        root.setPadding(dp(14), dp(10), dp(14), dp(9));
        stage.addView(root, new FrameLayout.LayoutParams(-1, -1));

        LinearLayout brandRow = new LinearLayout(this);
        brandRow.setGravity(Gravity.CENTER_VERTICAL);
        TextView logo = new TextView(this);
        logo.setBackgroundResource(R.drawable.ic_lumen_mark_tile);
        logo.setContentDescription("Project Lumen Logo");
        brandRow.addView(logo, new LinearLayout.LayoutParams(dp(44), dp(44)));

        LinearLayout titles = new LinearLayout(this);
        titles.setOrientation(LinearLayout.VERTICAL);
        titles.setPadding(dp(10), 0, 0, 0);
        TextView title = text("18+ BEREICH", 21, Color.WHITE, true);
        title.setSingleLine(true);
        title.setEllipsize(TextUtils.TruncateAt.END);
        titles.addView(title);
        TextView subtitle = text("GESCHÜTZTER ELTERNZUGANG", 9, TEXT_SECONDARY, true);
        subtitle.setSingleLine(true);
        subtitle.setEllipsize(TextUtils.TruncateAt.END);
        subtitle.setLetterSpacing(0.04f);
        titles.addView(subtitle);
        brandRow.addView(titles, new LinearLayout.LayoutParams(0, -2, 1f));
        root.addView(brandRow);

        LinearLayout actions = new LinearLayout(this);
        actions.setOrientation(LinearLayout.HORIZONTAL);
        LinearLayout.LayoutParams actionRowParams = new LinearLayout.LayoutParams(-1, dp(40));
        actionRowParams.setMargins(0, dp(7), 0, 0);
        root.addView(actions, actionRowParams);

        Button lock = button("Sperren", true);
        lock.setOnClickListener(v -> {
            ParentalControl.lock("adult-hub-manual");
            log.event("-", "PARENTAL-LOCK", "reason=adult-hub-manual");
            finish();
        });
        actions.addView(lock, weighted(0));

        Button back = button("Zurück", false);
        back.setOnClickListener(v -> finish());
        actions.addView(back, weighted(dp(7)));

        TextView notice = text("XXX/Erotik und FSK 18 sind getrennt. Mehrdeutige Filmtitel allein werden nicht geschützt.",
                11, 0xFFBDD0DC, false);
        notice.setPadding(dp(11), dp(8), dp(11), dp(8));
        notice.setBackground(roundRect(CARD, 14, STROKE));
        LinearLayout.LayoutParams noticeParams = new LinearLayout.LayoutParams(-1, -2);
        noticeParams.setMargins(0, dp(8), 0, dp(7));
        root.addView(notice, noticeParams);

        LinearLayout scopes = new LinearLayout(this);
        scopes.setOrientation(LinearLayout.HORIZONTAL);
        moviesButton = scopeButton("Filme", Scope.MOVIES);
        seriesButton = scopeButton("Serien", Scope.SERIES);
        liveButton = scopeButton("Live-TV", Scope.LIVE);
        scopes.addView(moviesButton, weighted(0));
        scopes.addView(seriesButton, weighted(dp(6)));
        scopes.addView(liveButton, weighted(dp(6)));
        root.addView(scopes, new LinearLayout.LayoutParams(-1, dp(40)));

        LinearLayout protectionRow = new LinearLayout(this);
        protectionRow.setOrientation(LinearLayout.HORIZONTAL);
        explicitButton = protectionButton("XXX / Erotik", Protection.EXPLICIT);
        ageButton = protectionButton("FSK 18", Protection.AGE_18);
        allProtectedButton = protectionButton("Alle", Protection.ALL);
        protectionRow.addView(explicitButton, weighted(0));
        protectionRow.addView(ageButton, weighted(dp(6)));
        protectionRow.addView(allProtectedButton, weighted(dp(6)));
        LinearLayout.LayoutParams protectionParams = new LinearLayout.LayoutParams(-1, dp(40));
        protectionParams.setMargins(0, dp(6), 0, 0);
        root.addView(protectionRow, protectionParams);

        LinearLayout searchRow = new LinearLayout(this);
        searchRow.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout.LayoutParams searchRowParams = new LinearLayout.LayoutParams(-1, -2);
        searchRowParams.setMargins(0, dp(7), 0, 0);
        root.addView(searchRow, searchRowParams);

        search = new EditText(this);
        search.setSingleLine(true);
        search.setHint("Geschützt suchen");
        search.setTextColor(Color.WHITE);
        search.setHintTextColor(0xFF7896AA);
        search.setTextSize(14);
        search.setPadding(dp(13), 0, dp(12), 0);
        search.setBackground(roundRect(CARD, 14, STROKE));
        search.addTextChangedListener(new TextWatcher() {
            @Override public void beforeTextChanged(CharSequence s, int start, int count, int after) { }
            @Override public void onTextChanged(CharSequence s, int start, int before, int count) {
                filterAsync();
            }
            @Override public void afterTextChanged(Editable editable) { }
        });
        searchRow.addView(search, new LinearLayout.LayoutParams(0, dp(44), 1f));

        count = text("0", 12, Color.WHITE, true);
        count.setGravity(Gravity.CENTER);
        count.setMinWidth(dp(48));
        count.setBackground(roundRect(ACCENT, 18, ACCENT));
        LinearLayout.LayoutParams countParams = new LinearLayout.LayoutParams(-2, dp(38));
        countParams.setMargins(dp(8), 0, 0, 0);
        searchRow.addView(count, countParams);

        status = text("Geschützter Katalog wird geprüft …", 11, TEXT_SECONDARY, false);
        status.setSingleLine(true);
        status.setEllipsize(TextUtils.TruncateAt.END);
        LinearLayout.LayoutParams statusParams = new LinearLayout.LayoutParams(-1, -2);
        statusParams.setMargins(0, dp(6), 0, dp(3));
        root.addView(status, statusParams);

        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setIndeterminate(true);
        if (progress.getIndeterminateDrawable() != null) {
            progress.getIndeterminateDrawable().setTint(ACCENT);
        }
        root.addView(progress, new LinearLayout.LayoutParams(-1, dp(3)));

        FrameLayout host = new FrameLayout(this);
        LinearLayout.LayoutParams hostParams = new LinearLayout.LayoutParams(-1, 0, 1f);
        hostParams.setMargins(0, dp(7), 0, 0);
        root.addView(host, hostParams);

        ListView list = new ListView(this);
        list.setDivider(new ColorDrawable(Color.TRANSPARENT));
        list.setDividerHeight(dp(7));
        list.setFastScrollEnabled(true);
        list.setCacheColorHint(Color.TRANSPARENT);
        list.setSelector(roundRect(0x33E94D5F, 16, ACCENT));
        adapter = new CatalogAdapter(this, true);
        list.setAdapter(adapter);
        list.setOnItemClickListener((parent, view, position, id) -> openContent(adapter.item(position)));
        host.addView(list, new FrameLayout.LayoutParams(-1, -1));

        empty = text("Noch keine geschützten Inhalte geladen.", 15, TEXT_SECONDARY, false);
        empty.setGravity(Gravity.CENTER);
        empty.setPadding(dp(22), dp(22), dp(22), dp(22));
        host.addView(empty, new FrameLayout.LayoutParams(-1, -1));
        list.setEmptyView(empty);
        updateStyles();
    }

    private void loadProtectedCatalog() {
        worker.execute(() -> {
            long started = SystemClock.elapsedRealtime();
            try {
                List<Channel> raw = CatalogSession.raw();
                boolean memoryHit = !raw.isEmpty();
                if (!memoryHit) {
                    PlaylistRepository repository = new PlaylistRepository(this);
                    List<Channel> restored = repository.restore((stage, detail) ->
                            log.event("-", "ADULT-" + stage, detail));
                    CatalogSession.publish(restored);
                }
                List<Channel> foundMovies = CatalogSession.adultMovies();
                List<Channel> foundSeries = CatalogSession.adultSeries();
                List<Channel> foundLive = CatalogSession.adultLive();
                long duration = SystemClock.elapsedRealtime() - started;
                log.event("-", "ADULT-CATALOG-READY", "movies=" + foundMovies.size()
                        + " series=" + foundSeries.size() + " live=" + foundLive.size()
                        + " memoryHit=" + memoryHit + " durationMs=" + duration);
                main.post(() -> {
                    if (!alive()) return;
                    movies = foundMovies;
                    series = foundSeries;
                    live = foundLive;
                    progress.setVisibility(View.GONE);
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

    private Button scopeButton(String label, Scope target) {
        Button button = button(label, false);
        button.setOnClickListener(v -> {
            scope = target;
            search.setText("");
            updateStyles();
            filterAsync();
        });
        return button;
    }

    private Button protectionButton(String label, Protection target) {
        Button button = button(label, false);
        button.setTextSize(10);
        button.setOnClickListener(v -> {
            protection = target;
            search.setText("");
            updateStyles();
            filterAsync();
        });
        return button;
    }

    private void updateStyles() {
        styleButton(moviesButton, scope == Scope.MOVIES, ACCENT);
        styleButton(seriesButton, scope == Scope.SERIES, ACCENT);
        styleButton(liveButton, scope == Scope.LIVE, ACCENT);
        styleButton(explicitButton, protection == Protection.EXPLICIT, ACCENT);
        styleButton(ageButton, protection == Protection.AGE_18, AGE_ACCENT);
        styleButton(allProtectedButton, protection == Protection.ALL, 0xFF6B7FE8);
        if (count != null) {
            int chip = protection == Protection.AGE_18 ? AGE_ACCENT : ACCENT;
            count.setBackground(roundRect(chip, 18, chip));
        }
    }

    private void styleButton(Button button, boolean selected, int selectedColor) {
        if (button == null) return;
        button.setTextColor(Color.WHITE);
        button.setBackground(roundRect(selected ? selectedColor : 0xFF17354A,
                12, selected ? selectedColor : STROKE));
    }

    private List<Channel> selectedSource() {
        if (scope == Scope.SERIES) return series;
        if (scope == Scope.LIVE) return live;
        return movies;
    }

    private boolean matchesProtection(Channel channel, Protection wanted) {
        if (wanted == Protection.ALL) return channel.adult;
        if (wanted == Protection.AGE_18) {
            return AdultContentPolicy.isAge18Class(channel.adultClass);
        }
        return AdultContentPolicy.isExplicitClass(channel.adultClass);
    }

    private void filterAsync() {
        if (search == null || adapter == null) return;
        int generation = filterGeneration.incrementAndGet();
        String query = search.getText().toString().trim();
        Scope wantedScope = scope;
        Protection wantedProtection = protection;
        List<Channel> source = selectedSource();
        worker.execute(() -> {
            ArrayList<Channel> result = new ArrayList<>();
            for (Channel channel : source) {
                if (Thread.currentThread().isInterrupted()) return;
                if (!matchesProtection(channel, wantedProtection)) continue;
                if (query.isEmpty() || containsIgnoreCase(channel.name, query)
                        || containsIgnoreCase(channel.group, query)) {
                    result.add(channel);
                }
            }
            List<Channel> immutable = Collections.unmodifiableList(result);
            main.post(() -> {
                if (!alive() || generation != filterGeneration.get()
                        || wantedScope != scope || wantedProtection != protection) return;
                adapter.submit(immutable);
                count.setText(String.valueOf(immutable.size()));
                status.setText(immutable.size() + " " + wantedProtection.label + " · "
                        + wantedScope.label + " · Elternzugang aktiv");
                empty.setText(emptyMessage(wantedScope, wantedProtection));
                log.event("-", "ADULT-SCOPE-READY", "type=" + wantedScope.type
                        + " protection=" + wantedProtection + " rows=" + immutable.size());
            });
        });
    }

    private static String emptyMessage(Scope scope, Protection protection) {
        if (protection == Protection.EXPLICIT) {
            return "Keine eindeutig als XXX oder Erotik gekennzeichneten " + scope.label
                    + " gefunden.\nNormale Filme werden nicht ersatzweise angezeigt.";
        }
        if (protection == Protection.AGE_18) {
            return "Keine eindeutig mit FSK 18 oder 18+ gekennzeichneten " + scope.label
                    + " gefunden.\nXXX/Erotik bleibt davon getrennt.";
        }
        return "Keine eindeutig geschützten " + scope.label
                + " gefunden.\nDer Familienkatalog wird niemals ersatzweise angezeigt.";
    }

    private void openContent(Channel channel) {
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
        log.event(interaction, "PARENTAL-ADULT-PLAY", "authorized=true type="
                + channel.type + " class=" + AdultContentPolicy.classLabel(channel.adultClass));
        startActivity(player);
    }

    private boolean alive() {
        return !destroyed && !isFinishing() && !isDestroyed();
    }

    private static boolean containsIgnoreCase(String value, String query) {
        if (value == null || query == null) return false;
        int limit = value.length() - query.length();
        for (int index = 0; index <= limit; index++) {
            if (value.regionMatches(true, index, query, 0, query.length())) return true;
        }
        return false;
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
