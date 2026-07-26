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
support = Path(__file__).resolve().parent / "r7-1-src"
helper = support / "ResponsiveUi.java"

for path in (main, gradle, helper):
    if not path.exists():
        raise SystemExit(f"missing R7.1 input: {path}")
shutil.copy2(helper, pkg / helper.name)


def method_span(text: str, name: str) -> tuple[int, int]:
    pattern = re.compile(
        rf"(?m)^    (?:public|private|protected)\s+(?:static\s+)?[\w<>\[\], ?.]+\s+{re.escape(name)}\s*\([^;{{}}]*\)\s*\{{")
    match = pattern.search(text)
    if not match:
        raise SystemExit(f"method not found: {name}")
    opening = text.find("{", match.start(), match.end())
    depth = 0
    index = opening
    state = "code"
    while index < len(text):
        char = text[index]
        nxt = text[index + 1] if index + 1 < len(text) else ""
        if state == "code":
            if char == '"': state = "string"
            elif char == "'": state = "char"
            elif char == "/" and nxt == "/": state = "line"; index += 1
            elif char == "/" and nxt == "*": state = "block"; index += 1
            elif char == "{": depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0: return match.start(), index + 1
        elif state == "string":
            if char == "\\": index += 1
            elif char == '"': state = "code"
        elif state == "char":
            if char == "\\": index += 1
            elif char == "'": state = "code"
        elif state == "line":
            if char == "\n": state = "code"
        elif state == "block":
            if char == "*" and nxt == "/": state = "code"; index += 1
        index += 1
    raise SystemExit(f"unterminated method: {name}")


def replace_method(text: str, name: str, replacement: str) -> str:
    start, end = method_span(text, name)
    return text[:start] + replacement.strip("\n") + text[end:]


g = gradle.read_text(encoding="utf-8")
g = re.sub(r"versionCode\s+\d+", "versionCode 134400", g, count=1)
g = re.sub(r"versionName\s+'[^']+'", "versionName '13.1.34-r7.1-responsive-typography-pilot'", g, count=1)
gradle.write_text(g, encoding="utf-8")

s = main.read_text(encoding="utf-8")
s = s.replace('text("13.1.33"', 'text("13.1.34"')
s = s.replace('Project Lumen 13.1.33 · R7 Premium UI/UX',
              'Project Lumen 13.1.34 · R7.1 Responsive UI')

