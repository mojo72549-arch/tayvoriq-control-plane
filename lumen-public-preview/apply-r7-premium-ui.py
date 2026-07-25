#!/usr/bin/env python3
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

root = Path(sys.argv[1] if len(sys.argv) > 1 else "project-lumen-preview")
pkg = root / "app/src/main/java/com/projectlumen/publicpreview"
main = pkg / "MainActivity.java"
gradle = root / "app/build.gradle"
support = Path(__file__).resolve().parent / "r7-src"

required = [main, gradle, support / "PremiumBackgroundView.java", support / "PremiumUi.java", support / "CountryFlagView.java"]
for path in required:
    if not path.exists():
        raise SystemExit(f"missing R7 input: {path}")

pkg.mkdir(parents=True, exist_ok=True)
for source in support.glob("*.java"):
    shutil.copy2(source, pkg / source.name)


def method_span(text: str, name: str) -> tuple[int, int]:
    pattern = re.compile(
        rf"(?m)^    (?:public|private|protected)\s+(?:static\s+)?[\w<>\[\], ?.]+\s+{re.escape(name)}\s*\([^;{{}}]*\)\s*\{{")
    match = pattern.search(text)
    if not match:
        raise SystemExit(f"method not found: {name}")
    opening = text.find("{", match.start(), match.end())
    depth = 0
    i = opening
    state = "code"
    while i < len(text):
        char = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if state == "code":
            if char == '"':
                state = "string"
            elif char == "'":
                state = "char"
            elif char == "/" and nxt == "/":
                state = "line"
                i += 1
            elif char == "/" and nxt == "*":
                state = "block"
                i += 1
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return match.start(), i + 1
        elif state == "string":
            if char == "\\":
                i += 1
            elif char == '"':
                state = "code"
        elif state == "char":
            if char == "\\":
                i += 1
            elif char == "'":
                state = "code"
        elif state == "line":
            if char == "\n":
                state = "code"
        elif state == "block":
            if char == "*" and nxt == "/":
                state = "code"
                i += 1
        i += 1
    raise SystemExit(f"unterminated method: {name}")


def replace_method(text: str, name: str, replacement: str) -> str:
    start, end = method_span(text, name)
    return text[:start] + replacement.strip("\n") + text[end:]


def insert_before_class_end(text: str, block: str) -> str:
    index = text.rfind("}")
    if index < 0:
        raise SystemExit("class end missing")
    return text[:index] + "\n" + block.strip("\n") + "\n" + text[index:]


g = gradle.read_text(encoding="utf-8")
g = re.sub(r"versionCode\s+\d+", "versionCode 134300", g, count=1)
g = re.sub(r"versionName\s+'[^']+'", "versionName '13.1.33-r7-premium-ui-ux-pilot'", g, count=1)
gradle.write_text(g, encoding="utf-8")

s = main.read_text(encoding="utf-8")
s = s.replace('text("v13.1.32 RC1"', 'text("13.1.33"')
s = s.replace('text("v13.1.29"', 'text("13.1.33"')
s = s.replace('text("v13.1.28"', 'text("13.1.33"')
for name, value in {
    "BG": "PremiumUi.BG",
    "SURFACE": "PremiumUi.SURFACE",
    "SURFACE_ALT": "PremiumUi.SURFACE_ALT",
    "PRIMARY": "PremiumUi.PRIMARY",
    "ACCENT": "PremiumUi.ACCENT",
    "TEXT": "PremiumUi.TEXT",
    "MUTED": "PremiumUi.MUTED",
    "BORDER": "PremiumUi.BORDER",
}.items():
    s = re.sub(rf"private static final int {name} = 0x[0-9A-Fa-f]+;", f"private static final int {name} = {value};", s, count=1)

