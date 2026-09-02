from pathlib import Path


LIVE_APIS = (Path("api/live.js"), Path("dashboard/api/live.js"))
MEDIA_APIS = (Path("api/pilot-media.js"), Path("dashboard/api/pilot-media.js"))
LIVE_PAGE = Path("dashboard/live.html")


def test_live_api_reads_isolated_pilot_state_and_exact_run():
    for path in LIVE_APIS:
        src = path.read_text(encoding="utf-8")
        assert "PILOT_BRANCH='lab/cinematic-control-center'" in src
        assert "PILOT_STATE='cinematic-control-center/run-state.json'" in src
        assert "pilotRunId=Number(pilotState?.run_id||0)" in src
        assert "buildPilot(pilotState,pilotRun,pilotJobs)" in src
        assert "visual_review_ready" in src
        assert "gpu_cleanup" in src
        assert "buildOperatorFeed" in src
        assert "operator_feed:operatorFeed" in src
        assert "Shot ${currentShot.id} rendert jetzt" in src
        assert "Keine Nutzeraktion nötig" in src
        assert "PRIVATE_REPO_TOKEN" in src


def test_pilot_failure_is_gate_specific_and_user_action_is_external_only():
    for path in LIVE_APIS:
        src = path.read_text(encoding="utf-8")
        for failure_class in (
            "EXTERNAL_BLOCKER",
            "GPU_PROVISION_FAILED",
            "MODEL_LOAD_FAILED",
            "SHOT_RENDER_FAILED",
            "ARTIFACT_TRANSFER_FAILED",
            "PILOT_PUBLISH_FAILED",
        ):
            assert failure_class in src
        assert "user_action_required:userActionRequired" in src


def test_pilot_media_proxy_exposes_only_fixed_review_video():
    for path in MEDIA_APIS:
        src = path.read_text(encoding="utf-8")
        assert "PILOT_MEDIA='cinematic-control-center/media/latest-pilot.mp4'" in src
        assert "PILOT_BRANCH='lab/cinematic-control-center'" in src
        assert "payload?.download_url" in src
        assert "res.redirect(307,payload.download_url)" in src
        assert "req.query" not in src
        assert "TAYVORIQ_GITHUB_TOKEN" in src
        assert "PRIVATE_REPO_TOKEN" in src


def test_live_console_embeds_video_shots_cleanup_and_failure_reason():
    src = LIVE_PAGE.read_text(encoding="utf-8")
    assert 'id="pilotVideo"' in src
    assert 'id="pilotShots"' in src
    assert 'id="pilotCleanup"' in src
    assert 'id="pilotErrorTitle"' in src
    assert "renderPilot(d.pilot)" in src
    assert "fetchPilotLog(p)" in src
    assert "Voice, Musik und finaler Sound" in src
    assert 'id="operatorPanel"' in src
    assert 'id="operatorTitle"' in src
    assert 'id="operatorList"' in src
    assert "Codex Live · Was ich gerade mache" in src
    assert "renderOperator(d.operator_feed||[],d.pilot||{})" in src


def test_log_proxy_accepts_existing_private_repo_token_name():
    for path in (Path("api/logs.js"), Path("dashboard/api/logs.js")):
        src = path.read_text(encoding="utf-8")
        assert "PRIVATE_REPO_TOKEN" in src
