import json
import threading
import unittest
from collections import deque
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials

from tools.youtube_publish_approved import refresh_youtube_credentials


BAD_GATEWAY = (502, "text/html", b"<!DOCTYPE html><title>Error 502 (Server Error)</title>")
NEW_TOKEN = (
    200,
    "application/json",
    json.dumps({"access_token": "test-access-token", "expires_in": 3600}).encode(),
)
INVALID_GRANT = (400, "application/json", b'{"error": "invalid_grant"}')


@contextmanager
def token_endpoint(*responses):
    pending_responses = deque(responses)
    calls = []

    class TokenHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            calls.append(self.path)
            status, content_type, body = pending_responses.popleft() if pending_responses else (
                500, "text/plain", b"Unexpected token request"
            )
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), TokenHandler) as server:
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
        thread.start()
        try:
            yield Credentials(
                token=None,
                refresh_token="test-refresh-token",
                token_uri=f"http://127.0.0.1:{server.server_port}/token",
                client_id="test-client-id",
                client_secret="test-client-secret",
            ), calls
        finally:
            server.shutdown()
            thread.join()


class YouTubeOAuthRetryTest(unittest.TestCase):
    @patch("urllib3.util.retry.time.sleep")
    def test_html_502_recovers_with_same_credentials(self, sleep):
        with token_endpoint(BAD_GATEWAY, BAD_GATEWAY, NEW_TOKEN) as (credentials, calls):
            refresh_youtube_credentials(credentials)

        self.assertEqual(credentials.token, "test-access-token")
        self.assertEqual(calls, ["/token"] * 3)
        sleep.assert_called_once_with(30.0)

    @patch("urllib3.util.retry.time.sleep")
    def test_repeated_502_stops_after_two_retries(self, sleep):
        with token_endpoint(BAD_GATEWAY, BAD_GATEWAY, BAD_GATEWAY) as (credentials, calls):
            with self.assertRaises(RefreshError):
                refresh_youtube_credentials(credentials)

        self.assertIsNone(credentials.token)
        self.assertEqual(calls, ["/token"] * 3)

    def test_invalid_grant_stops_immediately(self):
        with token_endpoint(INVALID_GRANT, NEW_TOKEN) as (credentials, calls):
            with self.assertRaisesRegex(RefreshError, "invalid_grant"):
                refresh_youtube_credentials(credentials)

        self.assertIsNone(credentials.token)
        self.assertEqual(calls, ["/token"])
