from __future__ import annotations

import http.client
import json
import threading
import unittest
from datetime import datetime, timezone

from demo.server import DemoHTTPServer


class StubSimulator:
    def __init__(self):
        self.orders = []

    def snapshot(self):
        return {"cash": 10_000, "symbol": "AAPL", "orders": len(self.orders)}

    def place_order(self, payload, idempotency_key, quote, now):
        assert isinstance(now, datetime) and now.tzinfo is timezone.utc
        self.orders.append((payload, idempotency_key, quote))
        return {"id": "sim-1", "status": "accepted", "quote_source": quote.source if quote else "unavailable"}

    def cancel_order(self, order_id):
        return {"id": order_id, "status": "cancelled"}


class StubQuote:
    def __init__(self, symbol="AAPL"):
        self.source = "fixture"
        self.symbol = symbol
        self.bid = 99.5
        self.ask = 100.5


def fixture_quote(symbol):
    return StubQuote(symbol)


class DemoServerSocketTests(unittest.TestCase):
    def setUp(self):
        self.simulator = StubSimulator()
        self.server = DemoHTTPServer(("127.0.0.1", 0), self.simulator, fixture_quote)
        self.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, method, path, body=None, headers=None):
        headers = dict(headers or {})
        headers.setdefault("Host", f"127.0.0.1:{self.port}")
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        data = response.read()
        connection.close()
        return response.status, json.loads(data.decode("utf-8")), dict(response.getheaders())

    def auth_headers(self):
        return {"X-Session-Token": self.server.session_token}

    def post_headers(self):
        return {
            **self.auth_headers(),
            "Origin": f"http://127.0.0.1:{self.port}",
            "X-CSRF-Token": self.server.csrf_token,
            "Content-Type": "application/json",
        }

    def test_only_loopback_binding_is_permitted(self):
        with self.assertRaises(ValueError):
            DemoHTTPServer(("0.0.0.0", 0), StubSimulator(), fixture_quote)

    def test_health_is_public_but_api_requires_token(self):
        status, body, _headers = self.request("GET", "/health")
        self.assertEqual((status, body), (200, {"status": "ok", "service": "local_simulator"}))
        status, body, _headers = self.request("GET", "/api/snapshot")
        self.assertEqual((status, body), (401, {"error": "authentication_required"}))

    def test_index_and_errors_do_not_expose_session_token(self):
        # Fetch raw content so the token check covers all HTML bytes.
        connection = http.client.HTTPConnection("127.0.0.1", self.port)
        connection.request("GET", "/", headers={"Host": f"127.0.0.1:{self.port}"})
        response = connection.getresponse()
        raw = response.read().decode("utf-8")
        connection.close()
        self.assertEqual(response.status, 200)
        self.assertNotIn(self.server.session_token, raw)
        self.assertEqual(response.getheader("Cache-Control"), "no-store")

    def test_strict_host_prevents_dns_rebinding(self):
        status, body, _headers = self.request("GET", "/health", headers={"Host": "evil.example"})
        self.assertEqual((status, body), (400, {"error": "invalid_host"}))

    def test_authenticated_snapshot_and_fixture_quote(self):
        status, body, _headers = self.request("GET", "/api/snapshot", headers=self.auth_headers())
        self.assertEqual(status, 200)
        self.assertEqual(body["snapshot"]["cash"], 10_000)
        status, body, _headers = self.request("GET", "/api/quote?symbol=AAPL", headers=self.auth_headers())
        self.assertEqual(status, 200)
        self.assertEqual(body["quote"]["source"], "fixture")

    def test_post_requires_exact_origin_and_csrf(self):
        payload = json.dumps({"order": {"symbol": "AAPL", "side": "buy", "quantity": 1}, "idempotency_key": "one", "quote_symbol": "AAPL"})
        status, body, _headers = self.request("POST", "/api/orders", payload, {**self.auth_headers(), "Content-Type": "application/json"})
        self.assertEqual((status, body), (403, {"error": "invalid_origin"}))
        headers = self.post_headers()
        headers["Origin"] = "http://localhost:%s" % self.port
        status, body, _headers = self.request("POST", "/api/orders", payload, headers)
        self.assertEqual((status, body), (403, {"error": "invalid_origin"}))
        status, body, _headers = self.request("POST", "/api/orders", payload, self.post_headers())
        self.assertEqual(status, 200)
        self.assertEqual(body["order"]["status"], "accepted")
        self.assertEqual(len(self.simulator.orders), 1)

    def test_order_and_quote_symbols_must_be_aapl_and_match_before_quote_lookup(self):
        quote_lookups = []

        def recording_quote_provider(symbol):
            quote_lookups.append(symbol)
            return StubQuote(symbol)

        self.server.quote_provider = recording_quote_provider
        mismatched = json.dumps({
            "order": {"symbol": "AAPL", "side": "buy", "quantity": 1},
            "idempotency_key": "mismatched-quote",
            "quote_symbol": "MSFT",
        })
        status, body, _headers = self.request("POST", "/api/orders", mismatched, self.post_headers())
        self.assertEqual((status, body), (400, {"error": "quote_symbol_mismatch"}))
        self.assertEqual(quote_lookups, [])
        self.assertEqual(self.simulator.orders, [])

        unsupported = json.dumps({
            "order": {"symbol": "MSFT", "side": "buy", "quantity": 1},
            "idempotency_key": "unsupported-symbol",
            "quote_symbol": "MSFT",
        })
        status, body, _headers = self.request("POST", "/api/orders", unsupported, self.post_headers())
        self.assertEqual((status, body), (400, {"error": "unsupported_symbol"}))
        self.assertEqual(quote_lookups, [])

    def test_route_input_is_strict_and_duplicate_json_is_rejected(self):
        status, body, _headers = self.request("GET", "/api/quote?nope=1", headers=self.auth_headers())
        self.assertEqual((status, body), (404, {"error": "not_found"}))
        duplicate = b'{"order":{},"order":{},"idempotency_key":"x"}'
        status, body, _headers = self.request("POST", "/api/orders", duplicate, self.post_headers())
        self.assertEqual((status, body), (400, {"error": "invalid_request"}))
        too_large = b"{" + b" " * (16 * 1024) + b"}"
        status, body, _headers = self.request("POST", "/api/orders", too_large, self.post_headers())
        self.assertEqual((status, body), (400, {"error": "invalid_request"}))


