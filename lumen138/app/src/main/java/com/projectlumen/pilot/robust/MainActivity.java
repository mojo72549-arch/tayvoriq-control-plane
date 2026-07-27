package com.projectlumen.pilot.robust;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.res.Configuration;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.ColorDrawable;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.text.Editable;
import android.text.InputType;
import android.text.Spannable;
import android.text.SpannableString;
import android.text.TextUtils;
import android.text.TextWatcher;
import android.text.style.ForegroundColorSpan;
import android.text.style.StyleSpan;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.Window;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.ProgressBar;
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
    private static final int ACCENT = 0xFF5EEAD4;
    private static final int BG = 0xFF06101D;
    private static final int SURFACE = 0xFF0E2435;
    private static final int SURFACE_ALT = 0xFF122D42;
    private static final int STROKE = 0xFF274B61;
    private static final int TEXT_SECONDARY = 0xFF9DB2C3;

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

    private TextView footerStatus;
    private TextView empty;
    private TextView count;
    private TextView loadingTitle;
    private TextView loadingDetail;
    private EditText search;
    private ListView list;
    private LinearLayout loadingCard;
    private ProgressBar loadingProgress;
    private Button sourceButton;
    private Button liveButton;
    private Button movieButton;
    private Button seriesButton;
    private Runnable pendingFilter;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        requestWindowFeature(Window.FEATURE_NO_TITLE);
        getWindow().setStatusBarColor(BG);
        getWindow().setNavigationBarColor(BG);
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
        int side = dp(tv() ? 24 : 14);
        root.setPadding(side, dp(tv() ? 16 : 10), side, dp(9));
        root.setBackground(new GradientDrawable(
                GradientDrawable.Orientation.TL_BR,
                new int[]{0xFF050D18, 0xFF071A29, 0xFF0B2536}));
        setContentView(root);

        LinearLayout header = new LinearLayout(this);
        header.setOrientation(LinearLayout.HORIZONTAL);
        header.setGravity(Gravity.CENTER_VERTICAL);

        LinearLayout brand = new LinearLayout(this);
        brand.setOrientation(LinearLayout.VERTICAL);
        TextView brandTitle = text("", tv() ? 27 : 23, Color.WHITE, true);
        brandTitle.setText(brandText());
        brandTitle.setSingleLine(true);
        brandTitle.setEllipsize(TextUtils.TruncateAt.END);
        brand.addView(brandTitle);

        LinearLayout brandMeta = new LinearLayout(this);
        brandMeta.setOrientation(LinearLayout.HORIZONTAL);
        brandMeta.setGravity(Gravity.CENTER_VERTICAL);
        TextView premium = text("PREMIUM MEDIA PLAYER", tv() ? 11 : 9, TEXT_SECONDARY, true);
        premium.setLetterSpacing(0.12f);
        brandMeta.addView(premium);
        TextView version = text("  13.1.40", tv() ? 11 : 9, ACCENT, true);
        version.setSingleLine(true);
        brandMeta.addView(version);
        brand.addView(brandMeta);
        header.addView(brand, new LinearLayout.LayoutParams(0,
                LinearLayout.LayoutParams.WRAP_CONTENT, 1f));

        Button diagnostics = actionButton("Diagnose", false);
        diagnostics.setOnClickListener(v -> startActivity(
                new Intent(this, DiagnosticsActivity.class)));
        header.addView(diagnostics, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, dp(tv() ? 44 : 38)));

        sourceButton = actionButton("+ Quelle", true);
        sourceButton.setEnabled(false);
        sourceButton.setOnClickListener(v -> showSourceMenu());
        LinearLayout.LayoutParams sourceParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, dp(tv() ? 44 : 38));
        sourceParams.setMargins(dp(7), 0, 0, 0);
        header.addView(sourceButton, sourceParams);
        root.addView(header);

        LinearLayout modes = new LinearLayout(this);
        modes.setOrientation(LinearLayout.HORIZONTAL);
        LinearLayout.LayoutParams modesParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, dp(tv() ? 50 : 43));
        modesParams.setMargins(0, dp(12), 0, dp(8));
        liveButton = modeButton("Live", Mode.LIVE);
        movieButton = modeButton("Filme", Mode.MOVIES);
        seriesButton = modeButton("Serien", Mode.SERIES);
        modes.addView(liveButton, weighted(0));
        modes.addView(movieButton, weighted(dp(6)));
        modes.addView(seriesButton, weighted(dp(6)));
        root.addView(modes, modesParams);

        LinearLayout searchBar = new LinearLayout(this);
        searchBar.setOrientation(LinearLayout.HORIZONTAL);
        searchBar.setGravity(Gravity.CENTER_VERTICAL);
        search = new EditText(this);
        search.setSingleLine(true);
        search.setHint("Sender, Filme oder Serien suchen");
        search.setTextColor(Color.WHITE);
        search.setHintTextColor(0xFF7893A7);
        search.setTextSize(tv() ? 17 : 14);
        search.setPadding(dp(14), 0, dp(12), 0);
        search.setBackground(roundRect(SURFACE, 14, STROKE));
        search.addTextChangedListener(new TextWatcher() {
            @Override public void beforeTextChanged(CharSequence s, int start, int count, int after) { }
            @Override public void onTextChanged(CharSequence s, int start, int before, int count) {
                scheduleFilter();
            }
            @Override public void afterTextChanged(Editable editable) { }
        });
        searchBar.addView(search, new LinearLayout.LayoutParams(
                0, dp(tv() ? 54 : 47), 1f));

        count = text("0", tv() ? 14 : 12, BG, true);
        count.setGravity(Gravity.CENTER);
        count.setMinWidth(dp(tv() ? 50 : 42));
        count.setPadding(dp(10), 0, dp(10), 0);
        count.setBackground(roundRect(ACCENT, 22, ACCENT));
        LinearLayout.LayoutParams countParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, dp(tv() ? 46 : 40));
        countParams.setMargins(dp(8), 0, 0, 0);
        searchBar.addView(count, countParams);
        root.addView(searchBar);

        loadingCard = new LinearLayout(this);
        loadingCard.setOrientation(LinearLayout.VERTICAL);
        loadingCard.setPadding(dp(14), dp(11), dp(14), dp(11));
        loadingCard.setBackground(roundRect(0xEE0D2233, 16, 0xFF2C5369));
        loadingTitle = text("Bibliothek wird geöffnet", tv() ? 16 : 14, Color.WHITE, true);
        loadingTitle.setSingleLine(true);
        loadingCard.addView(loadingTitle);
        loadingDetail = text("Bitte einen Moment …", tv() ? 13 : 11, TEXT_SECONDARY, false);
        loadingDetail.setMaxLines(2);
        LinearLayout.LayoutParams detailParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
        detailParams.setMargins(0, dp(3), 0, dp(8));
        loadingCard.addView(loadingDetail, detailParams);
        loadingProgress = new ProgressBar(this, null,
                android.R.attr.progressBarStyleHorizontal);
        loadingProgress.setIndeterminate(true);
        if (loadingProgress.getIndeterminateDrawable() != null) {
            loadingProgress.getIndeterminateDrawable().setTint(ACCENT);
        }
        if (loadingProgress.getProgressDrawable() != null) {
            loadingProgress.getProgressDrawable().setTint(ACCENT);
        }
        loadingCard.addView(loadingProgress, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, dp(4)));
        LinearLayout.LayoutParams loadingParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
        loadingParams.setMargins(0, dp(8), 0, 0);
        root.addView(loadingCard, loadingParams);

        FrameLayout host = new FrameLayout(this);
        LinearLayout.LayoutParams hostParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f);
        hostParams.setMargins(0, dp(8), 0, dp(5));
        root.addView(host, hostParams);

        list = new ListView(this);
        list.setDivider(new ColorDrawable(Color.TRANSPARENT));
        list.setDividerHeight(dp(7));
        list.setFastScrollEnabled(true);
        list.setSmoothScrollbarEnabled(true);
        list.setCacheColorHint(Color.TRANSPARENT);
        list.setSelector(roundRect(0x335EEAD4, 15, ACCENT));
        list.setOnItemClickListener((parent, view, position, id) -> select(position));
        host.addView(list, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT));

        LinearLayout emptyPanel = new LinearLayout(this);
        emptyPanel.setOrientation(LinearLayout.VERTICAL);
        emptyPanel.setGravity(Gravity.CENTER);
        TextView emptyMark = text("✦", tv() ? 34 : 28, ACCENT, false);
        emptyMark.setGravity(Gravity.CENTER);
        emptyPanel.addView(emptyMark);
        empty = text("Noch keine Inhalte\nQuelle hinzufügen, um zu starten.",
                tv() ? 18 : 15, TEXT_SECONDARY, false);
        empty.setGravity(Gravity.CENTER);
        empty.setLineSpacing(0, 1.15f);
        empty.setPadding(dp(22), dp(6), dp(22), dp(22));
        emptyPanel.addView(empty);
        host.addView(emptyPanel, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT));
        list.setEmptyView(emptyPanel);

        adapter = new CatalogAdapter(this);
        list.setAdapter(adapter);

        footerStatus = text("Lokale Bibliothek", tv() ? 12 : 10, 0xFF7790A3, false);
        footerStatus.setSingleLine(true);
        footerStatus.setEllipsize(TextUtils.TruncateAt.END);
        root.addView(footerStatus);
        updateModeStyles();
    }

    private void restore() {
        boolean candidate = repository.hasRecoverableCandidate();
        setBusy(true,
                candidate ? "Import wird abgeschlossen" : "Bibliothek wird geöffnet",
                candidate
                        ? "Die bereits geladene Playlist wird geprüft und für den Schnellstart indexiert."
                        : "Gespeicherter Schnellindex wird geladen.");
        log.event("-", "RESTORE-QUEUED", "thread=background candidate=" + candidate);
        worker.execute(() -> {
            long started = SystemClock.elapsedRealtime();
            try {
                List<Channel> restored = repository.restore(
                        (stage, detail) -> reportProgress("-", stage, detail));
                main.post(() -> {
                    all = restored;
                    setBusy(false, "", "");
                    footerStatus.setText(repository.sourceName() + " · " + all.size()
                            + " Einträge · bereit in "
                            + (SystemClock.elapsedRealtime() - started) + " ms");
                    empty.setText(all.isEmpty()
                            ? "Noch keine Inhalte\nQuelle hinzufügen, um zu starten."
                            : "Keine Treffer im aktuellen Bereich.");
                    filterNow();
                    log.event("-", "RESTORE-PARSE-END",
                            "entries=" + all.size() + " durationMs="
                                    + (SystemClock.elapsedRealtime() - started));
                });
            } catch (Throwable failure) {
                log.exception("-", "RESTORE-ERROR", failure);
                main.post(() -> {
                    setBusy(false, "", "");
                    boolean recoverable = repository.hasRecoverableCandidate();
                    footerStatus.setText(recoverable
                            ? "Importprüfung pausiert · Diagnose öffnen"
                            : "Wiederherstellung fehlgeschlagen · Diagnose öffnen");
                    empty.setText(recoverable
                            ? "Import noch nicht abgeschlossen\nDie geladene Datei bleibt sicher gespeichert."
                            : "Bibliothek konnte nicht geöffnet werden\nQuelle erneut hinzufügen oder Diagnose öffnen.");
                });
            }
        });
    }

    private void showSourceMenu() {
        if (busy) return;
        new AlertDialog.Builder(this)
                .setTitle("Quelle hinzufügen")
                .setItems(new String[]{
                                "Server + Login",
                                "Playlist-Link",
                                "Lokale M3U/M3U8-Datei"},
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
                .setMessage("Download, Verschlüsselung und Katalogaufbau laufen jetzt in einem gemeinsamen Hintergrundvorgang.")
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
                .setMessage("Lumen erstellt die Playlist-Adresse lokal. Zugangsdaten erscheinen nicht in der Diagnose.")
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
                                + "&password="
                                + URLEncoder.encode(password, StandardCharsets.UTF_8.name())
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
                "application/vnd.apple.mpegurl", "text/plain",
                "application/octet-stream"});
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
        setBusy(true, "Quelle wird geladen",
                "Download, Verschlüsselung und Katalogaufbau laufen parallel.");
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
        setBusy(true, "Lokale Quelle wird verarbeitet",
                "Datei wird verschlüsselt und gleichzeitig katalogisiert.");
        log.event(interaction, "LOCAL-IMPORT-START", "uriPresent=true");
        worker.execute(() -> {
            try {
                List<Channel> result = repository.importUri(
                        "Lokale Playlist", getContentResolver(), uri,
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
            if (isFinishing() || loadingCard == null || !busy) return;
            loadingTitle.setText(progressTitle(stage));
            loadingDetail.setText(detail);
            updateProgressBar(stage, detail);
            footerStatus.setText(progressTitle(stage) + " · läuft im Hintergrund");
        });
    }

    private static boolean isVisibleProgressStage(String stage) {
        return stage.contains("CONNECT") || stage.contains("DOWNLOAD")
                || stage.contains("INDEX") || stage.contains("PARSE")
                || stage.contains("CACHE") || stage.contains("CANDIDATE")
                || stage.contains("ROLLBACK") || stage.equals("IMPORT-PAUSED");
    }

    private static String progressTitle(String stage) {
        if (stage.contains("CACHE") && stage.contains("RESTORE")) {
            return "Bibliothek wird sofort geöffnet";
        }
        if (stage.contains("CACHE")) return "Schnellstart wird vorbereitet";
        if (stage.contains("CANDIDATE")) return "Import wird abgeschlossen";
        if (stage.contains("CONNECT")) return "Verbindung wird aufgebaut";
        if (stage.contains("DOWNLOAD")) return "Quelle wird geladen";
        if (stage.contains("INDEX") || stage.contains("PARSE")) {
            return "Katalog wird aufgebaut";
        }
        if (stage.contains("ROLLBACK")) return "Sicherung wird wiederhergestellt";
        return "Bibliothek wird vorbereitet";
    }

    private void updateProgressBar(String stage, String detail) {
        int entries = numberAfter(detail, "Einträge=");
        if (entries >= 0 && (stage.contains("INDEX") || stage.contains("PARSE"))) {
            loadingProgress.setIndeterminate(false);
            loadingProgress.setMax(100_000);
            loadingProgress.setProgress(Math.min(100_000, entries));
        } else {
            loadingProgress.setIndeterminate(true);
        }
    }

    private static int numberAfter(String text, String marker) {
        int start = text == null ? -1 : text.indexOf(marker);
        if (start < 0) return -1;
        start += marker.length();
        int end = start;
        while (end < text.length() && Character.isDigit(text.charAt(end))) end++;
        if (end == start) return -1;
        try { return Integer.parseInt(text.substring(start, end)); }
        catch (NumberFormatException ignored) { return -1; }
    }

    private void finishImport(String interaction, List<Channel> result) {
        all = result;
        search.setText("");
        mode = Mode.LIVE;
        updateModeStyles();
        setBusy(false, "", "");
        footerStatus.setText(repository.sourceName() + " · " + all.size()
                + " Einträge · Schnellstart aktiv");
        empty.setText("Keine Treffer im aktuellen Bereich.");
        filterNow();
        log.event(interaction, "CATALOG-READY", "entries=" + all.size());
        Toast.makeText(this, all.size() + " Einträge sind bereit.",
                Toast.LENGTH_LONG).show();
    }

    private void importFailure(Throwable failure) {
        boolean recoverable = repository.hasRecoverableCandidate();
        setBusy(false, "", "");
        footerStatus.setText(recoverable
                ? "Download vollständig · Abschluss wird beim nächsten Start fortgesetzt"
                : "Import fehlgeschlagen · bisherige Bibliothek bleibt aktiv");
        Toast.makeText(this, recoverable
                ? "Die geladene Playlist bleibt gespeichert und wird beim nächsten Start fortgesetzt."
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
        Button button = new Button(this);
        button.setText(label);
        button.setTextSize(tv() ? 15 : 13);
        button.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        button.setAllCaps(false);
        button.setMinWidth(0);
        button.setMinHeight(0);
        button.setPadding(dp(8), 0, dp(8), 0);
        button.setOnClickListener(v -> {
            mode = target;
            search.setText("");
            updateModeStyles();
            filterNow();
        });
        return button;
    }

    private void updateModeStyles() {
        styleMode(liveButton, mode == Mode.LIVE);
        styleMode(movieButton, mode == Mode.MOVIES);
        styleMode(seriesButton, mode == Mode.SERIES);
    }

    private void styleMode(Button button, boolean selected) {
        if (button == null) return;
        button.setTextColor(selected ? BG : 0xFFDCE7EE);
        button.setBackground(roundRect(
                selected ? ACCENT : SURFACE_ALT,
                13,
                selected ? ACCENT : STROKE));
    }

    private void scheduleFilter() {
        if (pendingFilter != null) main.removeCallbacks(pendingFilter);
        pendingFilter = this::filterNow;
        main.postDelayed(pendingFilter, 180);
    }

    private void filterNow() {
        if (pendingFilter != null) main.removeCallbacks(pendingFilter);
        pendingFilter = null;
        int generation = filterGeneration.incrementAndGet();
        Mode wanted = mode;
        String query = search.getText().toString().trim();
        List<Channel> base = all;
        log.event("-", "LIST-SNAPSHOT-REQUEST",
                "mode=" + wanted + " base=" + base.size()
                        + " queryLength=" + query.length());
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
                if (!busy) {
                    footerStatus.setText(repository.sourceName() + " · " + label(wanted)
                            + " · " + immutable.size() + " Treffer");
                }
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
        return containsIgnoreCase(channel.name, query)
                || containsIgnoreCase(channel.group, query);
    }

    private static boolean containsIgnoreCase(String text, String needle) {
        int limit = text.length() - needle.length();
        for (int index = 0; index <= limit; index++) {
            if (text.regionMatches(true, index, needle, 0, needle.length())) return true;
        }
        return false;
    }

    private static String label(Mode mode) {
        return mode == Mode.MOVIES ? "Filme"
                : mode == Mode.SERIES ? "Serien" : "Live";
    }

    private EditText input(String hint, boolean password) {
        EditText editText = new EditText(this);
        editText.setSingleLine(true);
        editText.setHint(hint);
        editText.setTextColor(Color.WHITE);
        editText.setHintTextColor(0xFF7893A7);
        editText.setPadding(dp(12), dp(10), dp(12), dp(10));
        editText.setBackground(roundRect(SURFACE, 12, STROKE));
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
            throw new IllegalArgumentException(
                    "Nur HTTP- und HTTPS-Adressen werden unterstützt.");
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

    private void setBusy(boolean value, String title, String detail) {
        busy = value;
        sourceButton.setEnabled(!value);
        sourceButton.setAlpha(value ? 0.55f : 1f);
        loadingCard.setVisibility(value ? View.VISIBLE : View.GONE);
        if (value) {
            loadingTitle.setText(title);
            loadingDetail.setText(detail);
            loadingProgress.setIndeterminate(true);
        }
    }

    private Button actionButton(String value, boolean primary) {
        Button button = new Button(this);
        button.setText(value);
        button.setTextSize(tv() ? 13 : 11);
        button.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        button.setAllCaps(false);
        button.setSingleLine(true);
        button.setMinWidth(0);
        button.setMinHeight(0);
        button.setPadding(dp(tv() ? 13 : 10), 0, dp(tv() ? 13 : 10), 0);
        button.setTextColor(primary ? BG : 0xFFE5EEF4);
        button.setBackground(roundRect(
                primary ? ACCENT : SURFACE_ALT,
                12,
                primary ? ACCENT : STROKE));
        return button;
    }

    private SpannableString brandText() {
        SpannableString value = new SpannableString("LUMEN FLOW");
        value.setSpan(new StyleSpan(Typeface.BOLD), 0, value.length(),
                Spannable.SPAN_EXCLUSIVE_EXCLUSIVE);
        value.setSpan(new ForegroundColorSpan(ACCENT), 6, value.length(),
                Spannable.SPAN_EXCLUSIVE_EXCLUSIVE);
        return value;
    }

    private static String message(Throwable failure) {
        if (failure == null || failure.getMessage() == null
                || failure.getMessage().isBlank()) {
            return "Vorgang konnte nicht abgeschlossen werden.";
        }
        return failure.getMessage();
    }

    @Override
    public boolean dispatchTouchEvent(MotionEvent event) {
        if (event.getActionMasked() == MotionEvent.ACTION_DOWN) {
            lastInputEvent = event.getEventTime();
            log.event("-", "INPUT-DOWN",
                    "deliveryDelayMs=" + Math.max(0,
                            SystemClock.uptimeMillis() - event.getEventTime()));
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
        return (getResources().getConfiguration().uiMode
                & Configuration.UI_MODE_TYPE_MASK)
                == Configuration.UI_MODE_TYPE_TELEVISION;
    }

    private TextView text(String value, float size, int color, boolean bold) {
        TextView text = new TextView(this);
        text.setText(value);
        text.setTextSize(size);
        text.setTextColor(color);
        if (bold) text.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        return text;
    }

    private LinearLayout.LayoutParams weighted(int leftMargin) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                0, LinearLayout.LayoutParams.MATCH_PARENT, 1f);
        params.setMargins(leftMargin, 0, 0, 0);
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
