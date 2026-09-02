from pathlib import Path


LIVE_PAGE = Path("dashboard/live.html")
LOG_APIS = (Path("api/logs.js"), Path("dashboard/api/logs.js"))


def test_live_console_uses_realtime_api_and_automatic_refresh():
    src = LIVE_PAGE.read_text(encoding="utf-8")
    assert "fetch(`/api/live?v=${Date.now()}`" in src
    assert "state.pollMs=auth?(Number(live.active_count||0)>0?2500:5000):15000" in src
    assert "document.addEventListener('visibilitychange'" in src
    assert "Live Operations" in src
    assert "Technische Konsole" in src
    assert "Was passiert gerade?" in src


def test_live_console_detects_dispatched_recovery_without_executor():
    src = LIVE_PAGE.read_text(encoding="utf-8")
    assert "function continuityGap" in src
    assert "active===0&&rs.includes('DISPATCHED')" in src
    assert "Recovery ist als dispatched markiert, aber kein Executor läuft" in src


def test_live_console_can_show_completed_github_job_log_tail():
    page = LIVE_PAGE.read_text(encoding="utf-8")
    assert "/api/logs?repo=" in page
    assert "vollständiger GitHub-Logtail nach Abschluss" in page
    for path in LOG_APIS:
        src = path.read_text(encoding="utf-8")
        assert "actions/jobs/${job.id}/logs" in src
        assert "ALLOWED=new Set([CONTROL_REPO,STUDIO_REPO])" in src
        assert "Cache-Control','no-store, max-age=0, must-revalidate'" in src
        assert "REDACTED_GITHUB_TOKEN" in src
        assert "TELEGRAM_BOT_TOKEN" in src


def test_both_vercel_root_modes_route_to_same_live_console():
    root = Path("vercel.json").read_text(encoding="utf-8")
    dashboard = Path("dashboard/vercel.json").read_text(encoding="utf-8")
    assert '"destination": "/dashboard/live.html"' in root
    assert '"destination": "/live.html"' in dashboard
    assert "no-store, max-age=0, must-revalidate" in root
    assert "no-store, max-age=0, must-revalidate" in dashboard