s = replace_method(s, "buildMainUi", r'''
    private void buildMainUi() {
        PremiumBackgroundView background = new PremiumBackgroundView(this);
        root.addView(background, match());

        LinearLayout shell = new LinearLayout(this);
        shell.setOrientation(television ? LinearLayout.HORIZONTAL : LinearLayout.VERTICAL);
        shell.setPadding(dp(television ? 18 : 12), dp(television ? 18 : 10),
                dp(television ? 18 : 12), dp(television ? 18 : 10));
        shell.setBackgroundColor(Color.TRANSPARENT);
        root.addView(shell, match());

        nav = new LinearLayout(this);
        nav.setOrientation(television ? LinearLayout.VERTICAL : LinearLayout.HORIZONTAL);
        nav.setGravity(television ? Gravity.TOP : Gravity.CENTER_VERTICAL);
        nav.setPadding(dp(television ? 10 : 5), dp(television ? 14 : 5),
                dp(television ? 10 : 5), dp(television ? 14 : 5));
        nav.setBackground(PremiumUi.surface(this, false));

        page = new LinearLayout(this);
        page.setOrientation(LinearLayout.VERTICAL);
        page.setPadding(dp(television ? 26 : 10), dp(television ? 8 : 4),
                dp(television ? 20 : 10), 0);
        page.setBackgroundColor(Color.TRANSPARENT);

        if (television) {
            shell.addView(nav, new LinearLayout.LayoutParams(dp(205), ViewGroup.LayoutParams.MATCH_PARENT));
            LinearLayout.LayoutParams pageParams = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f);
            pageParams.setMargins(dp(14), 0, 0, 0);
            shell.addView(page, pageParams);
        } else {
            shell.addView(page, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));
            LinearLayout.LayoutParams navParams = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(66));
            navParams.setMargins(0, dp(8), 0, 0);
            shell.addView(nav, navParams);
        }

        LinearLayout header = new LinearLayout(this);
        header.setOrientation(LinearLayout.HORIZONTAL);
        header.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout brand = new LinearLayout(this);
        brand.setOrientation(LinearLayout.VERTICAL);
        TextView logo = text("LUMEN", television ? 29 : 23, TEXT, true);
        logo.setLetterSpacing(0.16f);
        brand.addView(logo);
        brand.addView(text("Deine Medien", television ? 14 : 11, MUTED, false));
        header.addView(brand, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));

        Button searchQuick = button("⌕", false);
        searchQuick.setContentDescription("Suche öffnen");
        searchQuick.setOnClickListener(v -> { screen = Screen.SEARCH; render(); });
        header.addView(searchQuick, new LinearLayout.LayoutParams(dp(television ? 58 : 46), dp(television ? 52 : 44)));

        Button profileQuick = button("◉  " + ProfileStore.activeName(this), false);
        profileQuick.setContentDescription("Profile und Jugendschutz");
        profileQuick.setOnClickListener(v -> startActivity(new Intent(this, ProfilesActivity.class)));
        LinearLayout.LayoutParams profileParams = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, dp(television ? 52 : 44));
        profileParams.setMargins(dp(8), 0, 0, 0);
        header.addView(profileQuick, profileParams);
        page.addView(header, marginBottom(television ? 18 : 12));

        pageTitle = text("", television ? 36 : 28, TEXT, true);
        page.addView(pageTitle);
        pageSubtitle = text("", television ? 16 : 13, MUTED, false);
        pageSubtitle.setPadding(0, dp(3), 0, dp(10));
        page.addView(pageSubtitle);

        contentScroll = new ScrollView(this);
        contentScroll.setFillViewport(true);
        contentScroll.setOverScrollMode(View.OVER_SCROLL_NEVER);
        content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(0, 0, 0, dp(16));
        contentScroll.addView(content);
        page.addView(contentScroll, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));
        render();
    }
''')

s = replace_method(s, "rebuildNav", r'''
    private void rebuildNav() {
        nav.removeAllViews();
        addNavAction(television ? "⌂  Start" : "⌂\nStart", "start", () -> { screen = Screen.START; render(); });
        if (hasDisplayChannels()) {
            addNavAction(television ? "●  Live" : "●\nLive", "live", () -> openMedia(MediaSection.LIVE));
            addNavAction(television ? "◆  Filme" : "◆\nFilme", "vod", () -> openMedia(MediaSection.VOD));
            addNavAction(television ? "▤  Serien" : "▤\nSerien", "series", () -> openMedia(MediaSection.SERIES));
        }
        addNavAction(television ? "•••  Mehr" : "•••\nMehr", "more", () -> { screen = Screen.SETTINGS; render(); });
    }
''')

