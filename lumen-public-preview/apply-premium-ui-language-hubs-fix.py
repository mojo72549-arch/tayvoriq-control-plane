#!/usr/bin/env python3
from __future__ import annotations
import pathlib
import sys


def once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def block(text: str, start: str, end: str, replacement: str, label: str) -> str:
    a = text.find(start)
    if a < 0:
        raise SystemExit(f"{label}: start not found")
    b = text.find(end, a)
    if b < 0:
        raise SystemExit(f"{label}: end not found")
    return text[:a] + replacement + text[b:]


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: apply-premium-ui-language-hubs-fix.py <project-root>")

    root = pathlib.Path(sys.argv[1])
    java = root / "app/src/main/java/com/projectlumen/publicpreview/MainActivity.java"
    gradle = root / "app/build.gradle"
    strings = root / "app/src/main/res/values/strings.xml"
    readme = root / "README.md"
    text = java.read_text(encoding="utf-8")

    text = once(text, "import android.widget.FrameLayout;\n", "import android.widget.FrameLayout;\nimport android.widget.HorizontalScrollView;\n", "HorizontalScrollView import")

    text = once(text,
        "    private static final int BG = 0xFF07111E;\n"
        "    private static final int SURFACE = 0xFF102338;\n"
        "    private static final int SURFACE_ALT = 0xFF0D1D30;\n"
        "    private static final int PRIMARY = 0xFF5EEAD4;\n"
        "    private static final int TEXT = 0xFFF1F7FC;\n"
        "    private static final int MUTED = 0xFF91A8BB;\n",
        "    private static final int BG = 0xFF05070B;\n"
        "    private static final int SURFACE = 0xFF11151D;\n"
        "    private static final int SURFACE_ALT = 0xFF181E28;\n"
        "    private static final int PRIMARY = 0xFF6AE4FF;\n"
        "    private static final int ACCENT = 0xFF7C5CFC;\n"
        "    private static final int TEXT = 0xFFF7F9FC;\n"
        "    private static final int MUTED = 0xFFA7B0BE;\n"
        "    private static final int BORDER = 0xFF2A3342;\n",
        "premium palette")

    text = once(text,
        "    private int livePage;\n    private MediaSection mediaSection = MediaSection.LIVE;\n\n"
        "    private enum Screen { START, MEDIA, EPG, SOURCE, SETTINGS }\n"
        "    private enum MediaSection { LIVE, VOD, SERIES }\n",
        "    private int livePage;\n    private MediaSection mediaSection = MediaSection.LIVE;\n"
        "    private LanguageHub languageHub = LanguageHub.ALL;\n\n"
        "    private enum Screen { START, MEDIA, EPG, SOURCE, SETTINGS }\n"
        "    private enum MediaSection { LIVE, VOD, SERIES }\n"
        "    private enum LanguageHub { ALL, GERMAN, TURKISH, ENGLISH, OTHER }\n",
        "language hub state")

    text = once(text,
        "        brand.addView(text(\"LUMEN FLOW\", television ? 32 : 25, TEXT, true));\n"
        "        brand.addView(text(\"Public Diagnostics Preview\", television ? 15 : 12, MUTED, false));\n",
        "        brand.addView(text(\"PROJECT LUMEN\", television ? 32 : 25, TEXT, true));\n"
        "        brand.addView(text(\"Premium Media Player · lokal & privat\", television ? 15 : 12, MUTED, false));\n",
        "premium brand")

    text = text.replace('text("v13.1.23"', 'text("v13.1.24"')

    old_nav_build = '''        nav = new LinearLayout(this);
        nav.setOrientation(LinearLayout.HORIZONTAL);
        nav.setPadding(0, dp(10), 0, dp(10));
        page.addView(nav, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        addNav("Start", Screen.START);
        addNav(television ? "Einstellungen" : "Einst.", Screen.SETTINGS);
'''
    new_nav_build = '''        HorizontalScrollView navScroll = new HorizontalScrollView(this);
        navScroll.setHorizontalScrollBarEnabled(false);
        navScroll.setFillViewport(false);
        nav = new LinearLayout(this);
        nav.setOrientation(LinearLayout.HORIZONTAL);
        nav.setPadding(0, dp(10), dp(10), dp(10));
        navScroll.addView(nav, new HorizontalScrollView.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        page.addView(navScroll, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
'''
    text = once(text, old_nav_build, new_nav_build, "scrollable navigation")

    nav_methods = r'''    private void rebuildNav() {
        nav.removeAllViews();
        addNavAction("Start", "start", () -> { screen = Screen.START; render(); });
        if (hasDisplayChannels()) {
            addNavAction("Live-TV", "live", () -> openMedia(MediaSection.LIVE));
            addNavAction("Filme", "vod", () -> openMedia(MediaSection.VOD));
            addNavAction("Serien", "series", () -> openMedia(MediaSection.SERIES));
        }
        addNavAction(television ? "Einstellungen" : "Einst.", "settings", () -> { screen = Screen.SETTINGS; render(); });
    }

    private void addNavAction(String label, String key, Runnable action) {
        Button button = button(label, false);
        boolean selected = currentNavKey().equals(key);
        button.setTextColor(selected ? BG : TEXT);
        button.setBackground(roundRect(selected ? PRIMARY : SURFACE_ALT, 18));
        button.setTag(key);
        button.setOnClickListener(v -> action.run());
        int width = television ? 168 : Math.max(88, label.length() * 12 + 34);
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(dp(width), dp(television ? 54 : 44));
        p.setMargins(nav.getChildCount() == 0 ? 0 : dp(7), 0, 0, 0);
        nav.addView(button, p);
    }

    private String currentNavKey() {
        if (screen == Screen.SETTINGS) return "settings";
        if (screen == Screen.MEDIA) {
            return switch (mediaSection) {
                case LIVE -> "live";
                case VOD -> "vod";
                case SERIES -> "series";
            };
        }
        return "start";
    }

    private boolean hasDisplayChannels() {
        synchronized (channels) {
            return importPreviewActive ? !previewChannels.isEmpty() : !channels.isEmpty();
        }
    }

'''
    text = block(text, "    private void addNav(String label, Screen target) {\n", "    private void render() {\n", nav_methods, "navigation methods")

    old_render_head = '''    private void render() {
        if (content == null) return;
        content.removeAllViews();
        for (int i = 0; i < nav.getChildCount(); i++) {
            Button b = (Button) nav.getChildAt(i);
            boolean selected = b.getTag() == screen
                    || (b.getTag() == Screen.START && screen != Screen.SETTINGS);
            b.setTextColor(selected ? BG : TEXT);
            b.setBackground(roundRect(selected ? PRIMARY : 0xFF17354A, 14));
        }
'''
    new_render_head = '''    private void render() {
        if (content == null) return;
        content.removeAllViews();
        rebuildNav();
'''
    text = once(text, old_render_head, new_render_head, "render navigation refresh")

    premium_home = r'''    private void renderStart() {
        List<Channel> display = displayChannelsSnapshot();
        pageTitle.setText("Für dich");
        if (restoringSource) {
            pageSubtitle.setText("Deine gespeicherte Bibliothek wird vorbereitet");
            premiumHero("Willkommen zurück", "Project Lumen stellt deine lokal verschlüsselte Liste wieder her. Es ist kein neuer Download notwendig.", null, null);
            cardInfo("Lokale Wiederherstellung", "Sender, Filme und Serien erscheinen automatisch, sobald die lokale Entschlüsselung abgeschlossen ist.");
            return;
        }
        if (display.isEmpty()) {
            pageSubtitle.setText("Deine persönliche Medienoberfläche");
            premiumHero("Alles an einem Ort", "Richte eine rechtmäßig nutzbare Playlist ein. Project Lumen sortiert Live-TV, Filme und Serien anschließend automatisch und speichert alles lokal verschlüsselt.", "Liste hinzufügen", () -> { screen = Screen.SOURCE; render(); });
            sectionTitle("Sicher eingerichtet", "Keine leeren Bereiche, keine erneute Eingabe nach jedem Start.");
            cardAction("Lokales Video öffnen", "Eine Videodatei ohne Upload direkt mit dem Media3-Player abspielen", this::openVideoPicker);
            cardInfo("Local First", "Project Lumen hostet oder vermittelt keine Inhalte. Playlist und Metadaten bleiben auf diesem Gerät.");
            return;
        }

        HomeSnapshot home = buildHomeSnapshot(display);
        String sourceLabel = activeSourceName == null || activeSourceName.isBlank() ? "Gespeicherte Liste" : activeSourceName;
        pageSubtitle.setText(sourceLabel + " · " + display.size() + " Einträge bereit");
        premiumHero("Deine Medien. Klar sortiert.", home.liveCount + " Live-Sender · " + home.vodCount + " Filme · " + home.seriesCount + " Serien", "Jetzt live", () -> openMedia(MediaSection.LIVE));

        sectionTitle("Live-TV nach Sprache", "Automatisch aus Sprache, Land und Anbietergruppe erkannt");
        languageHubRow(home);

        premiumMediaRow("Jetzt live", "Direkt starten", home.livePreview);
        premiumMediaRow("Filme & Mediathek", home.vodCount + " Titel erkannt", home.vodPreview);
        premiumMediaRow("Serien", home.seriesCount + " Einträge erkannt", home.seriesPreview);

        sectionTitle("Bibliothek", importPreviewActive ? "Die lokale Verschlüsselung läuft noch im Hintergrund" : "Beim nächsten Start automatisch wieder verfügbar");
        cardAction("Liste verwalten", "Quelle ansehen, ersetzen oder eine weitere Liste importieren", () -> { screen = Screen.SOURCE; render(); });
    }

    private void premiumHero(String title, String detail, String actionLabel, Runnable action) {
        LinearLayout hero = card();
        hero.setPadding(dp(television ? 30 : 22), dp(television ? 28 : 22), dp(television ? 30 : 22), dp(television ? 28 : 22));
        hero.setBackground(gradientRect(0xFF15233A, 0xFF251A45, 24));
        TextView eyebrow = text("PROJECT LUMEN", television ? 15 : 12, PRIMARY, true);
        eyebrow.setLetterSpacing(0.12f);
        hero.addView(eyebrow);
        TextView headline = text(title, television ? 38 : 29, TEXT, true);
        headline.setPadding(0, dp(10), 0, dp(8));
        hero.addView(headline);
        TextView copy = text(detail, television ? 18 : 15, 0xFFD6DDE8, false);
        copy.setMaxWidth(dp(television ? 760 : 520));
        hero.addView(copy);
        if (actionLabel != null && action != null) {
            Button primary = button(actionLabel, true);
            primary.setOnClickListener(v -> action.run());
            LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, dp(television ? 58 : 50));
            p.setMargins(0, dp(18), 0, 0);
            hero.addView(primary, p);
            hero.setOnClickListener(v -> action.run());
        }
        content.addView(hero, marginBottom(18));
    }

    private void sectionTitle(String title, String detail) {
        TextView heading = text(title, television ? 26 : 21, TEXT, true);
        content.addView(heading);
        TextView sub = text(detail, television ? 15 : 13, MUTED, false);
        sub.setPadding(0, dp(3), 0, dp(10));
        content.addView(sub);
    }

    private void languageHubRow(HomeSnapshot home) {
        HorizontalScrollView scroll = new HorizontalScrollView(this);
        scroll.setHorizontalScrollBarEnabled(false);
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        addLanguageHubCard(row, "🇩🇪", "Deutsch", home.germanCount, LanguageHub.GERMAN, 0xFF172D44, 0xFF244C70);
        addLanguageHubCard(row, "🇹🇷", "Türkisch", home.turkishCount, LanguageHub.TURKISH, 0xFF401B24, 0xFF752B3A);
        addLanguageHubCard(row, "🇬🇧", "Englisch", home.englishCount, LanguageHub.ENGLISH, 0xFF1E2948, 0xFF354B82);
        addLanguageHubCard(row, "🌍", "Weitere", home.otherCount, LanguageHub.OTHER, 0xFF24352C, 0xFF3B654D);
        scroll.addView(row, new HorizontalScrollView.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        content.addView(scroll, marginBottom(18));
    }

    private void addLanguageHubCard(LinearLayout row, String flag, String title, int count, LanguageHub hub, int startColor, int endColor) {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setGravity(Gravity.BOTTOM);
        card.setPadding(dp(16), dp(14), dp(16), dp(14));
        card.setBackground(gradientRect(startColor, endColor, 20));
        card.setClickable(true);
        card.setFocusable(true);
        card.addView(text(flag, television ? 34 : 28, TEXT, false));
        TextView label = text(title, television ? 21 : 17, TEXT, true);
        label.setPadding(0, dp(10), 0, dp(2));
        card.addView(label);
        card.addView(text(count + " Live-Sender", television ? 14 : 12, 0xFFD9E1EC, false));
        card.setOnClickListener(v -> openLanguageHub(hub));
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(dp(television ? 230 : 160), dp(television ? 150 : 120));
        p.setMargins(row.getChildCount() == 0 ? 0 : dp(9), 0, 0, 0);
        row.addView(card, p);
    }

    private void premiumMediaRow(String title, String detail, List<Channel> items) {
        if (items.isEmpty()) return;
        sectionTitle(title, detail);
        HorizontalScrollView scroll = new HorizontalScrollView(this);
        scroll.setHorizontalScrollBarEnabled(false);
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        for (Channel channel : items) addPremiumMediaCard(row, channel);
        scroll.addView(row, new HorizontalScrollView.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        content.addView(scroll, marginBottom(18));
    }

    private void addPremiumMediaCard(LinearLayout row, Channel channel) {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setGravity(Gravity.BOTTOM);
        card.setPadding(dp(15), dp(14), dp(15), dp(14));
        LanguageHub hub = classifyLanguage(channel);
        int start = switch (hub) {
            case GERMAN -> 0xFF172C43;
            case TURKISH -> 0xFF411D26;
            case ENGLISH -> 0xFF202B4D;
            case OTHER, ALL -> 0xFF242B35;
        };
        int end = switch (hub) {
            case GERMAN -> 0xFF24577A;
            case TURKISH -> 0xFF7A2B3D;
            case ENGLISH -> 0xFF3A528E;
            case OTHER, ALL -> 0xFF3A4555;
        };
        card.setBackground(gradientRect(start, end, 18));
        card.setClickable(true);
        card.setFocusable(true);
        card.addView(text(languageFlag(hub), television ? 29 : 24, TEXT, false));
        TextView name = text(channel.name, television ? 18 : 15, TEXT, true);
        name.setMaxLines(2);
        name.setPadding(0, dp(9), 0, dp(4));
        card.addView(name);
        TextView meta = text(channel.group + " · " + languageLabel(hub), television ? 13 : 11, 0xFFD5DCE6, false);
        meta.setMaxLines(1);
        card.addView(meta);
        card.setOnClickListener(v -> play(channel));
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(dp(television ? 270 : 190), dp(television ? 185 : 150));
        p.setMargins(row.getChildCount() == 0 ? 0 : dp(9), 0, 0, 0);
        row.addView(card, p);
    }

'''
    text = block(text, "    private void renderStart() {\n", "    private void renderSource() {\n", premium_home, "premium home")

    text = once(text,
        "    private void openMedia(MediaSection section) {\n"
        "        mediaSection = section;\n"
        "        filter = \"\";\n"
        "        livePage = 0;\n"
        "        screen = Screen.MEDIA;\n"
        "        render();\n"
        "    }\n",
        "    private void openMedia(MediaSection section) {\n"
        "        mediaSection = section;\n"
        "        languageHub = LanguageHub.ALL;\n"
        "        filter = \"\";\n"
        "        livePage = 0;\n"
        "        screen = Screen.MEDIA;\n"
        "        render();\n"
        "    }\n\n"
        "    private void openLanguageHub(LanguageHub hub) {\n"
        "        mediaSection = MediaSection.LIVE;\n"
        "        languageHub = hub;\n"
        "        filter = \"\";\n"
        "        livePage = 0;\n"
        "        screen = Screen.MEDIA;\n"
        "        render();\n"
        "    }\n",
        "language hub opener")

    text = once(text,
        '''        pageTitle.setText(mediaSectionTitle());
        if (snapshot.isEmpty()) {
''',
        '''        pageTitle.setText(mediaSectionTitle());
        if (mediaSection == MediaSection.LIVE) languageFilterRow(snapshot);
        if (snapshot.isEmpty()) {
''',
        "language filter row")

    text = once(text,
        '''    private String mediaSectionTitle() {
        return switch (mediaSection) {
            case LIVE -> "Live-Fernsehen";
            case VOD -> "Filme & Mediathek";
            case SERIES -> "Serien";
        };
    }
''',
        '''    private String mediaSectionTitle() {
        return switch (mediaSection) {
            case LIVE -> languageHub == LanguageHub.ALL ? "Live-Fernsehen" : "Live-Fernsehen · " + languageLabel(languageHub);
            case VOD -> "Filme & Mediathek";
            case SERIES -> "Serien";
        };
    }

    private void languageFilterRow(List<Channel> source) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        addLanguageFilterChip(row, "Alle", LanguageHub.ALL, countLanguage(source, LanguageHub.ALL));
        addLanguageFilterChip(row, "Deutsch", LanguageHub.GERMAN, countLanguage(source, LanguageHub.GERMAN));
        addLanguageFilterChip(row, "Türkisch", LanguageHub.TURKISH, countLanguage(source, LanguageHub.TURKISH));
        addLanguageFilterChip(row, "Englisch", LanguageHub.ENGLISH, countLanguage(source, LanguageHub.ENGLISH));
        addLanguageFilterChip(row, "Weitere", LanguageHub.OTHER, countLanguage(source, LanguageHub.OTHER));
        HorizontalScrollView scroll = new HorizontalScrollView(this);
        scroll.setHorizontalScrollBarEnabled(false);
        scroll.addView(row, new HorizontalScrollView.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        content.addView(scroll, marginBottom(12));
    }

    private void addLanguageFilterChip(LinearLayout row, String label, LanguageHub hub, int count) {
        Button chip = button(label + "  " + count, languageHub == hub);
        chip.setOnClickListener(v -> { languageHub = hub; livePage = 0; render(); });
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, dp(television ? 50 : 42));
        p.setMargins(row.getChildCount() == 0 ? 0 : dp(7), 0, 0, 0);
        row.addView(chip, p);
    }
''',
        "media title and language chips")

    classification = r'''    private int countLanguage(List<Channel> source, LanguageHub hub) {
        int count = 0;
        for (Channel channel : source) {
            if (!matchesMediaSection(channel, MediaSection.LIVE)) continue;
            if (hub == LanguageHub.ALL || classifyLanguage(channel) == hub) count++;
        }
        return count;
    }

    private HomeSnapshot buildHomeSnapshot(List<Channel> source) {
        HomeSnapshot result = new HomeSnapshot();
        for (Channel channel : source) {
            MediaSection section = classifyMediaSection(channel);
            if (section == MediaSection.LIVE) {
                result.liveCount++;
                LanguageHub hub = classifyLanguage(channel);
                switch (hub) {
                    case GERMAN -> result.germanCount++;
                    case TURKISH -> result.turkishCount++;
                    case ENGLISH -> result.englishCount++;
                    case OTHER, ALL -> result.otherCount++;
                }
                if (result.livePreview.size() < 12) result.livePreview.add(channel);
            } else if (section == MediaSection.VOD) {
                result.vodCount++;
                if (result.vodPreview.size() < 12) result.vodPreview.add(channel);
            } else {
                result.seriesCount++;
                if (result.seriesPreview.size() < 12) result.seriesPreview.add(channel);
            }
        }
        return result;
    }

    private MediaSection classifyMediaSection(Channel channel) {
        String group = channel.group == null ? "" : channel.group.toLowerCase(Locale.ROOT);
        String url = channel.url == null ? "" : channel.url.toLowerCase(Locale.ROOT);
        boolean series = url.contains("/series/") || containsAny(group, "serie", "series", "tv show", "staffel", "episode");
        boolean vod = !series && (url.contains("/movie/") || containsAny(group, " vod", "vod ", "filme", "film ", "movie", "kino", "mediathek"));
        return series ? MediaSection.SERIES : vod ? MediaSection.VOD : MediaSection.LIVE;
    }

    private boolean matchesMediaSection(Channel channel, MediaSection section) {
        return classifyMediaSection(channel) == section;
    }

    private LanguageHub classifyLanguage(Channel channel) {
        String explicit = normalizeLanguageText(channel.language + " " + channel.country);
        if (containsLanguageToken(explicit, "de", "deu", "ger", "german", "deutsch", "germany", "deutschland", "at", "aut")) return LanguageHub.GERMAN;
        if (containsLanguageToken(explicit, "tr", "tur", "turkish", "turkce", "turkiye", "tuerkisch")) return LanguageHub.TURKISH;
        if (containsLanguageToken(explicit, "en", "eng", "english", "gb", "gbr", "uk", "us", "usa", "aus", "irl")) return LanguageHub.ENGLISH;

        String group = normalizeLanguageText(channel.group);
        if (containsLanguageToken(group, "de", "deu", "ger") || containsAny(group, "deutsch", "german", "germany", "deutschland", "dach", "bundesliga")) return LanguageHub.GERMAN;
        if (containsLanguageToken(group, "tr", "tur") || containsAny(group, "turk", "turkiye", "tuerk", "yerli")) return LanguageHub.TURKISH;
        if (containsLanguageToken(group, "en", "eng", "uk", "gb", "gbr", "us", "usa") || containsAny(group, "english", "united kingdom", "great britain", "australia")) return LanguageHub.ENGLISH;

        String name = normalizeLanguageText(channel.name);
        if (startsWithAny(name, "ard", "zdf", "rtl", "sat 1", "sat.1", "prosieben", "pro7", "vox", "kabel eins", "kika", "phoenix", "3sat")) return LanguageHub.GERMAN;
        if (startsWithAny(name, "trt", "kanal d", "show tv", "tv8", "a haber", "haberturk", "haber turk", "star tv tr", "teve2")) return LanguageHub.TURKISH;
        if (startsWithAny(name, "bbc", "itv", "cnn", "nbc", "cbs", "abc", "fox", "sky uk", "channel 4", "channel 5")) return LanguageHub.ENGLISH;
        return LanguageHub.OTHER;
    }

    private static String normalizeLanguageText(String value) {
        if (value == null) return "";
        return value.toLowerCase(Locale.ROOT)
                .replace('ä', 'a').replace('ö', 'o').replace('ü', 'u').replace('ß', 's')
                .replace('ç', 'c').replace('ş', 's').replace('ğ', 'g').replace('ı', 'i')
                .replaceAll("[^a-z0-9]+", " ").trim();
    }

    private static boolean containsLanguageToken(String value, String... tokens) {
        String padded = " " + value + " ";
        for (String token : tokens) if (padded.contains(" " + token + " ")) return true;
        return false;
    }

    private static boolean startsWithAny(String value, String... prefixes) {
        for (String prefix : prefixes) if (value.startsWith(prefix)) return true;
        return false;
    }

    private static String languageLabel(LanguageHub hub) {
        return switch (hub) {
            case ALL -> "Alle Sprachen";
            case GERMAN -> "Deutsch";
            case TURKISH -> "Türkisch";
            case ENGLISH -> "Englisch";
            case OTHER -> "Weitere Sprachen";
        };
    }

    private static String languageFlag(LanguageHub hub) {
        return switch (hub) {
            case GERMAN -> "🇩🇪";
            case TURKISH -> "🇹🇷";
            case ENGLISH -> "🇬🇧";
            case ALL, OTHER -> "🌍";
        };
    }

'''
    text = block(text, "    private boolean matchesMediaSection(Channel channel, MediaSection section) {\n", "    private static boolean containsAny(String value, String... needles) {\n", classification, "language classification")

    text = once(text,
        "            if (!matchesMediaSection(channel, mediaSection)) continue;\n"
        "            boolean matches = needle.isBlank()\n"
        "                    || channel.name.toLowerCase(Locale.ROOT).contains(needle)\n"
        "                    || channel.group.toLowerCase(Locale.ROOT).contains(needle);\n",
        "            if (!matchesMediaSection(channel, mediaSection)) continue;\n"
        "            if (mediaSection == MediaSection.LIVE && languageHub != LanguageHub.ALL && classifyLanguage(channel) != languageHub) continue;\n"
        "            boolean matches = needle.isBlank()\n"
        "                    || channel.name.toLowerCase(Locale.ROOT).contains(needle)\n"
        "                    || channel.group.toLowerCase(Locale.ROOT).contains(needle)\n"
        "                    || channel.language.toLowerCase(Locale.ROOT).contains(needle)\n"
        "                    || channel.country.toLowerCase(Locale.ROOT).contains(needle);\n",
        "language-filtered paging")

    text = once(text,
        '''            String pendingName = null;
            String pendingGroup = "Weitere";
            int lines = 0;
''',
        '''            String pendingName = null;
            String pendingGroup = "Weitere";
            String pendingLanguage = "";
            String pendingCountry = "";
            String pendingLogo = "";
            int lines = 0;
''',
        "parser pending metadata")

    text = once(text,
        '''                    pendingGroup = attribute(line, "group-title");
                    if (pendingGroup.isBlank()) pendingGroup = "Weitere";
                    continue;
''',
        '''                    pendingGroup = attribute(line, "group-title");
                    if (pendingGroup.isBlank()) pendingGroup = "Weitere";
                    pendingLanguage = attribute(line, "tvg-language");
                    if (pendingLanguage.isBlank()) pendingLanguage = attribute(line, "language");
                    pendingCountry = attribute(line, "tvg-country");
                    if (pendingCountry.isBlank()) pendingCountry = attribute(line, "country");
                    pendingLogo = attribute(line, "tvg-logo");
                    continue;
''',
        "parse M3U language metadata")

    text = once(text,
        '''                result.add(new Channel(name, pendingGroup, line));
                pendingName = null;
                pendingGroup = "Weitere";
''',
        '''                result.add(new Channel(name, pendingGroup, line, pendingLanguage, pendingCountry, pendingLogo));
                pendingName = null;
                pendingGroup = "Weitere";
                pendingLanguage = "";
                pendingCountry = "";
                pendingLogo = "";
''',
        "create enriched channels")

    text = once(text,
        "                    filter = \"\"; livePage = 0; restoringSource = false; mediaSection = MediaSection.LIVE;\n",
        "                    filter = \"\"; livePage = 0; restoringSource = false; mediaSection = MediaSection.LIVE; languageHub = LanguageHub.ALL;\n",
        "clear language state")

    old_encrypt_method = r'''    private void encryptFileWithProgress(File input, File output, int entryCount) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey());
        long expected = Math.max(1L, input.length());
        long nextReport = 512L * 1024L;
        long total = 0L;
        try (FileOutputStream fileOut = new FileOutputStream(output)) {
            byte[] iv = cipher.getIV();
            fileOut.write(iv.length);
            fileOut.write(iv);
            try (CipherOutputStream encrypted = new CipherOutputStream(fileOut, cipher); FileInputStream in = new FileInputStream(input)) {
                byte[] buffer = new byte[64 * 1024];
                int read;
                while ((read = in.read(buffer)) >= 0) {
                    if (read == 0) continue;
                    encrypted.write(buffer, 0, read);
                    total += read;
                    if (total >= nextReport) {
                        long report = total;
                        int percent = (int) Math.min(99L, (report * 100L) / expected);
                        nextReport = total + 512L * 1024L;
                        runOnUiThread(() -> showDiagnostic(
                                "Quelle wird gespeichert",
                                "Phase 3/4 · " + entryCount + " Einträge werden lokal verschlüsselt gespeichert.\n"
                                        + "Fortschritt: " + percent + "%\n\n"
                                        + "Die Senderliste kann bereits geöffnet werden.",
                                true));
                    }
                }
            }
        }
    }

'''
    new_encrypt_method = r'''    private void encryptFileWithProgress(File input, File output, int entryCount) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey());
        long expected = Math.max(1L, input.length());
        int nextPercent = 5;
        long total = 0L;
        try (FileOutputStream fileOut = new FileOutputStream(output)) {
            byte[] iv = cipher.getIV();
            fileOut.write(iv.length);
            fileOut.write(iv);
            try (CipherOutputStream encrypted = new CipherOutputStream(fileOut, cipher); FileInputStream in = new FileInputStream(input)) {
                byte[] buffer = new byte[64 * 1024];
                int read;
                while ((read = in.read(buffer)) >= 0) {
                    if (read == 0) continue;
                    encrypted.write(buffer, 0, read);
                    total += read;
                    int percent = (int) Math.min(99L, (total * 100L) / expected);
                    if (percent >= nextPercent) {
                        int reportedPercent = Math.min(95, (percent / 5) * 5);
                        nextPercent = reportedPercent + 5;
                        runOnUiThread(() -> showDiagnostic(
                                "Quelle wird gespeichert",
                                "Phase 3/4 · " + entryCount + " Einträge werden lokal verschlüsselt gespeichert.\n"
                                        + "Fortschritt: " + reportedPercent + "%\n\n"
                                        + "Die Senderliste kann bereits geöffnet werden.",
                                true));
                    }
                }
            }
        }
    }

'''
    text = once(text, old_encrypt_method, new_encrypt_method, "progress reports every five percent")

    text = once(text,
        '''    private GradientDrawable roundRect(int color, int radiusDp) {
        GradientDrawable d = new GradientDrawable();
        d.setColor(color);
        d.setCornerRadius(dp(radiusDp));
        d.setStroke(dp(1), 0xFF28405A);
        return d;
    }
''',
        '''    private GradientDrawable roundRect(int color, int radiusDp) {
        GradientDrawable d = new GradientDrawable();
        d.setColor(color);
        d.setCornerRadius(dp(radiusDp));
        d.setStroke(dp(1), BORDER);
        return d;
    }

    private GradientDrawable gradientRect(int startColor, int endColor, int radiusDp) {
        GradientDrawable d = new GradientDrawable(GradientDrawable.Orientation.TL_BR, new int[]{startColor, endColor});
        d.setCornerRadius(dp(radiusDp));
        d.setStroke(dp(1), BORDER);
        return d;
    }
''',
        "premium gradient helper")

    text = once(text,
        '''    private static final class Channel {
        final String name;
        final String group;
        final String url;
        Channel(String name, String group, String url) { this.name = name; this.group = group == null || group.isBlank() ? "Weitere" : group; this.url = url; }
        @Override public String toString() { return name; }
    }
''',
        '''    private static final class HomeSnapshot {
        int liveCount;
        int vodCount;
        int seriesCount;
        int germanCount;
        int turkishCount;
        int englishCount;
        int otherCount;
        final List<Channel> livePreview = new ArrayList<>();
        final List<Channel> vodPreview = new ArrayList<>();
        final List<Channel> seriesPreview = new ArrayList<>();
    }

    private static final class Channel {
        final String name;
        final String group;
        final String url;
        final String language;
        final String country;
        final String logo;

        Channel(String name, String group, String url) {
            this(name, group, url, "", "", "");
        }

        Channel(String name, String group, String url, String language, String country, String logo) {
            this.name = name;
            this.group = group == null || group.isBlank() ? "Weitere" : group;
            this.url = url;
            this.language = language == null ? "" : language;
            this.country = country == null ? "" : country;
            this.logo = logo == null ? "" : logo;
        }

        @Override public String toString() { return name; }
    }
''',
        "enriched channel model")

    text = once(text,
        '''            line2.setText(channel == null ? "" : channel.group + " · Antippen zum Abspielen");
''',
        '''            line2.setText(channel == null ? "" : languageFlag(classifyLanguage(channel)) + " " + channel.group + " · " + languageLabel(classifyLanguage(channel)));
''',
        "premium channel metadata")

    text = text.replace('value.append("App=").append("13.1.23")', 'value.append("App=").append("13.1.24")')
    text = text.replace("ProjectLumen/13.1.23 Android", "ProjectLumen/13.1.24 Android")
    java.write_text(text, encoding="utf-8")

    gradle_text = gradle.read_text(encoding="utf-8")
    gradle_text = once(gradle_text, "versionCode 133300", "versionCode 133400", "versionCode")
    gradle_text = once(gradle_text, "versionName '13.1.23-media3-player-preview'", "versionName '13.1.24-premium-ui-language-hubs-preview'", "versionName")
    gradle.write_text(gradle_text, encoding="utf-8")

    strings_text = strings.read_text(encoding="utf-8").replace("Project Lumen 13.1.23 Preview", "Project Lumen 13.1.24 Preview")
    strings.write_text(strings_text, encoding="utf-8")

    if readme.exists():
        readme.write_text(readme.read_text(encoding="utf-8").replace("Project Lumen 13.1.23", "Project Lumen 13.1.24"), encoding="utf-8")

    checks = {
        "premium brand": "PROJECT LUMEN" in text and "Premium Media Player" in text,
        "premium hero": "private void premiumHero" in text,
        "horizontal rows": "private void premiumMediaRow" in text,
        "language hubs": "private enum LanguageHub" in text and "Live-TV nach Sprache" in text,
        "metadata parsing": 'attribute(line, "tvg-language")' in text and 'attribute(line, "tvg-country")' in text,
        "language classifier": "private LanguageHub classifyLanguage" in text,
        "language page filter": "classifyLanguage(channel) != languageHub" in text,
        "progress throttled": "reportedPercent = Math.min(95" in text and "nextPercent" in text,
        "media3 preserved": "private ExoPlayer exoPlayer" in text,
        "restore preserved": "Code=RESTORE-OK" in text,
        "version 13.1.24": 'text("v13.1.24"' in text,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise SystemExit("patch verification failed: " + ", ".join(failed))
    print("Project Lumen 13.1.24 premium UI and language hubs patch applied")
    for name in checks:
        print("OK: " + name)


if __name__ == "__main__":
    main()
