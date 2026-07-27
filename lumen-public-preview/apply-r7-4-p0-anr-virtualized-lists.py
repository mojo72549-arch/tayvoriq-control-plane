#!/usr/bin/env python3
from __future__ import annotations
import re, sys
from pathlib import Path

root=Path(sys.argv[1])
main=root/'app/src/main/java/com/projectlumen/publicpreview/MainActivity.java'
gradle=root/'app/build.gradle'

def method_span(text,name):
 p=re.compile(rf'(?m)^    (?:public|private|protected)\s+(?:static\s+)?[\w<>\[\], ?.]+\s+{re.escape(name)}\s*\([^;{{}}]*\)\s*(?:throws\s+[\w., ]+)?\s*\{{')
 m=p.search(text)
 if not m: raise SystemExit('method not found '+name)
 op=text.find('{',m.start(),m.end()); depth=0; i=op; state='code'
 while i<len(text):
  c=text[i]; n=text[i+1] if i+1<len(text) else ''
  if state=='code':
   if c=='"': state='string'
   elif c=="'": state='char'
   elif c=='/' and n=='/': state='line'; i+=1
   elif c=='/' and n=='*': state='block'; i+=1
   elif c=='{': depth+=1
   elif c=='}':
    depth-=1
    if depth==0:return m.start(),i+1
  elif state=='string':
   if c=='\\': i+=1
   elif c=='"': state='code'
  elif state=='char':
   if c=='\\': i+=1
   elif c=="'": state='code'
  elif state=='line':
   if c=='\n': state='code'
  elif state=='block':
   if c=='*' and n=='/': state='code';i+=1
  i+=1
 raise SystemExit('unterminated '+name)

def replace_method(text,name,repl):
 a,b=method_span(text,name); return text[:a]+repl.strip('\n')+text[b:]

g=gradle.read_text()
g=re.sub(r'versionCode\s+\d+','versionCode 134700',g,count=1)
g=re.sub(r"versionName\s+'[^']+'","versionName '13.1.37-p0-anr-virtualized-lists-pilot'",g,count=1)
gradle.write_text(g)

s=main.read_text()
s=s.replace('private static final int LIVE_PAGE_SIZE = 200;','private static final int LIVE_PAGE_SIZE = 60;')
s=s.replace('private static final int SEARCH_PAGE_SIZE = 200;','private static final int SEARCH_PAGE_SIZE = 60;')
if 'import java.util.concurrent.atomic.AtomicLong;' not in s:
 s=s.replace('import java.util.concurrent.atomic.AtomicBoolean;','import java.util.concurrent.atomic.AtomicBoolean;\nimport java.util.concurrent.atomic.AtomicLong;',1)
marker='    private String loadedProfileId = "";\n'
if 'libraryUiWorker' not in s:
 if marker not in s: raise SystemExit('field marker')
 s=s.replace(marker,marker+'''    private final ExecutorService libraryUiWorker = Executors.newSingleThreadExecutor();
    private final AtomicLong libraryUiGeneration = new AtomicLong();
    private volatile MediaUiResult preparedMediaUi;
    private volatile String scheduledMediaUiKey = "";
    private volatile long lastMediaNavigationAtMs;
''',1)
s=s.replace('text("13.1.36"','text("13.1.37"')
s=s.replace('Project Lumen 13.1.36 · P0 Bibliotheksschutz','Project Lumen 13.1.37 · P0 Schnelle Listen')