s = replace_method(s, "addNavAction", r'''
    private void addNavAction(String label, String key, Runnable action) {
        Button item = button(label, false);
        boolean selected = currentNavKey().equals(key);
        item.setTextColor(selected ? BG : TEXT);
        item.setBackground(PremiumUi.chip(this, selected, false));
        item.setTag(key);
        item.setGravity(television ? Gravity.START | Gravity.CENTER_VERTICAL : Gravity.CENTER);
        item.setOnClickListener(v -> action.run());
        item.setOnFocusChangeListener((view, focused) -> {
            view.animate().scaleX(focused ? 1.035f : 1f).scaleY(focused ? 1.035f : 1f)
                    .translationZ(focused ? dp(8) : 0).setDuration(125L).start();
            item.setBackground(PremiumUi.chip(this, selected, focused));
        });
        if (television) {
            LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(58));
            params.setMargins(0, nav.getChildCount() == 0 ? 0 : dp(8), 0, 0);
            nav.addView(item, params);
        } else {
            LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f);
            params.setMargins(nav.getChildCount() == 0 ? 0 : dp(3), 0, 0, 0);
            nav.addView(item, params);
        }
    }
''')

s = replace_method(s, "currentNavKey", r'''
    private String currentNavKey() {
        if (screen == Screen.MEDIA) {
            return switch (mediaSection) {
                case LIVE -> "live";
                case VOD -> "vod";
                case SERIES -> "series";
            };
        }
        if (screen == Screen.START) return "start";
        return "more";
    }
''')

s = replace_method(s, "render", r'''
    private void render() {
        if (content == null) return;
        refreshProfileStateIfNeeded();
        content.removeAllViews();
        if (contentScroll != null) contentScroll.post(() -> contentScroll.scrollTo(0, 0));
        rebuildNav();
        switch (screen) {
            case START -> renderStart();
            case MEDIA -> renderMedia();
            case EPG -> renderEpg();
            case SEARCH -> renderSearch();
            case FAVORITES -> renderFavorites();
            case SOURCE -> renderSource();
            case SETTINGS -> renderSettings();
        }
        if (pageSubtitle != null) {
            CharSequence value = pageSubtitle.getText();
            pageSubtitle.setVisibility(value == null || value.toString().isBlank() ? View.GONE : View.VISIBLE);
        }
    }
''')

s = replace_method(s, "renderStart", r'''
    private void renderStart() {
        List<Channel> display = displayChannelsSnapshot();
        pageTitle.setText(timeGreeting());
        pageSubtitle.setText("Profil " + ProfileStore.activeName(this));
        if (restoringSource) {
            premiumHero("Bibliothek wird geöffnet", restoreStageLabel(), "Systemstatus", this::openRestoreDiagnostic);
            return;
        }
        if (display.isEmpty()) {
            premiumHero("Deine Medien. Ein Ort.", "Eigene Quelle verbinden und direkt loslegen.",
                    "Quelle hinzufügen", () -> { screen = Screen.SOURCE; render(); });
            sectionTitle("Schnell starten", "");
            cardAction("Lokales Video", "Direkt vom Gerät abspielen", this::openVideoPicker);
            cardInfo("Lokal & privat", "Project Lumen enthält keine eigenen Inhalte.");
            return;
        }

        HomeSnapshot home = buildHomeSnapshot(display);
        pageSubtitle.setText("Profil " + ProfileStore.activeName(this) + " · " + display.size() + " Inhalte");
        premiumHero("Bereit zum Streamen", home.liveCount + " Live · " + home.vodCount + " Filme · "
                + home.seriesCount + " Serien", "Live öffnen", () -> openMedia(MediaSection.LIVE));

        List<Channel> continueWatching = continueWatchingChannels(display);
        premiumMediaRow("Weiterschauen", "", continueWatching);

        List<Channel> favoritePreview = new ArrayList<>();
        for (Channel channel : display) {
            if (isFavorite(channel)) favoritePreview.add(channel);
            if (favoritePreview.size() >= 14) break;
        }
        premiumMediaRow("Favoriten", "", favoritePreview);

        sectionTitle("Sprachen & Länder", "");
        languageHubRow(home);
        premiumMediaRow("Jetzt live", "", home.livePreview);
        premiumMediaRow("Filme", "", home.vodPreview);
        premiumMediaRow("Serien", "", home.seriesPreview);
    }
''')

