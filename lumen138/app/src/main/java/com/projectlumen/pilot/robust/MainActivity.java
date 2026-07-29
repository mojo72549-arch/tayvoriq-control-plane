package com.projectlumen.pilot.robust;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.SharedPreferences;
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
    private static final int ACCENT = 0xFF62E7D3;
    private static final int ACCENT_BLUE = 0xFF57B7F2;
    private static final int BG = 0xFF050D18;
    private static final int SURFACE = 0xEE0B2030;
    private static final int SURFACE_ALT = 0xEE122D42;
    private static final int STROKE = 0xFF2A5269;
    private static final int TEXT_SECONDARY = 0xFF9DB6C8;
    private static final String PREFS = "lumen_premium_view_state";

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
    private SharedPreferences preferences;
    private List<Channel> all = Collections.emptyList();
    private CatalogAdapter adapter;
    private Mode mode = Mode.LIVE;
    private MediaLanguage.Code language = MediaLanguage.Code.ALL;
    private boolean busy = true;
    private long lastInputEvent;
    private Runnable pendingFilter;

    private TextView sectionTitle;
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
    private Button allLanguageButton;
    private Button germanButton;
    private Button turkishButton;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        requestWindowFeature(Window.FEATURE_NO_TITLE);
        getWindow().setStatusBarColor(BG);
        getWindow().setNavigationBarColor(BG);
        log = DiagnosticLog.get(this);
        watchdog = new UiStallWatchdog(log);
        repository = new PlaylistRepository(this);
        preferences = getSharedPreferences(PREFS, MODE_PRIVATE);
        restoreViewState();
        log.event("-", "APP-CREATE-START", "thread=" + Thread.currentThread().getName());
        buildUi();
        log.event("-", "APP-CREATE-END", "uiReady=true premiumShell=true");
        restore();
    }

    private void restoreViewState() {
        try { mode = Mode.valueOf(preferences.getString("mode", Mode.LIVE.name())); }
        catch (Exception ignored) { mode = Mode.LIVE; }
        try { language = MediaLanguage.Code.valueOf(
                preferences.getString("language", MediaLanguage.Code.ALL.name())); }
        catch (Exception ignored) { language = MediaLanguage.Code.ALL; }
        if (language == MediaLanguage.Code.OTHER) language = MediaLanguage.Code.ALL;
    }

    private void saveViewState() {
        preferences.edit().putString("mode", mode.name())
                .putString("language", language.name()).apply();
    }

    private void buildUi() {
        FrameLayout stage = new FrameLayout(this);
        stage.setBackground(new GradientDrawable(
                GradientDrawable.Orientation.TL_BR,
                new int[]{0xFF040A14, 0xFF071D2D, 0xFF102A3A, 0xFF211B3D}));
        setContentView(stage);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        int side = dp(tv() ? 25 : 14);
        root.setPadding(side, dp(tv() ? 16 : 10), side, dp(8));
        stage.addView(root, new FrameLayout.LayoutParams(-1, -1));

        LinearLayout header = new LinearLayout(this);
        header.setGravity(Gravity.CENTER_VERTICAL);

        TextView mark = text("✦", tv() ? 23 : 19, BG, true);
        mark.setGravity(Gravity.CENTER);
        mark.setBackground(roundRect(ACCENT, 13, ACCENT));
        header.addView(mark, new LinearLayout.LayoutParams(dp(tv() ? 46 : 39), dp(tv() ? 46 : 39)));

        LinearLayout brand = new LinearLayout(this);
        brand.setOrientation(LinearLayout.VERTICAL);
        brand.setPadding(dp(10), 0, dp(6), 0);
        TextView title = text("", tv() ? 26 : 20, Color.WHITE, true);
        title.setText(brandText());
        title.setSingleLine(true);
        title.setEllipsize(TextUtils.TruncateAt.END);
        brand.addView(title);
        TextView meta = text("PREMIUM MEDIA PLAYER  ·  " + BuildConfig.VERSION_NAME,
                tv() ? 10 : 8, TEXT_SECONDARY, true);
        meta.setLetterSpacing(0.07f);
        meta.setSingleLine(true);
        meta.setEllipsize(TextUtils.TruncateAt.END);
        brand.addView(meta);
        header.addView(brand, new LinearLayout.LayoutParams(0, -2, 1f));

        Button diagnostics = actionButton("System", false);
        diagnostics.setOnClickListener(v -> startActivity(
                new Intent(this, DiagnosticsActivity.class)));
        header.addView(diagnostics, new LinearLayout.LayoutParams(-2, dp(tv() ? 43 : 37)));

        sourceButton = actionButton("+ Quelle", true);
        sourceButton.setEnabled(false);
        sourceButton.setOnClickListener(v -> showSourceMenu());
        LinearLayout.LayoutParams sourceParams = new LinearLayout.LayoutParams(-2, dp(tv() ? 43 : 37));
        sourceParams.setMargins(dp(7), 0, 0, 0);
        header.addView(sourceButton, sourceParams);
        root.addView(header);

        sectionTitle = text("", tv() ? 23 : 18, Color.WHITE, true);
        LinearLayout.LayoutParams sectionParams = new LinearLayout.LayoutParams(-1, -2);
        sectionParams.setMargins(0, dp(14), 0, dp(7));
        root.addView(sectionTitle, sectionParams);

        LinearLayout modes = new LinearLayout(this);
        modes.setOrientation(LinearLayout.HORIZONTAL);
        liveButton = modeButton("Live-TV", Mode.LIVE);
        movieButton = modeButton("Filme", Mode.MOVIES);
        seriesButton = modeButton("Serien", Mode.SERIES);
        modes.addView(liveButton, weighted(0));
        modes.addView(movieButton, weighted(dp(6)));
        modes.addView(seriesButton, weighted(dp(6)));
        root.addView(modes, new LinearLayout.LayoutParams(-1, dp(tv() ? 49 : 42)));

        LinearLayout languages = new LinearLayout(this);
        languages.setOrientation(LinearLayout.HORIZONTAL);
        germanButton = languageButton("🇩🇪 Deutsch", MediaLanguage.Code.DE);
        turkishButton = languageButton("🇹🇷 Türkçe", MediaLanguage.Code.TR);
        allLanguageButton = languageButton("Alle", MediaLanguage.Code.ALL);
        languages.addView(germanButton, weighted(0));
        languages.addView(turkishButton, weighted(dp(6)));
        languages.addView(allLanguageButton, weighted(dp(6)));
        LinearLayout.LayoutParams languageParams = new LinearLayout.LayoutParams(-1, dp(tv() ? 46 : 39));
        languageParams.setMargins(0, dp(7), 0, dp(9));
        root.addView(languages, languageParams);

        LinearLayout searchBar = new LinearLayout(this);
        searchBar.setGravity(Gravity.CENTER_VERTICAL);
        search = new EditText(this);
        search.setSingleLine(true);
        search.setHint("Sender, Film, Serie oder Gruppe suchen");
        search.setTextColor(Color.WHITE);
        search.setHintTextColor(0xFF7896AA);
        search.setTextSize(tv() ? 17 : 14);
        search.setPadding(dp(14), 0, dp(12), 0);
        search.setBackground(roundRect(SURFACE, 14, STROKE));
        search.addTextChangedListener(new TextWatcher() {
            @Override public void beforeTextChanged(CharSequence s, int start, int count, int after) { }
            @Override public void onTextChanged(CharSequence s, int start, int before, int count) { scheduleFilter(); }
            @Override public void afterTextChanged(Editable editable) { }
        });
        searchBar.addView(search, new LinearLayout.LayoutParams(0, dp(tv() ? 53 : 46), 1f));

        count = text("0", tv() ? 14 : 12, BG, true);
        count.setGravity(Gravity.CENTER);
        count.setMinWidth(dp(tv() ? 51 : 43));
        count.setPadding(dp(9), 0, dp(9), 0);
        count.setBackground(roundRect(ACCENT, 22, ACCENT));
        LinearLayout.LayoutParams countParams = new LinearLayout.LayoutParams(-2, dp(tv() ? 46 : 40));
        countParams.setMargins(dp(8), 0, 0, 0);
        searchBar.addView(count, countParams);
        root.addView(searchBar);

        loadingCard = new LinearLayout(this);
        loadingCard.setOrientation(LinearLayout.VERTICAL);
        loadingCard.setPadding(dp(14), dp(11), dp(14), dp(11));
        loadingCard.setBackground(roundRect(0xF011293A, 16, 0xFF35627B));
        loadingTitle = text("Bibliothek wird geöffnet", tv() ? 16 : 14, Color.WHITE, true);
        loadingTitle.setSingleLine(true);
        loadingCard.addView(loadingTitle);
        loadingDetail = text("Bitte einen Moment …", tv() ? 13 : 11, TEXT_SECONDARY, false);
        loadingDetail.setMaxLines(3);
        LinearLayout.LayoutParams detailParams = new LinearLayout.LayoutParams(-1, -2);
        detailParams.setMargins(0, dp(3), 0, dp(8));
        loadingCard.addView(loadingDetail, detailParams);
        loadingProgress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        loadingProgress.setIndeterminate(true);
        if (loadingProgress.getIndeterminateDrawable() != null) loadingProgress.getIndeterminateDrawable().setTint(ACCENT);
        if (loadingProgress.getProgressDrawable() != null) loadingProgress.getProgressDrawable().setTint(ACCENT);
        loadingCard.addView(loadingProgress, new LinearLayout.LayoutParams(-1, dp(4)));
        LinearLayout.LayoutParams loadingParams = new LinearLayout.LayoutParams(-1, -2);
        loadingParams.setMargins(0, dp(8), 0, 0);
        root.addView(loadingCard, loadingParams);

        FrameLayout host = new FrameLayout(this);
        LinearLayout.LayoutParams hostParams = new LinearLayout.LayoutParams(-1, 0, 1f);
        hostParams.setMargins(0, dp(8), 0, dp(5));
        root.addView(host, hostParams);

        list = new ListView(this);
        list.setDivider(new ColorDrawable(Color.TRANSPARENT));
        list.setDividerHeight(dp(7));
        list.setFastScrollEnabled(true);
        list.setSmoothScrollbarEnabled(true);
        list.setCacheColorHint(Color.TRANSPARENT);
        list.setSelector(roundRect(0x335EEAD4, 16, ACCENT));
        list.setOnItemClickListener((parent, view, position, id) -> select(position));
        host.addView(list, new FrameLayout.LayoutParams(-1, -1));

        LinearLayout emptyPanel = new LinearLayout(this);
        emptyPanel.setOrientation(LinearLayout.VERTICAL);
        emptyPanel.setGravity(Gravity.CENTER);
        TextView emptyMark = text("✦", tv() ? 35 : 29, ACCENT, false);
        emptyMark.setGravity(Gravity.CENTER);
        emptyPanel.addView(emptyMark);
        empty = text("Noch keine Inhalte\nQuelle hinzufügen, um zu starten.",
                tv() ? 18 : 15, TEXT_SECONDARY, false);
        empty.setGravity(Gravity.CENTER);
        empty.setLineSpacing(0, 1.15f);
        empty.setPadding(dp(22), dp(7), dp(22), dp(22));
        emptyPanel.addView(empty);
        host.addView(emptyPanel, new FrameLayout.LayoutParams(-1, -1));
        list.setEmptyView(emptyPanel);

        adapter = new CatalogAdapter(this);
        list.setAdapter(adapter);
        footerStatus = text("Lokale Bibliothek", tv() ? 12 : 10, 0xFF7E9AAF, false);
        footerStatus.setSingleLine(true);
        footerStatus.setEllipsize(TextUtils.TruncateAt.END);
        root.addView(footerStatus);
        updateSelectionStyles();
    }

    private void restore() {
        boolean candidate = repository.hasRecoverableCandidate();
        boolean reimportRequired = repository.legacyRecoveryRequiresReimport();
        setBusy(true,
                reimportRequired ? "Altimport wurde sicher angehalten"
                        : candidate ? "Import wird abgeschlossen" : "Bibliothek wird geöffnet",
                reimportRequired ? "Bitte den Playlist-Link einmal über + Quelle neu laden."
                        : candidate ? "Die geladene Playlist wird blockweise migriert und indexiert."
                        : "Gespeicherter Schnellindex wird geladen.");
        log.event("-", "RESTORE-QUEUED", "thread=background candidate=" + candidate
                + " reimportRequired=" + reimportRequired);
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
                    empty.setText(all.isEmpty() ? "Noch keine Inhalte\nQuelle hinzufügen, um zu starten."
                            : "Keine Treffer in diesem Bereich.");
                    filterNow();
                    log.event("-", "RESTORE-PARSE-END", "entries=" + all.size()
                            + " durationMs=" + (SystemClock.elapsedRealtime() - started));
                });
            } catch (Throwable failure) {
                log.exception("-", "RESTORE-ERROR", failure);
                main.post(() -> {
                    setBusy(false, "", "");
                    boolean needsReload = repository.legacyRecoveryRequiresReimport()
                            || message(failure).contains("Playlist-Link einmal neu laden");
                    footerStatus.setText(needsReload
                            ? "Altimport beendet · + Quelle ist verfügbar"
                            : "Wiederherstellung fehlgeschlagen · System öffnen");
                    empty.setText(needsReload
                            ? "Playlist-Link einmal neu laden\nDie bisherige App bleibt bedienbar."
                            : "Bibliothek konnte nicht geöffnet werden\nQuelle oder Systemstatus prüfen.");
                });
            }
        });
    }

    private void showSourceMenu() {
        if (busy) return;
        new AlertDialog.Builder(this).setTitle("Quelle hinzufügen")
                .setItems(new String[]{"Server + Login", "Playlist-Link", "Lokale M3U/M3U8-Datei"},
                        (dialog, which) -> {
                            if (which == 0) promptServer();
                            else if (which == 1) promptLink();
                            else openLocal();
                        }).setNegativeButton("Abbrechen", null).show();
    }

    private void promptLink() {
        EditText name = input("Name der Quelle", false);
        name.setText("Meine Playlist");
        EditText url = input("Vollständiger M3U/M3U8-Link", false);
        url.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        new AlertDialog.Builder(this).setTitle("Playlist-Link")
                .setMessage("Download, Verschlüsselung und Katalogaufbau laufen gemeinsam im Hintergrund.")
                .setView(form(name, url)).setPositiveButton("Laden", (dialog, which) -> {
                    try { importUrl(name.getText().toString(), requireHttpUrl(url.getText().toString()), "PLAYLIST-LINK"); }
                    catch (Throwable failure) { validation(failure); }
                }).setNegativeButton("Abbrechen", null).show();
    }

    private void promptServer() {
        EditText name = input("Name der Quelle", false);
        name.setText("Mein Server");
        EditText server = input("Serveradresse, z. B. http://server:8080", false);
        EditText user = input("Benutzername", false);
        EditText pass = input("Passwort", true);
        new AlertDialog.Builder(this).setTitle("Server + Login")
                .setMessage("Zugangsdaten werden lokal verarbeitet und nicht in der Diagnose angezeigt.")
                .setView(form(name, server, user, pass)).setPositiveButton("Verbinden", (dialog, which) -> {
                    try {
                        String base = requireHttpUrl(server.getText().toString());
                        while (base.endsWith("/")) base = base.substring(0, base.length() - 1);
                        String username = user.getText().toString().trim();
                        String password = pass.getText().toString();
                        if (username.isBlank() || password.isBlank()) throw new IllegalArgumentException("Benutzername oder Passwort fehlt.");
                        String url = base + "/get.php?username="
                                + URLEncoder.encode(username, StandardCharsets.UTF_8.name())
                                + "&password=" + URLEncoder.encode(password, StandardCharsets.UTF_8.name())
                                + "&type=m3u_plus&output=mpegts";
                        importUrl(name.getText().toString(), url, "SERVER-LOGIN");
                    } catch (Throwable failure) { validation(failure); }
                }).setNegativeButton("Abbrechen", null).show();
    }

    private void openLocal() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("*/*");
        intent.putExtra(Intent.EXTRA_MIME_TYPES, new String[]{"audio/x-mpegurl",
                "application/x-mpegurl", "application/vnd.apple.mpegurl",
                "text/plain", "application/octet-stream"});
        startActivityForResult(intent, REQUEST_LOCAL);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != REQUEST_LOCAL || resultCode != RESULT_OK
                || data == null || data.getData() == null) return;
        Uri uri = data.getData();
        try { getContentResolver().takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION); }
        catch (Throwable ignored) { }
        importLocal(uri);
    }

    private void importUrl(String name, String url, String origin) {
        String interaction = log.newInteractionId();
        setBusy(true, "Quelle wird geladen", "Download, Verschlüsselung und Katalogaufbau laufen parallel.");
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
        setBusy(true, "Lokale Quelle wird verarbeitet", "Datei wird verschlüsselt und gleichzeitig katalogisiert.");
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
            if (isFinishing() || loadingCard == null || !busy) return;
            loadingTitle.setText(progressTitle(stage));
            loadingDetail.setText(detail);
            int entries = numberAfter(detail, "Einträge=");
            if (entries >= 0 && (stage.contains("INDEX") || stage.contains("PARSE"))) {
                loadingProgress.setIndeterminate(false);
                loadingProgress.setMax(100_000);
                loadingProgress.setProgress(Math.min(100_000, entries));
            } else loadingProgress.setIndeterminate(true);
            footerStatus.setText(progressTitle(stage) + " · läuft im Hintergrund");
        });
    }

    private static boolean isVisibleProgressStage(String stage) {
        return stage.contains("CONNECT") || stage.contains("DOWNLOAD")
                || stage.contains("INDEX") || stage.contains("PARSE")
                || stage.contains("CACHE") || stage.contains("CANDIDATE")
                || stage.contains("LEGACY") || stage.contains("ROLLBACK")
                || stage.equals("IMPORT-PAUSED");
    }

    private static String progressTitle(String stage) {
        if (stage.contains("LEGACY-DECRYPT")) return "Altimport wird entschlüsselt";
        if (stage.contains("LEGACY-PARSE")) return "Altimport wird indexiert";
        if (stage.contains("CACHE") && stage.contains("RESTORE")) return "Bibliothek wird sofort geöffnet";
        if (stage.contains("CACHE")) return "Schnellstart wird vorbereitet";
        if (stage.contains("CANDIDATE")) return "Import wird abgeschlossen";
        if (stage.contains("CONNECT")) return "Verbindung wird aufgebaut";
        if (stage.contains("DOWNLOAD")) return "Quelle wird geladen";
        if (stage.contains("INDEX") || stage.contains("PARSE")) return "Katalog wird aufgebaut";
        if (stage.contains("ROLLBACK")) return "Sicherung wird wiederhergestellt";
        return "Bibliothek wird vorbereitet";
    }

    private static int numberAfter(String text, String marker) {
        int start = text == null ? -1 : text.indexOf(marker);
        if (start < 0) return -1;
        start += marker.length();
        int end = start;
        while (end < text.length() && Character.isDigit(text.charAt(end))) end++;
        try { return end == start ? -1 : Integer.parseInt(text.substring(start, end)); }
        catch (NumberFormatException ignored) { return -1; }
    }

    private void finishImport(String interaction, List<Channel> result) {
        all = result;
        search.setText("");
        mode = Mode.LIVE;
        language = MediaLanguage.Code.ALL;
        saveViewState();
        updateSelectionStyles();
        setBusy(false, "", "");
        footerStatus.setText(repository.sourceName() + " · " + all.size() + " Einträge · Schnellstart aktiv");
        empty.setText("Keine Treffer in diesem Bereich.");
        filterNow();
        log.event(interaction, "CATALOG-READY", "entries=" + all.size());
        Toast.makeText(this, all.size() + " Einträge sind bereit.", Toast.LENGTH_LONG).show();
    }

    private void importFailure(Throwable failure) {
        boolean recoverable = repository.hasRecoverableCandidate();
        setBusy(false, "", "");
        footerStatus.setText(recoverable
                ? "Download vollständig · Abschluss wird beim nächsten Start fortgesetzt"
                : "Import fehlgeschlagen · bisherige Bibliothek bleibt aktiv");
        Toast.makeText(this, recoverable ? "Die geladene Playlist bleibt gespeichert."
                : "Import fehlgeschlagen. Systemstatus öffnen; bisherige Bibliothek bleibt erhalten.",
                Toast.LENGTH_LONG).show();
    }

    private void select(int position) {
        Channel channel = adapter.item(position);
        if (channel == null) return;
        String interaction = log.newInteractionId();
        long delay = lastInputEvent <= 0 ? 0 : Math.max(0, SystemClock.uptimeMillis() - lastInputEvent);
        log.event(interaction, "INPUT-DELIVERED", "deliveryDelayMs=" + delay + " position=" + position);
        log.event(interaction, "SELECTION-VALIDATE-START", "item=" + log.anonymousId(channel.id));
        if (channel.url.isBlank()) {
            log.event(interaction, "SELECTION-INVALID", "reason=empty-url");
            Toast.makeText(this, "Dieser Eintrag enthält keine Stream-Adresse.", Toast.LENGTH_LONG).show();
            return;
        }
        log.event(interaction, "SELECTION-VALIDATE-OK", "type=" + channel.type
                + " language=" + MediaLanguage.detect(channel));
        Intent intent = new Intent(this, PlayerActivity.class);
        intent.putExtra(PlayerActivity.EXTRA_URL, channel.url);
        intent.putExtra(PlayerActivity.EXTRA_NAME, channel.name);
        intent.putExtra(PlayerActivity.EXTRA_INTERACTION, interaction);
        startActivity(intent);
    }

    private Button modeButton(String label, Mode target) {
        Button button = baseChoiceButton(label);
        button.setOnClickListener(v -> {
            mode = target;
            search.setText("");
            saveViewState();
            updateSelectionStyles();
            filterNow();
        });
        return button;
    }

    private Button languageButton(String label, MediaLanguage.Code target) {
        Button button = baseChoiceButton(label);
        button.setTextSize(tv() ? 13 : 11);
        button.setOnClickListener(v -> {
            language = target;
            search.setText("");
            saveViewState();
            updateSelectionStyles();
            filterNow();
        });
        return button;
    }

    private Button baseChoiceButton(String label) {
        Button button = new Button(this);
        button.setText(label);
        button.setTextSize(tv() ? 15 : 13);
        button.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        button.setAllCaps(false);
        button.setSingleLine(true);
        button.setMinWidth(0);
        button.setMinHeight(0);
        button.setPadding(dp(6), 0, dp(6), 0);
        return button;
    }

    private void updateSelectionStyles() {
        styleChoice(liveButton, mode == Mode.LIVE, ACCENT);
        styleChoice(movieButton, mode == Mode.MOVIES, ACCENT);
        styleChoice(seriesButton, mode == Mode.SERIES, ACCENT);
        styleChoice(germanButton, language == MediaLanguage.Code.DE, 0xFFF4D35E);
        styleChoice(turkishButton, language == MediaLanguage.Code.TR, 0xFFE94D5F);
        styleChoice(allLanguageButton, language == MediaLanguage.Code.ALL, ACCENT_BLUE);
        if (sectionTitle != null) sectionTitle.setText(label(mode) + "  ·  " + MediaLanguage.label(language));
    }

    private void styleChoice(Button button, boolean selected, int selectedColor) {
        if (button == null) return;
        button.setTextColor(selected ? BG : 0xFFDCE8EF);
        button.setBackground(roundRect(selected ? selectedColor : SURFACE_ALT,
                13, selected ? selectedColor : STROKE));
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
        Mode wantedMode = mode;
        MediaLanguage.Code wantedLanguage = language;
        String query = search.getText().toString().trim();
        List<Channel> base = all;
        log.event("-", "LIST-SNAPSHOT-REQUEST", "mode=" + wantedMode
                + " language=" + wantedLanguage + " base=" + base.size()
                + " queryLength=" + query.length());
        worker.execute(() -> {
            long started = SystemClock.elapsedRealtime();
            ArrayList<Channel> result = new ArrayList<>();
            for (Channel channel : base) {
                if (!matchesMode(channel, wantedMode)) continue;
                if (wantedLanguage != MediaLanguage.Code.ALL
                        && MediaLanguage.detect(channel) != wantedLanguage) continue;
                if (!query.isBlank() && !matches(channel, query)) continue;
                result.add(channel);
            }
            List<Channel> immutable = Collections.unmodifiableList(result);
            long duration = SystemClock.elapsedRealtime() - started;
            main.post(() -> {
                if (generation != filterGeneration.get() || wantedMode != mode
                        || wantedLanguage != language) return;
                adapter.submit(immutable);
                count.setText(Integer.toString(immutable.size()));
                if (!busy) footerStatus.setText(repository.sourceName() + " · " + label(wantedMode)
                        + " · " + MediaLanguage.label(wantedLanguage) + " · "
                        + immutable.size() + " Treffer");
                log.event("-", "LIST-SNAPSHOT-READY", "rows=" + immutable.size()
                        + " durationMs=" + duration + " language=" + wantedLanguage);
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
        editText.setHintTextColor(0xFF7893A7);
        editText.setPadding(dp(12), dp(10), dp(12), dp(10));
        editText.setBackground(roundRect(SURFACE, 12, STROKE));
        if (password) editText.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        return editText;
    }

    private LinearLayout form(EditText... fields) {
        LinearLayout form = new LinearLayout(this);
        form.setOrientation(LinearLayout.VERTICAL);
        form.setPadding(dp(18), dp(8), dp(18), 0);
        for (EditText field : fields) {
            LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2);
            params.setMargins(0, dp(5), 0, dp(5));
            form.addView(field, params);
        }
        return form;
    }

    private static String requireHttpUrl(String raw) throws Exception {
        String value = raw == null ? "" : raw.trim();
        if (value.isBlank()) throw new IllegalArgumentException("Adresse fehlt.");
        URI uri = new URI(value);
        String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase(Locale.ROOT);
        if (!scheme.equals("http") && !scheme.equals("https")) throw new IllegalArgumentException("Nur HTTP- und HTTPS-Adressen werden unterstützt.");
        if (uri.getHost() == null && uri.getAuthority() == null) throw new IllegalArgumentException("Serveradresse ist unvollständig.");
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
        button.setTextSize(tv() ? 13 : 10);
        button.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        button.setAllCaps(false);
        button.setSingleLine(true);
        button.setMinWidth(0);
        button.setMinHeight(0);
        button.setPadding(dp(tv() ? 13 : 9), 0, dp(tv() ? 13 : 9), 0);
        button.setTextColor(primary ? BG : 0xFFE5EEF4);
        button.setBackground(roundRect(primary ? ACCENT : SURFACE_ALT,
                12, primary ? ACCENT : STROKE));
        return button;
    }

    private SpannableString brandText() {
        SpannableString value = new SpannableString("PROJECT LUMEN");
        value.setSpan(new StyleSpan(Typeface.BOLD), 0, value.length(), Spannable.SPAN_EXCLUSIVE_EXCLUSIVE);
        value.setSpan(new ForegroundColorSpan(ACCENT), 8, value.length(), Spannable.SPAN_EXCLUSIVE_EXCLUSIVE);
        return value;
    }

    private static String message(Throwable failure) {
        return failure == null || failure.getMessage() == null || failure.getMessage().isBlank()
                ? "Vorgang konnte nicht abgeschlossen werden." : failure.getMessage();
    }

    @Override
    public boolean dispatchTouchEvent(MotionEvent event) {
        if (event.getActionMasked() == MotionEvent.ACTION_DOWN) {
            lastInputEvent = event.getEventTime();
            log.event("-", "INPUT-DOWN", "deliveryDelayMs=" + Math.max(0,
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
        return (getResources().getConfiguration().uiMode & Configuration.UI_MODE_TYPE_MASK)
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
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, -1, 1f);
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
