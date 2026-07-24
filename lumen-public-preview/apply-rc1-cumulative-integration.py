#!/usr/bin/env python3
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

root = Path(sys.argv[1] if len(sys.argv) > 1 else "project-lumen-preview")
pkg = root / "app/src/main/java/com/projectlumen/publicpreview"
main = pkg / "MainActivity.java"
manifest = root / "app/src/main/AndroidManifest.xml"
gradle = root / "app/build.gradle"
support = Path(__file__).resolve().parent / "rc1-src"

required = [main, manifest, gradle, support / "SecureBlobStore.java", support / "PlaybackStore.java",
            support / "PlaybackActivity.java", support / "MediaDetailActivity.java",
            support / "SeriesSelectionStore.java", support / "SeriesActivity.java",
            support / "LicenseFoundation.java", support / "ActivationActivity.java",
            support / "ParentalPolicy.java"]
for path in required:
    if not path.exists():
        raise SystemExit(f"missing RC1 input: {path}")

pkg.mkdir(parents=True, exist_ok=True)
for source in support.glob("*.java"):
    shutil.copy2(source, pkg / source.name)

# Manifest activities.
text = manifest.read_text(encoding="utf-8")
activities = [
    ("ActivationActivity", "Aktivierung &amp; Softwarelizenz"),
    ("MediaDetailActivity", "Filmdetails"),
    ("SeriesActivity", "Seriendetails"),
    ("PlaybackActivity", "Wiedergabe"),
]
insert = ""
for activity, label in activities:
    if f'.{activity}' not in text:
        insert += f'        <activity android:name=".{activity}" android:exported="false" android:label="{label}" />\n'
if insert:
    marker = '        <activity\n            android:name=".MainActivity"'
    if marker not in text:
        raise SystemExit("MainActivity manifest marker missing")
    text = text.replace(marker, insert + marker, 1)
manifest.write_text(text, encoding="utf-8")

# Version.
g = gradle.read_text(encoding="utf-8")
g = re.sub(r"versionCode\s+\d+", "versionCode 134200", g, count=1)
g = re.sub(r"versionName\s+'[^']+'", "versionName '13.1.32-rc1-r2-r4-r5-foundation-r6-readiness'", g, count=1)
gradle.write_text(g, encoding="utf-8")

s = main.read_text(encoding="utf-8")
s = s.replace('text("v13.1.29"', 'text("v13.1.32 RC1"')
s = s.replace('text("v13.1.28"', 'text("v13.1.32 RC1"')

if "loadedProfileId" not in s:
    marker = '    private LanguageHub epgLanguageHub = LanguageHub.ALL;\n'
    if marker not in s:
        raise SystemExit("profile field marker missing")
    s = s.replace(marker, marker + '    private String loadedProfileId = "";\n', 1)

s = s.replace(
    'pageSubtitle.setText(sourceLabel + " · " + display.size() + " Einträge bereit");',
    'pageSubtitle.setText(ProfileStore.activeName(this) + " · " + sourceLabel + " · " + display.size() + " Einträge bereit");')

start_old = '''        sectionTitle("Inhalte nach Sprache & Land", "Live-TV, Filme und Serien bleiben gemeinsam nach Herkunft sortiert");
        languageHubRow(home);

        premiumMediaRow("Jetzt live", "Direkt starten", home.livePreview);'''
start_new = '''        List<Channel> continueWatching = continueWatchingChannels(display);
        premiumMediaRow("Weiterschauen", "Fortsetzen im Profil " + ProfileStore.activeName(this), continueWatching);

        sectionTitle("Inhalte nach Sprache & Land", "Live-TV, Filme und Serien bleiben gemeinsam nach Herkunft sortiert");
        languageHubRow(home);

        premiumMediaRow("Jetzt live", "Direkt starten", home.livePreview);'''
if "continueWatchingChannels(display)" not in s:
    if start_old not in s:
        raise SystemExit("start page marker missing")
    s = s.replace(start_old, start_new, 1)

# Route all catalogue entries through media-specific flows; local-file playback remains unchanged.
replacements = {
    'card.setOnClickListener(v -> play(channel));': 'card.setOnClickListener(v -> openPremiumMedia(channel));',
    'list.setOnItemClickListener((parent, view, position, id) -> play(channelPage.items.get(position)));':
        'list.setOnItemClickListener((parent, view, position, id) -> openPremiumMedia(channelPage.items.get(position)));',
    'list.setOnItemClickListener((parent, view, position, id) -> play(pageItems.get(position)));':
        'list.setOnItemClickListener((parent, view, position, id) -> openPremiumMedia(pageItems.get(position)));',
    'list.setOnItemClickListener((parent, view, position, id) -> play(result.items.get(position)));':
        'list.setOnItemClickListener((parent, view, position, id) -> openPremiumMedia(result.items.get(position)));',
    'list.setOnItemClickListener((parent, view, position, id) -> play(items.get(position)));':
        'list.setOnItemClickListener((parent, view, position, id) -> openPremiumMedia(items.get(position)));',
}
for old, new in replacements.items():
    s = s.replace(old, new)