s = replace_method(s, "buildMainUi", r'''
    private void buildMainUi() {
        final boolean compact = ResponsiveUi.compact(this);
        final boolean large = ResponsiveUi.large(this);
        PremiumBackgroundView background = new PremiumBackgroundView(this);
        root.addView(background, match());

        LinearLayout shell = new LinearLayout(this);
        shell.setOrientation(television ? LinearLayout.HORIZONTAL : LinearLayout.VERTICAL);
        int shellSide = television ? 18 : (compact ? 8 : (large ? 16 : 12));
        int shellTop = television ? 18 : (compact ? 7 : 10);
        shell.setPadding(dp(shellSide), dp(shellTop), dp(shellSide), dp(compact ? 7 : 10));
        shell.setBackgroundColor(Color.TRANSPARENT);
        root.addView(shell, match());

        nav = new LinearLayout(this);
        nav.setOrientation(television ? LinearLayout.VERTICAL : LinearLayout.HORIZONTAL);
        nav.setGravity(television ? Gravity.TOP : Gravity.CENTER_VERTICAL);
        nav.setPadding(dp(television ? 10 : 4), dp(television ? 14 : 4),
                dp(television ? 10 : 4), dp(television ? 14 : 4));
        nav.setBackground(PremiumUi.surface(this, false));

        page = new LinearLayout(this);
        page.setOrientation(LinearLayout.VERTICAL);
        int pageSide = television ? 26 : (compact ? 8 : (large ? 14 : 10));
        page.setPadding(dp(pageSide), dp(television ? 8 : 3), dp(pageSide), 0);
        page.setBackgroundColor(Color.TRANSPARENT);

        if (television) {
            shell.addView(nav, new LinearLayout.LayoutParams(dp(205), ViewGroup.LayoutParams.MATCH_PARENT));
            LinearLayout.LayoutParams pageParams = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f);
            pageParams.setMargins(dp(14), 0, 0, 0);
            shell.addView(page, pageParams);
        } else {
            shell.addView(page, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));
            int navHeight = compact ? 58 : (large ? 68 : 63);
            LinearLayout.LayoutParams navParams = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(navHeight));
            navParams.setMargins(0, dp(compact ? 6 : 8), 0, 0);
            shell.addView(nav, navParams);
        }

        LinearLayout brand = new LinearLayout(this);
        brand.setOrientation(LinearLayout.VERTICAL);
        TextView logo = text("LUMEN", ResponsiveUi.sp(this, 25, 27, 30, 29), TEXT, true);
        logo.setLetterSpacing(compact ? 0.11f : 0.14f);
        ResponsiveUi.singleLine(logo);
        brand.addView(logo);
        TextView brandLine = text("Deine Medien", ResponsiveUi.sp(this, 11, 12, 13, 14), MUTED, false);
        ResponsiveUi.singleLine(brandLine);
        brand.addView(brandLine);

        Button searchQuick = button("⌕", false);
        searchQuick.setContentDescription("Suche öffnen");
        searchQuick.setOnClickListener(v -> { screen = Screen.SEARCH; render(); });

        Button profileQuick = button("◉  " + ProfileStore.activeName(this), false);
        profileQuick.setContentDescription("Profile und Jugendschutz");
        profileQuick.setOnClickListener(v -> startActivity(new Intent(this, ProfilesActivity.class)));
        ResponsiveUi.singleLine(profileQuick);

        if (compact) {
            LinearLayout header = new LinearLayout(this);
            header.setOrientation(LinearLayout.VERTICAL);
            LinearLayout top = new LinearLayout(this);
            top.setOrientation(LinearLayout.HORIZONTAL);
            top.setGravity(Gravity.CENTER_VERTICAL);
            top.addView(brand, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
            top.addView(searchQuick, new LinearLayout.LayoutParams(dp(42), dp(42)));
            header.addView(top, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT));
            LinearLayout.LayoutParams profileParams = new LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT, dp(42));
            profileParams.setMargins(0, dp(8), 0, 0);
            header.addView(profileQuick, profileParams);
            page.addView(header, marginBottom(12));
        } else {
            LinearLayout header = new LinearLayout(this);
            header.setOrientation(LinearLayout.HORIZONTAL);
            header.setGravity(Gravity.CENTER_VERTICAL);
            header.addView(brand, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
            header.addView(searchQuick, new LinearLayout.LayoutParams(dp(television ? 58 : 44), dp(television ? 52 : 44)));
            LinearLayout.LayoutParams profileParams = new LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.WRAP_CONTENT, dp(television ? 52 : 44));
            profileParams.setMargins(dp(8), 0, 0, 0);
            profileQuick.setMaxWidth(dp(television ? 250 : (large ? 190 : 155)));
            header.addView(profileQuick, profileParams);
            page.addView(header, marginBottom(television ? 18 : 13));
        }

        pageTitle = text("", ResponsiveUi.sp(this, 27, 30, 34, 36), TEXT, true);
        ResponsiveUi.polish(pageTitle, 2);
        page.addView(pageTitle);
        pageSubtitle = text("", ResponsiveUi.sp(this, 13, 14, 15, 16), MUTED, false);
        ResponsiveUi.polish(pageSubtitle, 2);
        pageSubtitle.setPadding(0, dp(4), 0, dp(compact ? 9 : 11));
        page.addView(pageSubtitle);

        contentScroll = new ScrollView(this);
        contentScroll.setFillViewport(true);
        contentScroll.setOverScrollMode(View.OVER_SCROLL_NEVER);
        content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(0, 0, 0, dp(compact ? 10 : 16));
        contentScroll.addView(content);
        page.addView(contentScroll, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));
        render();
    }
''')

