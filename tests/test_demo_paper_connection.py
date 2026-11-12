import contextlib
import importlib
import io
import json
import os
import time
import unittest
from unittest.mock import Mock, patch
from demo import paper_connection as paper
KEY = "key-NEVER-PRINT"
SECRET = "secret-NEVER-PRINT"
ACCOUNT_ID = "01234567-89ab-cdef-0123-456789abcdef"
OTHER_ID = "11234567-89ab-cdef-0123-456789abcdef"
ENV = {"APCA_API_KEY_ID": KEY, "APCA_API_SECRET_KEY": SECRET}
def payload(**overrides):
    data = {"id": ACCOUNT_ID, "status": "ACTIVE", "account_number": "account-NEVER-PRINT", "cash": "999999"}
    data.update(overrides)
    return json.dumps(data).encode()
class Response:
    def __init__(self, body=None, status=200, length=None):
        self.body = payload() if body is None else body
        self.status = status
        self.length = len(self.body) if length is None else length
        self.read_calls = []
        self.close_calls = 0
    def close(self):
        self.close_calls += 1
    def read(self, n):
        self.read_calls.append(n)
        out = self.body[:n]
        if self.length is not None:
            self.length -= len(out)
        return out


class PaperConnectionTests(unittest.TestCase):
    def setUp(self):
        p = patch.object(paper.http.client, "HTTPSConnection", autospec=True)
        self.connection_type = p.start()
        self.addCleanup(p.stop)
        self.connection = self.connection_type.return_value
        self.response = Response()
        self.connection.getresponse.return_value = self.response

    def test_import_does_not_read_environment_or_connect(self):
        with patch.object(os.environ, "get", side_effect=AssertionError("env read")), \
             patch("socket.create_connection", side_effect=AssertionError("network")):
            importlib.reload(paper)
        self.connection_type.assert_not_called()

    def test_exact_get_fixed_tls_origin_and_no_proxy_or_redirect(self):
        with patch.dict(os.environ, {"HTTPS_PROXY": "https://evil.invalid", "https_proxy": "https://evil.invalid"}):
            with patch("urllib.request.getproxies", side_effect=AssertionError("proxy")), \
                 patch("urllib.request.build_opener", side_effect=AssertionError("redirect")):
                self.assertEqual(paper._perform_check(KEY, SECRET, ACCOUNT_ID.upper()), ("ACTIVE", True))
        self.connection_type.assert_called_once_with("paper-api.alpaca.markets", timeout=5.0)
        self.connection.request.assert_called_once_with("GET", "/v2/account", headers={
            "Accept": "application/json", "APCA-API-KEY-ID": KEY, "APCA-API-SECRET-KEY": SECRET,
        })
        self.assertEqual(self.response.read_calls, [65537])
        self.assertEqual(self.response.close_calls, 1)
        self.connection.close.assert_called_once()

    def test_redirects_and_errors_are_not_read_or_followed(self):
        for status in (301, 302, 303, 307, 308, 400, 401, 403, 429, 500):
            with self.subTest(status=status):
                self.connection_type.reset_mock()
                response = Response(b"secret-body-NEVER-PRINT", status=status)
                self.connection.getresponse.return_value = response
                self.assertIsNone(paper._perform_check(KEY, SECRET, None))
                self.assertEqual(response.read_calls, [])
                self.assertEqual(response.close_calls, 1)
                self.assertEqual(self.connection_type.call_count, 1)
                self.connection.close.assert_called_once()

    def test_real_detached_http_responses_are_closed_on_every_path(self):
        cases = [
            (b'HTTP/1.1 302 Found\r\nConnection: close\r\nLocation: https://evil.invalid/\r\n\r\nsecret', None),
            (b'HTTP/1.1 200 OK\r\nConnection: close\r\n\r\n' + b'x' * (paper._MAX_BODY + 100), None),
            (b'HTTP/1.1 200 OK\r\nConnection: close\r\n\r\n' + payload(), ('ACTIVE', False)),
            (b'HTTP/1.1 200 OK\r\nConnection: close\r\n\r\nnot-json', None),
        ]
        for wire, expected in cases:
            with self.subTest(expected=expected, length=len(wire)):
                stream = io.BytesIO(wire)
                sock = Mock()
                sock.makefile.return_value = stream
                response = paper.http.client.HTTPResponse(sock)
                response.begin()
                self.assertTrue(response.will_close)
                self.connection.getresponse.return_value = response
                self.assertEqual(paper._perform_check(KEY, SECRET, None), expected)
                self.assertTrue(response.isclosed())
                self.assertTrue(stream.closed)

    def test_response_cleanup_errors_do_not_prevent_connection_cleanup(self):
        response = Mock(status=302)
        response.close.side_effect = RuntimeError(SECRET)
        self.connection.getresponse.return_value = response
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            self.assertIsNone(paper._perform_check(KEY, SECRET, None))
        self.assertEqual(output.getvalue(), '')
        response.close.assert_called_once()
        response.read.assert_not_called()
        self.connection.close.assert_called_once()

    def test_real_chunked_response_truncation_and_body_limit(self):
        body = payload()
        chunks = [
            (b'%x\r\n' % len(body) + body + b'\r\n0\r\n\r\n', ('ACTIVE', False)),
            (b'%x\r\n' % len(body) + body + b'\r\n', None),
            (b'%x\r\n' % (paper._MAX_BODY + 1) + b'x' * (paper._MAX_BODY + 1) + b'\r\n0\r\n\r\n', None),
        ]
        for chunked_body, expected in chunks:
            with self.subTest(length=len(chunked_body), expected=expected):
                stream = io.BytesIO(b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n' + chunked_body)
                sock = Mock()
                sock.makefile.return_value = stream
                response = paper.http.client.HTTPResponse(sock)
                response.begin()
                self.connection.getresponse.return_value = response
                self.assertEqual(paper._perform_check(KEY, SECRET, None), expected)
                self.assertTrue(stream.closed)

    def test_rejects_malformed_and_untrusted_json(self):
        cases = [
            b"", b"\xff", b"[]", b"null", b"{}", b'{"id":"' + ACCOUNT_ID.encode() + b'","status":"ACTIVE","status":"REJECTED"}',
            b'{"id":"' + ACCOUNT_ID.encode() + b'","status":"ACTIVE","nested":{"x":1,"x":2}}',
            b'{"id":"' + ACCOUNT_ID.encode() + b'","status":"ACTIVE","bad":NaN}',
            b'{"id":"' + ACCOUNT_ID.encode() + b'","status":"ACTIVE","bad":Infinity}',
            b'{"id":"' + ACCOUNT_ID.encode() + b'","status":"ACTIVE","bad":"\\ud800"}',
            b'{"id":"' + ACCOUNT_ID.encode() + b'","status":"ACTIVE","\\ud800":1}',
            payload(id="../../host"), payload(id=None), payload(status="active"),
            payload(status="TOKEN-NEVER-PRINT"), payload(status=None), payload(status=["ACTIVE"]),
            payload() + b"trailing", b"x" * (paper._MAX_BODY + 1),
        ]
        for body in cases:
            with self.subTest(body=body[:100]):
                self.connection.getresponse.return_value = Response(body)
                self.assertIsNone(paper._perform_check(KEY, SECRET, None))

    def test_content_length_truncation_rejected(self):
        self.connection.getresponse.return_value = Response(payload(), length=len(payload()) + 1)
        self.assertIsNone(paper._perform_check(KEY, SECRET, None))
        body = payload()
        wire = (b'HTTP/1.1 200 OK\r\nContent-Length: %d\r\n\r\n' % (len(body) + 1)) + body
        stream = io.BytesIO(wire)
        sock = Mock()
        sock.makefile.return_value = stream
        response = paper.http.client.HTTPResponse(sock)
        response.begin()
        self.connection.getresponse.return_value = response
        self.assertIsNone(paper._perform_check(KEY, SECRET, None))
        self.assertTrue(stream.closed)

    def test_response_body_size_boundary(self):
        body = payload()
        exact = body + b' ' * (paper._MAX_BODY - len(body))
        self.connection.getresponse.return_value = Response(exact)
        self.assertEqual(paper._perform_check(KEY, SECRET, None), ('ACTIVE', False))
        response = Response(exact + b' ')
        self.connection.getresponse.return_value = response
        self.assertIsNone(paper._perform_check(KEY, SECRET, None))
        self.assertEqual(response.read_calls, [paper._MAX_BODY + 1])
        self.assertEqual(response.close_calls, 1)


if __name__ == "__main__":
    unittest.main()