s = replace_method(s, "premiumHero", r'''
    private void premiumHero(String title, String detail, String actionLabel, Runnable action) {
        LinearLayout hero = card();
        hero.setPadding(dp(television ? 34 : 23), dp(television ? 31 : 24),
                dp(television ? 34 : 23), dp(television ? 31 : 24));
        hero.setBackground(PremiumUi.hero(this));
        TextView eyebrow = text("PROJECT LUMEN", television ? 14 : 11, PRIMARY, true);
        eyebrow.setLetterSpacing(0.14f);
        hero.addView(eyebrow);
        TextView headline = text(title, television ? 40 : 30, TEXT, true);
        headline.setPadding(0, dp(10), 0, dp(7));
        headline.setMaxLines(2);
        hero.addView(headline);
        if (detail != null && !detail.isBlank()) {
            TextView copy = text(detail, television ? 18 : 15, 0xFFD8E4EB, false);
            copy.setMaxLines(2);
            hero.addView(copy);
        }
        if (actionLabel != null && action != null) {
            Button primary = button(actionLabel + "  ›", true);
            primary.setOnClickListener(v -> action.run());
            LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT,
                    dp(television ? 58 : 50));
            params.setMargins(0, dp(19), 0, 0);
            hero.addView(primary, params);
            hero.setOnClickListener(v -> action.run());
        }
        content.addView(hero, marginBottom(20));
    }
''')

s = replace_method(s, "sectionTitle", r'''
    private void sectionTitle(String title, String detail) {
        TextView heading = text(title, television ? 27 : 21, TEXT, true);
        heading.setPadding(0, dp(2), 0, detail == null || detail.isBlank() ? dp(10) : dp(2));
        content.addView(heading);
        if (detail != null && !detail.isBlank()) {
            TextView sub = text(detail, television ? 15 : 12, MUTED, false);
            sub.setMaxLines(1);
            sub.setPadding(0, 0, 0, dp(10));
            content.addView(sub);
        }
    }
''')

s = replace_method(s, "languageHubRow", r'''
    private void languageHubRow(HomeSnapshot home) {
        HorizontalScrollView scroll = new HorizontalScrollView(this);
        scroll.setHorizontalScrollBarEnabled(false);
        scroll.setOverScrollMode(View.OVER_SCROLL_NEVER);
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        addLanguageHubCard(row, "DE", "Deutsch", home, LanguageHub.GERMAN, 0xE5153449, 0xE6225270);
        addLanguageHubCard(row, "TR", "Türkisch", home, LanguageHub.TURKISH, 0xE53F1723, 0xE5742639);
        addLanguageHubCard(row, "GB", "Englisch", home, LanguageHub.ENGLISH, 0xE51C2C50, 0xE53D548B);
        addLanguageHubCard(row, "WORLD", "Weitere", home, LanguageHub.OTHER, 0xE5163435, 0xE5285A52);
        scroll.addView(row, new HorizontalScrollView.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT,
                ViewGroup.LayoutParams.WRAP_CONTENT));
        content.addView(scroll, marginBottom(21));
    }
''')

s = replace_method(s, "addLanguageHubCard", r'''
    private void addLanguageHubCard(LinearLayout row, String flag, String title, HomeSnapshot home,
                                    LanguageHub hub, int startColor, int endColor) {
        LinearLayout tile = new LinearLayout(this);
        tile.setOrientation(LinearLayout.VERTICAL);
        tile.setGravity(Gravity.BOTTOM);
        tile.setPadding(dp(television ? 19 : 15), dp(television ? 18 : 14),
                dp(television ? 19 : 15), dp(television ? 18 : 14));
        tile.setBackground(gradientRect(startColor, endColor, 23));
        tile.setClickable(true);
        tile.setFocusable(true);
        attachPremiumFocus(tile);
        CountryFlagView flagView = new CountryFlagView(this, flag);
        tile.addView(flagView, new LinearLayout.LayoutParams(dp(television ? 70 : 58), dp(television ? 44 : 36)));
        TextView label = text(title, television ? 22 : 18, TEXT, true);
        label.setPadding(0, dp(12), 0, dp(3));
        tile.addView(label);
        String counts = home.count(hub, MediaSection.LIVE) + " Live  ·  "
                + home.count(hub, MediaSection.VOD) + " Filme  ·  "
                + home.count(hub, MediaSection.SERIES) + " Serien";
        TextView summary = text(counts, television ? 14 : 11, 0xFFE0E9EF, false);
        summary.setMaxLines(2);
        tile.addView(summary);
        tile.setOnClickListener(v -> openLanguageHub(hub));
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(dp(television ? 270 : 190),
                dp(television ? 174 : 140));
        params.setMargins(row.getChildCount() == 0 ? 0 : dp(10), 0, 0, 0);
        row.addView(tile, params);
    }
''')