s = s.replace('''            globalSearch = search.getText().toString().trim();
            searchPage = 0;
            render();''', '''            globalSearch = search.getText().toString().trim();
            saveSearchHistory(globalSearch);
            searchPage = 0;
            render();''')
s = s.replace('''        if (globalSearch.isBlank()) {
            cardInfo("Suchbegriff eingeben", "Die Suche läuft vollständig lokal im verschlüsselten Katalog. Es wird kein Suchtext an einen Server übertragen.");
            return;
        }''', '''        if (globalSearch.isBlank()) {
            cardInfo("Suchbegriff eingeben", "Die Suche läuft vollständig lokal im Katalog. Es wird kein Suchtext an einen Server übertragen.");
            addRecentSearches();
            return;
        }''')

# Profile-separated favorites; works whether R4 already transformed these lines or not.
s = s.replace('Set<String> stored = getPreferences(MODE_PRIVATE).getStringSet("favorite_ids_v1", Collections.emptySet());',
              'Set<String> stored = getSharedPreferences(ProfileStore.favoriteNamespace(this), MODE_PRIVATE).getStringSet("favorite_ids_v1", Collections.emptySet());')
s = s.replace('getPreferences(MODE_PRIVATE).edit().putStringSet("favorite_ids_v1", new HashSet<>(favoriteIds)).apply();',
              'getSharedPreferences(ProfileStore.favoriteNamespace(this), MODE_PRIVATE).edit().putStringSet("favorite_ids_v1", new HashSet<>(favoriteIds)).apply();')

old_snapshot = '''    private List<Channel> displayChannelsSnapshot() {
        return importPreviewActive ? previewSnapshot : activeSnapshot;
    }'''
new_snapshot = '''    private List<Channel> displayChannelsSnapshot() {
        List<Channel> source = importPreviewActive ? previewSnapshot : activeSnapshot;
        return ParentalPolicy.filter(this, source);
    }'''
if old_snapshot in s:
    s = s.replace(old_snapshot, new_snapshot, 1)

if 'cardAction("Aktivierung & Softwarelizenz"' not in s:
    marker = '        cardAction("Diagnose öffnen", "Letzten Import- oder Playerstatus anzeigen", this::openDiagnostics);'
    addition = '''        cardAction("Aktivierung & Softwarelizenz", "Gerätecode, Lizenzstatus und Kaufwiederherstellung", () -> startActivity(new Intent(this, ActivationActivity.class)));
''' + marker
    if marker not in s:
        raise SystemExit("settings marker missing")
    s = s.replace(marker, addition, 1)
if 'Wiedergabeverlauf löschen' not in s:
    s = s.replace('cardInfo("Favoriten", favoriteIds.size() + " lokal gespeicherte Favoriten");',
                  'cardInfo("Favoriten & Verlauf", favoriteIds.size() + " Favoriten · " + new PlaybackStore(this).recent(500).size() + " Wiedergabeeinträge im aktiven Profil");\n        cardAction("Wiedergabeverlauf löschen", "Nur den Verlauf und Weiterschauen-Stand des aktiven Profils entfernen", this::confirmClearPlaybackHistory);')

if 'Dieser Inhalt ist im Kinderprofil gesperrt.' not in s[s.find('private void play(Channel channel)'):s.find('private void play(Channel channel)') + 700]:
    s = s.replace('''    private void play(Channel channel) {
        if (channel == null || channel.url.isBlank()) {''', '''    private void play(Channel channel) {
        if (channel != null && !ParentalPolicy.isAllowed(this, channel)) {
            Toast.makeText(this, "Dieser Inhalt ist im Kinderprofil gesperrt.", Toast.LENGTH_LONG).show();
            return;
        }
        if (channel == null || channel.url.isBlank()) {''', 1)

