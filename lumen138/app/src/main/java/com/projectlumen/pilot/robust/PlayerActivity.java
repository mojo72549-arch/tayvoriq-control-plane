package com.projectlumen.pilot.robust;

import android.app.Activity;
import android.content.Context;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.media.AudioManager;
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

import androidx.media3.common.AudioAttributes;
import androidx.media3.common.C;
import androidx.media3.common.Format;
import androidx.media3.common.MediaItem;
import androidx.media3.common.MimeTypes;
import androidx.media3.common.PlaybackException;
import androidx.media3.common.Player;
import androidx.media3.common.TrackGroup;
import androidx.media3.common.TrackSelectionOverride;
import androidx.media3.common.Tracks;
import androidx.media3.common.VideoSize;
import androidx.media3.common.util.UnstableApi;
import androidx.media3.datasource.DefaultDataSource;
import androidx.media3.datasource.DefaultHttpDataSource;
import androidx.media3.datasource.HttpDataSource;
import androidx.media3.exoplayer.DefaultRenderersFactory;
import androidx.media3.exoplayer.ExoPlayer;
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory;
import androidx.media3.exoplayer.trackselection.DefaultTrackSelector;
import androidx.media3.ui.PlayerView;

import java.util.ArrayList;
import java.util.List;
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
    private Button audioButton;
    private ExoPlayer player;
    private DefaultTrackSelector trackSelector;

    private final List<AudioChoice> audioChoices = new ArrayList<>();
    private long openedAt;
    private long resumePosition = C.TIME_UNSET;
    private boolean playWhenReady = true;
    private boolean forceTs;
    private boolean fallbackUsed;
    private boolean audioAutoRecoveryUsed;
    private boolean stopped;
    private boolean compatibilityProfile;
    private int automaticRetryCount;
    private int audioChoiceIndex = -1;
    private Runnable pendingRetry;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        requestWindowFeature(Window.FEATURE_NO_TITLE);
        getWindow().setStatusBarColor(Color.BLACK);
        getWindow().setNavigationBarColor(Color.BLACK);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        setVolumeControlStream(AudioManager.STREAM_MUSIC);

        log = DiagnosticLog.get(this);
        interaction = getIntent().getStringExtra(EXTRA_INTERACTION);
        url = getIntent().getStringExtra(EXTRA_URL);
        name = getIntent().getStringExtra(EXTRA_NAME);
        if (name == null || name.isBlank()) name = "Stream";

        buildUi();
        log.event(interaction, "PLAYER-VIEW-CREATE-END",
                "created=true engine=Media3 audioRecovery=true httpRecovery=true");
        logDeviceAudioState();
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
        stopped = false;
        if (url != null && !url.isBlank() && player == null && pendingRetry == null) {
            startPlayer(false, false);
        }
    }

    @Override
    protected void onStop() {
        stopped = true;
        cancelPendingRetry();
        releasePlayer();
        super.onStop();
    }

    @Override
    protected void onDestroy() {
        cancelPendingRetry();
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
        top.setPadding(dp(14), dp(10), dp(14), dp(10));
        top.setBackground(roundRect(0xE6071724, 15, 0x663A637A));

        LinearLayout titleRow = new LinearLayout(this);
        titleRow.setGravity(Gravity.CENTER_VERTICAL);
        TextView title = text(name, 16, Color.WHITE, true);
        title.setSingleLine(true);
        titleRow.addView(title, new LinearLayout.LayoutParams(0, -2, 1f));

        audioButton = button("Ton: Auto", false);
        audioButton.setEnabled(false);
        audioButton.setAlpha(0.55f);
        audioButton.setOnClickListener(v -> selectNextAudioTrack());
        titleRow.addView(audioButton, new LinearLayout.LayoutParams(dp(112), dp(38)));
        top.addView(titleRow);

        status = text("Stream wird vorbereitet …", 12, 0xFFB7CAD8, false);
        status.setSingleLine(true);
        top.addView(status);

        FrameLayout.LayoutParams topParams = new FrameLayout.LayoutParams(
                Math.min(getResources().getDisplayMetrics().widthPixels - dp(24), dp(560)),
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

    private void startPlayer(boolean forcedTs, boolean compatibility) {
        cancelPendingRetry();
        releasePlayer();
        forceTs = forcedTs;
        compatibilityProfile = compatibility;
        openedAt = SystemClock.elapsedRealtime();
        errorCard.setVisibility(View.GONE);
        if (compatibility) {
            status.setText("Serververbindung wird neu aufgebaut …");
        } else {
            status.setText(forcedTs
                    ? "MPEG-TS-Fallback wird geöffnet …" : "Verbindung wird aufgebaut …");
        }
        audioChoices.clear();
        audioChoiceIndex = -1;
        audioButton.setText("Ton: Auto");
        audioButton.setEnabled(false);
        audioButton.setAlpha(0.55f);

        try {
            String userAgent = compatibility
                    ? "VLC/3.0.20 LibVLC/3.0.20"
                    : "ProjectLumen/13.1.50 Media3";
            DefaultHttpDataSource.Factory http = new DefaultHttpDataSource.Factory()
                    .setUserAgent(userAgent)
                    .setConnectTimeoutMs(15_000)
                    .setReadTimeoutMs(30_000)
                    .setAllowCrossProtocolRedirects(true);
            DefaultDataSource.Factory data = new DefaultDataSource.Factory(this, http);

            trackSelector = new DefaultTrackSelector(this);
            trackSelector.setParameters(trackSelector.buildUponParameters()
                    .setPreferredAudioLanguages("de", "tr", "en")
                    .setConstrainAudioChannelCountToDeviceCapabilities(true));

            DefaultRenderersFactory renderers = new DefaultRenderersFactory(this)
                    .setEnableDecoderFallback(true);
            player = new ExoPlayer.Builder(this, renderers)
                    .setTrackSelector(trackSelector)
                    .setMediaSourceFactory(new DefaultMediaSourceFactory(data))
                    .build();
            player.setAudioAttributes(new AudioAttributes.Builder()
                    .setUsage(C.USAGE_MEDIA)
                    .setContentType(C.AUDIO_CONTENT_TYPE_MOVIE)
                    .build(), true);
            player.setVolume(1f);
            player.addListener(listener);
            playerView.setPlayer(player);

            player.setMediaItem(mediaItem(url, forcedTs));
            if (resumePosition != C.TIME_UNSET && !isLikelyLive(url)) {
                player.seekTo(resumePosition);
            }
            player.setPlayWhenReady(playWhenReady);
            log.event(interaction, "PLAY-PREPARE-START",
                    "engine=Media3 forcedTs=" + forcedTs
                            + " profile=" + profile(url)
                            + " connectionProfile=" + (compatibility ? "COMPAT" : "LUMEN")
                            + " decoderFallback=true");
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
                pendingRetry = null;
                status.setText(audioChoices.isEmpty()
                        ? "Bild bereit · Tonspur wird geprüft" : "Wiedergabe bereit");
                log.event(interaction, "PLAY-READY",
                        "elapsedMs=" + elapsed()
                                + " volume=" + (player == null ? -1f : player.getVolume())
                                + " connectionProfile="
                                + (compatibilityProfile ? "COMPAT" : "LUMEN"));
            } else if (state == Player.STATE_ENDED) {
                status.setText("Wiedergabe beendet");
                log.event(interaction, "PLAY-ENDED", "elapsedMs=" + elapsed());
            }
        }

        @Override
        public void onTracksChanged(Tracks tracks) {
            inspectAndRecoverAudio(tracks);
        }

        @Override
        public void onIsPlayingChanged(boolean playing) {
            if (playing) {
                status.setText(audioChoices.isEmpty()
                        ? "Bild läuft · keine Tonspur erkannt" : "Wiedergabe läuft");
                log.event(interaction, "PLAY-STARTED",
                        "elapsedMs=" + elapsed() + " audioChoices=" + audioChoices.size());
            }
        }

        @Override
        public void onRenderedFirstFrame() {
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
            String mediaError = errorName(error);
            int httpStatus = httpStatus(error);
            String details = errorDetails(error);
            PlaybackFailurePolicy.Decision decision = PlaybackFailurePolicy.decide(
                    mediaError, httpStatus, automaticRetryCount, forceTs, url);

            log.event(interaction, "PLAY-ERROR",
                    "engine=Media3 code=" + error.errorCode
                            + " name=" + mediaError
                            + " classified=" + decision.code
                            + " forcedTs=" + forceTs
                            + " elapsedMs=" + elapsed() + " " + details);

            if (httpStatus > 0) {
                log.event(interaction, "PLAY-HTTP-STATUS",
                        "status=" + httpStatus
                                + " automaticRetryCount=" + automaticRetryCount
                                + " connectionProfile="
                                + (compatibilityProfile ? "COMPAT" : "LUMEN"));
            }

            if (decision.automaticRetry) {
                scheduleAutomaticRetry(decision, httpStatus);
                return;
            }

            if (!fallbackUsed && decision.transportStreamFallback) {
                fallbackUsed = true;
                log.event(interaction, "PLAY-FALLBACK-TS", "reason=" + mediaError);
                status.setText("Format wird als MPEG-TS erneut geöffnet …");
                playerView.postDelayed(() -> {
                    if (!stopped && !isFinishing()) startPlayer(true, compatibilityProfile);
                }, 250L);
                return;
            }

            if (httpStatus > 0 && automaticRetryCount > 0) {
                log.event(interaction, "PLAY-HTTP-RETRY-EXHAUSTED",
                        "status=" + httpStatus + " attempts=" + automaticRetryCount);
            }
            showError(decision.code, decision.message, true);
        }
    };

    private void scheduleAutomaticRetry(PlaybackFailurePolicy.Decision decision,
                                        int httpStatus) {
        automaticRetryCount++;
        compatibilityProfile = true;
        releasePlayer();
        errorCard.setVisibility(View.GONE);
        status.setText(httpStatus > 0
                ? "Server meldet HTTP " + httpStatus + " · neuer Versuch …"
                : "Verbindung wird einmal neu aufgebaut …");
        log.event(interaction, "PLAY-HTTP-RETRY-SCHEDULED",
                "status=" + httpStatus
                        + " attempt=" + automaticRetryCount
                        + " delayMs=" + decision.retryDelayMs
                        + " nextProfile=COMPAT");
        pendingRetry = () -> {
            pendingRetry = null;
            if (!stopped && !isFinishing() && !isDestroyed()) {
                startPlayer(false, true);
            }
        };
        playerView.postDelayed(pendingRetry, decision.retryDelayMs);
    }

    private void cancelPendingRetry() {
        if (pendingRetry == null || playerView == null) return;
        playerView.removeCallbacks(pendingRetry);
        pendingRetry = null;
    }

    private void inspectAndRecoverAudio(Tracks tracks) {
        audioChoices.clear();
        int audioTracks = 0;
        int supportedTracks = 0;
        int selectedTracks = 0;
        AudioChoice firstSupported = null;

        for (Tracks.Group group : tracks.getGroups()) {
            if (group.getType() != C.TRACK_TYPE_AUDIO) continue;
            TrackGroup mediaGroup = group.getMediaTrackGroup();
            for (int index = 0; index < group.length; index++) {
                audioTracks++;
                Format format = group.getTrackFormat(index);
                boolean supported = group.isTrackSupported(index);
                boolean selected = group.isTrackSelected(index);
                if (supported) supportedTracks++;
                if (selected) selectedTracks++;
                AudioChoice choice = new AudioChoice(
                        mediaGroup, index, format, supported, selected);
                audioChoices.add(choice);
                if (firstSupported == null && supported) firstSupported = choice;
                log.event(interaction, "PLAY-AUDIO-TRACK",
                        "index=" + (audioChoices.size() - 1)
                                + " selected=" + selected
                                + " supported=" + supported
                                + " mime=" + safe(format.sampleMimeType)
                                + " codecs=" + safe(format.codecs)
                                + " language=" + safe(format.language)
                                + " channels=" + format.channelCount
                                + " sampleRate=" + format.sampleRate
                                + " bitrate=" + format.bitrate);
            }
        }

        log.event(interaction, "PLAY-AUDIO-SUMMARY",
                "tracks=" + audioTracks
                        + " supported=" + supportedTracks
                        + " selected=" + selectedTracks);

        if (supportedTracks > 0) {
            audioButton.setEnabled(true);
            audioButton.setAlpha(1f);
            int selectedIndex = selectedChoiceIndex();
            audioChoiceIndex = selectedIndex;
            audioButton.setText(selectedIndex >= 0
                    ? "Ton: " + audioChoices.get(selectedIndex).shortLabel() : "Ton: Auto");
        }

        if (selectedTracks == 0 && firstSupported != null
                && !audioAutoRecoveryUsed && player != null) {
            audioAutoRecoveryUsed = true;
            TrackSelectionOverride override = new TrackSelectionOverride(
                    firstSupported.group, firstSupported.trackIndex);
            player.setTrackSelectionParameters(
                    player.getTrackSelectionParameters().buildUpon()
                            .setOverrideForType(override).build());
            log.event(interaction, "PLAY-AUDIO-AUTO-SELECT",
                    "mime=" + safe(firstSupported.format.sampleMimeType)
                            + " language=" + safe(firstSupported.format.language));
            status.setText("Tonspur wird automatisch aktiviert …");
        } else if (audioTracks > 0 && supportedTracks == 0) {
            status.setText("Bild läuft · Tonformat nicht unterstützt");
            log.event(interaction, "PLAY-AUDIO-UNSUPPORTED", "tracks=" + audioTracks);
        } else if (audioTracks == 0) {
            status.setText("Bild läuft · keine Tonspur im Stream erkannt");
            log.event(interaction, "PLAY-AUDIO-NONE", "tracks=0");
        }
    }

    private int selectedChoiceIndex() {
        for (int index = 0; index < audioChoices.size(); index++) {
            if (audioChoices.get(index).selected) return index;
        }
        return -1;
    }

    private void selectNextAudioTrack() {
        if (player == null || audioChoices.isEmpty()) return;
        int start = audioChoiceIndex;
        for (int step = 1; step <= audioChoices.size(); step++) {
            int index = (Math.max(-1, start) + step) % audioChoices.size();
            AudioChoice choice = audioChoices.get(index);
            if (!choice.supported) continue;
            TrackSelectionOverride override = new TrackSelectionOverride(
                    choice.group, choice.trackIndex);
            player.setTrackSelectionParameters(
                    player.getTrackSelectionParameters().buildUpon()
                            .setOverrideForType(override).build());
            audioChoiceIndex = index;
            audioButton.setText("Ton: " + choice.shortLabel());
            status.setText("Tonspur " + choice.longLabel() + " wird aktiviert …");
            log.event(interaction, "PLAY-AUDIO-MANUAL-SELECT",
                    "index=" + index
                            + " mime=" + safe(choice.format.sampleMimeType)
                            + " language=" + safe(choice.format.language));
            return;
        }
    }

    private void logDeviceAudioState() {
        AudioManager audio = (AudioManager) getSystemService(Context.AUDIO_SERVICE);
        if (audio == null) return;
        log.event(interaction, "PLAY-DEVICE-AUDIO",
                "musicVolume=" + audio.getStreamVolume(AudioManager.STREAM_MUSIC)
                        + " musicMax=" + audio.getStreamMaxVolume(AudioManager.STREAM_MUSIC)
                        + " musicMuted=" + audio.isStreamMute(AudioManager.STREAM_MUSIC)
                        + " mode=" + audio.getMode());
    }

    private void retry() {
        cancelPendingRetry();
        fallbackUsed = false;
        forceTs = false;
        compatibilityProfile = false;
        automaticRetryCount = 0;
        audioAutoRecoveryUsed = false;
        resumePosition = C.TIME_UNSET;
        playWhenReady = true;
        log.event(interaction, "PLAY-RETRY", "manual=true resetHttpRecovery=true");
        startPlayer(false, false);
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
            trackSelector = null;
        }
    }

    private void showError(String code, String message, boolean retryVisible) {
        status.setText("Wiedergabe nicht möglich");
        errorText.setText("Wiedergabe nicht möglich\n\n"
                + message + "\n\nDiagnosecode: " + code);
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

    private static String errorName(PlaybackException error) {
        String value = error == null ? null : error.getErrorCodeName();
        return value == null || value.isBlank()
                ? "ERROR_CODE_UNSPECIFIED" : value;
    }

    private static int httpStatus(Throwable error) {
        Throwable current = error;
        int depth = 0;
        while (current != null && depth < 8) {
            if (current instanceof HttpDataSource.InvalidResponseCodeException) {
                return ((HttpDataSource.InvalidResponseCodeException) current).responseCode;
            }
            current = current.getCause();
            depth++;
        }
        return -1;
    }

    private static String errorDetails(PlaybackException error) {
        StringBuilder result = new StringBuilder("causeChain=");
        Throwable current = error;
        int depth = 0;
        while (current != null && depth < 8) {
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
        if (lower.endsWith(".ts") || lower.contains(".ts?")
                || lower.contains("/live/")) return "MPEG-TS-LIVE";
        return "AUTO";
    }

    private static boolean isLikelyLive(String streamUrl) {
        if (streamUrl == null) return true;
        String lower = streamUrl.toLowerCase(Locale.ROOT);
        return lower.contains("/live/") || lower.endsWith(".ts")
                || lower.contains(".ts?") || lower.contains(".m3u8");
    }

    private static String safe(String value) {
        return value == null || value.isBlank()
                ? "-" : value.replaceAll("[\\r\\n\\t]", " ");
    }

    private long elapsed() {
        return openedAt <= 0 ? 0
                : Math.max(0, SystemClock.elapsedRealtime() - openedAt);
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
        button.setTextSize(11);
        button.setAllCaps(false);
        button.setSingleLine(true);
        button.setTextColor(primary ? 0xFF07111E : Color.WHITE);
        button.setPadding(dp(9), 0, dp(9), 0);
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

    private static final class AudioChoice {
        final TrackGroup group;
        final int trackIndex;
        final Format format;
        final boolean supported;
        final boolean selected;

        AudioChoice(TrackGroup group, int trackIndex, Format format,
                    boolean supported, boolean selected) {
            this.group = group;
            this.trackIndex = trackIndex;
            this.format = format;
            this.supported = supported;
            this.selected = selected;
        }

        String shortLabel() {
            if (format.language != null && !format.language.isBlank()) {
                return format.language.toUpperCase(Locale.ROOT);
            }
            String mime = format.sampleMimeType == null
                    ? "Audio" : format.sampleMimeType;
            int slash = mime.indexOf('/');
            return (slash >= 0 ? mime.substring(slash + 1) : mime)
                    .toUpperCase(Locale.ROOT);
        }

        String longLabel() {
            return shortLabel() + (format.channelCount > 0
                    ? " · " + format.channelCount + " Kanäle" : "");
        }
    }
}
