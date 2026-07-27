package com.projectlumen.pilot.robust;

import android.app.Activity;
import android.graphics.Color;
import android.media.MediaPlayer;
import android.net.Uri;
import android.os.Bundle;
import android.view.Gravity;
import android.widget.FrameLayout;
import android.widget.MediaController;
import android.widget.TextView;
import android.widget.VideoView;

public final class PlayerActivity extends Activity {
    static final String EXTRA_URL = "url";
    static final String EXTRA_NAME = "name";
    static final String EXTRA_INTERACTION = "interaction";
    private DiagnosticLog log;
    private String interaction;
    private TextView overlay;
    private VideoView video;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        log = DiagnosticLog.get(this);
        interaction = getIntent().getStringExtra(EXTRA_INTERACTION);
        String url = getIntent().getStringExtra(EXTRA_URL);
        String name = getIntent().getStringExtra(EXTRA_NAME);
        FrameLayout root = new FrameLayout(this); root.setBackgroundColor(Color.BLACK); setContentView(root);
        video = new VideoView(this); video.setBackgroundColor(Color.BLACK); root.addView(video, new FrameLayout.LayoutParams(-1, -1));
        overlay = new TextView(this); overlay.setTextColor(Color.WHITE); overlay.setTextSize(15); overlay.setGravity(Gravity.START); overlay.setPadding(dp(16), dp(14), dp(16), dp(14)); overlay.setBackgroundColor(0xD907111E); overlay.setText((name == null ? "Stream" : name) + "\nStream wird geöffnet …");
        FrameLayout.LayoutParams op = new FrameLayout.LayoutParams(Math.min(getResources().getDisplayMetrics().widthPixels - dp(24), dp(420)), -2, Gravity.BOTTOM | Gravity.END); op.setMargins(dp(12), dp(12), dp(12), dp(12)); root.addView(overlay, op);
        log.event(interaction, "PLAYER-VIEW-CREATE-END", "created=true");
        if (url == null || url.isBlank()) { fail("PLAY-NO-URL", "Keine abspielbare Adresse vorhanden."); return; }
        MediaController controller = new MediaController(this); controller.setAnchorView(video); video.setMediaController(controller);
        video.setOnPreparedListener(mp -> { log.event(interaction, "PLAY-PREPARED", "durationMs=" + mp.getDuration()); mp.setOnInfoListener((player, what, extra) -> info(what)); overlay.setText((name == null ? "Stream" : name) + "\nWiedergabe läuft"); overlay.postDelayed(() -> overlay.setVisibility(android.view.View.GONE), 2500); });
        video.setOnErrorListener((mp, what, extra) -> { fail("PLAY-ERROR-" + what + "-" + extra, "Wiedergabe nicht möglich. Diagnose öffnen und teilen."); return true; });
        log.event(interaction, "PLAYER-SET-MEDIA", "urlPresent=true");
        try { video.setVideoURI(Uri.parse(url)); log.event(interaction, "PLAY-PREPARE-START", "engine=VideoView"); video.start(); }
        catch (Throwable failure) { log.exception(interaction, "PLAY-SET-MEDIA-ERROR", failure); fail("PLAY-SET-MEDIA-ERROR", failure.getMessage()); }
    }
    private boolean info(int what) { if (what == MediaPlayer.MEDIA_INFO_VIDEO_RENDERING_START) log.event(interaction, "PLAY-FIRST-FRAME", "ok=true"); else if (what == MediaPlayer.MEDIA_INFO_BUFFERING_START) log.event(interaction, "PLAY-BUFFER-START", "ok=true"); else if (what == MediaPlayer.MEDIA_INFO_BUFFERING_END) log.event(interaction, "PLAY-BUFFER-END", "ok=true"); return false; }
    private void fail(String code, String message) { log.event(interaction, "PLAY-ERROR", "code=" + code + " message=" + message); overlay.setVisibility(android.view.View.VISIBLE); overlay.setText("Wiedergabe nicht möglich\nCode " + code + "\n" + message + "\n\nZurück: Player schließen"); }
    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
}
