from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected one match, got {count}')
    path.write_text(text.replace(old, new, 1), encoding='utf-8')

main = ROOT / 'app/src/main/java/com/projectlumen/pilot/robust/MainActivity.java'
adapter = ROOT / 'app/src/main/java/com/projectlumen/pilot/robust/CatalogAdapter.java'
manifest = ROOT / 'app/src/main/AndroidManifest.xml'
build = ROOT / 'app/build.gradle'
strings = ROOT / 'app/src/main/res/values/strings.xml'

replace_once(main,
'''    private Button allLanguageButton;
    private Button germanButton;
    private Button turkishButton;
''',
'''    private Button allLanguageButton;
    private Button germanButton;
    private Button turkishButton;
    private TextView parentalHint;
    private Button parentalButton;
    private ParentalUiController parental;
''', 'main fields')

replace_once(main,
'''        preferences = getSharedPreferences(PREFS, MODE_PRIVATE);
        restoreViewState();
''',
'''        preferences = getSharedPreferences(PREFS, MODE_PRIVATE);
        if (state == null) ParentalControl.lockSession();
        restoreViewState();
''', 'default lock')

replace_once(main,
'''        restore();
    }

    private void restoreViewState() {
''',
'''        restore();
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (parental != null) parental.refresh(true);
    }

    private void restoreViewState() {
''', 'on resume')

replace_once(main,
'''        LinearLayout.LayoutParams languageParams = new LinearLayout.LayoutParams(-1, dp(tv() ? 46 : 39));
        languageParams.setMargins(0, dp(7), 0, dp(9));
        root.addView(languages, languageParams);

        LinearLayout searchBar = new LinearLayout(this);
''',
'''        LinearLayout.LayoutParams languageParams = new LinearLayout.LayoutParams(-1, dp(tv() ? 46 : 39));
        languageParams.setMargins(0, dp(7), 0, dp(7));
        root.addView(languages, languageParams);

        LinearLayout safety = new LinearLayout(this);
        safety.setGravity(Gravity.CENTER_VERTICAL);
        safety.setPadding(dp(11), 0, dp(5), 0);
        safety.setBackground(roundRect(0xC80A1A28, 13, 0xFF264B60));
        parentalHint = text("Erwachsenen-Inhalte verborgen", tv() ? 13 : 10,
                TEXT_SECONDARY, false);
        parentalHint.setSingleLine(true);
        parentalHint.setEllipsize(TextUtils.TruncateAt.END);
        safety.addView(parentalHint, new LinearLayout.LayoutParams(0, -2, 1f));
        parentalButton = actionButton("🔒 Kinderfilter", false);
        safety.addView(parentalButton, new LinearLayout.LayoutParams(-2, dp(tv() ? 40 : 34)));
        LinearLayout.LayoutParams safetyParams = new LinearLayout.LayoutParams(-1,
                dp(tv() ? 47 : 40));
        safetyParams.setMargins(0, 0, 0, dp(8));
        root.addView(safety, safetyParams);

        LinearLayout searchBar = new LinearLayout(this);
''', 'safety row')

replace_once(main,
'''        root.addView(footerStatus);
        updateSelectionStyles();
''',
'''        root.addView(footerStatus);
        updateSelectionStyles();
        parental = new ParentalUiController(this, log, parentalButton,
                parentalHint, this::filterNow);
''', 'controller init')

replace_once(main,
'''    private void finishImport(String interaction, List<Channel> result) {
        all = result;
        search.setText("");
        mode = Mode.LIVE;
        language = MediaLanguage.Code.ALL;
        saveViewState();
        updateSelectionStyles();
''',
'''    private void finishImport(String interaction, List<Channel> result) {
        ParentalControl.clearClassificationCache();
        all = result;
        search.setText("");
        mode = Mode.LIVE;
        language = MediaLanguage.Code.ALL;
        ParentalControl.lockSession();
        saveViewState();
        updateSelectionStyles();
        if (parental != null) parental.refresh(false);
''', 'import relock')

old_select = '''    private void select(int position) {
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
'''
new_select = '''    private void select(int position) {
        Channel channel = adapter.item(position);
        if (channel == null) return;
        String interaction = log.newInteractionId();
        long delay = lastInputEvent <= 0 ? 0 : Math.max(0,
                SystemClock.uptimeMillis() - lastInputEvent);
        log.event(interaction, "INPUT-DELIVERED",
                "deliveryDelayMs=" + delay + " position=" + position);
        log.event(interaction, "SELECTION-VALIDATE-START",
                "item=" + log.anonymousId(channel.id));
        boolean adult = ParentalControl.isAdult(channel);
        if (adult && !ParentalControl.isSessionUnlocked()) {
            log.event(interaction, "PARENTAL-CONTENT-BLOCKED",
                    "reason=adult-session-locked type=" + channel.type);
            parental.requestUnlock(() -> startChannel(channel, interaction, true));
            return;
        }
        startChannel(channel, interaction, adult);
    }

    private void startChannel(Channel channel, String interaction, boolean adult) {
        if (channel.url.isBlank()) {
            log.event(interaction, "SELECTION-INVALID", "reason=empty-url");
            Toast.makeText(this, "Dieser Eintrag enthält keine Stream-Adresse.",
                    Toast.LENGTH_LONG).show();
            return;
        }
        if (adult) ParentalControl.touchSession();
        log.event(interaction, "SELECTION-VALIDATE-OK", "type=" + channel.type
                + " language=" + MediaLanguage.detect(channel)
                + " adultAllowed=" + adult);
        Intent intent = new Intent(this, PlayerActivity.class);
        intent.putExtra(PlayerActivity.EXTRA_URL, channel.url);
        intent.putExtra(PlayerActivity.EXTRA_NAME, channel.name);
        intent.putExtra(PlayerActivity.EXTRA_INTERACTION, interaction);
        intent.putExtra(ParentalControl.EXTRA_ADULT_CONTENT, adult);
        startActivity(intent);
    }
'''
replace_once(main, old_select, new_select, 'selection guard')