s = replace_method(s, "premiumMediaRow", r'''
    private void premiumMediaRow(String title, String detail, List<Channel> items) {
        if (items == null || items.isEmpty()) return;
        sectionTitle(title, detail);
        HorizontalScrollView scroll = new HorizontalScrollView(this);
        scroll.setHorizontalScrollBarEnabled(false);
        scroll.setOverScrollMode(View.OVER_SCROLL_NEVER);
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        for (Channel channel : items) addPremiumMediaCard(row, channel);
        scroll.addView(row, new HorizontalScrollView.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT,
                ViewGroup.LayoutParams.WRAP_CONTENT));
        content.addView(scroll, marginBottom(20));
    }
''')

s = replace_method(s, "addPremiumMediaCard", r'''
    private void addPremiumMediaCard(LinearLayout row, Channel channel) {
        boolean portrait = channel.section != MediaSection.LIVE;
        int cardWidth = television ? (portrait ? 220 : 310) : (portrait ? 160 : 218);
        int artworkHeight = television ? (portrait ? 292 : 176) : (portrait ? 220 : 122);

        LinearLayout tile = new LinearLayout(this);
        tile.setOrientation(LinearLayout.VERTICAL);
        tile.setBackground(PremiumUi.surface(this, true));
        tile.setClickable(true);
        tile.setFocusable(true);
        tile.setClipToOutline(false);
        attachPremiumFocus(tile);

        FrameLayout artwork = new FrameLayout(this);
        artwork.setBackground(gradientRect(artworkStart(channel.hub), artworkEnd(channel.hub), 20));
        artwork.setClipToOutline(true);
        ImageView image = new ImageView(this);
        image.setScaleType(portrait ? ImageView.ScaleType.CENTER_CROP : ImageView.ScaleType.FIT_CENTER);
        image.setContentDescription(channel.name);
        image.setPadding(portrait ? 0 : dp(13), portrait ? 0 : dp(8), portrait ? 0 : dp(13), portrait ? 0 : dp(8));
        artwork.addView(image, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT));

        TextView favorite = text(isFavorite(channel) ? "★" : "☆", television ? 18 : 15, TEXT, true);
        favorite.setGravity(Gravity.CENTER);
        favorite.setBackground(roundRect(0xB807111B, 16));
        FrameLayout.LayoutParams favoriteParams = new FrameLayout.LayoutParams(dp(television ? 40 : 34),
                dp(television ? 35 : 30), Gravity.TOP | Gravity.START);
        favoriteParams.setMargins(dp(9), dp(9), 0, 0);
        artwork.addView(favorite, favoriteParams);

        String badgeText = channel.section == MediaSection.LIVE ? "LIVE" : languageFlag(channel.hub);
        TextView badge = text(badgeText, television ? 14 : 11, channel.section == MediaSection.LIVE ? BG : TEXT, true);
        badge.setGravity(Gravity.CENTER);
        badge.setBackground(roundRect(channel.section == MediaSection.LIVE ? PRIMARY : 0xB807111B, 16));
        FrameLayout.LayoutParams badgeParams = new FrameLayout.LayoutParams(
                channel.section == MediaSection.LIVE ? dp(television ? 58 : 48) : dp(television ? 42 : 34),
                dp(television ? 35 : 30), Gravity.TOP | Gravity.END);
        badgeParams.setMargins(0, dp(9), dp(9), 0);
        artwork.addView(badge, badgeParams);

        tile.addView(artwork, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(artworkHeight)));
        loadArtwork(image, channel);

        LinearLayout body = new LinearLayout(this);
        body.setOrientation(LinearLayout.VERTICAL);
        body.setPadding(dp(14), dp(12), dp(14), dp(14));
        TextView name = text(channel.name, television ? 19 : 15, TEXT, true);
        name.setMaxLines(2);
        body.addView(name);
        String metaText;
        if (channel.section == MediaSection.LIVE && !epgSnapshot.isEmpty()) {
            metaText = formatEpgLine(channel, System.currentTimeMillis());
        } else {
            metaText = languageLabel(channel.hub);
        }
        TextView meta = text(metaText, television ? 13 : 11, MUTED, false);
        meta.setMaxLines(1);
        meta.setPadding(0, dp(5), 0, 0);
        body.addView(meta);
        tile.addView(body);

        tile.setOnClickListener(v -> openPremiumMedia(channel));
        tile.setOnLongClickListener(v -> { toggleFavorite(channel); render(); return true; });
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(dp(cardWidth),
                ViewGroup.LayoutParams.WRAP_CONTENT);
        params.setMargins(row.getChildCount() == 0 ? 0 : dp(11), 0, 0, dp(8));
        row.addView(tile, params);
    }
''')