s = replace_method(s, "rebuildNav", r'''
    private void rebuildNav() {
        nav.removeAllViews();
        addNavAction(television ? "⌂  Start" : "⌂ Start", "start", () -> { screen = Screen.START; render(); });
        if (hasDisplayChannels()) {
            addNavAction(television ? "●  Live" : "● Live", "live", () -> openMedia(MediaSection.LIVE));
            addNavAction(television ? "◆  Filme" : "◆ Filme", "vod", () -> openMedia(MediaSection.VOD));
            addNavAction(television ? "▤  Serien" : "▤ Serien", "series", () -> openMedia(MediaSection.SERIES));
        }
        addNavAction(television ? "•••  Mehr" : "••• Mehr", "more", () -> { screen = Screen.SETTINGS; render(); });
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
        ResponsiveUi.singleLine(item);
        ResponsiveUi.setSp(item, hasDisplayChannels() ? 11 : 13,
                hasDisplayChannels() ? 12 : 14, 14, 16);
        item.setOnFocusChangeListener((view, focused) -> {
            view.animate().scaleX(focused ? 1.03f : 1f).scaleY(focused ? 1.03f : 1f)
                    .translationZ(focused ? dp(8) : 0).setDuration(115L).start();
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
            premiumHero("Deine Medien", "Quelle hinzufügen und loslegen.",
                    "Quelle hinzufügen", () -> { screen = Screen.SOURCE; render(); });
            sectionTitle("Schnell starten", "");
            cardAction("Lokales Video", "Direkt vom Gerät abspielen", this::openVideoPicker);
            cardInfo("Lokal & privat", "Nur eigene Quellen verwenden.");
            return;
        }

        HomeSnapshot home = buildHomeSnapshot(display);
        pageSubtitle.setText(ProfileStore.activeName(this) + " · " + display.size() + " Inhalte");
        premiumHero("Bereit", home.liveCount + " Live · " + home.vodCount + " Filme · "
                + home.seriesCount + " Serien", "Live öffnen", () -> openMedia(MediaSection.LIVE));
        premiumMediaRow("Weiterschauen", "", continueWatchingChannels(display));
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
        boolean compact = ResponsiveUi.compact(this);
        LinearLayout hero = card();
        hero.setPadding(dp(television ? 34 : (compact ? 18 : 23)),
                dp(television ? 31 : (compact ? 19 : 24)),
                dp(television ? 34 : (compact ? 18 : 23)),
                dp(television ? 31 : (compact ? 19 : 24)));
        hero.setBackground(PremiumUi.hero(this));
        TextView eyebrow = text("PROJECT LUMEN", ResponsiveUi.sp(this, 10, 11, 12, 14), PRIMARY, true);
        eyebrow.setLetterSpacing(compact ? 0.10f : 0.14f);
        ResponsiveUi.singleLine(eyebrow);
        hero.addView(eyebrow);
        TextView headline = text(title, ResponsiveUi.sp(this, 25, 29, 33, 40), TEXT, true);
        headline.setPadding(0, dp(compact ? 8 : 10), 0, dp(7));
        ResponsiveUi.polish(headline, 2);
        hero.addView(headline);
        if (detail != null && !detail.isBlank()) {
            TextView copy = text(detail, ResponsiveUi.sp(this, 14, 15, 16, 18), 0xFFD8E4EB, false);
            ResponsiveUi.polish(copy, 2);
            hero.addView(copy);
        }
        if (actionLabel != null && action != null) {
            Button primary = button(actionLabel + "  ›", true);
            primary.setOnClickListener(v -> action.run());
            ResponsiveUi.singleLine(primary);
            LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                    compact ? ViewGroup.LayoutParams.MATCH_PARENT : ViewGroup.LayoutParams.WRAP_CONTENT,
                    dp(television ? 58 : (compact ? 48 : 52)));
            params.setMargins(0, dp(compact ? 15 : 19), 0, 0);
            hero.addView(primary, params);
            hero.setOnClickListener(v -> action.run());
        }
        content.addView(hero, marginBottom(compact ? 16 : 20));
    }
''')

