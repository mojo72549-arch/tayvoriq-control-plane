"""Restore the already approved files from the private Contabo result."""
import argparse
import json
import re
import shutil
import tempfile
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from tayvoriq_artifact_approval import validate_decision, verify_package
from tayvoriq_contabo_review_binding import pending


def restore(archive, decision, request, review_id, destination):
    validate_decision(decision, review_id)
    if (request.get('execution_backend') != 'contabo_private_runner'
            or request.get('request_id') != decision.get('request_id')
            or request.get('source_context_sha256') != decision.get('source_context_sha256')):
        raise ValueError('CONTABO_REQUEST_BINDING_MISMATCH')

    prefix = f'site/tayvoriq/runs/{review_id}'
    control = 'out/control-plane'
    manifest_path = f'{control}/production-manifest.json'
    result_path = f'{control}/contabo-result.json'
    with tempfile.TemporaryDirectory() as staging, ZipFile(archive) as bundle:
        root = Path(staging)
        members = [name for name in bundle.namelist() if name.startswith(prefix+'/') and not name.endswith('/')]
        members.extend([manifest_path, result_path])
        if len(members) != len(set(members)) or any('..' in PurePosixPath(name).parts or '\\' in name for name in members):
            raise ValueError('CONTABO_ARCHIVE_PATH_INVALID')
        for name in members:
            bundle.extract(name, root)
        manifest = json.loads((root / manifest_path).read_text(encoding='utf-8'))
        result = json.loads((root / result_path).read_text(encoding='utf-8'))
        if (manifest.get('implementation_sha') != decision['studio_sha']
                or result.get('request_id') != decision['request_id']
                or str(result.get('run_id')) != review_id
                or result.get('source_context_sha256') != decision['source_context_sha256']
                or result.get('quality_passed') is not True
                or result.get('quality_gates_weakened') is not False):
            raise ValueError('CONTABO_RESULT_BINDING_MISMATCH')
        source = root / prefix
        normalized = pending(source, request, review_id, decision['artifact_run_id'], decision['studio_sha'])
        if normalized['telegram_message_id'] != decision['telegram_message_id']:
            raise ValueError('CONTABO_REVIEW_MESSAGE_MISMATCH')
        verify_package(source, decision, review_id)
        shutil.copytree(source, destination, dirs_exist_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('review_id', type=str)
    parser.add_argument('archive', type=Path)
    args = parser.parse_args()
    rid = args.review_id
    if not re.fullmatch(r'[0-9]{1,20}', rid):
        raise ValueError('REVIEW_ID_INVALID')
    decision = json.loads(Path(f'.automation/tayvoriq-artifact-decisions/{rid}.json').read_text())
    request_id = str(decision.get('request_id') or '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{4,80}', request_id):
        raise ValueError('REQUEST_ID_INVALID')
    request = json.loads(Path(f'requests/{request_id}.json').read_text())
    restore(args.archive, decision, request, rid, Path(f'approved-artifact/implementation/site/tayvoriq/runs/{rid}'))


if __name__ == '__main__':
    main()
