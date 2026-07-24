package com.projectlumen.publicpreview;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.view.Gravity;
import android.view.ViewGroup;
import android.widget.*;
import java.util.*;
import java.util.regex.*;

/** Series -> season -> episode browser with D-pad friendly controls. */
public final class SeriesActivity extends Activity {
    public static final String EXTRA_TOKEN = "series_token";
    private static final int BG = 0xFF05070B, SURFACE = 0xFF141A24, TEXT = 0xFFF7F9FC,
            MUTED = 0xFFA7B0BE, PRIMARY = 0xFF6AE4FF;
    private static final Pattern COMBINED = Pattern.compile(
            "(?i)(?:\\bS(?:eason)?\\s*0*(\\d{1,3})\\s*[-._ ]*E(?:pisode)?\\s*0*(\\d{1,4})\\b|\\bStaffel\\s*0*(\\d{1,3})\\s*[-._ ]*(?:Folge|Episode)\\s*0*(\\d{1,4})\\b)");
    private static final Pattern EPISODE = Pattern.compile("(?i)\\b(?:E|Episode|Folge)\\s*0*(\\d{1,4})\\b");
    private static final Pattern SEASON = Pattern.compile("(?i)\\b(?:S|Season|Staffel)\\s*0*(\\d{1,3})\\b");
    private SeriesSelectionStore.Selection selection;
    private final Map<Integer, List<Episode>> seasons = new LinkedHashMap<>();
    private int selectedSeason;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        try {
            selection = SeriesSelectionStore.load(this, getIntent().getStringExtra(EXTRA_TOKEN));
            buildEpisodes(); render();
        } catch (Exception failure) {
            Toast.makeText(this, failure.getMessage(), Toast.LENGTH_LONG).show(); finish();
        }
    }
    private void buildEpisodes() {
        Map<Integer, List<Episode>> temp = new LinkedHashMap<>();
        int fallback = 1;
        for (SeriesSelectionStore.Item item : selection.items) {
            Episode parsed = parse(item, fallback++);
            temp.computeIfAbsent(parsed.season, ignored -> new ArrayList<>()).add(parsed);
        }
        List<Integer> numbers = new ArrayList<>(temp.keySet()); Collections.sort(numbers);
        for (Integer season : numbers) {
            List<Episode> list = temp.get(season);
            list.sort(Comparator.comparingInt((Episode e) -> e.episode)
                    .thenComparing(e -> e.title.toLowerCase(Locale.ROOT)));
            seasons.put(season, list);
        }
        selectedSeason = numbers.isEmpty() ? 1 : numbers.get(0);
    }
    private void render() {
        ScrollView scroll = new ScrollView(this); scroll.setFillViewport(true);
        LinearLayout root = new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(28), dp(24), dp(28), dp(40)); root.setBackgroundColor(BG);
        scroll.addView(root, new ScrollView.LayoutParams(-1, -2));
        root.addView(text(selection.title, tv() ? 34 : 28, TEXT, true));
        root.addView(text(selection.items.size() + " Episoden lokal erkannt", tv() ? 17 : 14, MUTED, false), margin(0, 5, 0, 16));
        HorizontalScrollView seasonScroll = new HorizontalScrollView(this);
        LinearLayout seasonRow = new LinearLayout(this); seasonRow.setOrientation(LinearLayout.HORIZONTAL);
        for (Integer season : seasons.keySet()) {
            Button chip = button(season == 0 ? "Ohne Staffel" : "Staffel " + season);
            chip.setBackgroundColor(season == selectedSeason ? PRIMARY : SURFACE);
            chip.setTextColor(season == selectedSeason ? BG : TEXT);
            chip.setOnClickListener(v -> { selectedSeason = season; render(); });
            LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(-2, dp(tv() ? 54 : 46));
            p.setMargins(seasonRow.getChildCount() == 0 ? 0 : dp(8), 0, 0, 0); seasonRow.addView(chip, p);
        }
        seasonScroll.addView(seasonRow, new HorizontalScrollView.LayoutParams(-2, -2));
        root.addView(seasonScroll, margin(0, 0, 0, 16));
        PlaybackStore playback = new PlaybackStore(this);
        Button first = null;
        for (Episode episode : seasons.getOrDefault(selectedSeason, Collections.emptyList())) {
            LinearLayout card = new LinearLayout(this); card.setOrientation(LinearLayout.VERTICAL);
            card.setPadding(dp(18), dp(14), dp(18), dp(14)); card.setBackgroundColor(SURFACE);
            card.addView(text("Folge " + episode.episode + " · " + episode.title, tv() ? 20 : 17, TEXT, true));
            PlaybackStore.Entry progress = playback.getByUrl(episode.item.url);
            String detail = episode.item.group + (progress != null && progress.isContinueWatching()
                    ? " · " + progress.progressPercent() + "% angesehen" : "");
            card.addView(text(detail, tv() ? 15 : 13, MUTED, false), margin(0, 4, 0, 10));
            Button play = button(progress != null && progress.isContinueWatching() ? "Fortsetzen" : "Abspielen");
            long start = progress != null && progress.isContinueWatching() ? progress.positionMs : 0;
            play.setOnClickListener(v -> play(episode, start)); card.addView(play);
            root.addView(card, margin(0, 0, 0, 10)); if (first == null) first = play;
        }
        setContentView(scroll); if (first != null) first.requestFocus();
    }
    private void play(Episode episode, long start) {
        Intent intent = new Intent(this, PlaybackActivity.class);
        intent.putExtra(PlaybackActivity.EXTRA_TITLE, episode.title);
        intent.putExtra(PlaybackActivity.EXTRA_GROUP, episode.item.group);
        intent.putExtra(PlaybackActivity.EXTRA_URL, episode.item.url);
        intent.putExtra(PlaybackActivity.EXTRA_MEDIA_TYPE, "SERIES");
        intent.putExtra(PlaybackActivity.EXTRA_START_POSITION, Math.max(0, start));
        startActivity(intent);
    }
    private static Episode parse(SeriesSelectionStore.Item item, int fallback) {
        String name = item.name == null ? "Episode" : item.name;
        Matcher combined = COMBINED.matcher(name);
        if (combined.find()) {
            int season = number(combined.group(1) != null ? combined.group(1) : combined.group(3), 1);
            int episode = number(combined.group(2) != null ? combined.group(2) : combined.group(4), fallback);
            String title = (name.substring(0, combined.start()) + " " + name.substring(combined.end()))
                    .replaceAll("[-._|]+", " ").replaceAll("\\s+", " ").trim();
            return new Episode(season, episode, title.isEmpty() ? name : title, item);
        }
        Matcher sm = SEASON.matcher(name); int season = sm.find() ? number(sm.group(1), 1) : 1;
        Matcher em = EPISODE.matcher(name); int episode = em.find() ? number(em.group(1), fallback) : fallback;
        return new Episode(season, episode, name, item);
    }
    private static int number(String value, int fallback) {
        try { return Math.max(0, Integer.parseInt(value)); } catch (Exception ignored) { return fallback; }
    }
    private Button button(String label) {
        Button b = new Button(this); b.setText(label); b.setTextSize(tv() ? 18 : 16);
        b.setAllCaps(false); b.setFocusable(true); b.setMinHeight(dp(tv() ? 54 : 48)); return b;
    }
    private TextView text(String value, int size, int color, boolean bold) {
        TextView v = new TextView(this); v.setText(value); v.setTextSize(size); v.setTextColor(color);
        v.setGravity(Gravity.START); if (bold) v.setTypeface(null, 1); return v;
    }
    private LinearLayout.LayoutParams margin(int l, int t, int r, int b) {
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(-1, -2); p.setMargins(dp(l), dp(t), dp(r), dp(b)); return p;
    }
    private boolean tv() { return (getResources().getConfiguration().uiMode & 0x0f) == 4; }
    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
    private static final class Episode {
        final int season, episode; final String title; final SeriesSelectionStore.Item item;
        Episode(int season, int episode, String title, SeriesSelectionStore.Item item) {
            this.season = season; this.episode = episode; this.title = title; this.item = item;
        }
    }
}
