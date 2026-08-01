from __future__ import annotations

import atexit
from pathlib import Path
import re
import sys


# GitHub Actions executes the existing RC5 and RC6 patch scripts directly from
# this directory. Run the RC6.3 finishing patch only after apply_rc6_quality.py
# has completed, so all previous recovery and clean-PiP anchors remain intact.
if Path(sys.argv[0]).name == "apply_rc6_quality.py":
    ROOT = Path(__file__).resolve().parents[1]

    def finish_rc63() -> None:
        build = ROOT / "app/build.gradle"
        content = build.read_text(encoding="utf-8")
        content, code_count = re.subn(r"versionCode\s+\d+", "versionCode 1320630", content)
        content, name_count = re.subn(
            r"versionName\s+'[^']+'",
            "versionName '13.2.0-rc6.3-fast-tabs'",
            content,
        )
        if code_count < 1 or name_count < 1:
            raise RuntimeError("RC6.3 version anchors missing")
        build.write_text(content, encoding="utf-8")

        strings = ROOT / "app/src/main/res/values/strings.xml"
        content = strings.read_text(encoding="utf-8")
        content, label_count = re.subn(
            r'<string name="app_name">[^<]+</string>',
            '<string name="app_name">Project Lumen RC6.3</string>',
            content,
            count=1,
        )
        content = re.sub(
            r'<string name="app_name_rc61">[^<]+</string>',
            '<string name="app_name_rc61">Project Lumen RC6.3</string>',
            content,
            count=1,
        )
        if label_count != 1:
            raise RuntimeError("RC6.3 app label anchor missing")
        strings.write_text(content, encoding="utf-8")

        manifest = ROOT / "app/src/main/AndroidManifest.xml"
        content = manifest.read_text(encoding="utf-8")
        content, manifest_label_count = re.subn(
            r'android:label="@string/[^"]+"',
            'android:label="@string/app_name"',
            content,
            count=1,
        )
        if manifest_label_count != 1:
            raise RuntimeError("RC6.3 manifest label anchor missing")
        manifest.write_text(content, encoding="utf-8")

        player = ROOT / "app/src/main/java/com/projectlumen/pilot/robust/PlayerActivity.java"
        content = player.read_text(encoding="utf-8")

        entry_pattern = re.compile(
            r"    private boolean enterBackPictureInPicture\(\) \{.*?\n"
            r"    private boolean supportsPictureInPicture\(\) \{",
            re.DOTALL,
        )
        entry_replacement = '''    private boolean enterBackPictureInPicture() {
        if (!supportsPictureInPicture() || !playbackActive() || isFinishing()
                || isInPictureInPictureMode()) return false;

        // Hide every Project Lumen overlay before Android captures the PiP
        // transition frame. Waiting one animation frame prevents the title,
        // audio selector and status card from being frozen over the video.
        applyPictureInPictureUi(true);
        final PictureInPictureParams params = new PictureInPictureParams.Builder()
                .setAspectRatio(new Rational(16, 9))
                .build();
        final View transitionView = playerView != null
                ? playerView : getWindow().getDecorView();
        transitionView.postOnAnimation(() -> {
            try {
                boolean entered = enterPictureInPictureMode(params);
                log.event(interaction, "PLAYER-BACK-MINIMIZE",
                        "accepted=" + entered + " cleanUi=true");
                if (!entered) applyPictureInPictureUi(false);
            } catch (Throwable failure) {
                applyPictureInPictureUi(false);
                log.exception(interaction, "PLAYER-BACK-PIP-ERROR", failure);
            }
        });
        return true;
    }

    private boolean supportsPictureInPicture() {'''
        content, entry_count = entry_pattern.subn(entry_replacement, content, count=1)
        if entry_count != 1:
            raise RuntimeError("RC6.3 PiP entry anchor missing")

        callback_pattern = re.compile(
            r"    @Override\n"
            r"    public void onPictureInPictureModeChanged\(boolean active, Configuration configuration\) \{.*?\n"
            r"    private void buildUi\(\) \{",
            re.DOTALL,
        )
        callback_replacement = '''    private void applyPictureInPictureUi(boolean active) {
        inPictureInPicture = active;
        if (playerView != null) {
            playerView.setControllerAutoShow(!active);
            playerView.setUseController(!active);
            if (active) playerView.hideController();
        }
        if (topOverlay != null) {
            topOverlay.animate().cancel();
            topOverlay.clearAnimation();
            topOverlay.setAlpha(active ? 0f : 1f);
            topOverlay.setVisibility(active ? View.GONE : View.VISIBLE);
        }
        if (errorCard != null && active) errorCard.setVisibility(View.GONE);
        if (active) {
            getWindow().getDecorView().invalidate();
            if (playerView != null) playerView.invalidate();
        }
    }

    @Override
    public void onPictureInPictureModeChanged(boolean active, Configuration configuration) {
        super.onPictureInPictureModeChanged(active, configuration);
        applyPictureInPictureUi(active);
        log.event(interaction, active ? "PIP-ENTERED" : "PIP-EXITED",
                "trigger=BACK cleanUi=true");
    }

    private void buildUi() {'''
        content, callback_count = callback_pattern.subn(callback_replacement, content, count=1)
        if callback_count != 1:
            raise RuntimeError("RC6.3 PiP callback anchor missing")

        player.write_text(content, encoding="utf-8")

        main_activity = ROOT / "app/src/main/java/com/projectlumen/pilot/robust/MainActivity.java"
        content = main_activity.read_text(encoding="utf-8")

        if "import java.util.EnumMap;" not in content:
            content = content.replace(
                "import java.util.Collections;\n",
                "import java.util.Collections;\nimport java.util.EnumMap;\n",
                1,
            )
        if "import java.util.concurrent.Future;" not in content:
            content = content.replace(
                "import java.util.concurrent.Executors;\n",
                "import java.util.concurrent.Executors;\nimport java.util.concurrent.Future;\n",
                1,
            )

        field_anchor = '''    private final AtomicInteger filterGeneration = new AtomicInteger();
    private final Map<String, Button> languageButtons = new LinkedHashMap<>();
    private final Map<String, Button> groupButtons = new LinkedHashMap<>();
'''
        field_replacement = '''    private final AtomicInteger filterGeneration = new AtomicInteger();
    private final ExecutorService filterWorker = Executors.newFixedThreadPool(2, r -> {
        Thread thread = new Thread(r, "lumen-fast-filter");
        thread.setDaemon(true);
        return thread;
    });
    private final Map<String, Button> languageButtons = new LinkedHashMap<>();
    private final Map<String, Button> groupButtons = new LinkedHashMap<>();
    private final Map<Channel.Type, List<Channel>> typeBuckets =
            new EnumMap<>(Channel.Type.class);
    private final LinkedHashMap<String, ProviderCatalog.Snapshot> snapshotCache =
            new LinkedHashMap<String, ProviderCatalog.Snapshot>(24, 0.75f, true) {
                @Override
                protected boolean removeEldestEntry(
                        Map.Entry<String, ProviderCatalog.Snapshot> eldest) {
                    return size() > 24;
                }
            };
    private volatile int catalogRevision;
    private Future<?> activeFilterTask;
'''
        if content.count(field_anchor) != 1:
            raise RuntimeError("RC6.3 fast-filter field anchor missing")
        content = content.replace(field_anchor, field_replacement, 1)

        restore_anchor = "    private void restore() {\n"
        fast_helpers = '''    private void rebuildFastCatalogIndex() {
        EnumMap<Channel.Type, ArrayList<Channel>> buckets =
                new EnumMap<>(Channel.Type.class);
        for (Channel.Type value : Channel.Type.values()) {
            buckets.put(value, new ArrayList<>());
        }
        for (Channel channel : all) {
            if (channel == null || channel.type == null) continue;
            ArrayList<Channel> bucket = buckets.get(channel.type);
            if (bucket != null) bucket.add(channel);
        }
        typeBuckets.clear();
        for (Map.Entry<Channel.Type, ArrayList<Channel>> entry : buckets.entrySet()) {
            typeBuckets.put(entry.getKey(), Collections.unmodifiableList(entry.getValue()));
        }
        catalogRevision++;
        synchronized (snapshotCache) {
            snapshotCache.clear();
        }
        log.event("-", "FAST-CATALOG-INDEX-READY",
                "revision=" + catalogRevision
                        + " live=" + modeBase(Mode.LIVE).size()
                        + " movies=" + modeBase(Mode.MOVIES).size()
                        + " series=" + modeBase(Mode.SERIES).size());
    }

    private List<Channel> modeBase(Mode target) {
        List<Channel> indexed = typeBuckets.get(type(target));
        return indexed == null ? Collections.emptyList() : indexed;
    }

    private String snapshotKey(Mode target, String language, String group, String query) {
        return catalogRevision + "|" + target.name() + "|"
                + (language == null ? "" : language) + "|"
                + (group == null ? "" : group) + "|"
                + (query == null ? "" : query.toLowerCase(Locale.ROOT));
    }

    private ProviderCatalog.Snapshot cachedSnapshot(String key) {
        synchronized (snapshotCache) {
            return snapshotCache.get(key);
        }
    }

    private void cacheSnapshot(String key, ProviderCatalog.Snapshot snapshot) {
        synchronized (snapshotCache) {
            snapshotCache.put(key, snapshot);
        }
    }

    private void prewarmOtherModes() {
        final int revision = catalogRevision;
        final String language = selectedLanguage;
        for (Mode candidate : Mode.values()) {
            if (candidate == mode) continue;
            final List<Channel> base = modeBase(candidate);
            if (base.isEmpty()) continue;
            final String key = snapshotKey(candidate, language,
                    ProviderCatalog.ALL_GROUPS, "");
            if (cachedSnapshot(key) != null) continue;
            filterWorker.execute(() -> {
                long started = SystemClock.elapsedRealtime();
                ProviderCatalog.Snapshot snapshot = ProviderCatalog.build(
                        base, type(candidate), language,
                        ProviderCatalog.ALL_GROUPS, "");
                if (revision != catalogRevision) return;
                cacheSnapshot(key, snapshot);
                log.event("-", "TAB-PREWARM-READY",
                        "mode=" + candidate + " rows=" + snapshot.rows.size()
                                + " durationMs="
                                + (SystemClock.elapsedRealtime() - started));
            });
        }
    }

'''
        if content.count(restore_anchor) != 1:
            raise RuntimeError("RC6.3 restore anchor missing")
        content = content.replace(restore_anchor, fast_helpers + restore_anchor, 1)

        content, restored_count = re.subn(
            r"(\s+all = restored;\n)(\s+setBusy\(false, \"\", \"\"\);)",
            r"\1                    rebuildFastCatalogIndex();\n\2",
            content,
            count=1,
        )
        content, imported_count = re.subn(
            r"(\s+all = result;\n)(\s+search\.setText\(\"\"\);)",
            r"\1        rebuildFastCatalogIndex();\n\2",
            content,
            count=1,
        )
        if restored_count != 1 or imported_count != 1:
            raise RuntimeError("RC6.3 catalog index activation anchors missing")

        content = content.replace(
            '''                    filterNow();
                    log.event("-", "RESTORE-PARSE-END",''',
            '''                    filterNow();
                    prewarmOtherModes();
                    log.event("-", "RESTORE-PARSE-END",''',
            1,
        )
        content = content.replace(
            '''        filterNow();
        log.event(interaction, "CATALOG-READY",''',
            '''        filterNow();
        prewarmOtherModes();
        log.event(interaction, "CATALOG-READY",''',
            1,
        )

        mode_pattern = re.compile(
            r"    private Button modeButton\(String label, Mode target\) \{.*?\n"
            r"    private void renderLanguageButtons",
            re.DOTALL,
        )
        mode_replacement = '''    private Button modeButton(String label, Mode target) {
        Button button = baseChoiceButton(label);
        button.setOnClickListener(v -> {
            if (busy || target == mode) return;
            long started = SystemClock.elapsedRealtime();
            mode = target;
            selectedGroup = ProviderCatalog.ALL_GROUPS;
            if (search != null && search.length() > 0) search.setText("");
            saveViewState();
            updateSelectionStyles();
            filterNow();
            log.event("-", "TAB-SWITCH-REQUEST",
                    "mode=" + target + " dispatchMs="
                            + (SystemClock.elapsedRealtime() - started));
        });
        return button;
    }

    private void renderLanguageButtons'''
        content, mode_count = mode_pattern.subn(mode_replacement, content, count=1)
        if mode_count != 1:
            raise RuntimeError("RC6.3 mode switch anchor missing")

        filter_pattern = re.compile(
            r"    private void scheduleFilter\(\) \{.*?\n"
            r"    private static Channel.Type type\(Mode mode\) \{",
            re.DOTALL,
        )
        filter_replacement = '''    private void scheduleFilter() {
        if (pendingFilter != null) main.removeCallbacks(pendingFilter);
        pendingFilter = this::filterNow;
        main.postDelayed(pendingFilter, 90);
    }

    private void filterNow() {
        if (pendingFilter != null) main.removeCallbacks(pendingFilter);
        pendingFilter = null;
        int generation = filterGeneration.incrementAndGet();
        Mode wantedMode = mode;
        String wantedLanguage = selectedLanguage;
        String wantedGroup = selectedGroup;
        String query = search == null ? "" : search.getText().toString().trim();
        List<Channel> base = modeBase(wantedMode);
        String cacheKey = snapshotKey(
                wantedMode, wantedLanguage, wantedGroup, query);
        ProviderCatalog.Snapshot cached = cachedSnapshot(cacheKey);
        log.event("-", "LIST-SNAPSHOT-REQUEST", "mode=" + wantedMode
                + " providerLanguage=" + (wantedLanguage.isBlank() ? "all" : wantedLanguage)
                + " base=" + base.size()
                + " groupSelected=" + !wantedGroup.isEmpty()
                + " queryLength=" + query.length()
                + " cacheHit=" + (cached != null));
        if (cached != null) {
            applySnapshot(generation, wantedMode, wantedLanguage, wantedGroup,
                    cached, 0, true);
            return;
        }

        Future<?> previous = activeFilterTask;
        if (previous != null) previous.cancel(true);
        final int revision = catalogRevision;
        activeFilterTask = filterWorker.submit(() -> {
            long started = SystemClock.elapsedRealtime();
            ProviderCatalog.Snapshot snapshot = ProviderCatalog.build(
                    base, type(wantedMode), wantedLanguage, wantedGroup, query);
            if (Thread.currentThread().isInterrupted() || revision != catalogRevision) return;
            long duration = SystemClock.elapsedRealtime() - started;
            cacheSnapshot(cacheKey, snapshot);
            main.post(() -> applySnapshot(generation, wantedMode, wantedLanguage,
                    wantedGroup, snapshot, duration, false));
        });
    }

    private void applySnapshot(int generation, Mode wantedMode,
                               String wantedLanguage, String wantedGroup,
                               ProviderCatalog.Snapshot snapshot, long duration,
                               boolean cacheHit) {
        if (generation != filterGeneration.get()
                || wantedMode != mode
                || !TextUtils.equals(wantedLanguage, selectedLanguage)
                || !TextUtils.equals(wantedGroup, selectedGroup)) return;

        boolean changed = false;
        if (!TextUtils.equals(selectedLanguage, snapshot.selectedLanguage)) {
            selectedLanguage = snapshot.selectedLanguage;
            changed = true;
        }
        if (!TextUtils.equals(selectedGroup, snapshot.selectedGroup)) {
            selectedGroup = snapshot.selectedGroup;
            changed = true;
        }
        if (changed) saveViewState();

        boolean languagesChanged = !sameLanguages(availableLanguages, snapshot.languages);
        boolean groupsChanged = !availableGroups.equals(snapshot.groups);
        availableLanguages = snapshot.languages;
        availableGroups = snapshot.groups;
        if (languagesChanged) renderLanguageButtons(snapshot.languages);
        if (groupsChanged) renderGroupButtons(snapshot.groups);
        adapter.submit(snapshot.rows);
        count.setText(Integer.toString(snapshot.rows.size()));
        updateSelectionStyles();
        list.setSelection(0);

        if (!busy) {
            String groupLabel = selectedGroup.isEmpty() ? allCategoryLabel() : selectedGroup;
            footerStatus.setText(repository.sourceName() + " · " + label(wantedMode)
                    + " · " + selectedLanguageLabel()
                    + " · " + groupLabel + " · " + snapshot.rows.size() + " Treffer");
        }
        log.event("-", "LIST-SNAPSHOT-READY", "rows=" + snapshot.rows.size()
                + " languages=" + snapshot.languages.size()
                + " groups=" + snapshot.groups.size()
                + " durationMs=" + duration
                + " cacheHit=" + cacheHit
                + " providerLanguage="
                + (selectedLanguage.isBlank() ? "all" : selectedLanguage)
                + " groupSelected=" + !selectedGroup.isEmpty());
        list.post(() -> log.event("-", "LIST-FIRST-FRAME",
                "visibleChildren=" + list.getChildCount()
                        + " cacheHit=" + cacheHit));
    }

    private static boolean sameLanguages(List<ProviderLanguage.Facet> left,
                                         List<ProviderLanguage.Facet> right) {
        if (left == right) return true;
        if (left == null || right == null || left.size() != right.size()) return false;
        for (int index = 0; index < left.size(); index++) {
            ProviderLanguage.Facet first = left.get(index);
            ProviderLanguage.Facet second = right.get(index);
            String firstId = first == null ? "" : first.id;
            String secondId = second == null ? "" : second.id;
            if (!TextUtils.equals(firstId, secondId)) return false;
        }
        return true;
    }

    private static Channel.Type type(Mode mode) {'''
        content, filter_count = filter_pattern.subn(filter_replacement, content, count=1)
        if filter_count != 1:
            raise RuntimeError("RC6.3 filter pipeline anchor missing")

        destroy_anchor = '''        watchdog.stop();
        worker.shutdownNow();
        super.onDestroy();
'''
        destroy_replacement = '''        watchdog.stop();
        worker.shutdownNow();
        filterWorker.shutdownNow();
        if (adapter != null) adapter.close();
        super.onDestroy();
'''
        if content.count(destroy_anchor) != 1:
            raise RuntimeError("RC6.3 shutdown anchor missing")
        content = content.replace(destroy_anchor, destroy_replacement, 1)
        main_activity.write_text(content, encoding="utf-8")

        final_player = player.read_text(encoding="utf-8")
        final_main = main_activity.read_text(encoding="utf-8")
        required = {
            "clean_transition": "postOnAnimation" in final_player,
            "overlay_hidden_before_entry": "applyPictureInPictureUi(true);" in final_player,
            "controller_hidden": "playerView.setUseController(!active);" in final_player,
            "overlay_gone": "topOverlay.setVisibility(active ? View.GONE : View.VISIBLE);" in final_player,
            "type_index": "FAST-CATALOG-INDEX-READY" in final_main,
            "snapshot_cache": "cacheHit=" in final_main,
            "prewarm": "TAB-PREWARM-READY" in final_main,
            "latest_only_filter": "activeFilterTask" in final_main,
            "fast_search_debounce": "postDelayed(pendingFilter, 90)" in final_main,
            "version": "13.2.0-rc6.3-fast-tabs" in build.read_text(encoding="utf-8"),
            "label": "Project Lumen RC6.3" in strings.read_text(encoding="utf-8"),
        }
        missing = [name for name, ok in required.items() if not ok]
        if missing:
            raise RuntimeError(f"RC6.3 finishing verification failed: {missing}")
        print("RC6.3 fast-tabs finishing patch passed:", ", ".join(required))

    atexit.register(finish_rc63)
