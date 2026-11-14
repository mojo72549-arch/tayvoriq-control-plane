import base64
import sys
import json as jsonlib
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

import tayvoriq_request_state as state
from tayvoriq_orchestration_contract import contract_hash


def digest(letter):
    return letter * 64


def approval():
    request = jsonlib.loads((ROOT / 'requests/telegram-3549-trend-1.json').read_text())
    request['status'] = 'APPROVED'
    request['state_history'] = [{'state': 'APPROVED'}]
    return request


def at(day):
    return datetime(2026, 11, day, tzinfo=timezone.utc)


def identity(actor):
    return dict(actor=actor, run=354900, attempt=1)


def initial():
    return state.start(approval(), cutoff=at(11))


def proof_for(record, **proof):
    keys = ('request_id', 'contract_sha256', 'source_context_sha256')
    return {**{name: record[name] for name in keys}, **proof}


MASTER = dict(media_probe_passed=True, youtube_sha256=digest('a'), tiktok_sha256=digest('b'))
AUDIT = dict(passed=True, artifact_sha256=digest('c'), youtube_sha256=digest('a'), tiktok_sha256=digest('b'))
REVIEW = dict(confirmed=True, review_sha256=digest('d'), video_sha256=digest('b'), audit_sha256=digest('c'), message_id=987654)
STAGE_PROOFS = {
    'APPROVED': dict(duplicates_clear=True),
    **{name: dict(passed=True, artifact_sha256=digest('e'))
       for name in ('SOURCES_VALID', 'SCRIPT_READY', 'AUDIO_READY')},
    'VISUALS_READY': MASTER,
    'MASTER_READY': AUDIT,
    'QUALITY_PASSED': REVIEW,
}


def advance(record, **proof):
    who = identity(state.STAGES[record['state']][0])
    claimed = state.claim(record, record['revision'], **who)
    return state.complete(claimed, claimed['revision'], **who, proof=proof_for(record, **proof))


def reach(target):
    record = initial()
    while record['state'] != target:
        record = advance(record, **STAGE_PROOFS[record['state']])
    return record


def test_stale_and_previously_delivered_or_published_approval_cannot_start():
    with pytest.raises(ValueError, match='REQUEST_STALE'):
        state.start(approval(), cutoff=at(12))
    for evidence in ({'production_completion': {'telegram_message_id': 123}},
                     {'telegram_review_message_id': 123}, {'youtube_video_id': '123'},
                     {'tiktok_post_id': '123'}):
        with pytest.raises(ValueError, match='REQUEST_ALREADY_HANDLED'):
            state.start({**approval(), **evidence}, cutoff=at(11))
    unsigned = approval()
    unsigned['content_angle'] = 'New angle'
    with pytest.raises(SystemExit, match='contract_sha256 mismatch'):
        state.start(unsigned, cutoff=at(11))
    unsigned['source'] = 'manual'
    unsigned['contract_sha256'] = contract_hash(unsigned)
    with pytest.raises(ValueError, match='TELEGRAM_APPROVAL_REQUIRED'):
        state.start(unsigned, cutoff=at(11))
    with pytest.raises(ValueError, match='TELEGRAM_APPROVAL_REQUIRED'):
        state.start({**approval(), 'telegram_message_id': True}, cutoff=at(11))


def test_stage_lease_requires_one_owner_and_run_and_rejects_stale_writes():
    record = initial()
    who = identity('control')
    claimed = state.claim(record, 0, **who)
    proof = proof_for(record, duplicates_clear=True)
    with pytest.raises(ValueError, match='STALE_REQUEST_REVISION'):
        state.claim(claimed, 0, **who)
    with pytest.raises(ValueError, match='REQUEST_ALREADY_CLAIMED'):
        state.claim(claimed, 1, **who)
    with pytest.raises(ValueError, match='STAGE_LEASE_MISMATCH'):
        state.complete(claimed, 1, **{**who, 'run': 10}, proof=proof)
    with pytest.raises(ValueError, match='STAGE_EVIDENCE_REQUIRED'):
        state.complete(claimed, 1, **who, proof={**proof, 'source_context_sha256': digest('f')})
    assert state.complete(claimed, 1, **who, proof=proof)['state'] == 'SOURCES_VALID'


def test_media_audit_delivery_and_publication_require_correlated_evidence():
    record = reach('VISUALS_READY')
    with pytest.raises(ValueError, match='MASTER_READY'):
        advance(record, **{**MASTER, 'media_probe_passed': False})
    record = advance(record, **MASTER)
    with pytest.raises(ValueError, match='QUALITY_PASSED'):
        advance(record, **{**AUDIT, 'youtube_sha256': digest('f')})
    record = advance(record, **AUDIT)
    for invalid in ({'message_id': True}, {'message_id': 0}, {'video_sha256': digest('f')}):
        with pytest.raises(ValueError, match='REVIEW_DELIVERED'):
            advance(record, **{**REVIEW, **invalid})
    record = advance(record, **REVIEW)
    publication = dict(approved_message_id=REVIEW['message_id'], approval_id='callback',
                       youtube_video_id='yt-video', tiktok_post_id='tt-post')
    with pytest.raises(ValueError, match='PUBLICATION_APPROVAL_REQUIRED'):
        advance(record, **publication)
    with pytest.raises(ValueError, match='PUBLICATION_APPROVAL_REVIEW_MISMATCH'):
        state.approve_publication(record, record['revision'], actor='control', message_id=11,
                                  approval_id='callback', review_sha256=REVIEW['review_sha256'])
    record = state.approve_publication(record, record['revision'], actor='control',
                                       message_id=REVIEW['message_id'], approval_id='callback',
                                       review_sha256=REVIEW['review_sha256'])
    with pytest.raises(ValueError, match='PUBLISHED'):
        advance(record, **{**publication, 'tiktok_post_id': ''})
    with pytest.raises(ValueError, match='PUBLISHED'):
        advance(record, **{**publication, 'approved_message_id': 999})
    assert advance(record, **publication)['state'] == 'PUBLISHED'


