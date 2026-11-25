import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from tayvoriq_agent_trend_radar_v5 import _editorial_scan


def test_reviewed_packet_is_bound_to_the_exact_owner_selection(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sid = '20261125-evening-agentv2-c5187225d'
    monkeypatch.setenv('TAYVORIQ_RESEARCH_SELECTION_ID', sid)
    now = datetime(2026, 11, 25, 16, 30, tzinfo=timezone.utc)
    rows = []
    for i in range(2):
        rows.append({'title': f'Story {i}', 'sources': [
            {'url': f'https://{publisher}.example/story-{i}', 'publisher': publisher,
             'reporting_origin': publisher, 'published_at': now.isoformat(), 'supports': f'Original {publisher}'}
            for publisher in ('first', 'second')]})
    packet = {'selection_id': sid, 'slot': 'evening', 'target_date': '2026-11-25',
              'checked_at': now.isoformat(), 'candidates': rows}
    path = Path('state/tayvoriq-verified-research') / (sid + '.json')
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(packet))
    assert len(_editorial_scan('evening', now)[0]['candidates']) == 2
    packet['selection_id'] = '20261125-evening-agentv2-c00000000'
    path.write_text(json.dumps(packet))
    assert _editorial_scan('evening', now) is None
    packet['selection_id'] = sid
    packet['checked_at'] = '2026-11-24T16:30:00+00:00'
    path.write_text(json.dumps(packet))
    assert _editorial_scan('evening', now) is None


def test_a_selection_cannot_choose_an_arbitrary_research_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('TAYVORIQ_RESEARCH_SELECTION_ID', '../../../another')
    assert _editorial_scan('evening', datetime.now(timezone.utc)) is None
