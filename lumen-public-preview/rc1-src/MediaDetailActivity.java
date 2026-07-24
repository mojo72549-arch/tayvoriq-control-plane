package com.projectlumen.publicpreview;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.view.Gravity;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import com.bumptech.glide.Glide;
import com.bumptech.glide.load.engine.DiskCacheStrategy;

/** Premium film/VOD detail screen with resume and start-over actions. */
public final class MediaDetailActivity extends Activity {
    public static final String EXTRA_TITLE = "title";
    public static final String EXTRA_GROUP = "group";
    public static final String EXTRA_URL = "url";
    public static final String EXTRA_LOGO = "logo";
    public static final String EXTRA_LANGUAGE = "language";
    public static final String EXTRA_MEDIA_TYPE = "media_type";
    private static final int BG = 0xFF05070B, SURFACE = 0xFF141A24, TEXT = 0xFFF7F9FC, MUTED = 0xFFA7B0BE;
    private String title, group, url, logo, language, mediaType;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        title = safe(getIntent().getStringExtra(EXTRA_TITLE), "Film");
        group = safe(getIntent().getStringExtra(EXTRA_GROUP), "Weitere");
        url = safe(getIntent().getStringExtra(EXTRA_URL), "");
        logo = safe(getIntent().getStringExtra(EXTRA_LOGO), "");
        language = safe(getIntent().getStringExtra(EXTRA_LANGUAGE), "");
        mediaType = safe(getIntent().getStringExtra(EXTRA_MEDIA_TYPE), "VOD");
        render();
    }

    private void render() {
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(28), dp(24), dp(28), dp(40));
        root.setBackgroundColor(BG);
        scroll.addView(root, new ScrollView.LayoutParams(-1, -2));
        ImageView poster = new ImageView(this);
        poster.setScaleType(ImageView.ScaleType.CENTER_CROP);
        poster.setBackgroundColor(SURFACE);
        LinearLayout.LayoutParams posterParams = new LinearLayout.LayoutParams(dp(tv() ? 310 : 230), dp(tv() ? 430 : 330));
        posterParams.gravity = Gravity.CENTER_HORIZONTAL;
        root.addView(poster, posterParams);
        if (!logo.isBlank()) Glide.with(this).load(logo).diskCacheStrategy(DiskCacheStrategy.AUTOMATIC).into(poster);
        TextView heading = text(title, tv() ? 34 : 28, TEXT, true);
        heading.setGravity(Gravity.CENTER_HORIZONTAL);
        root.addView(heading, margin(0, 20, 0, 6));
        TextView meta = text(group + (language.isBlank() ? "" : " · " + language), tv() ? 18 : 15, MUTED, false);
        meta.setGravity(Gravity.CENTER_HORIZONTAL);
        root.addView(meta, margin(0, 0, 0, 18));

        PlaybackStore.Entry progress = new PlaybackStore(this).getByUrl(url);
        if (progress != null && progress.isContinueWatching()) {
            root.addView(info("Wiedergabefortschritt", progress.progressPercent() + "% angesehen"));
            Button resume = button("Fortsetzen bei " + formatTime(progress.positionMs));
            resume.setOnClickListener(v -> play(progress.positionMs));
            root.addView(resume, margin(0, 14, 0, 0));
        }
        Button play = button(progress != null && progress.isContinueWatching() ? "Von vorn abspielen" : "Abspielen");
        play.setOnClickListener(v -> play(0));
        root.addView(play, margin(0, 12, 0, 0));
        TextView privacy = text("Die Quelle bleibt lokal auf diesem Gerät. Project Lumen liefert oder verkauft keine Inhalte.", 14, MUTED, false);
        privacy.setGravity(Gravity.CENTER_HORIZONTAL);
        root.addView(privacy, margin(0, 22, 0, 0));
        setContentView(scroll);
        play.requestFocus();
    }

    private void play(long start) {
        Intent intent = new Intent(this, PlaybackActivity.class);
        intent.putExtra(PlaybackActivity.EXTRA_TITLE, title);
        intent.putExtra(PlaybackActivity.EXTRA_GROUP, group);
        intent.putExtra(PlaybackActivity.EXTRA_URL, url);
        intent.putExtra(PlaybackActivity.EXTRA_MEDIA_TYPE, mediaType);
        intent.putExtra(PlaybackActivity.EXTRA_START_POSITION, Math.max(0, start));
        startActivity(intent);
    }
    private LinearLayout info(String label, String value) {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(18), dp(14), dp(18), dp(14));
        card.setBackgroundColor(SURFACE);
        card.addView(text(label, 16, TEXT, true));
        card.addView(text(value, 14, MUTED, false), margin(0, 4, 0, 0));
        return card;
    }
    private Button button(String label) {
        Button b = new Button(this); b.setText(label); b.setTextSize(tv() ? 18 : 16);
        b.setAllCaps(false); b.setFocusable(true); b.setMinHeight(dp(tv() ? 58 : 50)); return b;
    }
    private TextView text(String value, int size, int color, boolean bold) {
        TextView v = new TextView(this); v.setText(value); v.setTextSize(size); v.setTextColor(color);
        if (bold) v.setTypeface(null, 1); return v;
    }
    private LinearLayout.LayoutParams margin(int l, int t, int r, int b) {
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(-1, -2); p.setMargins(dp(l), dp(t), dp(r), dp(b)); return p;
    }
    private boolean tv() { return (getResources().getConfiguration().uiMode & 0x0f) == 4; }
    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
    private static String formatTime(long millis) {
        long seconds = Math.max(0, millis / 1000L);
        return String.format(java.util.Locale.GERMANY, "%02d:%02d:%02d", seconds / 3600L, (seconds % 3600L) / 60L, seconds % 60L);
    }
    private static String safe(String value, String fallback) {
        if (value == null) return fallback;
        String cleaned = value.replaceAll("[\\p{Cntrl}]", " ").trim(); return cleaned.isEmpty() ? fallback : cleaned;
    }
}
