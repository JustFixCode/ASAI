import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import broker.alpaca_paper as alpaca_paper

from broker import (
    ALPACA_PAPER_URL,
    AlpacaPaperStocksClient,
    BrokerConfigurationError,
    BrokerProtocolError,
    BrokerRequestError,
    BrokerTimeoutUnknownStatus,
    HttpResponse,
    OrderRequest,
)


class FakeTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append((method, url, dict(headers), body, timeout))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class AlpacaPaperClientTests(unittest.TestCase):
    def client(self, fake, **kwargs):
        return AlpacaPaperStocksClient(
            "key-id-that-must-not-leak", "secret-that-must-not-leak",
            transport=fake, **kwargs,
        )

    def test_get_account_uses_exact_documented_paper_https_endpoint(self):
        fake = FakeTransport(HttpResponse(200, b'{"id":"account-1","status":"ACTIVE"}'))
        account = self.client(fake).get_account()
        self.assertEqual(account["id"], "account-1")
        method, url, headers, body, timeout = fake.calls[0]
        self.assertEqual((method, url, body), ("GET", ALPACA_PAPER_URL + "/v2/account", None))
        self.assertEqual(headers["APCA-API-KEY-ID"], "key-id-that-must-not-leak")
        self.assertEqual(headers["APCA-API-SECRET-KEY"], "secret-that-must-not-leak")
        self.assertEqual(timeout, 10.0)

    def test_positions_requires_array_of_objects(self):
        fake = FakeTransport(HttpResponse(200, b'[{"symbol":"AAPL"}]'))
        self.assertEqual(self.client(fake).get_positions(), [{"symbol": "AAPL"}])
        with self.assertRaises(BrokerProtocolError):
            self.client(FakeTransport(HttpResponse(200, b'{"symbol":"AAPL"}'))).get_positions()

    def test_live_custom_and_non_https_hosts_are_unconditionally_rejected(self):
        for host in ("https://api.alpaca.markets", "http://paper-api.alpaca.markets", "https://example.test"):
            with self.assertRaises(BrokerConfigurationError):
                AlpacaPaperStocksClient("key", "secret", base_url=host)

    def test_environment_credentials_are_runtime_only_and_required(self):
        previous = {name: os.environ.pop(name, None) for name in ("APCA_API_KEY_ID", "APCA_API_SECRET_KEY")}
        try:
            with self.assertRaises(BrokerConfigurationError):
                AlpacaPaperStocksClient.from_environment(transport=FakeTransport())
        finally:
            for name, value in previous.items():
                if value is not None:
                    os.environ[name] = value

    def test_credentials_and_error_body_are_redacted_from_exceptions(self):
        fake = FakeTransport(HttpResponse(401, b'{"message":"secret-that-must-not-leak key-id-that-must-not-leak"}'))
        with self.assertRaises(BrokerRequestError) as caught:
            self.client(fake).get_account()
        message = str(caught.exception)
        self.assertNotIn("secret-that-must-not-leak", message)
        self.assertNotIn("key-id-that-must-not-leak", message)

    def test_submit_is_disabled_by_default(self):
        order = OrderRequest("AAPL", "1", "buy", request_key="manual-review-42")
        fake = FakeTransport()
        with self.assertRaises(BrokerConfigurationError):
            self.client(fake).submit_order(order)
        self.assertEqual(fake.calls, [])

    def test_submit_has_stable_client_id_and_only_one_attempt(self):
        order = OrderRequest(" aapl ", "2", "buy", type="limit", limit_price="100.25", request_key="approval-7")
        same_order = OrderRequest("AAPL", "2", "buy", type="limit", limit_price="100.25", request_key="approval-7")
        self.assertEqual(order.resolved_client_order_id(), same_order.resolved_client_order_id())
        fake = FakeTransport(HttpResponse(201, ('{\"id\":\"broker-order-1\",\"client_order_id\":\"' + order.resolved_client_order_id() + '\",\"status\":\"accepted\"}').encode()))
        result = self.client(fake, allow_paper_submit=True).submit_order(order)
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(len(fake.calls), 1)
        method, url, _, raw_body, _ = fake.calls[0]
        self.assertEqual((method, url), ("POST", ALPACA_PAPER_URL + "/v2/orders"))
        self.assertEqual(json.loads(raw_body.decode("utf-8"))["client_order_id"], order.resolved_client_order_id())

    def test_submit_timeout_is_unknown_and_recovery_lookup_uses_same_id(self):
        order = OrderRequest("MSFT", "1", "sell", request_key="approval-8")
        fake = FakeTransport(TimeoutError("timed out"), HttpResponse(200, ('{\"id\":\"broker-order-2\",\"client_order_id\":\"' + order.resolved_client_order_id() + '\",\"status\":\"new\"}').encode()))
        client = self.client(fake, allow_paper_submit=True)
        with self.assertRaises(BrokerTimeoutUnknownStatus) as caught:
            client.submit_order(order)
        self.assertEqual(caught.exception.client_order_id, order.resolved_client_order_id())
        resolved = client.get_order_by_client_order_id(caught.exception.client_order_id)
        self.assertEqual(resolved["id"], "broker-order-2")
        self.assertEqual(len(fake.calls), 2)  # no automatic POST retry
        self.assertEqual(fake.calls[1][1], ALPACA_PAPER_URL + "/v2/orders:by_client_order_id?client_order_id=" + order.resolved_client_order_id())

    def test_get_status_cancel_and_invalid_responses_fail_closed(self):
        fake = FakeTransport(HttpResponse(200, b'{"id":"abc","client_order_id":"approved-abc","status":"accepted"}'), HttpResponse(204, b""))
        client = self.client(fake)
        self.assertEqual(client.get_order("abc")["id"], "abc")
        self.assertIsNone(client.cancel_order("abc"))
        with self.assertRaises(BrokerProtocolError):
            self.client(FakeTransport(HttpResponse(200, b"not-json"))).get_account()
        with self.assertRaises(BrokerRequestError):
            self.client(FakeTransport(HttpResponse(500, b"internal details"))).get_account()

    def test_urllib_transport_never_follows_redirects_or_resends_credentials(self):
        class RedirectingOpener:
            def __init__(self):
                self.calls = []

            def open(self, request, timeout):
                self.calls.append((request.full_url, dict(request.header_items()), timeout))
                error = HTTPError(request.full_url, 302, "Found", {}, None)
                error.read = lambda: b"redirect"
                raise error

        opener = RedirectingOpener()
        with patch("broker.alpaca_paper.build_opener", return_value=opener) as make_opener:
            response = alpaca_paper._urllib_transport(
                "POST", ALPACA_PAPER_URL + "/v2/orders",
                {"APCA-API-KEY-ID": "key", "APCA-API-SECRET-KEY": "secret"}, b"{}", 3.0,
            )
        self.assertEqual(response, HttpResponse(302, b"redirect"))
        self.assertEqual(len(opener.calls), 1)
        self.assertEqual(opener.calls[0][0], ALPACA_PAPER_URL + "/v2/orders")
        handler = make_opener.call_args.args[0]
        self.assertIsNone(handler.redirect_request(None, None, 302, "Found", None, "https://evil.example"))

    def test_order_response_must_be_complete_consistent_and_unambiguous(self):
        order = OrderRequest("AAPL", "1", "buy", request_key="approval-9")
        cases = (
            b'{"id":"broker-order-1","status":"accepted"}',
            (b'{"id":"broker-order-1","client_order_id":"' + order.resolved_client_order_id().encode()
             + b'","status":"mystery"}'),
            b'{"id":"broker-order-1","client_order_id":"wrong-id","status":"accepted"}',
        )
        for body in cases:
            with self.subTest(body=body):
                with self.assertRaises(BrokerProtocolError):
                    self.client(FakeTransport(HttpResponse(201, body)), allow_paper_submit=True).submit_order(order)
        with self.assertRaises(BrokerProtocolError):
            self.client(FakeTransport(HttpResponse(200, b'{"id":"other","client_order_id":"valid-id","status":"new"}'))).get_order("expected")
        with self.assertRaises(BrokerProtocolError):
            self.client(FakeTransport(HttpResponse(204, b"unexpected"))).cancel_order("expected")

    def test_idempotency_key_cannot_be_caller_overridden_or_unbounded(self):
        order = OrderRequest("AAPL", "1", "buy", request_key="approval-10")
        with self.assertRaises(BrokerConfigurationError):
            OrderRequest("AAPL", "1", "buy", request_key="approval-10", client_order_id="manual-id")
        self.assertEqual(
            OrderRequest("AAPL", "1", "buy", request_key="approval-10", client_order_id=order.resolved_client_order_id()).resolved_client_order_id(),
            order.resolved_client_order_id(),
        )
        with self.assertRaises(BrokerConfigurationError):
            OrderRequest("AAPL", "1", "buy", request_key="x" * 49)

    def test_transport_exceptions_are_sanitized(self):
        with self.assertRaises(BrokerRequestError) as caught:
            self.client(FakeTransport(RuntimeError("secret-that-must-not-leak"))).get_account()
        self.assertNotIn("secret-that-must-not-leak", str(caught.exception))

    def test_order_validation_excludes_crypto_forex_and_unsafe_values(self):
        with self.assertRaises(BrokerConfigurationError):
            OrderRequest("BTC/USD", "1", "buy", request_key="x")
        with self.assertRaises(BrokerConfigurationError):
            OrderRequest("AAPL", "NaN", "buy", request_key="x")
        with self.assertRaises(BrokerConfigurationError):
            OrderRequest("AAPL", "1", "buy", type="market", limit_price="1", request_key="x")
        with self.assertRaises(BrokerConfigurationError):
            self.client(FakeTransport()).get_order("../../etc/passwd")


if __name__ == "__main__":
    unittest.main()
