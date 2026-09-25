from pathlib import Path


LIVE_APIS = (Path("api/live.js"), Path("dashboard/api/live.js"))


def test_live_api_exposes_v5_retention_contract_fields():
    required = (
        "series_name",
        "episode_number",
        "cta_type",
        "follow_reason",
        "open_loop_status",
        "next_episode_candidate",
        "follow_conversion_gate",
        "return_viewer_gate",
        "golden_path_v5_state",
    )
    for path in LIVE_APIS:
        src = path.read_text(encoding="utf-8")
        for field in required:
            assert field in src, (path, field)


def test_control_center_renders_v5_retention_panel():
    src = Path("dashboard/live.html").read_text(encoding="utf-8")
    for element_id in (
        "retentionCard",
        "retSeries",
        "retEpisode",
        "retCtaType",
        "retFollowReason",
        "retOpenLoop",
        "retNextEpisode",
        "retFollowGate",
        "retReturnGate",
    ):
        assert f'id="{element_id}"' in src
    assert "renderRetention(req)" in src
    assert "Standalone / keine Serie" in src
    assert "Kein harter Folge-Teil geplant" in src
