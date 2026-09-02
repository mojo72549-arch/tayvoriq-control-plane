from pathlib import Path


LIVE_APIS = (Path("api/live.js"), Path("dashboard/api/live.js"))


def test_live_api_reads_canonical_pointer_and_exact_request():
    for path in LIVE_APIS:
        src = path.read_text(encoding="utf-8")
        assert "ACTIVE_POINTER='.github/state/tayvoriq-active-production-request.json'" in src
        assert "requests/${pointer.request_id}.json" in src
        assert "canonical_run_id" in src
        assert "github-realtime+canonical-pointer" in src


def test_live_api_exposes_job_and_step_telemetry_from_both_repositories():
    for path in LIVE_APIS:
        src = path.read_text(encoding="utf-8")
        assert "STUDIO_REPO='mojo72549-arch/shorts-agent-studio'" in src
        assert "/jobs?filter=latest&per_page=100" in src
        assert "job_status" in src
        assert "step_number" in src
        assert "step_status" in src
        assert "owner:meta.owner" in src


def test_live_api_disables_stale_server_cache():
    for path in LIVE_APIS:
        src = path.read_text(encoding="utf-8")
        assert "Cache-Control','no-store, max-age=0, must-revalidate'" in src
        assert "s-maxage" not in src


def test_ops_health_uses_only_canonical_active_request():
    src = Path("scripts/tayvoriq_ops_health.py").read_text(encoding="utf-8")
        
    assert 'ACTIVE_POINTER = Path(".github/state/tayvoriq-active-production-request.json")' in src
    assert 'Path("requests") / f"{request_id}.json"' in src
    assert 'for path in Path("requests").glob("*.json")' not in src
    assert "pointer_run_id = pointer.get(\"golden_path_run_id\")" in src
    assert "recovery_generation = int((request_data or {}).get(\"recovery_generation\")" in src


def test_quality_health_is_execution_state_not_only_policy_state():
    src = Path("scripts/tayvoriq_ops_health.py").read_text(encoding="utf-8")
    assert 'publishable_stage = next((x for x in stages if x.get("label") == "Publishable Output")' in src
    assert 'quality_stage = next((x for x in stages if x.get("label") == "Quality Audit")' in src
    assert 'quality_detail = "Wartet auf reparierten Publishable Output"' in src
    assert '"status": quality_status' in src


def test_production_green_promoter_never_dispatches_codefix_helper():
    src = Path(".github/workflows/tayvoriq-production-green-promoter.yml").read_text(encoding="utf-8")
    assert "gh workflow run tayvoriq-deterministic-codefix-continuity.yml" not in src
    assert "Report verified Production Green state to Orchestrator" in src
    assert "actions: read" in src
