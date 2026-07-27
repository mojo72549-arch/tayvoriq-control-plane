package com.projectlumen.pilot.robust;

import android.app.Activity;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.os.SystemClock;
import android.view.Gravity;
import android.view.View;
import android.view.Window;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;

import androidx.media3.common.C;
import androidx.media3.common.MediaItem;
import androidx.media3.common.MimeTypes;
import androidx.media3.common.PlaybackException;
import androidx.media3.common.Player;
import androidx.media3.common.VideoSize;
import androidx.media3.common.util.UnstableApi;
import androidx.media3.datasource.DefaultDataSource;
import androidx.media3.datasource.DefaultHttpDataSource;
import androidx.media3.datasource.HttpDataSource;
import androidx.media3.exoplayer.ExoPlayer;
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory;
import androidx.media3.ui.PlayerView;

import java.util.Locale;

@UnstableApi
public final class PlayerActivity extends Activity {
    static final String EXTRA_URL = "url";
    static final String EXTRA_NAME = "name";
    static final String EXTRA_INTERACTION = "interaction";

    private DiagnosticLog log;
    private String interaction;
    private String url;
    private String name;

    private PlayerView playerView;
    private TextView status;
    private LinearLayout errorCard;
    private TextView errorText;
    private ExoPlayer player;