s = replace_method(s, "sectionTitle", r'''
    private void sectionTitle(String title, String detail) {
        TextView heading = text(title, ResponsiveUi.sp(this, 19, 21, 23, 27), TEXT, true);
        ResponsiveUi.polish(heading, 2);
        heading.setPadding(0, dp(2), 0, detail == null || detail.isBlank() ? dp(9) : dp(2));
        content.addView(heading);
        if (detail != null && !detail.isBlank()) {
            TextView sub = text(detail, ResponsiveUi.sp(this, 12, 13, 14, 15), MUTED, false);
            ResponsiveUi.polish(sub, 2);
            sub.setPadding(0, 0, 0, dp(9));
            content.addView(sub);
        }
    }
''')

s = replace_method(s, "addLanguageHubCard", r'''
    private void addLanguageHubCard(LinearLayout row, String flag, String title, HomeSnapshot home,
                                    LanguageHub hub, int startColor, int endColor) {
        boolean compact = ResponsiveUi.compact(this);
        LinearLayout tile = new LinearLayout(this);
        tile.setOrientation(LinearLayout.VERTICAL);
        tile.setGravity(Gravity.BOTTOM);
        tile.setPadding(dp(television ? 19 : (compact ? 13 : 15)), dp(television ? 18 : 14),
                dp(television ? 19 : (compact ? 13 : 15)), dp(television ? 18 : 14));
        tile.setBackground(gradientRect(startColor, endColor, compact ? 19 : 23));
        tile.setClickable(true);
        tile.setFocusable(true);
        attachPremiumFocus(tile);
        CountryFlagView flagView = new CountryFlagView(this, flag);
        tile.addView(flagView, new LinearLayout.LayoutParams(dp(television ? 70 : (compact ? 52 : 58)),
                dp(television ? 44 : (compact ? 32 : 36))));
        TextView label = text(title, ResponsiveUi.sp(this, 17, 18, 20, 22), TEXT, true);
        ResponsiveUi.polish(label, 1);
        label.setPadding(0, dp(10), 0, dp(3));
        tile.addView(label);
        String counts = home.count(hub, MediaSection.LIVE) + " Live · "
                + home.count(hub, MediaSection.VOD) + " Filme · "
                + home.count(hub, MediaSection.SERIES) + " Serien";
        TextView summary = text(counts, ResponsiveUi.sp(this, 10, 11, 12, 14), 0xFFE0E9EF, false);
        ResponsiveUi.polish(summary, 2);
        tile.addView(summary);
        tile.setOnClickListener(v -> openLanguageHub(hub));
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                dp(television ? 270 : (compact ? 172 : 190)),
                dp(television ? 174 : (compact ? 128 : 140)));
        params.setMargins(row.getChildCount() == 0 ? 0 : dp(compact ? 8 : 10), 0, 0, 0);
        row.addView(tile, params);
    }
''')