s=replace_method(s,'hasDisplayChannels',r'''
    private boolean hasDisplayChannels() {
        List<Channel> source = importPreviewActive ? previewSnapshot : activeSnapshot;
        return source != null && !source.isEmpty();
    }
''')
s=replace_method(s,'openMedia',r'''
    private void openMedia(MediaSection section) {
        if (!acceptMediaNavigation()) return;
        mediaSection = section;
        languageHub = LanguageHub.ALL;
        filter = "";
        livePage = 0;
        preparedMediaUi = null;
        scheduledMediaUiKey = "";
        screen = Screen.MEDIA;
        render();
    }
''')
s=replace_method(s,'openLanguageHub',r'''
    private void openLanguageHub(LanguageHub hub) {
        if (!acceptMediaNavigation()) return;
        mediaSection = MediaSection.LIVE;
        languageHub = hub;
        filter = "";
        livePage = 0;
        preparedMediaUi = null;
        scheduledMediaUiKey = "";
        screen = Screen.MEDIA;
        render();
    }
''')

s=replace_method(s,'renderMedia',r'''
    private void renderMedia() {
        List<Channel> source = rawChannelsSnapshot();
        pageTitle.setText(mediaSectionTitle());
        if (source.isEmpty()) {
            pageSubtitle.setText("Keine Liste geladen");
            cardAction("Liste hinzufügen", "Eine rechtmäßig nutzbare Quelle einrichten.", () -> { screen = Screen.SOURCE; render(); });
            return;
        }

        String key = mediaUiKey(source);
        MediaUiResult result = preparedMediaUi;
        if (result == null || !result.key.equals(key)) {
            pageSubtitle.setText("Senderliste wird vorbereitet");
            cardInfo("Einen Moment", "Die erste Seite wird speicherschonend aufgebaut.");
            scheduleMediaUi(source, key);
            return;
        }
        renderResolvedMedia(result);
    }
''')

