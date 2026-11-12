import json
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch
from urllib.error import HTTPError

import market_data.alpaca_latest_quote as quotes
from market_data import (
    ALPACA_MARKET_DATA_URL,
    IEX_FEED,
    MAX_RESPONSE_BYTES,
    AlpacaLatestIexQuoteClient,
    MarketDataConfigurationError,
    MarketDataHttpResponse,
    MarketDataProtocolError,
    MarketDataRequestError,
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


def quote_body(*, bid=100.10, ask=100.20, timestamp="2026-11-11T18:00:00.123456Z"):
    return json.dumps({"quote": {"bp": bid, "ap": ask, "t": timestamp}}).encode("utf-8")


class AlpacaLatestIexQuoteClientTests(unittest.TestCase):
    now = datetime(2026, 11, 11, 18, 0, 5, tzinfo=timezone.utc)

    def client(self, fake, *, clock=None, max_quote_age=timedelta(seconds=10), **kwargs):
        return AlpacaLatestIexQuoteClient(
            "key-id-that-must-not-leak", "secret-that-must-not-leak",
            clock=clock or (lambda: self.now), max_quote_age=max_quote_age,
            transport=fake, **kwargs,
        )

    def test_uses_the_exact_fixed_https_iex_endpoint_and_provenance(self):
        fake = FakeTransport(MarketDataHttpResponse(200, quote_body()))
        result = self.client(fake).get_latest_quote(" aapl ")
        method, url, headers, body, timeout = fake.calls[0]
        expected = ALPACA_MARKET_DATA_URL + "/v2/stocks/AAPL/quotes/latest?feed=iex"
        self.assertEqual((method, url, body, timeout), ("GET", expected, None, 10.0))
        self.assertEqual(headers["Accept"], "application/json")
        self.assertEqual(headers["APCA-API-KEY-ID"], "key-id-that-must-not-leak")
        self.assertEqual(headers["APCA-API-SECRET-KEY"], "secret-that-must-not-leak")
        self.assertEqual(result.symbol, "AAPL")
        self.assertEqual(result.feed, IEX_FEED)
        self.assertEqual(result.endpoint, expected)
        self.assertEqual(result.retrieved_at, self.now)
        self.assertEqual((result.bid_price, result.ask_price), (Decimal("100.1"), Decimal("100.2")))

    def test_clock_is_read_only_after_the_response_returns(self):
        events = []

        class OrderedTransport(FakeTransport):
            def __call__(self, *args):
                events.append("transport")
                return super().__call__(*args)

        fake = OrderedTransport(MarketDataHttpResponse(200, quote_body()))
        client = self.client(fake, clock=lambda: events.append("clock") or self.now)
        client.get_latest_quote("AAPL")
        self.assertEqual(events, ["transport", "clock"])

    def test_preserves_nanosecond_timestamp_without_rounding(self):
        fake = FakeTransport(MarketDataHttpResponse(
            200, quote_body(timestamp="2026-11-11T20:00:00.123456789+02:00")))
        result = self.client(fake, max_quote_age=timedelta(seconds=10)).get_latest_quote("MSFT")
        self.assertEqual(result.timestamp_rfc3339, "2026-11-11T20:00:00.123456789+02:00")
        self.assertEqual(result.timestamp, datetime(2026, 11, 11, 18, 0, 0, 123456, tzinfo=timezone.utc))
        self.assertEqual(result.timestamp_nanoseconds, 1_794_420_000_123_456_789)

    def test_nanosecond_precision_prevents_an_unsafe_freshness_round_down(self):
        now = datetime(2026, 11, 11, 18, 0, 0, tzinfo=timezone.utc)
        fake = FakeTransport(MarketDataHttpResponse(
            200, quote_body(timestamp="2026-11-11T18:00:00.000000001Z")))
        with self.assertRaisesRegex(MarketDataProtocolError, "future"):
            self.client(fake, clock=lambda: now, max_quote_age=timedelta(seconds=1)).get_latest_quote("AAPL")

    def test_freshness_rejects_stale_and_future_quotes(self):
        for timestamp, reason in (
            ("2026-11-11T17:59:54Z", "stale"),
            ("2026-11-11T18:00:05.000001Z", "future"),
        ):
            with self.subTest(timestamp=timestamp):
                fake = FakeTransport(MarketDataHttpResponse(200, quote_body(timestamp=timestamp)))
                with self.assertRaisesRegex(MarketDataProtocolError, reason):
                    self.client(fake, max_quote_age=timedelta(seconds=10)).get_latest_quote("AAPL")

    def test_rejects_non_iex_feed_unsafe_symbols_and_paths_before_transport(self):
        invalid_symbols = ("", "AAPL/../../orders", "BRK/B", "TOOLONG", 7)
        for symbol in invalid_symbols:
            with self.subTest(symbol=symbol):
                fake = FakeTransport()
                with self.assertRaises(MarketDataConfigurationError):
                    self.client(fake).get_latest_quote(symbol)
                self.assertEqual(fake.calls, [])
        fake = FakeTransport()
        client = self.client(fake)
        with self.assertRaises(MarketDataConfigurationError):
            client.get_latest_quote("AAPL", feed="sip")
        with self.assertRaises(MarketDataConfigurationError):
            client._request_json("POST", "/v2/stocks/AAPL/quotes/latest?feed=iex")
        with self.assertRaises(MarketDataConfigurationError):
            client._request_json("GET", "/v2/stocks/AAPL/quotes/latest?feed=iex&x=1")
        self.assertEqual(fake.calls, [])

    def test_rejects_duplicate_keys_at_every_json_object_level(self):
        for body in (
            b'{"quote":{"bp":1,"ap":2,"t":"2026-11-11T18:00:00Z"},"quote":{}}',
            b'{"quote":{"bp":1,"bp":2,"ap":3,"t":"2026-11-11T18:00:00Z"}}',
        ):
            with self.subTest(body=body):
                with self.assertRaisesRegex(MarketDataProtocolError, "invalid JSON"):
                    self.client(FakeTransport(MarketDataHttpResponse(200, body))).get_latest_quote("AAPL")

    def test_requires_safe_json_numeric_prices_and_complete_uncrossed_quote(self):
        bad_bodies = (
            b'{"quote":{"bp":"100.1","ap":100.2,"t":"2026-11-11T18:00:00Z"}}',
            b'{"quote":{"bp":true,"ap":100.2,"t":"2026-11-11T18:00:00Z"}}',
            b'{"quote":{"bp":NaN,"ap":100.2,"t":"2026-11-11T18:00:00Z"}}',
            b'{"quote":{"bp":101,"ap":100,"t":"2026-11-11T18:00:00Z"}}',
            b'{"quote":{"bp":100,"ap":101}}',
        )
        for body in bad_bodies:
            with self.subTest(body=body):
                with self.assertRaises(MarketDataProtocolError):
                    self.client(FakeTransport(MarketDataHttpResponse(200, body))).get_latest_quote("AAPL")

    def test_rejects_invalid_rfc3339_times_but_accepts_one_to_nine_fraction_digits(self):
        for timestamp in ("2026-11-11 18:00:00Z", "2026-11-11T18:00:00.1234567890Z",
                          "2026-02-30T18:00:00Z", "2026-11-11T18:00:00"):
            with self.subTest(timestamp=timestamp):
                fake = FakeTransport(MarketDataHttpResponse(200, quote_body(timestamp=timestamp)))
                with self.assertRaisesRegex(MarketDataProtocolError, "timestamp"):
                    self.client(fake).get_latest_quote("AAPL")
        for fraction in ("1", "123456", "123456789"):
            with self.subTest(fraction=fraction):
                timestamp = "2026-11-11T18:00:00." + fraction + "Z"
                fake = FakeTransport(MarketDataHttpResponse(200, quote_body(timestamp=timestamp)))
                self.assertEqual(self.client(fake).get_latest_quote("AAPL").timestamp_rfc3339, timestamp)

    def test_bounded_responses_non_200_and_transport_failures_do_not_leak_secrets(self):
        huge = b"x" * (MAX_RESPONSE_BYTES + 1)
        with self.assertRaisesRegex(MarketDataProtocolError, "size limit"):
            self.client(FakeTransport(MarketDataHttpResponse(200, huge))).get_latest_quote("AAPL")
        for response in (MarketDataHttpResponse(302, b"secret-that-must-not-leak"),
                         MarketDataHttpResponse(500, b"key-id-that-must-not-leak"),
                         RuntimeError("secret-that-must-not-leak")):
            with self.subTest(response=response):
                with self.assertRaises(MarketDataRequestError) as caught:
                    self.client(FakeTransport(response)).get_latest_quote("AAPL")
                self.assertNotIn("secret-that-must-not-leak", str(caught.exception))
                self.assertNotIn("key-id-that-must-not-leak", str(caught.exception))

    def test_transport_contract_and_configuration_are_checked(self):
        with self.assertRaises(MarketDataProtocolError):
            self.client(FakeTransport({"status": 200})).get_latest_quote("AAPL")
        for bad_clock in (lambda: datetime(2026, 1, 1), lambda: "not-a-time"):
            fake = FakeTransport(MarketDataHttpResponse(200, quote_body()))
            with self.assertRaises(MarketDataConfigurationError):
                self.client(fake, clock=bad_clock).get_latest_quote("AAPL")
        for kwargs in ({"max_quote_age": timedelta(seconds=-1)}, {"timeout_seconds": 0},
                       {"timeout_seconds": True}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(MarketDataConfigurationError):
                    self.client(FakeTransport(), **kwargs)

    def test_urllib_transport_does_not_follow_redirects_and_bounds_reads(self):
        class RedirectingOpener:
            def __init__(self):
                self.calls = []
                self.error = None

            def open(self, request, timeout):
                self.calls.append((request.full_url, dict(request.header_items()), timeout))
                error = HTTPError(request.full_url, 302, "Found", {}, None)
                error.read = lambda size=-1: b"redirect" if size == MAX_RESPONSE_BYTES + 1 else b"unbounded"
                self.error = error
                raise error

        opener = RedirectingOpener()
        with patch("market_data.alpaca_latest_quote.build_opener", return_value=opener) as make_opener:
            response = quotes._urllib_transport(
                "GET", ALPACA_MARKET_DATA_URL + "/v2/stocks/AAPL/quotes/latest?feed=iex",
                {"APCA-API-KEY-ID": "key", "APCA-API-SECRET-KEY": "secret"}, None, 3.0,
            )
        self.assertEqual(response, MarketDataHttpResponse(302, b"redirect"))
        self.assertEqual(len(opener.calls), 1)
        handler = make_opener.call_args.args[0]
        self.assertIsNone(handler.redirect_request(None, None, 302, "Found", None, "https://evil.example"))
        opener.error.close()


if __name__ == "__main__":
    unittest.main()
