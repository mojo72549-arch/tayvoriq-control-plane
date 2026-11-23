from pathlib import Path


WORKER = Path("infra/telegram-approval-worker-v2.js")
TRENDS = Path(".github/workflows/tayvoriq-telegram-trends-now.yml")
ORCHESTRATOR = Path(".github/workflows/tayvoriq-agent-orchestrator-v2.yml")


def test_telegram_operator_has_safe_v5_commands():
    src = WORKER.read_text(encoding="utf-8")
    assert "tayvoriq_telegram_trends_now" in src
    assert "/trends" in src
    assert "/status" in src
    assert "/hilfe" in src
    assert "berlinDateSlot" in src
    assert "loadOpsHealth" in src
    assert "operatorStatusText" in src
    assert "Vor deiner Trendfreigabe startet keine Produktion" in src
    assert "Control Center ist nur Beobachtung" in src


def test_trends_command_enters_existing_v5_trend_workflow():
    src = TRENDS.read_text(encoding="utf-8")
    controller = ORCHESTRATOR.read_text(encoding="utf-8")
    assert "repository_dispatch:" in controller
    for event in ("tayvoriq_trend_approved", "tayvoriq_telegram_trends_now", "tayvoriq_trends_rejected",
                  "tayvoriq_research_tick"):
        assert f"      - {event}\n" in controller
    assert "uses: ./.github/workflows/tayvoriq-telegram-trends-now.yml" in controller
    assert "uses: ./.github/workflows/tayvoriq-request-dispatch.yml" in controller
    assert "uses: ./.github/workflows/tayvoriq-rejected-trend-refresh.yml" in controller
    assert "workflow_call:" in src
    assert 'EVENT_NAME: ${{ github.event_name }}' in src
    assert 'PAYLOAD_REQUESTED_VIA: ${{ github.event.client_payload.requested_via || \'\' }}' in src
    assert 'test "$PAYLOAD_REQUESTED_VIA" = "telegram_command"' in src
    assert 'case "$slot" in morning|evening)' in src
    assert "2 <= len(trends) <= 5" in src
    assert "quality_gates_weakened" in src
    assert "telegram_only_user_path" in src


def test_operator_does_not_add_unbounded_stop_or_publish_command():
    src = WORKER.read_text(encoding="utf-8").casefold()
    assert "/stop" not in src
    assert "tayvoriq_telegram_publish_now" not in src