if "private void openPremiumMedia(Channel channel)" not in s:
    marker = '    private void play(Channel channel) {'
    if marker not in s:
        raise SystemExit("play marker missing")
    methods = r'''
    private void openPremiumMedia(Channel channel) {
        if (channel == null) return;
        if (!ParentalPolicy.isAllowed(this, channel)) {
            Toast.makeText(this, "Dieser Inhalt ist im Kinderprofil gesperrt.", Toast.LENGTH_LONG).show();
            return;
        }
        if (channel.section == MediaSection.LIVE) { play(channel); return; }
        if (channel.section == MediaSection.VOD) {
            Intent intent = new Intent(this, MediaDetailActivity.class);
            intent.putExtra(MediaDetailActivity.EXTRA_TITLE, channel.name);
            intent.putExtra(MediaDetailActivity.EXTRA_GROUP, channel.group);
            intent.putExtra(MediaDetailActivity.EXTRA_URL, channel.url);
            intent.putExtra(MediaDetailActivity.EXTRA_LOGO, channel.logo);
            intent.putExtra(MediaDetailActivity.EXTRA_LANGUAGE, languageLabel(channel.hub));
            intent.putExtra(MediaDetailActivity.EXTRA_MEDIA_TYPE, "VOD");
            startActivity(intent);
            return;
        }
        try {
            String key = seriesKey(channel);
            List<SeriesSelectionStore.Item> episodes = new ArrayList<>();
            for (Channel candidate : displayChannelsSnapshot()) {
                if (candidate.section != MediaSection.SERIES || !seriesKey(candidate).equals(key)) continue;
                episodes.add(new SeriesSelectionStore.Item(candidate.name, candidate.group, candidate.url,
                        candidate.logo, languageLabel(candidate.hub)));
                if (episodes.size() >= 2_000) break;
            }
            if (episodes.isEmpty()) episodes.add(new SeriesSelectionStore.Item(channel.name, channel.group,
                    channel.url, channel.logo, languageLabel(channel.hub)));
            String token = SeriesSelectionStore.save(this, seriesTitle(channel), episodes);
            Intent intent = new Intent(this, SeriesActivity.class);
            intent.putExtra(SeriesActivity.EXTRA_TOKEN, token);
            startActivity(intent);
        } catch (Exception failure) {
            Toast.makeText(this, "Serienansicht konnte nicht geöffnet werden: " + safeMessage(failure), Toast.LENGTH_LONG).show();
        }
    }

    private static String seriesKey(Channel channel) {
        if (channel == null) return "";
        String group = channel.group == null ? "" : channel.group.trim();
        String normalized = group.toLowerCase(Locale.ROOT);
        String source = normalized.isBlank() || normalized.equals("series") || normalized.equals("serien")
                || normalized.equals("tv series") || normalized.equals("weitere") || normalized.contains("all series")
                ? channel.name : group;
        return source.toLowerCase(Locale.ROOT)
                .replaceAll("(?i)\\bS(?:eason)?\\s*0*\\d{1,3}\\s*[-._ ]*E(?:pisode)?\\s*0*\\d{1,4}\\b", " ")
                .replaceAll("(?i)\\bStaffel\\s*0*\\d{1,3}\\s*[-._ ]*(?:Folge|Episode)\\s*0*\\d{1,4}\\b", " ")
                .replaceAll("(?i)\\b(?:Season|Staffel|Episode|Folge)\\s*0*\\d{1,4}\\b", " ")
                .replaceAll("[-._|]+", " ").replaceAll("\\s+", " ").trim();
    }

    private static String seriesTitle(Channel channel) {
        String key = seriesKey(channel);
        if (!key.isBlank()) {
            StringBuilder title = new StringBuilder();
            for (String part : key.split(" ")) {
                if (part.isBlank()) continue;
                if (title.length() > 0) title.append(' ');
                title.append(Character.toUpperCase(part.charAt(0))).append(part.substring(1));
            }
            if (title.length() > 0) return title.toString();
        }
        return channel == null ? "Serie" : channel.name;
    }

    private List<Channel> continueWatchingChannels(List<Channel> source) {
        List<PlaybackStore.Entry> entries = new PlaybackStore(this).continueWatching(16);
        if (entries.isEmpty() || source == null || source.isEmpty()) return Collections.emptyList();
        Map<String, Channel> byKey = new java.util.LinkedHashMap<>();
        for (Channel channel : source) if (channel.section != MediaSection.LIVE)
            byKey.putIfAbsent(PlaybackStore.keyForUrl(channel.url), channel);
        List<Channel> result = new ArrayList<>();
        for (PlaybackStore.Entry entry : entries) {
            Channel channel = byKey.get(entry.key);
            if (channel != null && ParentalPolicy.isAllowed(this, channel)) result.add(channel);
        }
        return result;
    }

    private void saveSearchHistory(String query) {
        if (query == null || query.isBlank()) return;
        android.content.SharedPreferences prefs = getSharedPreferences(ProfileStore.historyNamespace(this), MODE_PRIVATE);
        Set<String> stored = prefs.getStringSet("search_history_v1", Collections.emptySet());
        java.util.LinkedHashSet<String> updated = new java.util.LinkedHashSet<>();
        updated.add(query.trim());
        if (stored != null) for (String value : stored) {
            if (updated.size() >= 12) break;
            if (value != null && !value.isBlank()) updated.add(value);
        }
        prefs.edit().putStringSet("search_history_v1", updated).apply();
    }

    private void addRecentSearches() {
        Set<String> stored = getSharedPreferences(ProfileStore.historyNamespace(this), MODE_PRIVATE)
                .getStringSet("search_history_v1", Collections.emptySet());
        if (stored == null || stored.isEmpty()) return;
        sectionTitle("Letzte Suchen", "Nur im aktiven Profil gespeichert");
        LinearLayout row = new LinearLayout(this); row.setOrientation(LinearLayout.HORIZONTAL);
        int count = 0;
        for (String value : stored) {
            if (value == null || value.isBlank() || count++ >= 8) continue;
            Button chip = button(value, false);
            chip.setOnClickListener(v -> { globalSearch = value; searchPage = 0; render(); });
            LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT,
                    dp(television ? 50 : 42));
            params.setMargins(row.getChildCount() == 0 ? 0 : dp(7), 0, 0, 0); row.addView(chip, params);
        }
        HorizontalScrollView scroll = new HorizontalScrollView(this); scroll.setHorizontalScrollBarEnabled(false);
        scroll.addView(row, new HorizontalScrollView.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT,
                ViewGroup.LayoutParams.WRAP_CONTENT)); content.addView(scroll, marginBottom(10));
    }

    private void confirmClearPlaybackHistory() {
        new AlertDialog.Builder(this).setTitle("Wiedergabeverlauf löschen?")
                .setMessage("Weiterschauen und zuletzt gesehen werden nur für das aktive Profil zurückgesetzt.")
                .setPositiveButton("Löschen", (dialog, which) -> { new PlaybackStore(this).clear(); render(); })
                .setNegativeButton("Abbrechen", null).show();
    }

    private void refreshProfileStateIfNeeded() {
        String active = ProfileStore.activeId(this);
        if (active.equals(loadedProfileId)) return;
        loadedProfileId = active; loadFavoriteIds(); globalSearch = ""; ParentalPolicy.invalidate();
    }

'''
    s = s.replace(marker, methods + marker, 1)

