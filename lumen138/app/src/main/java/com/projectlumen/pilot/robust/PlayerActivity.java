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

import androidx.annotation.Nullable;
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

import java.net.URI;
import java.util.Locale;

@UnstableApi
public final class PlayerActivity extends Activity {
    static final String EXTRA_URL = "url";
    static final String EXTRA_NAME = "name";
    static final String EXTRA_INTERACTION = "interaction";

    private static final int CONNECT_TIMEOUT_MS = 15_000;
    private static final int READ_TIMEOUT_MS = 30_000;

    private DiagnosticLog log;
    private String interaction;
    private String streamUrl;
    private String streamName;

    private PlayerView playerView;
    private TextView title;
    private TextView status;
    private LinearLayout messageCard;
    private Button retryButton;

    private ExoPlayer player;
    private long openedAt;
    private long resumePosition = C.TIME_UNSET;
    private boolean resumePlayWhenReady = true;
    private boolean forcedTransportStream;
    private boolean automaticFallbackUsed;
    private boolean released;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        requestWindowFeature(Window.FEATURE_NO_TITLE);
        getWindow().setStatusBarColor(Color.BLACK);
        getWindow().setNavigationBarColor(Color.BLACK);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);

        log = DiagnosticLog.get(this);
        interaction = getIntent().getStringExtra(EXTRA_INTERACTION);
        streamUrl = getIntent().getStringExtra(EXTRA_URL);
        streamName = getIntent().getStringExtra(EXTRA_NAME);
        if (streamName == null || streamName.isBlank()) streamName = "Stream";

        buildUi();
        log.event(interaction, "PLAYER-VIEW-CREATE-END", "created=true engine=Media3");

        if (streamUrl == null || streamUrl.isBlank()) {
            showFailure("PLAY-NO-URL", "Keine abspielbare Streamadresse vorhanden.", false);
            return;
        }

        log.event(interaction, "PLAYER-SET-MEDIA",
                "urlPresent=true profile=" + profileLabel(streamUrl));
    }

    @Override
    protected void onStart() {
        super.onStart();
        if (streamUrl != null && !streamUrl.isBlank()) startPlayer(false);
    }

    @Override
    protected void onStop() {
        saveAndRelease();
        super.onStop();
    }

    @Override
    protected void onDestroy() {
        saveAndRelease();
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
        playerView.setControllerHideOnTouch(true);
        playerView.setShowBuffering(PlayerView.SHOW_BUFFERING_ALWAYS);
        playerView.setKeepScreenOn(true);
        root.addView(playerView, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT));

        LinearLayout topCard = new LinearLayout(this);
        topCard.setOrientation(LinearLayout.VERTICAL);
        topCard.setPadding(dp(15), dp(11), dp(15), dp(11));
        topCard.setBackground(roundRect(0xD907111E, 15, 0x66335B72));

        title = text(streamName, 16, Color.WHITE, true);
        title.setSingleLine(true);
        topCard.addView(title);

        status = text("Stream wird vorbereitet …", 12, 0xFFB7CAD8, false);
        status.setSingleLine(true);
        LinearLayout.LayoutParams statusParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
        statusParams.setMargins(0, dp(2), 0, 0);
        topCard.addView(status, statusParams);

        FrameLayout.LayoutParams topParams = new FrameLayout.LayoutParams(
                Math.min(getResources().getDisplayMetrics().widthPixels - dp(24), dp(520)),
                FrameLayout.LayoutParams.WRAP_CONTENT,
                Gravity.TOP | Gravity.START);
        topParams.setMargins(dp(12), dp(12), dp(12), dp(12));
        root.addView(topCard, topParams);

        messageCard = new LinearLayout(this);
        messageCard.setOrientation(LinearLayout.VERTICAL);
        messageCard.setGravity(Gravity.CENTER_HORIZONTAL);
        messageCard.setPadding(dp(18), dp(16), dp(18), dp(16));
        messageCard.setBackground(roundRect(0xF20A1825, 17, 0xFF31566C));
        messageCard.setVisibility(View.GONE);

        TextView message = text("", 14, Color.WHITE, false);
        message.setGravity(Gravity.CENTER);
        message.setLineSpacing(0, 1.15f);
        message.setTag("message");
        messageCard.addView(message, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT));

        LinearLayout actions = new LinearLayout(this);
        actions.setOrientation(LinearLayout.HORIZONTAL);
        actions.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams actionsParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
        actionsParams.setMargins(0, dp(13), 0, 0);
        messageCard.addView(actions, actionsParams);

        retryButton = button("Erneut versuchen", true);
        retryButton.setOnClickListener(v -> retryFromBeginning());
        actions.addView(retryButton, new LinearLayout.LayoutParams(dp(158), dp(44)));

        Button back = button("Zurück", false);
        back.setOnClickListener(v -> finish());
        LinearLayout.LayoutParams backParams = new LinearLayout.LayoutParams(dp(102), dp(44));
        backParams.setMargins(dp(8), 0, 0, 0);
        actions.addView(back, backParams);

        FrameLayout.LayoutParams messageParams = new FrameLayout.LayoutParams(
                Math.min(getResources().getDisplayMetrics().widthPixels - dp(30), dp(480)),
                FrameLayout.LayoutParams.WRAP_CONTENT,
                Gravity.CENTER);
        root.addView(messageCard, messageParams);
    }

    private void startPlayer(boolean forceTs) {
        saveAndRelease();
        released = false;
        forcedTransportStream = forceTs;
        openedAt = SystemClock.elapsedRealtime();
        messageCard.setVisibility(View.GONE);
        status.setText(forceTs
                ? "MPEG-TS-Fallback wird vorbereitet …"
                : "Verbindung wird aufgebaut …");

        try {
            DefaultHttpDataSource.Factory httpFactory = new DefaultHttpDataSource.Factory()
                    .setUserAgent("ProjectLumen/13.1.42 Media3")
                    .setConnectTimeoutMs(CONNECT_TIMEOUT_MS)
                    .setReadTimeoutMs(READ_TIMEOUT_MS)
                    .setAllowCrossProtocolRedirects(true);
            DefaultDataSource.Factory dataSourceFactory =
                    new DefaultDataSource.Factory(this, httpFactory);

            player = new ExoPlayer.Builder(this)
                    .setMediaSourceFactory(new DefaultMediaSourceFactory(dataSourceFactory))
                    .build();
            player.addListener(listener);
            playerView.setPlayer(player);

            MediaItem item = buildMediaItem(streamUrl, forceTs);
            player.setMediaItem(item);
            if (resumePosition != C.TIME_UNSET && !isLikelyLive(streamUrl)) {
                player.seekTo(resumePosition);
            }
            player.setPlayWhenReady(resumePlayWhenReady);
            log.event(interaction, "PLAY-PREPARE-START",
                    "engine=Media3 forcedTs=" + forceTs
                            + " mime=" + safeMime(item.localConfiguration == null
                            ? null : item.localConfiguration.mimeType));
            player.prepare();
            player.play();
        } catch (Throwable failure) {
            log.exception(interaction, "PLAY-SET-MEDIA-ERROR", failure);
            showFailure("PLAY-SET-MEDIA-ERROR",
                    "Der Stream konnte nicht an den Player übergeben werden.", true);
        }
    }

    private final Player.Listener listener = new Player.Listener() {
        @Override
        public void onPlaybackStateChanged(int playbackState) {
            if (playbackState == Player.STATE_BUFFERING) {
                status.setText("Stream wird gepuffert …");
                log.event(interaction, "PLAY-BUFFER-START",
                        "elapsedMs=" + elapsed());
            } else if (playbackState == Player.STATE_READY) {
                status.setText("Wiedergabe bereit");
                log.event(interaction, "PLAY-READY",
                        "elapsedMs=" + elapsed() + " durationMs="
                                + (player == null ? C.TIME_UNSET : player.getDuration()));
            } else if (playbackState == Player.STATE_ENDED) {
                status.setText("Wiedergabe beendet");
                log.event(interaction, "PLAY-ENDED", "elapsedMs=" + elapsed());
            }
        }

        @Override
        public void onIsPlayingChanged(boolean isPlaying) {
            if (isPlaying) {
                status.setText("Wiedergabe läuft");
                log.event(interaction, "PLAY-STARTED", "elapsedMs=" + elapsed());
            }
        }

        @Override
        public void onRenderedFirstFrame() {
            status.setText("Wiedergabe läuft");
            log.event(interaction, "PLAY-FIRST-FRAME",
                    "elapsedMs=" + elapsed() + " engine=Media3");
            title.postDelayed(() -> {
                if (!isFinishing() && player != null && player.isPlaying()) {
                    View parent = (View) title.getParent();
                    if (parent != null) parent.setVisibility(View.GONE);
                }
            }, 2500);
        }

        @Override
        public void onVideoSizeChanged(VideoSize videoSize) {
            log.event(interaction, "PLAY-VIDEO-SIZE",
                    "width=" + videoSize.width + " height=" + videoSize.height
                            + " ratio=" + videoSize.pixelWidthHeightRatio);
        }

        @Override
        public void onPlayerError(PlaybackException error) {
            String details = errorDetails(error);
            log.event(interaction, "PLAY-ERROR",
                    "engine=Media3 code=" + error.errorCode
                            + " name=" + error.errorCodeName
                            + " forcedTs=" + forcedTransportStream
                            + " elapsedMs=" + elapsed() + " " + details);

            if (!automaticFallbackUsed && !forcedTransportStream
                    && shouldTryTransportStreamFallback(error, streamUrl)) {
                automaticFallbackUsed = true;
                status.setText("Format wird als MPEG-TS erneut geöffnet …");
                log.event(interaction, "PLAY-FALLBACK-TS",
                        "reason=" + error.errorCodeName);
                playerView.postDelayed(() -> startPlayer(true), 250);
                return;
            }

            showFailure(error.errorCodeName,
                    friendlyMessage(error, details), true);
        }
    };

    private void retryFromBeginning() {
        automaticFallbackUsed = false;
        forcedTransportStream = false;
        resumePosition = C.TIME_UNSET;
        resumePlayWhenReady = true;
        log.event(interaction, "PLAY-RETRY", "manual=true");
        startPlayer(false);
    }

    private void saveAndRelease() {
        if (player == null || released) return;
        released = true;
        try {
            if (!isLikelyLive(streamUrl)) resumePosition = player.getCurrentPosition();
            resumePlayWhenReady = player.getPlayWhenReady();
            player.removeListener(listener);
            playerView.setPlayer(null);
            player.release();
        } catch (Throwable failure) {
            log.exception(interaction, "PLAYER-RELEASE-ERROR", failure);
        } finally {
            player = null;
        }
    }

    private void showFailure(String code, String message, boolean canRetry) {
        status.setText("Wiedergabe nicht möglich");
        View messageView = messageCard.findViewWithTag("message");
        if (messageView instanceof TextView) {
            ((TextView) messageView).setText(
                    "Wiedergabe nicht möglich\n\n" + message
                            + "\n\nDiagnosecode: " + code);
        }
        retryButton.setVisibility(canRetry ? View.VISIBLE : View.GONE);
        messageCard.setVisibility(View.VISIBLE);
    }

    private static MediaItem buildMediaItem(String url, boolean forceTs) {
        MediaItem.Builder builder = new MediaItem.Builder().setUri(url);
        String lower = url.toLowerCase(Locale.ROOT);
        if (forceTs || lower.contains(".ts?") || lower.endsWith(".ts")) {
            builder.setMimeType(MimeTypes.VIDEO_MP2T);
        } else if (lower.contains(".m3u8") || lower.contains("format=m3u8")) {
            builder.setMimeType(MimeTypes.APPLICATION_M3U8);
        }
        return builder.build();
    }

    private static boolean shouldTryTransportStreamFallback(
            PlaybackException error, String url) {
        if (url == null) return false;
        String lower = url.toLowerCase(Locale.ROOT);
        if (lower.contains(".m3u8")) return false;
        String name = error.errorCodeName == null ? "" : error.errorCodeName;
        return name.contains("PARSING")
                || name.contains("UNSPECIFIED")
                || name.contains("IO_UNSPECIFIED")
                || lower.contains("/live/")
                || lower.endsWith(".ts")
                || lower.contains(".ts?");
    }

    private static String friendlyMessage(PlaybackException error, String details) {
        String name = error.errorCodeName == null ? "" : error.errorCodeName;
        if (name.contains("BAD_HTTP_STATUS")) {
            return details.contains("httpStatus=401") || details.contains("httpStatus=403")
                    ? "Der Server hat den Stream abgewiesen. Zugang oder Streamadresse prüfen."
                    : "Der Streaming-Server hat mit einem Fehlerstatus geantwortet.";
        }
        if (name.contains("NETWORK_CONNECTION_TIMEOUT")) {
            return "Der Streaming-Server antwortet nicht rechtzeitig.";
        }
        if (name.contains("NETWORK_CONNECTION_FAILED")) {
            return "Die Netzwerkverbindung zum Streaming-Server ist fehlgeschlagen.";
        }
        if (name.contains("PARSING") || name.contains("CONTENT_TYPE")) {
            return "Das gelieferte Streamformat konnte nicht erkannt oder gelesen werden.";
        }
        if (name.contains("DECODER") || name.contains("DECODING")) {
            return "Der Video- oder Audiocodec wird auf diesem Gerät nicht unterstützt.";
        }
        return "Der Stream konnte nicht gestartet werden. Der genaue technische Fehler wurde in der Diagnose gespeichert.";
    }

    private static String errorDetails(PlaybackException error) {
        StringBuilder result = new StringBuilder();
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
        return "causeChain=" + result;
    }

    private static String profileLabel(String url) {
        String lower = url.toLowerCase(Locale.ROOT);
        if (lower.contains(".m3u8")) return "HLS";
        if (lower.endsWith(".ts") || lower.contains(".ts?") || lower.contains("/live/")) {
            return "MPEG-TS-LIVE";
        }
        try {
            URI uri = new URI(url);
            return "AUTO-" + (uri.getScheme() == null ? "UNKNOWN" : uri.getScheme().toUpperCase(Locale.ROOT));
        } catch (Exception ignored) {
            return "AUTO";
        }
    }

    private static boolean isLikelyLive(String url) {
        if (url == null) return true;
        String lower = url.toLowerCase(Locale.ROOT);
        return lower.contains("/live/") || lower.endsWith(".ts")
                || lower.contains(".ts?") || lower.contains(".m3u8");
    }

    private static String safeMime(@Nullable String mime) {
        return mime == null || mime.isBlank() ? "AUTO" : mime;
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
        button.setPadding(dp(10), 0, dp(10), 0);
        button.setBackground(roundRect(
                primary ? 0xFF5EEAD4 : 0xFF17354A,
                13,
                primary ? 0xFF5EEAD4 : 0xFF31566C));
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