s = replace_method(s, "attachPremiumFocus", r'''
    private void attachPremiumFocus(View view) {
        view.setOnFocusChangeListener((target, focused) -> {
            float scale = focused ? 1.045f : 1.0f;
            target.animate().scaleX(scale).scaleY(scale).translationZ(focused ? dp(10) : 0)
                    .setDuration(135L).start();
            target.setAlpha(focused ? 1f : 0.96f);
        });
    }
''')

s = replace_method(s, "renderSource", r'''
    private void renderSource() {
        List<Channel> display = displayChannelsSnapshot();
        pageTitle.setText("Quellen");
        pageSubtitle.setText("");
        premiumHero("Eigene Inhalte verbinden", "Server-Login, Playlist-Link oder lokale Datei.", null, null);
        sectionTitle("Quelle wählen", "");
        cardAction("Server-Login", "Adresse und Zugangsdaten", this::promptServerLogin);
        cardAction("Playlist-Link", "M3U oder M3U8 verbinden", this::promptPlaylistLink);
        cardAction("Lokale Datei", "Vom Gerät auswählen", this::openPlaylistPicker);
        if (!display.isEmpty()) {
            sectionTitle("Aktive Bibliothek", "");
            cardInfo(importPreviewActive ? "Speicherung läuft" : "Bereit",
                    display.size() + " Inhalte · lokal geschützt");
            cardAction("Zur Startseite", "Bibliothek öffnen", () -> { screen = Screen.START; render(); });
        }
    }
''')

s = replace_method(s, "renderSettings", r'''
    private void renderSettings() {
        pageTitle.setText("Mehr");
        pageSubtitle.setText("");

        sectionTitle("Bibliothek", "");
        cardAction("Suche", "Sender, Filme und Serien", () -> { screen = Screen.SEARCH; render(); });
        cardAction("Favoriten", favoriteIds.size() + " gespeichert", () -> { screen = Screen.FAVORITES; render(); });
        cardAction("Programm", epgSnapshot.isEmpty() ? "EPG einrichten" : "Programmdaten öffnen",
                () -> { screen = Screen.EPG; render(); });

        sectionTitle("Profile & Schutz", "");
        cardAction("Profile", "Profil wechseln oder Kinderprofil verwalten",
                () -> startActivity(new Intent(this, ProfilesActivity.class)));
        cardAction("Aktivierung", "Softwarelizenz und Gerätecode",
                () -> startActivity(new Intent(this, ActivationActivity.class)));

        sectionTitle("Quellen", "");
        cardAction("Quelle verwalten", activeSourceFile.isBlank() ? "Noch keine Quelle" : "Bibliothek verbunden",
                () -> { screen = Screen.SOURCE; render(); });
        if (!epgSnapshot.isEmpty()) cardAction("EPG aktualisieren", "Programmdaten ersetzen", this::openEpgPicker);

        sectionTitle("System", "");
        cardAction("Systemstatus", "Diagnose und technische Details", this::openDiagnostics);
        cardAction("Diagnose teilen", "Bereinigte Logdatei senden", this::shareDiagnosticLog);
        cardInfo("Speicher", activeSourceFile.isBlank() ? "Keine Bibliothek gespeichert" : "Lokale Verschlüsselung aktiv");
        cardInfo("Profilinhalt", favoriteIds.size() + " Favoriten · "
                + new PlaybackStore(this).recent(500).size() + " Wiedergabeeinträge");
        cardAction("Wiedergabeverlauf löschen", "Nur für das aktive Profil", this::confirmClearPlaybackHistory);
        if (!epgSnapshot.isEmpty()) cardAction("EPG-Daten löschen", "Lokale Programmdaten entfernen", this::confirmClearEpg);
        cardAction("Lokale Daten löschen", "Bibliothek und Metadaten entfernen", this::confirmClearData);
        cardInfo("Version", "Project Lumen 13.1.33 · R7 Premium UI/UX");
    }
''')