if __name__ == "__main__":
    unittest.main()

class DemoServerAdversarialRegressionTests(DemoServerSocketTests):
    def raw_request(self, request: bytes) -> bytes:
        connection = __import__('socket').create_connection(('127.0.0.1', self.port), timeout=2)
        try:
            connection.sendall(request)
            connection.shutdown(__import__('socket').SHUT_WR)
            parts = []
            while True:
                chunk = connection.recv(4096)
                if not chunk:
                    break
                parts.append(chunk)
            return b''.join(parts)
        finally:
            connection.close()

    def test_bootstrap_never_releases_csrf_without_exactly_one_session_token(self):
        for headers in ({}, {'X-Session-Token': 'wrong'}):
            status, body, _ = self.request('GET', '/api/bootstrap', headers=headers)
            self.assertEqual((status, body), (401, {'error': 'authentication_required'}))
            self.assertNotIn(self.server.csrf_token, json.dumps(body))
        raw = (f'GET /api/bootstrap HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n'
               f'X-Session-Token: {self.server.session_token}\r\nX-Session-Token: wrong\r\n\r\n').encode()
        self.assertIn(b'401 Unauthorized', self.raw_request(raw))

    def test_get_cannot_change_state_and_writes_need_session_origin_and_csrf(self):
        payload = json.dumps({'order': {'symbol': 'AAPL', 'side': 'BUY', 'quantity': 1, 'limit_price': '100.50'}, 'idempotency_key': 'read-only', 'quote_symbol': 'AAPL'})
        status, body, _ = self.request('GET', '/api/orders', headers=self.auth_headers())
        self.assertEqual((status, body), (404, {'error': 'not_found'}))
        status, body, _ = self.request('POST', '/api/orders', payload, {'Content-Type': 'application/json'})
        self.assertEqual((status, body), (401, {'error': 'authentication_required'}))
        bad_csrf = self.post_headers(); bad_csrf['X-CSRF-Token'] = 'wrong'
        status, body, _ = self.request('POST', '/api/orders', payload, bad_csrf)
        self.assertEqual((status, body), (403, {'error': 'csrf_required'}))
        self.assertEqual(self.simulator.orders, [])

    def test_duplicate_security_headers_and_oversized_body_close_without_request_smuggling(self):
        base = f'Host: 127.0.0.1:{self.port}\r\nX-Session-Token: {self.server.session_token}\r\n'
        duplicate_origin = (f'POST /api/orders HTTP/1.1\r\n{base}Origin: http://127.0.0.1:{self.port}\r\nOrigin: http://evil.example\r\nX-CSRF-Token: {self.server.csrf_token}\r\nContent-Type: application/json\r\nContent-Length: 2\r\n\r\n{{}}').encode()
        self.assertIn(b'403 Forbidden', self.raw_request(duplicate_origin))
        oversized = (f'POST /api/orders HTTP/1.1\r\n{base}Origin: http://127.0.0.1:{self.port}\r\nX-CSRF-Token: {self.server.csrf_token}\r\nContent-Type: application/json\r\nContent-Length: 20000\r\n\r\nGET /health HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n\r\n').encode()
        response = self.raw_request(oversized)
        self.assertIn(b'400 Bad Request', response)
        self.assertNotIn(b'200 OK', response)

    def test_slow_incomplete_body_does_not_block_another_loopback_request(self):
        import socket
        slow = socket.create_connection(('127.0.0.1', self.port), timeout=2)
        try:
            slow.sendall((f'POST /api/orders HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\nX-Session-Token: {self.server.session_token}\r\nOrigin: http://127.0.0.1:{self.port}\r\nX-CSRF-Token: {self.server.csrf_token}\r\nContent-Type: application/json\r\nContent-Length: 16\r\n\r\n').encode())
            status, body, _ = self.request('GET', '/health')
            self.assertEqual((status, body), (200, {'status': 'ok', 'service': 'local_simulator'}))
        finally:
            slow.close()

    def test_fixture_http_ui_flow_places_only_a_simulated_order_and_html_is_accurate(self):
        status, bootstrap, _ = self.request('GET', '/api/bootstrap', headers=self.auth_headers())
        self.assertEqual(status, 200)
        headers = self.post_headers(); headers['X-CSRF-Token'] = bootstrap['csrf_token']
        status, quote, _ = self.request('GET', '/api/quote?symbol=AAPL', headers=self.auth_headers())
        self.assertEqual((status, quote['quote']['source']), (200, 'fixture'))
        payload = json.dumps({'order': {'symbol': 'AAPL', 'side': 'BUY', 'quantity': 1, 'limit_price': '100.50'}, 'idempotency_key': 'ui-fill-1', 'quote_symbol': 'AAPL'})
        status, result, _ = self.request('POST', '/api/orders', payload, headers)
        self.assertEqual((status, result['order']['status']), (200, 'accepted'))
        html = __import__('pathlib').Path('demo/index.html').read_text(encoding='utf-8')
        self.assertIn('In-memory simulator state', html)
        self.assertIn('Get AAPL quote', html)
        self.assertIn("'simulated fixture'", html)
        self.assertIn("$('session-token').value = '';", html)
        self.assertIn("'X-Session-Token': token", html)
        self.assertNotIn('Get fixture quote', html)