replace_once(main,
'''        MediaLanguage.Code wantedLanguage = language;
        String query = search.getText().toString().trim();
''',
'''        MediaLanguage.Code wantedLanguage = language;
        boolean adultAllowed = ParentalControl.isSessionUnlocked();
        String query = search.getText().toString().trim();
''', 'filter state')

replace_once(main,
'''        log.event("-", "LIST-SNAPSHOT-REQUEST", "mode=" + wantedMode
                + " language=" + wantedLanguage + " base=" + base.size()
                + " queryLength=" + query.length());
''',
'''        log.event("-", "LIST-SNAPSHOT-REQUEST", "mode=" + wantedMode
                + " language=" + wantedLanguage + " base=" + base.size()
                + " queryLength=" + query.length()
                + " parental=" + (adultAllowed ? "unlocked" : "locked"));
''', 'filter log request')

replace_once(main,
'''            ArrayList<Channel> result = new ArrayList<>();
            for (Channel channel : base) {
                if (!matchesMode(channel, wantedMode)) continue;
''',
'''            ArrayList<Channel> result = new ArrayList<>();
            int hiddenAdult = 0;
            for (Channel channel : base) {
                if (!adultAllowed && ParentalControl.isAdult(channel)) {
                    hiddenAdult++;
                    continue;
                }
                if (!matchesMode(channel, wantedMode)) continue;
''', 'filter adult skip')

replace_once(main,
'''            List<Channel> immutable = Collections.unmodifiableList(result);
            long duration = SystemClock.elapsedRealtime() - started;
''',
'''            int hidden = hiddenAdult;
            List<Channel> immutable = Collections.unmodifiableList(result);
            long duration = SystemClock.elapsedRealtime() - started;
''', 'filter hidden final')

replace_once(main,
'''                if (generation != filterGeneration.get() || wantedMode != mode
                        || wantedLanguage != language) return;
''',
'''                if (generation != filterGeneration.get() || wantedMode != mode
                        || wantedLanguage != language
                        || adultAllowed != ParentalControl.isSessionUnlocked()) return;
''', 'filter stale state')

replace_once(main,
'''                        + " · " + MediaLanguage.label(wantedLanguage) + " · "
                        + immutable.size() + " Treffer");
''',
'''                        + " · " + MediaLanguage.label(wantedLanguage) + " · "
                        + immutable.size() + " Treffer · "
                        + (adultAllowed ? "Erwachsenenmodus" : "Kinderfilter"));
''', 'footer parental')

replace_once(main,
'''                log.event("-", "LIST-SNAPSHOT-READY", "rows=" + immutable.size()
                        + " durationMs=" + duration + " language=" + wantedLanguage);
''',
'''                log.event("-", "LIST-SNAPSHOT-READY", "rows=" + immutable.size()
                        + " durationMs=" + duration + " language=" + wantedLanguage
                        + " parental=" + (adultAllowed ? "unlocked" : "locked")
                        + " hiddenAdult=" + hidden);
''', 'filter ready log')

replace_once(main,
'''            lastInputEvent = event.getEventTime();
            log.event("-", "INPUT-DOWN",
''',
'''            lastInputEvent = event.getEventTime();
            if (parental != null) parental.onUserActivity();
            log.event("-", "INPUT-DOWN",
''', 'touch session')

replace_once(main,
'''    protected void onDestroy() {
        watchdog.stop();
''',
'''    protected void onDestroy() {
        if (parental != null) parental.destroy();
        watchdog.stop();
''', 'destroy parental')

replace_once(adapter,
'''        } else {
            Brand brand = Brand.of(channel.name);
            holder.logo.setText(brand.label);
            holder.logo.setBackground(roundRect(brand.fill, 13, brand.stroke));
            holder.name.setText(channel.name);
            holder.group.setText(channel.group + "  ·  " + typeLabel(channel.type));
            holder.language.setText(MediaLanguage.shortLabel(channel));
''',
'''        } else {
            boolean adult = ParentalControl.isAdult(channel);
            Brand brand = adult ? new Brand("18+", 0xFFFF6B7A, 0xFFFF9DA7)
                    : Brand.of(channel.name);
            holder.logo.setText(brand.label);
            holder.logo.setBackground(roundRect(brand.fill, 13, brand.stroke));
            holder.name.setText(channel.name);
            holder.group.setText(channel.group + "  ·  " + typeLabel(channel.type)
                    + (adult ? "  ·  18+" : ""));
            holder.language.setText(MediaLanguage.shortLabel(channel));
''', 'adult badge')

replace_once(manifest,
'''    <application
        android:allowBackup="false"
''',
'''    <application
        android:name=".LumenApplication"
        android:allowBackup="false"
''', 'application guard')

replace_once(build, "versionCode 1314300", "versionCode 1314400", 'version code')
replace_once(build, "versionName '13.1.43-p0-audio-premium-hubs'",
             "versionName '13.1.44-p0-parental-control'", 'version name')
strings.write_text('<resources><string name="app_name">Project Lumen 13.1.44 Jugendschutz</string></resources>\n', encoding='utf-8')
print('Project Lumen parental patch applied successfully')