s = replace_method(s, "cardAction", r'''
    private void cardAction(String title, String detail, Runnable action) {
        LinearLayout tile = card();
        tile.setOrientation(LinearLayout.HORIZONTAL);
        tile.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout copy = new LinearLayout(this);
        copy.setOrientation(LinearLayout.VERTICAL);
        copy.addView(text(title, television ? 21 : 17, TEXT, true));
        if (detail != null && !detail.isBlank()) {
            TextView info = text(detail, television ? 14 : 12, MUTED, false);
            info.setMaxLines(1);
            info.setPadding(0, dp(4), 0, 0);
            copy.addView(info);
        }
        tile.addView(copy, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        Button open = button("›", false);
        open.setOnClickListener(v -> action.run());
        tile.addView(open, new LinearLayout.LayoutParams(dp(television ? 52 : 44), dp(television ? 48 : 42)));
        tile.setOnClickListener(v -> action.run());
        attachPremiumFocus(tile);
        content.addView(tile, marginBottom(9));
    }
''')

s = replace_method(s, "cardInfo", r'''
    private void cardInfo(String title, String detail) {
        LinearLayout tile = card();
        tile.setBackground(PremiumUi.surface(this, false));
        tile.addView(text(title, television ? 19 : 16, TEXT, true));
        if (detail != null && !detail.isBlank()) {
            TextView info = text(detail, television ? 14 : 12, MUTED, false);
            info.setMaxLines(3);
            info.setPadding(0, dp(5), 0, 0);
            info.setTextIsSelectable(true);
            tile.addView(info);
        }
        content.addView(tile, marginBottom(9));
    }
''')

s = replace_method(s, "card", r'''
    private LinearLayout card() {
        LinearLayout tile = new LinearLayout(this);
        tile.setOrientation(LinearLayout.VERTICAL);
        tile.setPadding(dp(television ? 20 : 16), dp(television ? 18 : 15),
                dp(television ? 20 : 16), dp(television ? 18 : 15));
        tile.setBackground(PremiumUi.surface(this, false));
        tile.setClickable(true);
        tile.setFocusable(true);
        return tile;
    }
''')

s = replace_method(s, "button", r'''
    private Button button(String label, boolean primary) {
        Button control = new Button(this);
        control.setAllCaps(false);
        control.setText(label);
        control.setTextSize(television ? 16f : 14f);
        control.setTypeface(Typeface.DEFAULT_BOLD);
        control.setTextColor(primary ? BG : TEXT);
        control.setBackground(PremiumUi.button(this, primary, false));
        control.setPadding(dp(13), 0, dp(13), 0);
        control.setFocusable(true);
        control.setMinWidth(0);
        control.setOnFocusChangeListener((view, focused) -> {
            view.animate().scaleX(focused ? 1.035f : 1f).scaleY(focused ? 1.035f : 1f)
                    .translationZ(focused ? dp(7) : 0).setDuration(120L).start();
            control.setBackground(PremiumUi.button(this, primary, focused));
        });
        return control;
    }
''')

s = replace_method(s, "input", r'''
    private EditText input(String hint, boolean password) {
        EditText field = new EditText(this);
        field.setSingleLine(true);
        field.setHint(hint);
        field.setTextColor(TEXT);
        field.setHintTextColor(MUTED);
        field.setBackground(PremiumUi.surface(this, false));
        field.setPadding(dp(15), dp(10), dp(15), dp(10));
        field.setInputType(password ? InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD
                : InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        return field;
    }
''')

s = replace_method(s, "roundRect", r'''
    private GradientDrawable roundRect(int color, int radiusDp) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(color);
        drawable.setCornerRadius(dp(radiusDp));
        drawable.setStroke(dp(1), BORDER);
        return drawable;
    }
''')

s = replace_method(s, "gradientRect", r'''
    private GradientDrawable gradientRect(int startColor, int endColor, int radiusDp) {
        GradientDrawable drawable = new GradientDrawable(GradientDrawable.Orientation.TL_BR,
                new int[]{startColor, endColor});
        drawable.setCornerRadius(dp(radiusDp));
        drawable.setStroke(dp(1), 0x665C7592);
        return drawable;
    }
''')