insert_marker='    private void renderEpg() {'
helpers=r'''
    private List<Channel> rawChannelsSnapshot() {
        List<Channel> source = importPreviewActive ? previewSnapshot : activeSnapshot;
        return source == null ? Collections.emptyList() : source;
    }

    private boolean acceptMediaNavigation() {
        long now = android.os.SystemClock.elapsedRealtime();
        if (now - lastMediaNavigationAtMs < 350L) {
            appendDiagnosticLog("UI", "Mehrfaches Öffnen der Liste ignoriert", "Code=UI-LIST-DEBOUNCED", null);
            return false;
        }
        lastMediaNavigationAtMs = now;
        return true;
    }

    private String mediaUiKey(List<Channel> source) {
        return System.identityHashCode(source) + ":" + source.size() + ":"
                + ProfileStore.activeId(this) + ":" + mediaSection + ":" + languageHub + ":"
                + (filter == null ? "" : filter.trim().toLowerCase(Locale.ROOT)) + ":" + livePage;
    }

    private void invalidateMediaUi() {
        preparedMediaUi = null;
        scheduledMediaUiKey = "";
        libraryUiGeneration.incrementAndGet();
    }

    private void scheduleMediaUi(List<Channel> source, String key) {
        if (key.equals(scheduledMediaUiKey)) return;
        scheduledMediaUiKey = key;
        final long request = libraryUiGeneration.incrementAndGet();
        final MediaSection requestedSection = mediaSection;
        final LanguageHub requestedHub = languageHub;
        final String requestedFilter = filter == null ? "" : filter.trim().toLowerCase(Locale.ROOT);
        final int requestedPage = Math.max(0, livePage);
        final boolean childMode = ProfileStore.isChildMode(this);
        final long startedNs = System.nanoTime();

        libraryUiWorker.execute(() -> {
            MediaUiResult built = buildMediaUi(source, key, request, requestedSection, requestedHub,
                    requestedFilter, requestedPage, childMode, startedNs);
            if (built == null) return;
            mainHandler.post(() -> {
                if (request != libraryUiGeneration.get() || screen != Screen.MEDIA) return;
                preparedMediaUi = built;
                livePage = built.page.start / LIVE_PAGE_SIZE;
                appendDiagnosticLog("UI", "Senderliste seitenweise vorbereitet",
                        "Code=UI-LIST-PAGE-READY · Geprueft=" + built.scanned
                                + " · Treffer=" + built.page.total
                                + " · Seite=" + built.page.items.size()
                                + " · WorkerMs=" + built.workerMs, null);
                render();
            });
        });
    }

    private MediaUiResult buildMediaUi(List<Channel> source, String key, long request,
                                       MediaSection requestedSection, LanguageHub requestedHub,
                                       String requestedFilter, int requestedPage, boolean childMode,
                                       long startedNs) {
        int[] sectionCounts = new int[MediaSection.values().length];
        int[][] hubSectionCounts = new int[LanguageHub.values().length][MediaSection.values().length];
        int requestedStart = requestedPage * LIVE_PAGE_SIZE;
        List<Channel> items = new ArrayList<>(LIVE_PAGE_SIZE);
        List<Channel> tail = new ArrayList<>(LIVE_PAGE_SIZE);
        int total = 0;
        int scanned = 0;
        for (Channel channel : source) {
            if ((scanned++ & 1023) == 0 && request != libraryUiGeneration.get()) return null;
            if (channel == null) continue;
            if (childMode && !ParentalPolicy.isAllowed(this, channel)) continue;
            MediaSection section = channel.section;
            LanguageHub hub = channel.hub == LanguageHub.ALL ? LanguageHub.OTHER : channel.hub;
            sectionCounts[section.ordinal()]++;
            hubSectionCounts[hub.ordinal()][section.ordinal()]++;
            if (section != requestedSection) continue;
            if (requestedHub != LanguageHub.ALL && hub != requestedHub) continue;
            if (!requestedFilter.isBlank() && !channel.searchText.contains(requestedFilter)) continue;
            if (total >= requestedStart && items.size() < LIVE_PAGE_SIZE) items.add(channel);
            if (tail.size() == LIVE_PAGE_SIZE) tail.remove(0);
            tail.add(channel);
            total++;
        }
        int actualStart = requestedStart;
        if (actualStart >= total && total > 0) {
            int actualPage = Math.max(0, (total - 1) / LIVE_PAGE_SIZE);
            actualStart = actualPage * LIVE_PAGE_SIZE;
            int expected = total - actualStart;
            int from = Math.max(0, tail.size() - expected);
            items = new ArrayList<>(tail.subList(from, tail.size()));
        }
        long workerMs = (System.nanoTime() - startedNs) / 1_000_000L;
        return new MediaUiResult(key, new ChannelPage(Collections.unmodifiableList(items), total, actualStart),
                sectionCounts, hubSectionCounts, scanned, workerMs);
    }

    private void renderResolvedMedia(MediaUiResult result) {
        long renderStartedNs = System.nanoTime();
        mediaSectionFilterRowFast(result);
        languageFilterRowFast(result);
        ChannelPage channelPage = result.page;
        int from = channelPage.total == 0 ? 0 : channelPage.start + 1;
        int to = channelPage.start + channelPage.items.size();
        pageSubtitle.setText(from + "–" + to + " von " + channelPage.total + " passenden Einträgen");
        if (channelPage.total == 0) {
            cardInfo("Noch keine Inhalte", "Andere Sprache oder Quelle wählen.");
            cardAction("Liste verwalten", "Quelle prüfen oder eine andere Liste importieren", () -> { screen = Screen.SOURCE; render(); });
            return;
        }
        if (importPreviewActive) cardInfo("Import läuft weiter", "Die Liste ist bereits nutzbar. Die Speicherung läuft im Hintergrund.");
        EditText search = input("Sender, Film oder Serie", false);
        search.setText(filter);
        Button apply = button("Suchen", true);
        apply.setOnClickListener(v -> {
            filter = search.getText().toString().trim();
            livePage = 0;
            invalidateMediaUi();
            render();
        });
        LinearLayout searchRow = new LinearLayout(this);
        searchRow.setOrientation(LinearLayout.HORIZONTAL);
        searchRow.addView(search, new LinearLayout.LayoutParams(0, dp(television ? 56 : 48), 1f));
        LinearLayout.LayoutParams ap = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, dp(television ? 56 : 48));
        ap.setMargins(dp(7), 0, 0, 0);
        searchRow.addView(apply, ap);
        content.addView(searchRow, marginBottom(10));

        ListView list = new ListView(this);
        list.setDividerHeight(dp(5));
        list.setBackgroundColor(Color.TRANSPARENT);
        list.setNestedScrollingEnabled(true);
        ChannelAdapter adapter = new ChannelAdapter(this, channelPage.items);
        list.setAdapter(adapter);
        list.setOnItemClickListener((parent, view, position, id) -> openPremiumMedia(channelPage.items.get(position)));
        list.setOnItemLongClickListener((parent, view, position, id) -> {
            toggleFavorite(channelPage.items.get(position));
            invalidateMediaUi();
            render();
            return true;
        });
        content.addView(list, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(television ? 620 : 480)));
        addPager(livePage, channelPage.start, channelPage.items.size(), channelPage.total, value -> {
            livePage = value;
            invalidateMediaUi();
            render();
        });
        long renderMs = (System.nanoTime() - renderStartedNs) / 1_000_000L;
        appendDiagnosticLog("UI", "Senderlistenseite gerendert",
                "Code=UI-LIST-RENDER-OK · Elemente=" + channelPage.items.size() + " · MainThreadMs=" + renderMs, null);
    }

    private void mediaSectionFilterRowFast(MediaUiResult result) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        for (MediaSection section : MediaSection.values()) {
            String label = switch (section) { case LIVE -> "Live-TV"; case VOD -> "Filme"; case SERIES -> "Serien"; };
            int count = languageHub == LanguageHub.ALL
                    ? result.sectionCounts[section.ordinal()]
                    : result.hubSectionCounts[languageHub.ordinal()][section.ordinal()];
            Button chip = button(label + "  " + count, mediaSection == section);
            chip.setOnClickListener(v -> {
                mediaSection = section; livePage = 0; filter = ""; invalidateMediaUi(); render();
            });
            LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, dp(television ? 50 : 42));
            p.setMargins(row.getChildCount() == 0 ? 0 : dp(7), 0, 0, 0);
            row.addView(chip, p);
        }
        HorizontalScrollView scroll = new HorizontalScrollView(this);
        scroll.setHorizontalScrollBarEnabled(false);
        scroll.addView(row, new HorizontalScrollView.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        content.addView(scroll, marginBottom(8));
    }

    private void languageFilterRowFast(MediaUiResult result) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        LanguageHub[] hubs = { LanguageHub.ALL, LanguageHub.GERMAN, LanguageHub.TURKISH, LanguageHub.ENGLISH, LanguageHub.OTHER };
        String[] labels = { "🌍 Alle", "🇩🇪 Deutsch", "🇹🇷 Türkisch", "🇬🇧 Englisch", "🌍 Weitere" };
        for (int i = 0; i < hubs.length; i++) {
            LanguageHub hub = hubs[i];
            int count = hub == LanguageHub.ALL
                    ? result.sectionCounts[mediaSection.ordinal()]
                    : result.hubSectionCounts[hub.ordinal()][mediaSection.ordinal()];
            Button chip = button(labels[i] + "  " + count, languageHub == hub);
            chip.setOnClickListener(v -> { languageHub = hub; livePage = 0; invalidateMediaUi(); render(); });
            LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, dp(television ? 50 : 42));
            p.setMargins(row.getChildCount() == 0 ? 0 : dp(7), 0, 0, 0);
            row.addView(chip, p);
        }
        HorizontalScrollView scroll = new HorizontalScrollView(this);
        scroll.setHorizontalScrollBarEnabled(false);
        scroll.addView(row, new HorizontalScrollView.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        content.addView(scroll, marginBottom(12));
    }

'''
if insert_marker not in s: raise SystemExit('insert marker')
s=s.replace(insert_marker,helpers+insert_marker,1)

