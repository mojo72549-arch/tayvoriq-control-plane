"""Atomically persist request transitions on an isolated GitHub state branch."""
from __future__ import annotations

import base64
import json
import re
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from tayvoriq_request_state import REQUEST_ID


STATE_BRANCH = 'tayvoriq-request-state'


class Conflict(RuntimeError):
    """Another writer advanced the state branch from the same parent."""


class GitHubStateAPI:
    def __init__(self, repository, token):
        if not re.fullmatch(r'[A-Za-z0-9._-]+/[A-Za-z0-9._-]+', repository) or not token:
            raise ValueError('GITHUB_STATE_API_CONFIGURATION_INVALID')
        self._prefix = 'https://api.github.com/repos/' + repository
        self._headers = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json',
                         'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'}

    def __call__(self, method, path, *, params=None, json=None, missing_ok=False):
        query = '?' + urlencode(params) if params else ''
        return self._request(method, path + query, json, missing_ok)

    def _request(self, method, path, payload, missing_ok):
        data = json.dumps(payload).encode() if payload is not None else None
        request = Request(self._prefix + path, data=data, headers=self._headers, method=method)
        try:
            with urlopen(request, timeout=20) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code == 404 and missing_ok:
                return None
            raise


class RequestStore:
    def __init__(self, api):
        self._api = api

    @staticmethod
    def _path(request_id):
        if not isinstance(request_id, str) or not REQUEST_ID.fullmatch(request_id):
            raise ValueError('REQUEST_ID_INVALID')
        return f'requests/{request_id}.json'

    def _head(self):
        return self._api('GET', '/git/ref/heads/' + STATE_BRANCH)['object']['sha']

    def _get(self, request_id, head):
        return self._api('GET', '/contents/' + self._path(request_id), params={'ref': head}, missing_ok=True)

    def read(self, request_id):
        document = self._get(request_id, self._head())
        return self._decode(document) if document else None

    @staticmethod
    def _decode(document):
        if document.get('encoding') != 'base64':
            raise ValueError('UNSUPPORTED_REQUEST_ENCODING')
        return json.loads(base64.b64decode(document['content']))

    def write(self, record, *, expected_revision):
        request_id = record['request_id']
        path = self._path(request_id)
        head = self._head()
        document = self._get(request_id, head)
        current = self._decode(document) if document else None
        actual_revision = current['revision'] if current is not None else -1
        if actual_revision != expected_revision or record['revision'] != expected_revision + 1:
            raise Conflict('STALE_REQUEST_REVISION')
        if current and any(current[key] != record[key] for key in ('contract_sha256', 'source_context_sha256')):
            raise ValueError('IMMUTABLE_REQUEST_BINDING_CHANGED')
        base_tree = self._api('GET', '/git/commits/' + head)['tree']['sha']
        tree = self._api('POST', '/git/trees', json={
            'base_tree': base_tree,
            'tree': [{'path': path, 'mode': '100644', 'type': 'blob',
                      'content': json.dumps(record, ensure_ascii=False, sort_keys=True) + '\n'}],
        })
        commit = self._api('POST', '/git/commits', json={
            'tree': tree['sha'], 'parents': [head], 'message': f'Request {request_id} {record["state"]}',
        })
        # Non-force can publish only a descendant of the current ref. Two
        # workers starting from the same parent produce sibling commits.
        try:
            self._api('PATCH', '/git/refs/heads/' + STATE_BRANCH, json={'sha': commit['sha'], 'force': False})
        except HTTPError as error:
            if error.code not in (409, 422):
                raise
            if self._head() == head:
                raise
            raise Conflict('NON_FAST_FORWARD') from error