copy_replacements = {
    'pageTitle.setText("Liste verwalten");': 'pageTitle.setText("Quellen");',
    'pageSubtitle.setText("Sender, Filme und Serien gemeinsam durchsuchen");': 'pageSubtitle.setText("Alles an einem Ort finden");',
    'input("Sender, Titel oder Gruppe suchen", false)': 'input("Sender, Film oder Serie", false)',
    'input("Sender, Film, Serie oder Gruppe", false)': 'input("Sender, Film oder Serie", false)',
    'cardInfo("Suchbegriff eingeben", "Die Suche läuft vollständig lokal im Katalog. Es wird kein Suchtext an einen Server übertragen.");':
        'cardInfo("Wonach suchst du?", "Sender, Film oder Serie eingeben.");',
    'pageSubtitle.setText(favorites.size() + " gespeicherte Favoriten · lokal auf diesem Gerät");':
        'pageSubtitle.setText(favorites.size() + " Favoriten");',
    'cardInfo("Bedienung", "Antippen startet die Wiedergabe. Länger drücken entfernt einen Eintrag wieder aus den Favoriten.");':
        'cardInfo("Tipp", "Lange drücken entfernt einen Favoriten.");',
    'cardInfo("Noch keine passenden Einträge erkannt", "Project Lumen ordnet den Bereich im POC anhand von Streampfad und Gruppenname zu. Die Liste bleibt unverändert gespeichert.");':
        'cardInfo("Noch keine Inhalte", "Andere Sprache oder Quelle wählen.");',
}
for old, new in copy_replacements.items():
    s = s.replace(old, new)

s = s.replace('diagnosticFab = button("Diagnose", true);', 'diagnosticFab = button("Systemstatus", false);')
s = s.replace('playerDiagnosticButton = button("Diagnose", true);', 'playerDiagnosticButton = button("Status", false);')
s = s.replace('view.setBackground(roundRect(SURFACE, 14));\n            view.setPadding(dp(14), dp(8), dp(14), dp(8));',
              'view.setBackground(PremiumUi.surface(MainActivity.this, false));\n            view.setPadding(dp(16), dp(11), dp(16), dp(11));\n            view.setFocusable(true);')

for filename in ("MediaDetailActivity.java", "SeriesActivity.java", "ProfilesActivity.java", "ActivationActivity.java"):
    path = pkg / filename
    if not path.exists():
        raise SystemExit(f"R7 secondary screen missing: {filename}")
    text = path.read_text(encoding="utf-8")
    text = text.replace("setContentView(scroll);", "setContentView(PremiumUi.frame(this, scroll));")
    text = text.replace("setBackgroundColor(BG);", "setBackgroundColor(0x00000000);")
    text = text.replace("setBackgroundColor(Color.rgb(7, 9, 14));", "setBackgroundColor(0x00000000);")
    text = text.replace("setBackgroundColor(SURFACE);", "setBackground(PremiumUi.surface(this, false));")
    text = text.replace("setBackgroundColor(Color.rgb(25, 30, 41));", "setBackground(PremiumUi.surface(this, false));")
    text = text.replace("private static final int BG = 0xFF05070B", "private static final int BG = PremiumUi.BG")
    text = text.replace("SURFACE = 0xFF141A24", "SURFACE = PremiumUi.SURFACE")
    text = text.replace("TEXT = 0xFFF7F9FC", "TEXT = PremiumUi.TEXT")
    text = text.replace("MUTED = 0xFFA7B0BE", "MUTED = PremiumUi.MUTED")
    path.write_text(text, encoding="utf-8")

if "private String timeGreeting()" not in s:
    s = insert_before_class_end(s, r'''
    private String timeGreeting() {
        int hour = java.time.LocalTime.now().getHour();
        if (hour < 11) return "Guten Morgen";
        if (hour < 18) return "Guten Tag";
        return "Guten Abend";
    }
''')

main.write_text(s, encoding="utf-8")

checks = {
    "version": "Project Lumen 13.1.33" in s,
    "background": "new PremiumBackgroundView(this)" in s,
    "bottom_or_rail_nav": "shell.setOrientation(television ? LinearLayout.HORIZONTAL : LinearLayout.VERTICAL)" in s,
    "five_nav": '"•••\\nMehr"' in s and '"▤\\nSerien"' in s,
    "short_start": 'premiumHero("Bereit zum Streamen"' in s,
    "vector_flags": "new CountryFlagView(this, flag)" in s,
    "diagnostics_retained": "private void openDiagnostics()" in s and 'diagnosticFab = button("Systemstatus", false);' in s,
    "r2_retained": "openPremiumMedia(channel)" in s and "continueWatchingChannels(display)" in s,
    "r4_retained": "ProfileStore.activeName(this)" in s and "ParentalPolicy.filter" in s,
    "r5_retained": "ActivationActivity.class" in s,
    "versionCode": "versionCode 134300" in g,
}
missing = [name for name, passed in checks.items() if not passed]
if missing:
    raise SystemExit("R7 integration checks failed: " + ", ".join(missing))
print("R7 premium UI/UX integration applied: " + ", ".join(checks))