old='diagnosticOpenList.setOnClickListener(v -> { hideDiagnostics(); mediaSection = MediaSection.LIVE; filter = ""; livePage = 0; screen = Screen.MEDIA; render(); });'
new='''diagnosticOpenList.setOnClickListener(v -> {
            if (!acceptMediaNavigation()) return;
            diagnosticOpenList.setEnabled(false);
            hideDiagnostics();
            mediaSection = MediaSection.LIVE;
            languageHub = LanguageHub.ALL;
            filter = "";
            livePage = 0;
            preparedMediaUi = null;
            scheduledMediaUiKey = "";
            screen = Screen.MEDIA;
            mainHandler.post(() -> {
                diagnosticOpenList.setEnabled(true);
                render();
            });
        });'''
if old not in s: raise SystemExit('diag listener marker')
s=s.replace(old,new,1)

s=replace_method(s,'hideDiagnostics',r'''
    private void hideDiagnostics() {
        if (diagnosticPanel == null) return;
        diagnosticPanel.clearAnimation();
        diagnosticPanel.setVisibility(View.GONE);
        diagnosticFab.setVisibility(View.VISIBLE);
        diagnosticFab.bringToFront();
        root.postInvalidateOnAnimation();
    }
''')

s=s.replace('loadedProfileId = active; loadFavoriteIds(); globalSearch = ""; ParentalPolicy.invalidate();',
            'loadedProfileId = active; loadFavoriteIds(); globalSearch = ""; ParentalPolicy.invalidate(); invalidateMediaUi();',1)