s = replace_method(s, "addPremiumMediaCard", r'''
    private void addPremiumMediaCard(LinearLayout row, Channel channel) {
        boolean portrait = channel.section != MediaSection.LIVE;
        boolean compact = ResponsiveUi.compact(this);
        int cardWidth = television ? (portrait ? 220 : 310)
                : compact ? (portrait ? 142 : 194) : (portrait ? 160 : 218);
        int artworkHeight = television ? (portrait ? 292 : 176)
                : compact ? (portrait ? 196 : 108) : (portrait ? 220 : 122);
        LinearLayout tile = new LinearLayout(this);
        tile.setOrientation(LinearLayout.VERTICAL);
        tile.setBackground(PremiumUi.surface(this, true));
        tile.setClickable(true);
        tile.setFocusable(true);
        tile.setClipToOutline(false);
        attachPremiumFocus(tile);
        FrameLayout artwork = new FrameLayout(this);
        artwork.setBackground(gradientRect(artworkStart(channel.hub), artworkEnd(channel.hub), compact ? 17 : 20));
        artwork.setClipToOutline(true);
        ImageView image = new ImageView(this);
        image.setScaleType(portrait ? ImageView.ScaleType.CENTER_CROP : ImageView.ScaleType.FIT_CENTER);
        image.setContentDescription(channel.name);
        image.setPadding(portrait ? 0 : dp(12), portrait ? 0 : dp(7), portrait ? 0 : dp(12), portrait ? 0 : dp(7));
        artwork.addView(image, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT));
        TextView favorite = text(isFavorite(channel) ? "★" : "☆", ResponsiveUi.sp(this, 14, 15, 16, 18), TEXT, true);
        favorite.setGravity(Gravity.CENTER);
        favorite.setBackground(roundRect(0xB807111B, 16));
        FrameLayout.LayoutParams favoriteParams = new FrameLayout.LayoutParams(dp(television ? 40 : 32),
                dp(television ? 35 : 29), Gravity.TOP | Gravity.START);
        favoriteParams.setMargins(dp(8), dp(8), 0, 0);
        artwork.addView(favorite, favoriteParams);
        String badgeText = channel.section == MediaSection.LIVE ? "LIVE" : languageFlag(channel.hub);
        TextView badge = text(badgeText, ResponsiveUi.sp(this, 10, 11, 12, 14),
                channel.section == MediaSection.LIVE ? BG : TEXT, true);
        badge.setGravity(Gravity.CENTER);
        badge.setBackground(roundRect(channel.section == MediaSection.LIVE ? PRIMARY : 0xB807111B, 16));
        FrameLayout.LayoutParams badgeParams = new FrameLayout.LayoutParams(
                channel.section == MediaSection.LIVE ? dp(television ? 58 : 46) : dp(television ? 42 : 33),
                dp(television ? 35 : 29), Gravity.TOP | Gravity.END);
        badgeParams.setMargins(0, dp(8), dp(8), 0);
        artwork.addView(badge, badgeParams);
        tile.addView(artwork, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(artworkHeight)));
        loadArtwork(image, channel);
        LinearLayout body = new LinearLayout(this);
        body.setOrientation(LinearLayout.VERTICAL);
        body.setPadding(dp(compact ? 11 : 14), dp(compact ? 10 : 12), dp(compact ? 11 : 14), dp(compact ? 11 : 14));
        TextView name = text(channel.name, ResponsiveUi.sp(this, 14, 15, 16, 19), TEXT, true);
        ResponsiveUi.polish(name, 2);
        body.addView(name);
        String metaText = channel.section == MediaSection.LIVE && !epgSnapshot.isEmpty()
                ? formatEpgLine(channel, System.currentTimeMillis()) : languageLabel(channel.hub);
        TextView meta = text(metaText, ResponsiveUi.sp(this, 10, 11, 12, 13), MUTED, false);
        ResponsiveUi.polish(meta, 1);
        meta.setPadding(0, dp(4), 0, 0);
        body.addView(meta);
        tile.addView(body);
        tile.setOnClickListener(v -> openPremiumMedia(channel));
        tile.setOnLongClickListener(v -> { toggleFavorite(channel); render(); return true; });
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(dp(cardWidth), ViewGroup.LayoutParams.WRAP_CONTENT);
        params.setMargins(row.getChildCount() == 0 ? 0 : dp(compact ? 8 : 11), 0, 0, dp(7));
        row.addView(tile, params);
    }
''')

