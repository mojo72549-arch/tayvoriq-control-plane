package com.projectlumen.publicpreview;

import android.app.Activity;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.View;
import android.view.ViewGroup;
import android.widget.FrameLayout;
import android.widget.TextView;

import androidx.media3.common.MediaItem;
import androidx.media3.common.PlaybackException;
import androidx.media3.common.Player;
import androidx.media3.datasource.DefaultDataSource;
import androidx.media3.datasource.DefaultHttpDataSource;
import androidx.media3.exoplayer.ExoPlayer;
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory;
import androidx.media3.ui.PlayerView;

import java.util.Map;

/** Dedicated playback surface with encrypted per-profile resume state. */
public final class PlaybackActivity extends Activity {
    public static final String EXTRA_TITLE = "title";
    public static final String EXTRA_GROUP = "group";
    public static final String EXTRA_URL = "url";
    public static final String EXTRA_MEDIA_TYPE = "media_type";
    public static final String EXTRA_START_POSITION = "start_position";

    private final Handler handler = new Handler(Looper.getMainLooper());
    private ExoPlayer player;
    private PlayerView playerView;
    private TextView status;
    private String title, group, url, mediaType;
    private boolean live, completed;
    private final Runnable checkpoint = new Runnable() {
        @Override public void run() {
            persistProgress(false);
            handler.postDelayed(this, 15_000L);
        }
    };

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        title = safe(getIntent().getStringExtra(EXTRA_TITLE), "Wiedergabe");
        group = safe(getIntent().getStringExtra(EXTRA_GROUP), "");
        url = safe(getIntent().getStringExtra(EXTRA_URL), "");
        mediaType = safe(getIntent().getStringExtra(EXTRA_MEDIA_TYPE), "VOD");
        live = "LIVE".equalsIgnoreCase(mediaType);

        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.BLACK);
        playerView = new PlayerView(this);
        playerView.setUseController(true);
        playerView.setControllerAutoShow(true);
        playerView.setKeepScreenOn(true);
        root.addView(playerView, new FrameLayout.LayoutParams(-1, -1));
        status = new TextView(this);
        status.setTextColor(Color.WHITE);
        status.setTextSize(18);
        status.setGravity(Gravity.CENTER_VERTICAL);
        status.setPadding(dp(18), dp(14), dp(18), dp(14));
        status.setBackgroundColor(0xD907111E);
        status.setText(title + "\nStream wird vorbereitet …");
        FrameLayout.LayoutParams params = new FrameLayout.LayoutParams(
                Math.min(getResources().getDisplayMetrics().widthPixels - dp(24), dp(620)),
                ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.BOTTOM | Gravity.END);
        params.setMargins(dp(12), dp(12), dp(12), dp(12));
        root.addView(status, params);
        setContentView(root);
        if (url.isBlank()) {
            status.setText(title + "\nKeine abspielbare Adresse vorhanden.");
            return;
        }
        startPlayback();
    }

    private void startPlayback() {
        DefaultHttpDataSource.Factory http = new DefaultHttpDataSource.Factory()
                .setUserAgent("VLC/3.0.20 LibVLC/3.0.20")
                .setConnectTimeoutMs(30_000).setReadTimeoutMs(45_000)
                .setAllowCrossProtocolRedirects(true)
                .setDefaultRequestProperties(Map.of("Accept", "*/*"));
        DefaultMediaSourceFactory media = new DefaultMediaSourceFactory(new DefaultDataSource.Factory(this, http));
        player = new ExoPlayer.Builder(this).setMediaSourceFactory(media).build();
        playerView.setPlayer(player);
        player.addListener(new Player.Listener() {
            @Override public void onPlaybackStateChanged(int state) {
                if (state == Player.STATE_BUFFERING) status.setText(title + "\nPufferung …");
                else if (state == Player.STATE_READY) {
                    status.setText(title + "\nWiedergabe bereit · Zurück schließt den Player");
                    status.postDelayed(() -> status.setVisibility(View.GONE), 2500L);
                } else if (state == Player.STATE_ENDED) {
                    completed = true;
                    persistProgress(true);
                    status.setVisibility(View.VISIBLE);
                    status.setText(title + "\nWiedergabe beendet");
                }
            }
            @Override public void onPlayerError(PlaybackException error) {
                status.setVisibility(View.VISIBLE);
                status.setText(title + "\nWiedergabe nicht möglich\nCode: " + error.getErrorCodeName());
            }
        });
        player.setMediaItem(MediaItem.fromUri(Uri.parse(url)));
        player.prepare();
        long start = Math.max(0, getIntent().getLongExtra(EXTRA_START_POSITION, 0L));
        if (!live && start > 0) player.seekTo(start);
        player.setPlayWhenReady(true);
        handler.postDelayed(checkpoint, 15_000L);
    }

    private void persistProgress(boolean forceCompleted) {
        if (player == null || live || url.isBlank()) return;
        try {
            new PlaybackStore(this).record(url, title, group, mediaType,
                    Math.max(0, player.getCurrentPosition()), Math.max(0, player.getDuration()),
                    forceCompleted || completed || player.getPlaybackState() == Player.STATE_ENDED);
        } catch (Throwable ignored) {}
    }

    @Override protected void onPause() { persistProgress(false); super.onPause(); }
    @Override protected void onDestroy() {
        handler.removeCallbacks(checkpoint);
        persistProgress(false);
        if (playerView != null) playerView.setPlayer(null);
        if (player != null) try { player.release(); } catch (Throwable ignored) {}
        player = null;
        super.onDestroy();
    }
    @Override public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (keyCode == KeyEvent.KEYCODE_BACK) { finish(); return true; }
        return super.onKeyDown(keyCode, event);
    }
    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
    private static String safe(String value, String fallback) {
        if (value == null) return fallback;
        String cleaned = value.replaceAll("[\\p{Cntrl}]", " ").trim();
        return cleaned.isEmpty() ? fallback : cleaned;
    }
}