    private long openedAt;
    private long resumePosition = C.TIME_UNSET;
    private boolean playWhenReady = true;
    private boolean forceTs;
    private boolean fallbackUsed;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        requestWindowFeature(Window.FEATURE_NO_TITLE);
        getWindow().setStatusBarColor(Color.BLACK);
        getWindow().setNavigationBarColor(Color.BLACK);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);

        log = DiagnosticLog.get(this);
        interaction = getIntent().getStringExtra(EXTRA_INTERACTION);
        url = getIntent().getStringExtra(EXTRA_URL);
        name = getIntent().getStringExtra(EXTRA_NAME);
        if (name == null || name.isBlank()) name = "Stream";

        buildUi();
        log.event(interaction, "PLAYER-VIEW-CREATE-END", "created=true engine=Media3");
        if (url == null || url.isBlank()) {
            showError("PLAY-NO-URL", "Keine abspielbare Streamadresse vorhanden.", false);
        } else {
            log.event(interaction, "PLAYER-SET-MEDIA",
                    "urlPresent=true profile=" + profile(url));
        }
    }

    @Override
    protected void onStart() {
        super.onStart();
        if (url != null && !url.isBlank()) startPlayer(false);
    }

    @Override
    protected void onStop() {
        releasePlayer();
        super.onStop();
    }

    @Override
    protected void onDestroy() {
        releasePlayer();
        super.onDestroy();
    }

    private void buildUi() {
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.BLACK);
        setContentView(root);

        playerView = new PlayerView(this);
        playerView.setBackgroundColor(Color.BLACK);
        playerView.setUseController(true);
        playerView.setControllerAutoShow(true);
        playerView.setShowBuffering(PlayerView.SHOW_BUFFERING_ALWAYS);
        root.addView(playerView, new FrameLayout.LayoutParams(-1, -1));

        LinearLayout top = new LinearLayout(this);
        top.setOrientation(LinearLayout.VERTICAL);
        top.setPadding(dp(15), dp(10), dp(15), dp(10));
        top.setBackground(roundRect(0xD907111E, 14, 0x55365C70));
        TextView title = text(name, 16, Color.WHITE, true);
        title.setSingleLine(true);
        top.addView(title);
        status = text("Stream wird vorbereitet …", 12, 0xFFB7CAD8, false);
        status.setSingleLine(true);
        top.addView(status);
        FrameLayout.LayoutParams topParams = new FrameLayout.LayoutParams(
                Math.min(getResources().getDisplayMetrics().widthPixels - dp(24), dp(520)),
                -2, Gravity.TOP | Gravity.START);
        topParams.setMargins(dp(12), dp(12), dp(12), dp(12));
        root.addView(top, topParams);

        errorCard = new LinearLayout(this);
        errorCard.setOrientation(LinearLayout.VERTICAL);
        errorCard.setGravity(Gravity.CENTER_HORIZONTAL);
        errorCard.setPadding(dp(18), dp(16), dp(18), dp(16));
        errorCard.setBackground(roundRect(0xF20A1825, 17, 0xFF31566C));
        errorCard.setVisibility(View.GONE);

        errorText = text("", 14, Color.WHITE, false);
        errorText.setGravity(Gravity.CENTER);
        errorText.setLineSpacing(0, 1.15f);
        errorCard.addView(errorText, new LinearLayout.LayoutParams(-1, -2));

        LinearLayout actions = new LinearLayout(this);
        actions.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams actionRow = new LinearLayout.LayoutParams(-2, -2);
        actionRow.setMargins(0, dp(13), 0, 0);
        errorCard.addView(actions, actionRow);

        Button retry = button("Erneut versuchen", true);
        retry.setOnClickListener(v -> retry());
        retry.setTag("retry");
        actions.addView(retry, new LinearLayout.LayoutParams(dp(158), dp(44)));

        Button back = button("Zurück", false);
        back.setOnClickListener(v -> finish());
        LinearLayout.LayoutParams backParams = new LinearLayout.LayoutParams(dp(102), dp(44));
        backParams.setMargins(dp(8), 0, 0, 0);
        actions.addView(back, backParams);

        FrameLayout.LayoutParams errorParams = new FrameLayout.LayoutParams(
                Math.min(getResources().getDisplayMetrics().widthPixels - dp(30), dp(480)),
                -2, Gravity.CENTER);
        root.addView(errorCard, errorParams);
    }

    private void startPlayer(boolean forcedTs) {
        releasePlayer();
        forceTs = forcedTs;
        openedAt = SystemClock.elapsedRealtime();
        errorCard.setVisibility(View.GONE);
        status.setText(forcedTs ? "MPEG-TS-Fallback wird geöffnet …" : "Verbindung wird aufgebaut …");

        try {
            DefaultHttpDataSource.Factory http = new DefaultHttpDataSource.Factory()
                    .setUserAgent("ProjectLumen/13.1.42 Media3")
                    .setConnectTimeoutMs(15_000)
                    .setReadTimeoutMs(30_000)
                    .setAllowCrossProtocolRedirects(true);
            DefaultDataSource.Factory data = new DefaultDataSource.Factory(this, http);
            player = new ExoPlayer.Builder(this)
                    .setMediaSourceFactory(new DefaultMediaSourceFactory(data))
                    .build();
            player.addListener(listener);
            playerView.setPlayer(player);

            MediaItem item = mediaItem(url, forcedTs);
            player.setMediaItem(item);
            if (resumePosition != C.TIME_UNSET && !isLikelyLive(url)) {
                player.seekTo(resumePosition);
            }
            player.setPlayWhenReady(playWhenReady);
            log.event(interaction, "PLAY-PREPARE-START",
                    "engine=Media3 forcedTs=" + forcedTs + " profile=" + profile(url));
            player.prepare();
            player.play();
        } catch (Throwable failure) {
            log.exception(interaction, "PLAY-SET-MEDIA-ERROR", failure);
            showError("PLAY-SET-MEDIA-ERROR",
                    "Der Stream konnte nicht an den Player übergeben werden.", true);
        }
    }

    private final Player.Listener listener = new Player.Listener() {
        @Override
        public void onPlaybackStateChanged(int state) {
            if (state == Player.STATE_BUFFERING) {
                status.setText("Stream wird gepuffert …");
                log.event(interaction, "PLAY-BUFFER-START", "elapsedMs=" + elapsed());
            } else if (state == Player.STATE_READY) {
                status.setText("Wiedergabe bereit");
                log.event(interaction, "PLAY-READY", "elapsedMs=" + elapsed());
            } else if (state == Player.STATE_ENDED) {
                status.setText("Wiedergabe beendet");
                log.event(interaction, "PLAY-ENDED", "elapsedMs=" + elapsed());
            }
        }

        @Override
        public void onIsPlayingChanged(boolean playing) {
            if (playing) {
                status.setText("Wiedergabe läuft");
                log.event(interaction, "PLAY-STARTED", "elapsedMs=" + elapsed());
            }
        }

        @Override
        public void onRenderedFirstFrame() {
            status.setText("Wiedergabe läuft");
            log.event(interaction, "PLAY-FIRST-FRAME",
                    "elapsedMs=" + elapsed() + " engine=Media3");
        }

        @Override
        public void onVideoSizeChanged(VideoSize size) {
            log.event(interaction, "PLAY-VIDEO-SIZE",
                    "width=" + size.width + " height=" + size.height);
        }

        @Override
        public void onPlayerError(PlaybackException error) {
            String errorName = errorName(error);
            String details = errorDetails(error);
            log.event(interaction, "PLAY-ERROR",
                    "engine=Media3 code=" + error.errorCode + " name=" + errorName
                            + " forcedTs=" + forceTs + " elapsedMs=" + elapsed()
                            + " " + details);

            if (!fallbackUsed && !forceTs && shouldFallback(errorName, url)) {
                fallbackUsed = true;
                log.event(interaction, "PLAY-FALLBACK-TS", "reason=" + errorName);
                status.setText("Format wird als MPEG-TS erneut geöffnet …");
                playerView.postDelayed(() -> startPlayer(true), 250);
                return;
            }
            showError(errorName, friendlyMessage(errorName, details), true);
        }
    };

    private void retry() {
        fallbackUsed = false;
        forceTs = false;
        resumePosition = C.TIME_UNSET;
        playWhenReady = true;
        log.event(interaction, "PLAY-RETRY", "manual=true");
        startPlayer(false);
    }

    private void releasePlayer() {
        if (player == null) return;
        try {
            if (!isLikelyLive(url)) resumePosition = player.getCurrentPosition();
            playWhenReady = player.getPlayWhenReady();
            player.removeListener(listener);
            playerView.setPlayer(null);
            player.release();
        } catch (Throwable failure) {
            log.exception(interaction, "PLAYER-RELEASE-ERROR", failure);
        } finally {
            player = null;
        }
    }

    private void showError(String code, String message, boolean retryVisible) {
        status.setText("Wiedergabe nicht möglich");
        errorText.setText("Wiedergabe nicht möglich\n\n" + message
                + "\n\nDiagnosecode: " + code);
        View retry = errorCard.findViewWithTag("retry");
        if (retry != null) retry.setVisibility(retryVisible ? View.VISIBLE : View.GONE);
        errorCard.setVisibility(View.VISIBLE);
    }

    private static MediaItem mediaItem(String streamUrl, boolean forcedTs) {
        MediaItem.Builder builder = new MediaItem.Builder().setUri(streamUrl);
        String lower = streamUrl.toLowerCase(Locale.ROOT);
        if (forcedTs || lower.endsWith(".ts") || lower.contains(".ts?")) {
            builder.setMimeType(MimeTypes.VIDEO_MP2T);
        } else if (lower.contains(".m3u8") || lower.contains("format=m3u8")) {
            builder.setMimeType(MimeTypes.APPLICATION_M3U8);
        }
        return builder.build();
    }

    private static boolean shouldFallback(String errorName, String streamUrl) {
        if (streamUrl == null) return false;
        String lower = streamUrl.toLowerCase(Locale.ROOT);
        if (lower.contains(".m3u8")) return false;
        return errorName.contains("PARSING")
                || errorName.contains("UNSPECIFIED")
                || lower.contains("/live/")
                || lower.endsWith(".ts")
                || lower.contains(".ts?");
    }

    private static String friendlyMessage(String errorName, String details) {
        if (errorName.contains("BAD_HTTP_STATUS")) {
            return details.contains("httpStatus=401") || details.contains("httpStatus=403")
                    ? "Der Server hat den Stream abgewiesen. Zugang oder Streamadresse prüfen."
                    : "Der Streaming-Server hat mit einem Fehlerstatus geantwortet.";
        }
        if (errorName.contains("TIMEOUT")) {
            return "Der Streaming-Server antwortet nicht rechtzeitig.";
        }
        if (errorName.contains("NETWORK_CONNECTION_FAILED")) {
            return "Die Netzwerkverbindung zum Streaming-Server ist fehlgeschlagen.";
        }
        if (errorName.contains("PARSING") || errorName.contains("CONTENT_TYPE")) {
            return "Das gelieferte Streamformat konnte nicht erkannt oder gelesen werden.";
        }
        if (errorName.contains("DECODER") || errorName.contains("DECODING")) {
            return "Der Video- oder Audiocodec wird auf diesem Gerät nicht unterstützt.";
        }
        return "Der genaue technische Fehler wurde in der Diagnose gespeichert.";
    }

    private static String errorName(PlaybackException error) {
        String value = error == null ? null : error.getErrorCodeName();
        return value == null || value.isBlank() ? "ERROR_CODE_UNSPECIFIED" : value;
    }

    private static String errorDetails(PlaybackException error) {
        StringBuilder result = new StringBuilder("causeChain=");
        Throwable current = error;
        int depth = 0;
        while (current != null && depth < 6) {
            if (depth > 0) result.append('>');
            result.append(current.getClass().getSimpleName());
            if (current instanceof HttpDataSource.InvalidResponseCodeException) {
                result.append(" httpStatus=")
                        .append(((HttpDataSource.InvalidResponseCodeException) current).responseCode);
            }
            current = current.getCause();
            depth++;
        }
        return result.toString();
    }

    private static String profile(String streamUrl) {
        String lower = streamUrl.toLowerCase(Locale.ROOT);
        if (lower.contains(".m3u8")) return "HLS";
        if (lower.contains("/live/") || lower.endsWith(".ts") || lower.contains(".ts?")) {
            return "MPEG-TS-LIVE";
        }
        return "AUTO";
    }

    private static boolean isLikelyLive(String streamUrl) {
        if (streamUrl == null) return true;
        String lower = streamUrl.toLowerCase(Locale.ROOT);
        return lower.contains("/live/") || lower.endsWith(".ts")
                || lower.contains(".ts?") || lower.contains(".m3u8");
    }

    private long elapsed() {
        return openedAt <= 0 ? 0 : Math.max(0, SystemClock.elapsedRealtime() - openedAt);
    }

    private TextView text(String value, int size, int color, boolean bold) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(size);
        view.setTextColor(color);
        if (bold) view.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        return view;
    }

    private Button button(String label, boolean primary) {
        Button button = new Button(this);
        button.setText(label);
        button.setTextSize(12);
        button.setAllCaps(false);
        button.setTextColor(primary ? 0xFF07111E : Color.WHITE);
        button.setBackground(roundRect(primary ? 0xFF5EEAD4 : 0xFF17354A,
                13, primary ? 0xFF5EEAD4 : 0xFF31566C));
        return button;
    }

    private GradientDrawable roundRect(int fill, int radiusDp, int stroke) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(fill);
        drawable.setCornerRadius(dp(radiusDp));
        drawable.setStroke(dp(1), stroke);
        return drawable;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