s = replace_method(s, "cardAction", r'''
    private void cardAction(String title, String detail, Runnable action) {
        boolean compact = ResponsiveUi.compact(this);
        LinearLayout tile = card();
        tile.setOrientation(LinearLayout.HORIZONTAL);
        tile.setGravity(Gravity.CENTER_VERTICAL);
        tile.setMinimumHeight(dp(compact ? 84 : (television ? 98 : 92)));
        LinearLayout copy = new LinearLayout(this);
        copy.setOrientation(LinearLayout.VERTICAL);
        copy.setPadding(0, 0, dp(8), 0);
        TextView titleView = text(title, ResponsiveUi.sp(this, 17, 18, 20, 21), TEXT, true);
        ResponsiveUi.polish(titleView, 2);
        copy.addView(titleView);
        if (detail != null && !detail.isBlank()) {
            TextView info = text(detail, ResponsiveUi.sp(this, 13, 14, 15, 14), MUTED, false);
            ResponsiveUi.polish(info, 2);
            info.setPadding(0, dp(5), 0, 0);
            copy.addView(info);
        }
        tile.addView(copy, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        Button open = button("›", false);
        open.setOnClickListener(v -> action.run());
        tile.addView(open, new LinearLayout.LayoutParams(dp(television ? 52 : 40), dp(television ? 48 : 40)));
        tile.setOnClickListener(v -> action.run());
        attachPremiumFocus(tile);
        content.addView(tile, marginBottom(compact ? 8 : 9));
    }
''')

s = replace_method(s, "cardInfo", r'''
    private void cardInfo(String title, String detail) {
        LinearLayout tile = card();
        tile.setBackground(PremiumUi.surface(this, false));
        TextView titleView = text(title, ResponsiveUi.sp(this, 16, 17, 19, 19), TEXT, true);
        ResponsiveUi.polish(titleView, 2);
        tile.addView(titleView);
        if (detail != null && !detail.isBlank()) {
            TextView info = text(detail, ResponsiveUi.sp(this, 13, 14, 15, 14), MUTED, false);
            ResponsiveUi.polish(info, 3);
            info.setPadding(0, dp(5), 0, 0);
            info.setTextIsSelectable(true);
            tile.addView(info);
        }
        content.addView(tile, marginBottom(ResponsiveUi.compact(this) ? 8 : 9));
    }
''')

s = replace_method(s, "card", r'''
    private LinearLayout card() {
        boolean compact = ResponsiveUi.compact(this);
        LinearLayout tile = new LinearLayout(this);
        tile.setOrientation(LinearLayout.VERTICAL);
        tile.setPadding(dp(television ? 20 : (compact ? 14 : 16)),
                dp(television ? 18 : (compact ? 13 : 15)),
                dp(television ? 20 : (compact ? 14 : 16)),
                dp(television ? 18 : (compact ? 13 : 15)));
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
        control.setTextSize(android.util.TypedValue.COMPLEX_UNIT_SP,
                ResponsiveUi.sp(this, 13, 14, 15, 16));
        control.setTypeface(Typeface.DEFAULT_BOLD);
        control.setTextColor(primary ? BG : TEXT);
        control.setBackground(PremiumUi.button(this, primary, false));
        control.setPadding(dp(ResponsiveUi.compact(this) ? 11 : 13), 0,
                dp(ResponsiveUi.compact(this) ? 11 : 13), 0);
        control.setFocusable(true);
        control.setMinWidth(0);
        control.setMinHeight(dp(48));
        control.setGravity(Gravity.CENTER);
        control.setOnFocusChangeListener((view, focused) -> {
            view.animate().scaleX(focused ? 1.03f : 1f).scaleY(focused ? 1.03f : 1f)
                    .translationZ(focused ? dp(7) : 0).setDuration(110L).start();
            control.setBackground(PremiumUi.button(this, primary, focused));
        });
        return control;
    }
''')

s = replace_method(s, "text", r'''
    private TextView text(String value, int size, int color, boolean bold) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(android.util.TypedValue.COMPLEX_UNIT_SP, size);
        view.setTextColor(color);
        view.setIncludeFontPadding(false);
        view.setLineSpacing(0f, 1.08f);
        if (bold) view.setTypeface(Typeface.DEFAULT_BOLD);
        if (android.os.Build.VERSION.SDK_INT >= 23) {
            view.setBreakStrategy(android.text.Layout.BREAK_STRATEGY_HIGH_QUALITY);
            view.setHyphenationFrequency(android.text.Layout.HYPHENATION_FREQUENCY_NONE);
        }
        return view;
    }
''')