s = s.replace('''    private void render() {
        if (content == null) return;''', '''    private void render() {
        if (content == null) return;
        refreshProfileStateIfNeeded();''', 1)

# R4 already defines onResume; enrich it. Fall back to creating one only when absent.
if "refreshProfileStateIfNeeded();" not in s[s.find("protected void onResume"):s.find("protected void onResume") + 500]:
    match = re.search(r'(protected\s+void\s+onResume\s*\(\s*\)\s*\{\s*\n\s*super\.onResume\(\);)', s)
    if match:
        addition = match.group(1) + '\n        String beforeProfile = loadedProfileId;\n        refreshProfileStateIfNeeded();\n        if (content != null && !ProfileStore.activeId(this).equals(beforeProfile)) render();'
        s = s[:match.start()] + addition + s[match.end():]
    else:
        marker = '    private void buildMainUi() {'
        resume = '''    @Override
    protected void onResume() {
        super.onResume();
        String beforeProfile = loadedProfileId;
        refreshProfileStateIfNeeded();
        if (content != null && !ProfileStore.activeId(this).equals(beforeProfile)) render();
    }

'''
        if marker not in s:
            raise SystemExit("onResume insertion marker missing")
        s = s.replace(marker, resume + marker, 1)

main.write_text(s, encoding="utf-8")

checks = {
    "version": 'text("v13.1.32 RC1"' in s,
    "detail": "MediaDetailActivity.class" in s,
    "series": "SeriesSelectionStore.save" in s,
    "continue": "continueWatchingChannels" in s,
    "profiles": "ProfileStore.favoriteNamespace" in s,
    "child": "ParentalPolicy.filter" in s,
    "activation": "ActivationActivity.class" in s,
    "versionCode": "versionCode 134200" in gradle.read_text(encoding="utf-8"),
}
missing = [name for name, passed in checks.items() if not passed]
if missing:
    raise SystemExit("RC1 integration checks failed: " + ", ".join(missing))
print("RC1 cumulative integration applied: " + ", ".join(checks))
