"""Fail-closed quote providers for the in-memory demonstration simulator.

The default provider is deliberately unavailable.  The fixture provider makes no
network or credential access and labels every quote ``fixture``.  The optional
Alpaca provider is read-only: it constructs only the existing fixed-origin IEX
latest-quote adapter when ``alpaca_iex`` is selected explicitly.  It has no
order, trade, URL, token, browser, or generic-request interface.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import os
import re
from typing import Protocol

from market_data.alpaca_latest_quote import AlpacaLatestIexQuoteClient, StockQuote

from .simulator import DemoQuote


_ALPACA_MAX_QUOTE_AGE = timedelta(seconds=15)
_ALPACA_TIMEOUT_SECONDS = 5.0
_MAX_PRICE = Decimal("1000000.00000000")
_SYMBOL_RE = re.compile(r"^[A-Z]{1,5}(?:\.[A-Z])?$")
_FIXTURE_PRICES: dict[str, tuple[Decimal, Decimal]] = {
    "AAPL": (Decimal("190.00"), Decimal("190.02")),
    "MSFT": (Decimal("420.00"), Decimal("420.03")),
    "SPY": (Decimal("500.00"), Decimal("500.02")),
}


class QuoteProvider(Protocol):
    """Small simulator-only quote lookup contract."""

    def get_quote(self, symbol: str) -> DemoQuote | None:
        """Return one validated quote, or ``None`` without raising provider detail."""


def make_quote_provider(mode: str = "unavailable") -> QuoteProvider:
    """Build a quote provider without implicit network or credential access.

    ``unavailable`` is the safe default.  ``fixture`` is explicit and local.
    Only selecting the exact ``alpaca_iex`` mode reads the two existing Alpaca
    environment variables via the isolated market-data adapter.  Construction
    never performs a network request.
    """
    if mode == "unavailable":
        return _UnavailableQuoteProvider()
    if mode == "fixture":
        return _FixtureQuoteProvider()
    if mode == "alpaca_iex":
        try:
            # This is the sole credential read in this module, and it is only
            # reachable after the caller explicitly selects the live mode.
            client = AlpacaLatestIexQuoteClient(
                os.environ.get("APCA_API_KEY_ID", ""),
                os.environ.get("APCA_API_SECRET_KEY", ""),
                clock=lambda: datetime.now(timezone.utc),
                max_quote_age=_ALPACA_MAX_QUOTE_AGE,
                timeout_seconds=_ALPACA_TIMEOUT_SECONDS,
            )
        except Exception:
            # Missing/malformed credentials are intentionally indistinguishable
            # from any other unavailable source to demo callers.
            return _UnavailableQuoteProvider()
        return _AlpacaIexQuoteProvider(client)
    raise ValueError("unsupported quote provider mode")


class _UnavailableQuoteProvider:
    """Provider used for default and failed explicit live setup."""

    def get_quote(self, symbol: str) -> None:
        return None


class _FixtureQuoteProvider:
    """Explicit local quotes; values are never represented as live evidence."""

    def get_quote(self, symbol: str) -> DemoQuote | None:
        normalized = _normalize_symbol(symbol)
        if normalized is None or normalized not in _FIXTURE_PRICES:
            return None
        bid, ask = _FIXTURE_PRICES[normalized]
        now = datetime.now(timezone.utc)
        return DemoQuote(
            symbol=normalized,
            bid=bid,
            ask=ask,
            provider_time=now,
            retrieved_at=now,
            source="fixture",
        )


class _AlpacaIexQuoteProvider:
    """Adapter from validated fixed-IEX evidence to the demo quote contract."""

    def __init__(self, client: AlpacaLatestIexQuoteClient) -> None:
        self._client = client

    def __repr__(self) -> str:
        # Never delegate to a client repr: an injected or future client must not
        # be able to disclose credential-bearing state through this provider.
        return "_AlpacaIexQuoteProvider(source='alpaca_iex')"

    def get_quote(self, symbol: str) -> DemoQuote | None:
        normalized = _normalize_symbol(symbol)
        if normalized is None:
            return None
        try:
            quote = self._client.get_latest_quote(normalized)
        except Exception:
            # Provider, parsing, freshness, timeout, and transport errors are
            # deliberately fail-closed and never expose raw provider text.
            return None
        return _as_demo_quote(quote, normalized)


def _normalize_symbol(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().upper()
    return normalized if _SYMBOL_RE.fullmatch(normalized) else None


def _as_demo_quote(quote: object, expected_symbol: str) -> DemoQuote | None:
    """Defence-in-depth revalidation before a quote reaches fill simulation."""
    if not isinstance(quote, StockQuote) or quote.symbol != expected_symbol:
        return None
    if quote.feed != "iex" or quote.endpoint != (
        "https://data.alpaca.markets/v2/stocks/"
        + expected_symbol + "/quotes/latest?feed=iex"
    ):
        return None
    if not _valid_aware_time(quote.timestamp) or not _valid_aware_time(quote.retrieved_at):
        return None
    if (quote.timestamp > quote.retrieved_at
            or quote.retrieved_at - quote.timestamp > _ALPACA_MAX_QUOTE_AGE):
        return None
    if not _valid_prices(quote.bid_price, quote.ask_price):
        return None
    # These are exact values recorded by the existing adapter after its response
    # arrives; do not replace them with a local clock reading.
    return DemoQuote(
        symbol=expected_symbol,
        bid=quote.bid_price,
        ask=quote.ask_price,
        provider_time=quote.timestamp,
        retrieved_at=quote.retrieved_at,
        source="alpaca_iex",
    )


def _valid_aware_time(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _valid_prices(bid: object, ask: object) -> bool:
    return (
        isinstance(bid, Decimal)
        and isinstance(ask, Decimal)
        and bid.is_finite()
        and ask.is_finite()
        and bid > 0
        and ask > 0
        and bid <= ask
        and bid.as_tuple().exponent >= -8
        and ask.as_tuple().exponent >= -8
        and bid <= _MAX_PRICE
        and ask <= _MAX_PRICE
    )


__all__ = ["QuoteProvider", "make_quote_provider"]
