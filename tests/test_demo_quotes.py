import http.client
import json
import os
import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import unittest
from unittest.mock import Mock, patch

from demo.quotes import make_quote_provider
from demo.server import make_server
from demo.simulator import DemoError, DemoSimulator
from market_data.alpaca_latest_quote import StockQuote


NOW = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)
ENDPOINT = "https://data.alpaca.markets/v2/stocks/AAPL/quotes/latest?feed=iex"


def stock_quote(*, bid="190.00", ask="190.02", age=1):
    return StockQuote(
        symbol="AAPL", feed="iex", bid_price=Decimal(bid), ask_price=Decimal(ask),
        timestamp=NOW - timedelta(seconds=age),
        timestamp_rfc3339="2026-11-12T11:59:59Z", timestamp_nanoseconds=0,
        retrieved_at=NOW, endpoint=ENDPOINT,
    )


class DemoQuoteProviderTests(unittest.TestCase):
    def test_default_and_fixture_do_not_read_credentials_or_make_network_calls(self):
        with patch("demo.quotes.os.environ.get") as getenv:
            self.assertIsNone(make_quote_provider().get_quote("AAPL"))
            quote = make_quote_provider("fixture").get_quote("AAPL")
        getenv.assert_not_called()
        self.assertIsNotNone(quote)
        assert quote is not None
        self.assertEqual(quote.symbol, "AAPL")
        self.assertEqual(quote.source, "fixture")
        self.assertEqual((quote.bid, quote.ask), (Decimal("190.00"), Decimal("190.02")))
        self.assertEqual(quote.provider_time, quote.retrieved_at)
        self.assertIsNotNone(quote.provider_time.tzinfo)

    def test_fixture_rejects_bad_or_unsupported_symbols_without_network(self):
        provider = make_quote_provider("fixture")
        for symbol in ("", "AAPL/../../orders", "TOOLONG", 7, "TSLA"):
            self.assertIsNone(provider.get_quote(symbol))

    def test_unknown_mode_is_rejected_without_setup(self):
        with patch("demo.quotes.AlpacaLatestIexQuoteClient") as client:
            with self.assertRaisesRegex(ValueError, "unsupported quote provider mode"):
                make_quote_provider("https://evil.example/?token=x")
        client.assert_not_called()

    def test_explicit_alpaca_mode_uses_fixed_read_only_client_and_existing_times(self):
        client = Mock()
        evidence = stock_quote()
        client.get_latest_quote.return_value = evidence
        with patch.dict(os.environ, {"APCA_API_KEY_ID": "test-key", "APCA_API_SECRET_KEY": "test-secret"}, clear=False):
            with patch("demo.quotes.AlpacaLatestIexQuoteClient", return_value=client) as constructor:
                provider = make_quote_provider("alpaca_iex")
                quote = provider.get_quote(" aapl ")

        constructor.assert_called_once()
        args, kwargs = constructor.call_args
        self.assertEqual(args, ("test-key", "test-secret"))
        self.assertEqual(kwargs["max_quote_age"], timedelta(seconds=15))
        self.assertEqual(kwargs["timeout_seconds"], 5.0)
        self.assertTrue(callable(kwargs["clock"]))
        client.get_latest_quote.assert_called_once_with("AAPL")
        self.assertIsNotNone(quote)
        assert quote is not None
        self.assertEqual(quote.source, "alpaca_iex")
        self.assertIs(quote.provider_time, evidence.timestamp)
        self.assertIs(quote.retrieved_at, evidence.retrieved_at)
        self.assertEqual((quote.bid, quote.ask), (Decimal("190.00"), Decimal("190.02")))

    def test_missing_live_environment_fails_closed_without_network_or_secret_leakage(self):
        secret = "do-not-expose-this-secret"
        with patch.dict(os.environ, {}, clear=True):
            with patch("demo.quotes.AlpacaLatestIexQuoteClient", side_effect=RuntimeError(secret)) as constructor:
                provider = make_quote_provider("alpaca_iex")
                self.assertIsNone(provider.get_quote("AAPL"))
        constructor.assert_called_once()
        self.assertNotIn(secret, repr(provider))

    def test_live_bad_symbol_and_provider_failure_return_none_without_real_network(self):
        client = Mock()
        with patch.dict(os.environ, {"APCA_API_KEY_ID": "test-key", "APCA_API_SECRET_KEY": "test-secret"}, clear=False):
            with patch("demo.quotes.AlpacaLatestIexQuoteClient", return_value=client):
                provider = make_quote_provider("alpaca_iex")
                self.assertIsNone(provider.get_quote("AAPL/orders"))
                client.get_latest_quote.assert_not_called()
                client.get_latest_quote.side_effect = TimeoutError("provider raw secret")
                self.assertIsNone(provider.get_quote("AAPL"))
        client.get_latest_quote.assert_called_once_with("AAPL")

    def test_live_quote_revalidates_stale_future_invalid_and_mixed_source_evidence(self):
        client = Mock()
        with patch.dict(os.environ, {"APCA_API_KEY_ID": "test-key", "APCA_API_SECRET_KEY": "test-secret"}, clear=False):
            with patch("demo.quotes.AlpacaLatestIexQuoteClient", return_value=client):
                provider = make_quote_provider("alpaca_iex")
                for bad in (
                    stock_quote(age=16), stock_quote(age=-1),
                    stock_quote(bid="190.021", ask="190.02"), stock_quote(bid="0", ask="190.02"),
                    stock_quote(bid="1.000000001", ask="2"), stock_quote(bid="1000000.01", ask="1000000.02"),
                    StockQuote("AAPL", "sip", Decimal("190"), Decimal("191"), NOW, "x", 0, NOW, ENDPOINT),
                    StockQuote("MSFT", "iex", Decimal("190"), Decimal("191"), NOW, "x", 0, NOW, ENDPOINT),
                ):
                    client.get_latest_quote.return_value = bad
                    self.assertIsNone(provider.get_quote("AAPL"))

    def test_real_loopback_fixture_order_integration_uses_no_live_network(self):
        server = make_server(quote_mode="fixture")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            body = json.dumps({
                "order": {"symbol": "AAPL", "side": "BUY", "quantity": 1, "limit_price": "190.02"},
                "idempotency_key": "local-fixture-fill",
                "quote_symbol": "AAPL",
            })
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
            connection.request("POST", "/api/orders", body=body, headers={
                "Host": f"127.0.0.1:{server.server_port}",
                "X-Session-Token": server.session_token,
                "Origin": f"http://127.0.0.1:{server.server_port}",
                "X-CSRF-Token": server.csrf_token,
                "Content-Type": "application/json",
            })
            response = connection.getresponse()
            payload = json.loads(response.read().decode("utf-8"))
            connection.close()
            self.assertEqual(response.status, 200)
            self.assertEqual(payload["order"]["status"], "FILLED")
            self.assertEqual(payload["order"]["quote_source"], "fixture")
            self.assertIn("fills are simulated", payload["order"]["warning"])
            self.assertEqual(server.simulator.snapshot()["cash"], "9809.98")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_fixture_quote_reaches_simulator_which_remains_final_validation_boundary(self):
        quote = make_quote_provider("fixture").get_quote("AAPL")
        self.assertIsNotNone(quote)
        assert quote is not None
        result = DemoSimulator().place_order(
            {"symbol": "AAPL", "side": "BUY", "quantity": 1, "limit_price": "190.02"},
            "fixture-fill", quote, quote.retrieved_at,
        )
        self.assertEqual(result["status"], "FILLED")
        self.assertEqual(result["quote_source"], "fixture")

        malformed = quote.__class__("AAPL", Decimal("200"), Decimal("190"), quote.provider_time, quote.retrieved_at, "fixture")
        with self.assertRaises(DemoError) as caught:
            DemoSimulator().place_order(
                {"symbol": "AAPL", "side": "BUY", "quantity": 1, "limit_price": "200.00"},
                "simulator-recheck", malformed, quote.retrieved_at,
            )
        self.assertEqual(caught.exception.code, "INVALID_QUOTE")


if __name__ == "__main__":
    unittest.main()