old_destroy='''        epgWorker.shutdownNow();
        mainHandler.removeCallbacksAndMessages(null);'''
new_destroy='''        epgWorker.shutdownNow();
        libraryUiWorker.shutdownNow();
        mainHandler.removeCallbacksAndMessages(null);'''
if old_destroy not in s: raise SystemExit('destroy marker')
s=s.replace(old_destroy,new_destroy,1)

class_marker='    private static final class ChannelPage {'
class_def=r'''
    private static final class MediaUiResult {
        final String key;
        final ChannelPage page;
        final int[] sectionCounts;
        final int[][] hubSectionCounts;
        final int scanned;
        final long workerMs;

        MediaUiResult(String key, ChannelPage page, int[] sectionCounts, int[][] hubSectionCounts,
                      int scanned, long workerMs) {
            this.key = key;
            this.page = page;
            this.sectionCounts = sectionCounts;
            this.hubSectionCounts = hubSectionCounts;
            this.scanned = scanned;
            this.workerMs = workerMs;
        }
    }

'''
if class_marker not in s: raise SystemExit('class marker')
s=s.replace(class_marker,class_def+class_marker,1)

main.write_text(s)

for strings in root.glob('app/src/main/res/values*/strings.xml'):
 t=strings.read_text()
 if 'name="app_name"' in t:
  t=re.sub(r'(<string\s+name="app_name"[^>]*>).*?(</string>)',r'\1Project Lumen 13.1.37\2',t,count=1,flags=re.S)
  strings.write_text(t)

checks={
 'version':'versionCode 134700' in gradle.read_text(),
 'page60':'private static final int LIVE_PAGE_SIZE = 60;' in s,
 'worker':'libraryUiWorker.execute' in s,
 'off_main':'UI-LIST-PAGE-READY' in s,
 'render_limit':'UI-LIST-RENDER-OK' in s,
 'debounce':'UI-LIST-DEBOUNCED' in s,
 'generation':'libraryUiGeneration' in s,
 'p0_store':'LibraryGenerationStore.active(this)' in s,
 'dns':'IMPORT-DNS' in s,
}
missing=[k for k,v in checks.items() if not v]
if missing: raise SystemExit('13.1.37 checks failed: '+','.join(missing))
print('13.1.37 ANR integration applied: '+', '.join(checks))
