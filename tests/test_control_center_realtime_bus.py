from pathlib import Path


PUBLISHER = Path('.github/workflows/tayvoriq-control-center-realtime-publisher.yml')


def test_realtime_publisher_is_observer_only():
    src = PUBLISHER.read_text(encoding='utf-8')
    assert 'TAYVORIQ Control Center Realtime Publisher' in src
    assert 'tayvoriq-ingest' in src
    assert 'workflow_run:' in src
    assert 'types: [requested, in_progress, completed]' in src
    assert 'gh workflow run' not in src
    assert 'repository_dispatch' not in src
    assert 'contents: write' not in src
    assert 'git push' not in src


def test_realtime_publisher_covers_core_lifecycle_signals():
    src = PUBLISHER.read_text(encoding='utf-8')
    for workflow in (
        'TAYVORIQ-X Golden Path',
        'TAYVORIQ Agent Orchestrator V2',
        'TAYVORIQ Production Green Promoter',
        'TAYVORIQ Deterministic Codefix Continuity',
        'TAYVORIQ Delivery Watch',
        'TAYVORIQ Request Continuity Watchdog',
        'TAYVORIQ Ops Health',
    ):
        assert workflow in src