s = replace_method(s, "input", r'''
    private EditText input(String hint, boolean password) {
        EditText field = new EditText(this);
        field.setSingleLine(true);
        field.setHint(hint);
        field.setTextSize(android.util.TypedValue.COMPLEX_UNIT_SP,
                ResponsiveUi.sp(this, 15, 16, 17, 18));
        field.setTextColor(TEXT);
        field.setHintTextColor(MUTED);
        field.setBackground(PremiumUi.surface(this, false));
        field.setPadding(dp(15), dp(10), dp(15), dp(10));
        field.setMinHeight(dp(48));
        field.setInputType(password ? InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD
                : InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        return field;
    }
''')

# Polish secondary screens without changing their feature flows.
for filename in ("MediaDetailActivity.java", "SeriesActivity.java", "ProfilesActivity.java", "ActivationActivity.java"):
    path = pkg / filename
    if not path.exists():
        raise SystemExit(f"R7.1 secondary screen missing: {filename}")
    text = path.read_text(encoding="utf-8")
    text = text.replace("root.setPadding(dp(28), dp(24), dp(28), dp(40));",
                        "int side = ResponsiveUi.sidePaddingDp(this); root.setPadding(dp(side), dp(ResponsiveUi.compact(this) ? 18 : 24), dp(side), dp(32));")
    text = text.replace("text(title, tv() ? 34 : 28", "text(title, ResponsiveUi.sp(this, 26, 29, 32, 34)")
    text = text.replace("text(selection.title, tv() ? 34 : 28", "text(selection.title, ResponsiveUi.sp(this, 26, 29, 32, 34)")
    text = text.replace('text("Profile", 34', 'text("Profile", ResponsiveUi.sp(this, 27, 30, 33, 34)')
    text = text.replace('text("Aktivierung & Softwarelizenz", 30',
                        'text("Aktivierung & Softwarelizenz", ResponsiveUi.sp(this, 24, 27, 30, 32)')
    text = text.replace("button.setTextSize(17);", "button.setTextSize(ResponsiveUi.sp(this, 15, 16, 17, 18));")
    text = text.replace("b.setTextSize(tv() ? 18 : 16);", "b.setTextSize(ResponsiveUi.sp(this, 15, 16, 17, 18));")
    text = text.replace("b.setTextSize(16);", "b.setTextSize(ResponsiveUi.sp(this, 15, 16, 17, 18));")
    text = text.replace("text.setTextSize(size);", "text.setTextSize(size); text.setIncludeFontPadding(false); text.setLineSpacing(0f, 1.08f);")
    text = text.replace("v.setTextSize(size);", "v.setTextSize(size); v.setIncludeFontPadding(false); v.setLineSpacing(0f, 1.08f);")
    path.write_text(text, encoding="utf-8")

main.write_text(s, encoding="utf-8")

checks = {
    "version": "Project Lumen 13.1.34" in s,
    "helper": (pkg / "ResponsiveUi.java").exists(),
    "compact_header": "if (compact)" in s and "header.addView(profileQuick, profileParams)" in s,
    "brand_single_line": "ResponsiveUi.singleLine(logo)" in s,
    "short_hero": 'premiumHero("Deine Medien", "Quelle hinzufügen und loslegen."' in s,
    "responsive_title": "ResponsiveUi.sp(this, 27, 30, 34, 36)" in s,
    "compact_nav": '"⌂ Start"' in s and "int navHeight = compact ? 58" in s,
    "safe_cards": "tile.setMinimumHeight(dp(compact ? 84" in s,
    "version_code": "versionCode 134400" in g,
}
missing = [name for name, passed in checks.items() if not passed]
if missing:
    raise SystemExit("R7.1 integration checks failed: " + ", ".join(missing))
print("R7.1 responsive typography integration applied: " + ", ".join(checks))