def failure(record, kind, **details):
    who = identity(state.STAGES[record['state']][0])
    leased = state.claim(record, record['revision'], **who)
    return state.fail(leased, leased['revision'], **who, kind=kind, proof_sha256=digest('f'), **details)


def test_transient_retry_preserves_every_valid_stage_and_stops_at_limit():
    record = reach('VISUALS_READY')
    evidence = record['evidence']
    failed = failure(record, 'transient')
    assert failed['state'] == 'RENDER_FAILED'
    with pytest.raises(ValueError, match='RECOVERY_OWNER_REQUIRED'):
        state.recover(failed, failed['revision'], actor='studio')
    for _ in range(2):
        retried = state.recover(failed, failed['revision'], actor='recovery')
        assert retried['state'] == 'VISUALS_READY'
        assert retried['evidence'] == evidence
        failed = failure(retried, 'transient')
    with pytest.raises(ValueError, match='STAGE_RETRY_LIMIT_REACHED'):
        state.recover(failed, failed['revision'], actor='recovery')


def test_quality_only_regenerates_the_failed_product_and_its_dependents():
    record = reach('MASTER_READY')
    failed = failure(record, 'quality', dimension='visuals')
    recovered = state.recover(failed, failed['revision'], actor='recovery')
    assert recovered['state'] == 'AUDIO_READY'
    assert recovered['evidence'] == {k: record['evidence'][k] for k in ('SOURCES_VALID', 'SCRIPT_READY', 'AUDIO_READY')}


@pytest.mark.parametrize('kind', ['defect', 'external', 'unknown_delivery'])
def test_defects_external_blockers_and_uncertain_delivery_require_evidence_before_continuation(kind):
    failed = failure(reach('QUALITY_PASSED'), kind)
    with pytest.raises(ValueError, match='AUTOMATIC_RECOVERY_FORBIDDEN'):
        state.recover(failed, failed['revision'], actor='recovery')


def test_storage_update_fails_atomically_when_two_workers_claim_same_parent():
    from tayvoriq_request_store import Conflict, RequestStore, STATE_BRANCH

    record = initial()
    request_path = '/contents/requests/' + record['request_id'] + '.json'
    ref_path = '/git/refs/heads/' + STATE_BRANCH

    class GitData:
        head = 'initial-head'
        commits = {'initial-head': (None, record)}
        uncommitted = {}
        contender = None

        def __call__(self, method, path, *, params=None, json=None, missing_ok=False):
            if (method, path) == ('GET', '/git/ref/heads/' + STATE_BRANCH):
                return {'object': {'sha': self.head}}
            if (method, path) == ('GET', request_path):
                parent = self.commits[params['ref']][1]
                payload = jsonlib.dumps(parent).encode()
                return {'encoding': 'base64', 'content': base64.b64encode(payload).decode()}
            if method == 'GET' and path.startswith('/git/commits/'):
                return {'tree': {'sha': 'existing-tree'}}
            if (method, path) == ('POST', '/git/trees'):
                version = str(len(self.uncommitted))
                assert json['base_tree'] == 'existing-tree'
                self.uncommitted[version] = jsonlib.loads(json['tree'][0]['content'])
                return {'sha': version}
            if (method, path) == ('POST', '/git/commits'):
                self.commits[json['tree']] = (json['parents'][0], self.uncommitted[json['tree']])
                return {'sha': json['tree']}
            if (method, path) != ('PATCH', ref_path):
                raise AssertionError((method, path))
            if self.contender is not None:
                contender, self.contender = self.contender, None
                store.write(contender, expected_revision=0)
            assert json['force'] is False
            if self.commits[json['sha']][0] != self.head:
                raise HTTPError(ref_path, 422, 'non-fast-forward', None, None)
            self.head = json['sha']

    git = GitData()
    store = RequestStore(git)
    first = state.claim(record, 0, actor='control', run=1, attempt=1)
    git.contender = state.claim(record, 0, actor='control', run=2, attempt=1)
    with pytest.raises(Conflict, match='NON_FAST_FORWARD'):
        store.write(first, expected_revision=0)
    assert store.read(record['request_id'])['lease']['run'] == 2
    with pytest.raises(Conflict, match='STALE_REQUEST_REVISION'):
        store.write(first, expected_revision=0)