class DemoFixtureModeEndToEndTests(unittest.TestCase):
    def test_real_fixture_mode_serves_static_quote_and_simulated_fill(self):
        from demo.server import make_server

        server = make_server(0, 'fixture')
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_port
            def request(method, path, body=None, headers=None):
                connection = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
                merged = {'Host': f'127.0.0.1:{port}', **(headers or {})}
                connection.request(method, path, body=body, headers=merged)
                response = connection.getresponse()
                result = response.status, json.loads(response.read().decode('utf-8'))
                connection.close()
                return result
            auth = {'X-Session-Token': server.session_token}
            status, bootstrap = request('GET', '/api/bootstrap', headers=auth)
            self.assertEqual(status, 200)
            status, quote = request('GET', '/api/quote?symbol=AAPL', headers=auth)
            self.assertEqual((status, quote['quote']['source']), (200, 'fixture'))
            payload = json.dumps({'order': {'symbol': 'AAPL', 'side': 'BUY', 'quantity': 1, 'limit_price': '190.02'}, 'idempotency_key': 'actual-fixture-flow', 'quote_symbol': 'AAPL'})
            status, order = request('POST', '/api/orders', payload, {
                **auth, 'Origin': f'http://127.0.0.1:{port}',
                'X-CSRF-Token': bootstrap['csrf_token'], 'Content-Type': 'application/json; charset=utf-8',
            })
            self.assertEqual((status, order['order']['status'], order['order']['quote_source']), (200, 'FILLED', 'fixture'))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
