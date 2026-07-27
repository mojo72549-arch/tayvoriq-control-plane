package com.projectlumen.pilot.robust;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.res.Configuration;
import android.graphics.Color;
import android.graphics.drawable.ColorDrawable;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.text.Editable;
import android.text.InputType;
import android.text.TextWatcher;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.Window;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.TextView;
import android.widget.Toast;

import java.net.URI;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

public final class MainActivity extends Activity {
    private static final int REQUEST_LOCAL = 8101;

    private enum Mode { LIVE, MOVIES, SERIES }

    private final Handler main = new Handler(Looper.getMainLooper());
    private final ExecutorService worker = Executors.newSingleThreadExecutor(r -> {
        Thread thread = new Thread(r, "lumen-catalog-worker");
        thread.setDaemon(true);
        return thread;
    });
    private final AtomicInteger filterGeneration = new AtomicInteger();

    private DiagnosticLog log;
    private UiStallWatchdog watchdog;
    private PlaylistRepository repository;
    private List<Channel> all = Collections.emptyList();
    private CatalogAdapter adapter;
    private Mode mode = Mode.LIVE;
    private boolean busy = true;
    private long lastInputEvent;

    private TextView status;
    private TextView empty;
    private TextView count;
    private EditText search;
    private ListView list;
    private Button sourceButton;
    private Button liveButton;
    private Button movieButton;
    private Button seriesButton;
    private Runnable pendingFilter;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        requestWindowFeature(Window.FEATURE_NO_TITLE);
        getWindow().setStatusBarColor(0xFF07111E);
        getWindow().setNavigationBarColor(0xFF07111E);
        log = DiagnosticLog.get(this);
        watchdog = new UiStallWatchdog(log);
        repository = new PlaylistRepository(this);
        log.event("-", "APP-CREATE-START", "thread=" + Thread.currentThread().getName());
        buildUi();
        log.event("-", "APP-CREATE-END", "uiReady=true");
        restore();
    }

    private void buildUi() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(tv() ? 24 : 12), dp(tv() ? 18 : 10),
                dp(tv() ? 24 : 12), dp(10));
        root.setBackground(new GradientDrawable(GradientDrawable.Orientation.TL_BR,
                new int[]{0xFF06101D, 0xFF092233, 0xFF10243A}));
        setContentView(root);

        LinearLayout header = new LinearLayout(this);
        header.setOrientation(LinearLayout.HORIZONTAL);
        header.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout brand = new LinearLayout(this);
        brand.setOrientation(LinearLayout.VERTICAL);
        brand.addView(text("LUMEN FLOW", tv() ? 31 : 24, Color.WHITE, true));
        brand.addView(text("Robust Import & Playback · " + BuildConfig.VERSION_NAME,
                tv() ? 14 : 11, 0xFFA7BED0, false));
        header.addView(brand, new LinearLayout.LayoutParams(0,
                LinearLayout.LayoutParams.WRAP_CONTENT, 1f));

        Button diagnostics = button("Diagnose", false);
        diagnostics.setOnClickListener(v -> startActivity(new Intent(this, DiagnosticsActivity.class)));
        header.addView(diagnostics, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, dp(tv() ? 54 : 46)));

        sourceButton = button("Quelle +", true);
        sourceButton.setEnabled(false);
        sourceButton.setOnClickListener(v -> showSourceMenu());
        LinearLayout.LayoutParams sourceParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, dp(tv() ? 54 : 46));
        sourceParams.setMargins(dp(8), 0, 0, 0);
        header.addView(sourceButton, sourceParams);
        root.addView(header);

        LinearLayout modes = new LinearLayout(this);
        modes.setOrientation(LinearLayout.HORIZONTAL);
        modes.setPadding(0, dp(10), 0, dp(8));
        liveButton = modeButton("Live-TV", Mode.LIVE);
        movieButton = modeButton("Filme", Mode.MOVIES);
        seriesButton = modeButton("Serien", Mode.SERIES);
        modes.addView(liveButton, weighted(0));
        modes.addView(movieButton, weighted(dp(7)));
        modes.addView(seriesButton, weighted(dp(7)));
        root.addView(modes);

        LinearLayout searchBar = new LinearLayout(this);
        searchBar.setOrientation(LinearLayout.HORIZONTAL);
        search = new EditText(this);
        search.setSingleLine(true);
        search.setHint("Sender, Film, Serie oder Gruppe suchen");
        search.setTextColor(Color.WHITE);
        search.setHintTextColor(0xFF8DA5B8);
        search.setTextSize(tv() ? 18 : 15);
        search.setPadding(dp(14), dp(10), dp(14), dp(10));
        search.setBackground(roundRect(0xFF102337, 15, 0xFF294A61));
        search.addTextChangedListener(new TextWatcher() {
            @Override public void beforeTextChanged(CharSequence s, int start, int count, int after) { }
            @Override public void onTextChanged(CharSequence s, int start, int before, int count) {
                scheduleFilter();
            }
            @Override public void afterTextChanged(Editable editable) { }
        });
        searchBar.addView(search, new LinearLayout.LayoutParams(0, dp(tv() ? 58 : 50), 1f));

        count = text("0", tv() ? 15 : 12, 0xFF07111E, true);
        count.setGravity(Gravity.CENTER);
        count.setPadding(dp(12), 0, dp(12), 0);
        count.setBackground(roundRect(0xFF5EEAD4, 20, 0xFF5EEAD4));
        LinearLayout.LayoutParams countParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, dp(tv() ? 48 : 42));
        countParams.setMargins(dp(8), 0, 0, 0);
        searchBar.addView(count, countParams);
        root.addView(searchBar);

        FrameLayout host = new FrameLayout(this);
        LinearLayout.LayoutParams hostParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f);
        hostParams.setMargins(0, dp(8), 0, dp(8));
        root.addView(host, hostParams);

        list = new ListView(this);
        list.setDivider(new ColorDrawable(Color.TRANSPARENT));
        list.setDividerHeight(dp(7));
        list.setFastScrollEnabled(true);
        list.setCacheColorHint(Color.TRANSPARENT);
        list.setSelector(roundRect(0x335EEAD4, 16, 0xFF5EEAD4));
        list.setOnItemClickListener((parent, view, position, id) -> select(position));
        host.addView(list, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT));

        empty = text("Bibliothek wird im Hintergrund vorbereitet …",
                tv() ? 19 : 15, 0xFFB6C9D8, false);
        empty.setGravity(Gravity.CENTER);
        empty.setPadding(dp(24), dp(24), dp(24), dp(24));
        host.addView(empty, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT));
        list.setEmptyView(empty);

        adapter = new CatalogAdapter(this);
        list.setAdapter(adapter);
        status = text("Lokale Wiederherstellung wird gestartet …",
                tv() ? 14 : 12, 0xFFA7BED0, false);
        status.setMaxLines(3);
        root.addView(status);
        updateModeStyles();
    }

    private void restore() {
        boolean candidate = repository.hasRecoverableCandidate();
        setBusy(true, candidate
                ? "Unterbrochener Import gefunden. Prüfung wird automatisch fortgesetzt …"
                : "Gespeicherte Bibliothek wird im Hintergrund wiederhergestellt …");
        log.event("-", "RESTORE-QUEUED", "thread=background candidate=" + candidate);
        worker.execute(() -> {
            long started = SystemClock.elapsedRealtime();
            try {
                List<Channel> restored = repository.restore(
                        (stage, detail) -> reportProgress("-", stage, detail));
                main.post(() -> {
                    all = restored;
                    setBusy(false, repository.sourceName() + " · " + all.size() + " Einträge bereit");
                    empty.setText(all.isEmpty()
                            ? "Noch keine Quelle eingerichtet\n\nQuelle hinzufügen: Server + Login, Playlist-Link oder lokale M3U/M3U8-Datei."
                            : "Keine Treffer im aktuellen Bereich.");
                    filterNow();
                    log.event("-", "RESTORE-PARSE-END",
                            "entries=" + all.size() + " durationMs="
                                    + (SystemClock.elapsedRealtime() - started));
                });
            } catch (Throwable failure) {
                log.exception("-", "RESTORE-ERROR", failure);
                main.post(() -> {
                    boolean recoverable = repository.hasRecoverableCandidate();
                    setBusy(false, recoverable
                            ? "Importprüfung konnte nicht abgeschlossen werden. Kandidat bleibt gespeichert."
                            : "Wiederherstellung fehlgeschlagen. Du kannst eine Quelle neu hinzufügen.");
                    empty.setText(recoverable
                            ? "Import ist noch nicht aktiviert\n\nDiagnose öffnen. Die verschlüsselte Kandidatendatei bleibt erhalten."
                            : "Wiederherstellung fehlgeschlagen\n\nDiagnose öffnen oder Quelle neu hinzufügen.");
                });
            }
        });
    }

    private void showSourceMenu() {
        if (busy) return;
        new AlertDialog.Builder(this)
                .setTitle("Quelle hinzufügen")
                .setItems(new String[]{"Server + Login", "Playlist-Link", "Lokale M3U/M3U8-Datei"},
                        (dialog, which) -> {
                            if (which == 0) promptServer();
                            else if (which == 1) promptLink();
                            else openLocal();
                        })
                .setNegativeButton("Abbrechen", null)
                .show();
    }

    private void promptLink() {
        EditText name = input("Name der Quelle", false);
        name.setText("Meine Playlist");
        EditText url = input("Vollständiger M3U/M3U8-Link", false);
        url.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        new AlertDialog.Builder(this)
                .setTitle("Playlist-Link")
                .setMessage("Download, Verschlüsselung und Prüfung laufen im Hintergrund. Die bisherige Bibliothek bleibt bis zum vollständigen Erfolg aktiv.")
                .setView(form(name, url))
                .setPositiveButton("Laden", (dialog, which) -> {
                    try {
                        importUrl(name.getText().toString(),
                                requireHttpUrl(url.getText().toString()), "PLAYLIST-LINK");
                    } catch (Throwable failure) {
                        validation(failure);
                    }
                })
                .setNegativeButton("Abbrechen", null)
                .show();
    }

    private void promptServer() {
        EditText name = input("Name der Quelle", false);
        name.setText("Mein Server");
        EditText server = input("Serveradresse, z. B. http://server:8080", false);
        EditText user = input("Benutzername", false);
        EditText pass = input("Passwort", true);
        new AlertDialog.Builder(this)
                .setTitle("Server + Login")
                .setMessage("Lumen erstellt die Playlist-Adresse lokal. Zugangsdaten werden nicht in der Diagnose angezeigt.")
                .setView(form(name, server, user, pass))
                .setPositiveButton("Verbinden", (dialog, which) -> {
                    try {
                        String base = requireHttpUrl(server.getText().toString());
                        while (base.endsWith("/")) base = base.substring(0, base.length() - 1);
                        String username = user.getText().toString().trim();
                        String password = pass.getText().toString();
                        if (username.isBlank() || password.isBlank()) {
                            throw new IllegalArgumentException("Benutzername oder Passwort fehlt.");
                        }
                        String url = base + "/get.php?username="
                                + URLEncoder.encode(username, StandardCharsets.UTF_8.name())
                                + "&password=" + URLEncoder.encode(password, StandardCharsets.UTF_8.name())
                                + "&type=m3u_plus&output=mpegts";
                        importUrl(name.getText().toString(), url, "SERVER-LOGIN");
                    } catch (Throwable failure) {
                        validation(failure);
                    }
                })
                .setNegativeButton("Abbrechen", null)
                .show();
    }

    private void openLocal() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("*/*");
        intent.putExtra(Intent.EXTRA_MIME_TYPES, new String[]{
                "audio/x-mpegurl", "application/x-mpegurl",
                "application/vnd.apple.mpegurl", "text/plain", "application/octet-stream"});
        startActivityForResult(intent, REQUEST_LOCAL);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != REQUEST_LOCAL || resultCode != RESULT_OK
                || data == null || data.getData() == null) return;
        Uri uri = data.getData();
        try {
            getContentResolver().takePersistableUriPermission(
                    uri, Intent.FLAG_GRANT_READ_URI_PERMISSION);
        } catch (Throwable ignored) { }
        importLocal(uri);
    }

    private void importUrl(String name, String url, String origin) {
        String interaction = log.newInteractionId();
        setBusy(true, "Quelle wird heruntergeladen, verschlüsselt und geprüft …");
        log.event(interaction, "IMPORT-START", "origin=" + origin + " urlPresent=true");
        worker.execute(() -> {
            try {
                List<Channel> result = repository.importUrl(name, url,
                        (stage, detail) -> reportProgress(interaction, stage, detail));
                main.post(() -> finishImport(interaction, result));
            } catch (Throwable failure) {
                log.exception(interaction, "IMPORT-ERROR", failure);
                main.post(() -> importFailure(failure));
            }
        });
    }

    private void importLocal(Uri uri) {
        String interaction = log.newInteractionId();
        setBusy(true, "Lokale Datei wird verschlüsselt und geprüft …");
        log.event(interaction, "LOCAL-IMPORT-START", "uriPresent=true");
        worker.execute(() -> {
            try {
                List<Channel> result = repository.importUri("Lokale Playlist",
                        getContentResolver(), uri,
                        (stage, detail) -> reportProgress(interaction, stage, detail));
                main.post(() -> finishImport(interaction, result));
            } catch (Throwable failure) {
                log.exception(interaction, "LOCAL-IMPORT-ERROR", failure);
                main.post(() -> importFailure(failure));
            }
        });
    }

    private void reportProgress(String interaction, String stage, String detail) {
        log.event(interaction, stage, detail);
        if (!isVisibleProgressStage(stage)) return;
        main.post(() -> {
            if (!isFinishing() && status != null && busy) {
                status.setText(progressLabel(stage, detail));
            }
        });
    }

    private static boolean isVisibleProgressStage(String stage) {
        return stage.contains("DOWNLOAD") || stage.contains("PARSE")
                || stage.contains("CANDIDATE") || stage.contains("ROLLBACK")
                || stage.equals("IMPORT-PAUSED");
    }

    private static String progressLabel(String stage, String detail) {
        if (stage.contains("CANDIDATE")) return "Unterbrochener Import wird fortgesetzt · " + detail;
        if (stage.contains("PARSE")) return "Playlist wird geprüft · " + detail;
        if (stage.contains("DOWNLOAD")) return "Playlist wird geladen · " + detail;
        return detail;
    }

    private void finishImport(String interaction, List<Channel> result) {
        all = result;
        search.setText("");
        mode = Mode.LIVE;
        updateModeStyles();
        setBusy(false, repository.sourceName() + " · " + all.size() + " Einträge importiert");
        empty.setText("Keine Treffer im aktuellen Bereich.");
        filterNow();
        log.event(interaction, "CATALOG-READY", "entries=" + all.size());
        Toast.makeText(this, all.size() + " Einträge sind bereit.", Toast.LENGTH_LONG).show();
    }

    private void importFailure(Throwable failure) {
        boolean recoverable = repository.hasRecoverableCandidate();
        setBusy(false, recoverable
                ? "Prüfung unterbrochen: " + message(failure)
                        + " · verschlüsselte Kandidatendatei bleibt gespeichert"
                : "Import fehlgeschlagen: " + message(failure)
                        + " · bisherige Bibliothek bleibt aktiv");
        Toast.makeText(this, recoverable
                ? "Prüfung unterbrochen. Beim nächsten Start wird sie automatisch fortgesetzt."
                : "Import fehlgeschlagen. Diagnose öffnen; die bisherige Bibliothek wurde nicht ersetzt.",
                Toast.LENGTH_LONG).show();
    }

    private void select(int position) {
        Channel channel = adapter.item(position);
        if (channel == null) return;
        String interaction = log.newInteractionId();
        long delay = lastInputEvent <= 0 ? 0
                : Math.max(0, SystemClock.uptimeMillis() - lastInputEvent);
        log.event(interaction, "INPUT-DELIVERED",
                "deliveryDelayMs=" + delay + " position=" + position);
        log.event(interaction, "SELECTION-VALIDATE-START",
                "item=" + log.anonymousId(channel.id));
        if (channel.url.isBlank()) {
            log.event(interaction, "SELECTION-INVALID", "reason=empty-url");
            Toast.makeText(this, "Dieser Eintrag enthält keine Stream-Adresse.",
                    Toast.LENGTH_LONG).show();
            return;
        }
        log.event(interaction, "SELECTION-VALIDATE-OK", "type=" + channel.type);
        log.event(interaction, "PLAYER-NAV-REQUEST",
                "item=" + log.anonymousId(channel.id));
        Intent intent = new Intent(this, PlayerActivity.class);
        intent.putExtra(PlayerActivity.EXTRA_URL, channel.url);
        intent.putExtra(PlayerActivity.EXTRA_NAME, channel.name);
        intent.putExtra(PlayerActivity.EXTRA_INTERACTION, interaction);
        startActivity(intent);
    }

    private Button modeButton(String label, Mode target) {
        Button button = button(label, false);
        button.setOnClickListener(v -> {
            mode = target;
            search.setText("");
            updateModeStyles();
            filterNow();
        });
        return button;
    }

    private void updateModeStyles() {
        style(liveButton, mode == Mode.LIVE);
        style(movieButton, mode == Mode.MOVIES);
        style(seriesButton, mode == Mode.SERIES);
    }

    private void style(Button button, boolean selected) {
        if (button == null) return;
        button.setTextColor(selected ? 0xFF07111E : Color.WHITE);
        button.setBackground(roundRect(selected ? 0xFF5EEAD4 : 0xFF17354A,
                14, selected ? 0xFF5EEAD4 : 0xFF2A5068));
    }

    private void scheduleFilter() {
        if (pendingFilter != null) main.removeCallbacks(pendingFilter);
        pendingFilter = this::filterNow;
        main.postDelayed(pendingFilter, 220);
    }

    private void filterNow() {
        if (pendingFilter != null) main.removeCallbacks(pendingFilter);
        pendingFilter = null;
        int generation = filterGeneration.incrementAndGet();
        Mode wanted = mode;
        String query = search.getText().toString().trim();
        List<Channel> base = all;
        log.event("-", "LIST-SNAPSHOT-REQUEST",
                "mode=" + wanted + " base=" + base.size() + " queryLength=" + query.length());
        worker.execute(() -> {
            long started = SystemClock.elapsedRealtime();
            ArrayList<Channel> result = new ArrayList<>();
            for (Channel channel : base) {
                if (!matchesMode(channel, wanted)) continue;
                if (!query.isBlank() && !matches(channel, query)) continue;
                result.add(channel);
            }
            List<Channel> immutable = Collections.unmodifiableList(result);
            long duration = SystemClock.elapsedRealtime() - started;
            main.post(() -> {
                if (generation != filterGeneration.get() || wanted != mode) return;
                adapter.submit(immutable);
                count.setText(Integer.toString(immutable.size()));
                status.setText(repository.sourceName() + " · " + label(wanted)
                        + " · " + immutable.size() + " Treffer");
                log.event("-", "LIST-SNAPSHOT-READY",
                        "rows=" + immutable.size() + " durationMs=" + duration);
                list.post(() -> log.event("-", "LIST-FIRST-FRAME",
                        "visibleChildren=" + list.getChildCount()));
            });
        });
    }

    private static boolean matchesMode(Channel channel, Mode mode) {
        return mode == Mode.LIVE ? channel.type == Channel.Type.LIVE
                : mode == Mode.MOVIES ? channel.type == Channel.Type.MOVIE
                : channel.type == Channel.Type.SERIES;
    }

    private static boolean matches(Channel channel, String query) {
        return containsIgnoreCase(channel.name, query) || containsIgnoreCase(channel.group, query);
    }

    private static boolean containsIgnoreCase(String text, String needle) {
        int limit = text.length() - needle.length();
        for (int index = 0; index <= limit; index++) {
            if (text.regionMatches(true, index, needle, 0, needle.length())) return true;
        }
        return false;
    }

    private static String label(Mode mode) {
        return mode == Mode.MOVIES ? "Filme" : mode == Mode.SERIES ? "Serien" : "Live-TV";
    }

    private EditText input(String hint, boolean password) {
        EditText editText = new EditText(this);
        editText.setSingleLine(true);
        editText.setHint(hint);
        editText.setTextColor(Color.WHITE);
        editText.setHintTextColor(0xFF8DA5B8);
        editText.setPadding(dp(12), dp(10), dp(12), dp(10));
        editText.setBackground(roundRect(0xFF102337, 12, 0xFF294A61));
        if (password) {
            editText.setInputType(InputType.TYPE_CLASS_TEXT
                    | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        }
        return editText;
    }

    private LinearLayout form(EditText... fields) {
        LinearLayout form = new LinearLayout(this);
        form.setOrientation(LinearLayout.VERTICAL);
        form.setPadding(dp(18), dp(8), dp(18), 0);
        for (EditText field : fields) {
            LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT);
            params.setMargins(0, dp(5), 0, dp(5));
            form.addView(field, params);
        }
        return form;
    }

    private static String requireHttpUrl(String raw) throws Exception {
        String value = raw == null ? "" : raw.trim();
        if (value.isBlank()) throw new IllegalArgumentException("Adresse fehlt.");
        URI uri = new URI(value);
        String scheme = uri.getScheme() == null
                ? "" : uri.getScheme().toLowerCase(Locale.ROOT);
        if (!scheme.equals("http") && !scheme.equals("https")) {
            throw new IllegalArgumentException("Nur HTTP- und HTTPS-Adressen werden unterstützt.");
        }
        if (uri.getHost() == null && uri.getAuthority() == null) {
            throw new IllegalArgumentException("Serveradresse ist unvollständig.");
        }
        return value;
    }

    private void validation(Throwable failure) {
        log.exception("-", "IMPORT-VALIDATION-ERROR", failure);
        Toast.makeText(this, message(failure), Toast.LENGTH_LONG).show();
    }

    private void setBusy(boolean value, String message) {
        busy = value;
        if (sourceButton != null) sourceButton.setEnabled(!value);
        if (search != null) search.setEnabled(!value);
        if (status != null) status.setText(message);
    }

    private static String message(Throwable failure) {
        return failure == null || failure.getMessage() == null || failure.getMessage().isBlank()
                ? "Vorgang konnte nicht abgeschlossen werden." : failure.getMessage();
    }

    @Override
    public boolean dispatchTouchEvent(MotionEvent event) {
        if (event.getActionMasked() == MotionEvent.ACTION_DOWN) {
            lastInputEvent = event.getEventTime();
            log.event("-", "INPUT-DOWN", "deliveryDelayMs="
                    + Math.max(0, SystemClock.uptimeMillis() - event.getEventTime()));
        }
        return super.dispatchTouchEvent(event);
    }

    @Override
    protected void onDestroy() {
        watchdog.stop();
        worker.shutdownNow();
        super.onDestroy();
    }

    private boolean tv() {
        return (getResources().getConfiguration().uiMode & Configuration.UI_MODE_TYPE_MASK)
                == Configuration.UI_MODE_TYPE_TELEVISION;
    }

    private TextView text(String value, float size, int color, boolean bold) {
        TextView textView = new TextView(this);
        textView.setText(value);
        textView.setTextSize(size);
        textView.setTextColor(color);
        if (bold) textView.setTypeface(null, android.graphics.Typeface.BOLD);
        return textView;
    }

    private Button button(String value, boolean primary) {
        Button button = new Button(this);
        button.setText(value);
        button.setTextColor(primary ? 0xFF07111E : Color.WHITE);
        button.setBackground(roundRect(primary ? 0xFF5EEAD4 : 0xFF17354A,
                14, primary ? 0xFF5EEAD4 : 0xFF2A5068));
        return button;
    }

    private LinearLayout.LayoutParams weighted(int left) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                0, dp(tv() ? 56 : 48), 1f);
        params.setMargins(left, 0, 0, 0);
        return params;
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
