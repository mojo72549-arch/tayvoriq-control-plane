from __future__ import annotations

import atexit
from pathlib import Path
import re
import sys


# GitHub Actions executes the existing RC5 and RC6 patch scripts directly from
# this directory.  Run the RC6.2 finishing patch only after apply_rc6_quality.py
# has completed, so all previous recovery anchors remain intact.
if Path(sys.argv[0]).name == "apply_rc6_quality.py":
    ROOT = Path(__file__).resolve().parents[1]

    def finish_rc62() -> None:
        build = ROOT / "app/build.gradle"
        content = build.read_text(encoding="utf-8")
        content, code_count = re.subn(r"versionCode\s+\d+", "versionCode 1320620", content, count=1)
        content, name_count = re.subn(
            r"versionName\s+'[^']+'",
            "versionName '13.2.0-rc6.2-clean-pip'",
            content,
            count=1,
        )
        if code_count != 1 or name_count != 1:
            raise RuntimeError("RC6.2 version anchors missing")
        build.write_text(content, encoding="utf-8")

        strings = ROOT / "app/src/main/res/values/strings.xml"
        content = strings.read_text(encoding="utf-8")
        content, label_count = re.subn(
            r'<string name="app_name">[^<]+</string>',
            '<string name="app_name">Project Lumen RC6.2</string>',
            content,
            count=1,
        )
        if label_count != 1:
            raise RuntimeError("RC6.2 app label anchor missing")
        strings.write_text(content, encoding="utf-8")

        player = ROOT / "app/src/main/java/com/projectlumen/pilot/robust/PlayerActivity.java"
        content = player.read_text(encoding="utf-8")

        entry_pattern = re.compile(
            r"    private boolean enterBackPictureInPicture\(\) \{.*?\n"
            r"    private boolean supportsPictureInPicture\(\) \{",
            re.DOTALL,
        )
        entry_replacement = '''    private boolean enterBackPictureInPicture() {
        if (!supportsPictureInPicture() || !playbackActive() || isFinishing()
                || isInPictureInPictureMode()) return false;

        // Hide every Project Lumen overlay before Android captures the PiP
        // transition frame. Waiting one animation frame prevents the title,
        // audio selector and status card from being frozen over the video.
        applyPictureInPictureUi(true);
        final PictureInPictureParams params = new PictureInPictureParams.Builder()
                .setAspectRatio(new Rational(16, 9))
                .build();
        final View transitionView = playerView != null
                ? playerView : getWindow().getDecorView();
        transitionView.postOnAnimation(() -> {
            try {
                boolean entered = enterPictureInPictureMode(params);
                log.event(interaction, "PLAYER-BACK-MINIMIZE",
                        "accepted=" + entered + " cleanUi=true");
                if (!entered) applyPictureInPictureUi(false);
            } catch (Throwable failure) {
                applyPictureInPictureUi(false);
                log.exception(interaction, "PLAYER-BACK-PIP-ERROR", failure);
            }
        });
        return true;
    }

    private boolean supportsPictureInPicture() {'''
        content, entry_count = entry_pattern.subn(entry_replacement, content, count=1)
        if entry_count != 1:
            raise RuntimeError("RC6.2 PiP entry anchor missing")

        callback_pattern = re.compile(
            r"    @Override\n"
            r"    public void onPictureInPictureModeChanged\(boolean active, Configuration configuration\) \{.*?\n"
            r"    private void buildUi\(\) \{",
            re.DOTALL,
        )
        callback_replacement = '''    private void applyPictureInPictureUi(boolean active) {
        inPictureInPicture = active;
        if (playerView != null) {
            playerView.setControllerAutoShow(!active);
            playerView.setUseController(!active);
            if (active) playerView.hideController();
        }
        if (topOverlay != null) {
            topOverlay.animate().cancel();
            topOverlay.clearAnimation();
            topOverlay.setAlpha(active ? 0f : 1f);
            topOverlay.setVisibility(active ? View.GONE : View.VISIBLE);
        }
        if (errorCard != null && active) errorCard.setVisibility(View.GONE);
        if (active) {
            getWindow().getDecorView().invalidate();
            if (playerView != null) playerView.invalidate();
        }
    }

    @Override
    public void onPictureInPictureModeChanged(boolean active, Configuration configuration) {
        super.onPictureInPictureModeChanged(active, configuration);
        applyPictureInPictureUi(active);
        log.event(interaction, active ? "PIP-ENTERED" : "PIP-EXITED",
                "trigger=BACK cleanUi=true");
    }

    private void buildUi() {'''
        content, callback_count = callback_pattern.subn(callback_replacement, content, count=1)
        if callback_count != 1:
            raise RuntimeError("RC6.2 PiP callback anchor missing")

        player.write_text(content, encoding="utf-8")

        final_source = player.read_text(encoding="utf-8")
        required = {
            "clean_transition": "postOnAnimation" in final_source,
            "overlay_hidden_before_entry": "applyPictureInPictureUi(true);" in final_source,
            "controller_hidden": "playerView.setUseController(!active);" in final_source,
            "overlay_gone": "topOverlay.setVisibility(active ? View.GONE : View.VISIBLE);" in final_source,
            "version": "13.2.0-rc6.2-clean-pip" in build.read_text(encoding="utf-8"),
            "label": "Project Lumen RC6.2" in strings.read_text(encoding="utf-8"),
        }
        missing = [name for name, ok in required.items() if not ok]
        if missing:
            raise RuntimeError(f"RC6.2 finishing verification failed: {missing}")
        print("RC6.2 clean PiP finishing patch passed:", ", ".join(required))

    atexit.register(finish_rc62)
