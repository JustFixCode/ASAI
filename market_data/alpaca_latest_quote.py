"""Fail-closed, read-only ingestion of Alpaca's latest IEX stock quote.

The only remote request this module can construct is the documented Alpaca
Market Data REST endpoint ``GET https://data.alpaca.markets/v2/stocks/{symbol}/
quotes/latest?feed=iex``.  It always requests IEX, disables redirects, sends no
body, and has neither a generic request API nor any order API.  It is not wired
to ASAI YAML, policy, memory, broker execution, or trading decisions.

IEX is a single exchange feed, not a consolidated SIP/NBBO or full-market feed.
Availability, real-time entitlement, coverage, and quote completeness remain
provider/account dependent.  A successful retrieval is evidence only and must
not be interpreted as permission to trade.

Alpaca can return RFC3339 timestamps with nanosecond precision.  This module
preserves the exact provider spelling and epoch nanoseconds; the compatibility
``timestamp`` field is UTC at Python ``datetime`` microsecond precision and is
truncated, never rounded.  Consumers requiring exact temporal evidence must use
``timestamp_rfc3339`` or ``timestamp_nanoseconds``.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import re
import socket
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

ALPACA_MARKET_DATA_URL = "https://data.alpaca.markets"
IEX_FEED = "iex"
MAX_RESPONSE_BYTES = 64 * 1024
_SYMBOL_RE = re.compile(r"^[A-Z]{1,5}(?:\.[A-Z])?$")
_LATEST_QUOTE_PATH_RE = re.compile(
    r"^/v2/stocks/[A-Z]{1,5}(?:\.[A-Z])?/quotes/latest\?feed=iex$"
)
_TIMESTAMP_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})T(?P<time>\d{2}:\d{2}:\d{2})"
    r"(?:\.(?P<fraction>\d{1,9}))?(?P<offset>Z|[+-]\d{2}:\d{2})$"
)
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_NANOSECONDS_PER_SECOND = 1_000_000_000


class MarketDataError(RuntimeError):
    """Base error; messages intentionally exclude credentials and response bodies."""


class MarketDataConfigurationError(MarketDataError):
    """The client, symbol, feed, clock, or freshness policy is unsafe."""


class MarketDataProtocolError(MarketDataError):
    """The transport or provider response is malformed, oversized, or unsafe."""


class MarketDataRequestError(MarketDataError):
    """The one permitted provider request was rejected or could not complete."""


@dataclass(frozen=True, slots=True)
class MarketDataHttpResponse:
    """Minimal response contract for urllib and injected, test-only transports."""

    status: int
    body: bytes


@dataclass(frozen=True, slots=True)
class StockQuote:
    """Validated quote evidence and retrieval provenance.

    ``endpoint`` and ``feed`` identify the fixed source. ``retrieved_at`` is
    read from the caller-provided clock *after* the network response arrives.
    ``timestamp_rfc3339`` and ``timestamp_nanoseconds`` preserve provider time
    exactly; ``timestamp`` is only a truncated-to-microseconds convenience view.
    """

    symbol: str
    feed: str
    bid_price: Decimal
    ask_price: Decimal
    timestamp: datetime
    timestamp_rfc3339: str
    timestamp_nanoseconds: int
    retrieved_at: datetime
    endpoint: str


Transport = Callable[[str, str, Mapping[str, str], None, float], MarketDataHttpResponse]
Clock = Callable[[], datetime]


class _NoRedirectHandler(HTTPRedirectHandler):
    """Return a redirect response; never forward credential-bearing headers."""

    def redirect_request(self, req: Request, fp: Any, code: int, msg: str,
                         headers: Any, newurl: str) -> None:
        return None


def _read_bounded(stream: Any) -> bytes:
    """Read at most the fixed response limit plus one detection byte."""
    data = stream.read(MAX_RESPONSE_BYTES + 1)
    if not isinstance(data, bytes):
        raise MarketDataProtocolError("market-data returned a non-bytes response body")
    return data


def _urllib_transport(method: str, url: str, headers: Mapping[str, str],
                      body: None, timeout: float) -> MarketDataHttpResponse:
    """Make exactly one fixed-origin HTTPS request, without redirects or retries."""
    request = Request(url, data=body, headers=dict(headers), method=method)
    try:
        opener = build_opener(_NoRedirectHandler())
        with opener.open(request, timeout=timeout) as response:  # nosec B310: fixed origin
            return MarketDataHttpResponse(response.status, _read_bounded(response))
    except HTTPError as exc:
        return MarketDataHttpResponse(exc.code, _read_bounded(exc))
    except (socket.timeout, TimeoutError) as exc:
        raise TimeoutError("market-data timeout") from exc
    except URLError as exc:
        raise MarketDataRequestError("market-data connection failed") from exc


class AlpacaLatestIexQuoteClient:
    """Fixed-origin GET-only client for a latest IEX US-stock quote.

    A clock is mandatory. Freshness is evaluated only after the response has
    returned, preventing pre-request time from being mislabeled as retrieval
    time. API credentials live only in this object's private state and are not
    represented in reprs or exception messages.
    """

    def __init__(self, api_key_id: str, api_secret_key: str, *, clock: Clock,
                 max_quote_age: timedelta, timeout_seconds: float = 10.0,
                 transport: Transport = _urllib_transport) -> None:
        if (not isinstance(api_key_id, str) or not api_key_id.strip()
                or not isinstance(api_secret_key, str) or not api_secret_key.strip()):
            raise MarketDataConfigurationError("runtime market-data credentials are required")
        if not callable(clock):
            raise MarketDataConfigurationError("clock must be callable")
        if not isinstance(max_quote_age, timedelta) or max_quote_age < timedelta(0):
            raise MarketDataConfigurationError("max_quote_age must be a non-negative timedelta")
        if (not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool)
                or not 0 < timeout_seconds <= 30):
            raise MarketDataConfigurationError("timeout_seconds must be between 0 and 30")
        if not callable(transport):
            raise MarketDataConfigurationError("transport must be callable")
        self._api_key_id = api_key_id
        self._api_secret_key = api_secret_key
        self._clock = clock
        self._max_quote_age = max_quote_age
        self._timeout_seconds = float(timeout_seconds)
        self._transport = transport

    def __repr__(self) -> str:
        return (f"{type(self).__name__}(origin={ALPACA_MARKET_DATA_URL!r}, "
                f"feed={IEX_FEED!r}, max_quote_age={self._max_quote_age!r})")

    def get_latest_quote(self, symbol: str, *, feed: str = IEX_FEED) -> StockQuote:
        """Retrieve, validate, and freshness-check one complete IEX quote."""
        normalized_symbol = _normalize_symbol(symbol)
        if feed != IEX_FEED:
            raise MarketDataConfigurationError("only the exact iex feed is permitted")
        path = f"/v2/stocks/{normalized_symbol}/quotes/latest?feed={IEX_FEED}"
        payload = self._request_json("GET", path)
        retrieved_at = _read_clock(self._clock)  # deliberately after network response
        return _parse_quote(payload, normalized_symbol, retrieved_at, self._max_quote_age,
                            ALPACA_MARKET_DATA_URL + path)

    def _request_json(self, method: str, path: str) -> Any:
        """Issue one exact bodyless, allowlisted GET and parse safe JSON."""
        if type(method) is not str or method != "GET":
            raise MarketDataConfigurationError("market-data request method must be exact GET")
        if not _is_allowed_latest_quote_path(path):
            raise MarketDataConfigurationError("market-data request path is not allowed")
        headers = {
            "Accept": "application/json",
            "APCA-API-KEY-ID": self._api_key_id,
            "APCA-API-SECRET-KEY": self._api_secret_key,
        }
        try:
            response = self._transport(method, ALPACA_MARKET_DATA_URL + path, headers, None,
                                       self._timeout_seconds)
        except (socket.timeout, TimeoutError):
            raise TimeoutError("market-data timeout") from None
        except MarketDataError:
            raise
        except Exception:
            raise MarketDataRequestError("market-data connection failed") from None
        if (not isinstance(response, MarketDataHttpResponse) or type(response.status) is not int
                or not isinstance(response.body, bytes)):
            raise MarketDataProtocolError("market-data transport returned an invalid response")
        if len(response.body) > MAX_RESPONSE_BYTES:
            raise MarketDataProtocolError("market-data response exceeds the size limit")
        if response.status != 200:
            raise MarketDataRequestError("market-data request was rejected or failed")
        try:
            return json.loads(response.body.decode("utf-8"), parse_float=Decimal,
                              parse_int=Decimal, parse_constant=_reject_json_constant,
                              object_pairs_hook=_reject_duplicate_object_keys)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            raise MarketDataProtocolError("market-data returned invalid JSON") from None


def _reject_duplicate_object_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError("non-finite JSON number")


def _normalize_symbol(value: object) -> str:
    if not isinstance(value, str):
        raise MarketDataConfigurationError("symbol must be a strict US stock ticker")
    symbol = value.strip().upper()
    if not _SYMBOL_RE.fullmatch(symbol):
        raise MarketDataConfigurationError("symbol must be a strict US stock ticker")
    return symbol


def _is_allowed_latest_quote_path(path: object) -> bool:
    return isinstance(path, str) and _LATEST_QUOTE_PATH_RE.fullmatch(path) is not None


def _read_clock(clock: Clock) -> datetime:
    try:
        now = clock()
    except Exception:
        raise MarketDataConfigurationError("clock failed") from None
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise MarketDataConfigurationError("clock must return an aware datetime")
    return now.astimezone(timezone.utc)


def _datetime_to_nanoseconds(value: datetime) -> int:
    utc_value = value.astimezone(timezone.utc)
    delta = utc_value - _EPOCH
    return ((delta.days * 86_400 + delta.seconds) * _NANOSECONDS_PER_SECOND
            + delta.microseconds * 1_000)


def _parse_quote(payload: Any, symbol: str, retrieved_at: datetime,
                 max_quote_age: timedelta, endpoint: str) -> StockQuote:
    if (not isinstance(payload, dict) or set(payload) != {"quote"}
            or not isinstance(payload["quote"], dict)):
        raise MarketDataProtocolError("market-data returned an invalid latest quote response")
    quote = payload["quote"]
    if not {"bp", "ap", "t"}.issubset(quote):
        raise MarketDataProtocolError("market-data latest quote is incomplete")
    bid = _positive_decimal(quote["bp"], "bid")
    ask = _positive_decimal(quote["ap"], "ask")
    if bid > ask:
        raise MarketDataProtocolError("market-data latest quote is crossed")
    timestamp, timestamp_ns = _parse_timestamp(quote["t"])
    age_ns = _datetime_to_nanoseconds(retrieved_at) - timestamp_ns
    if age_ns < 0:
        raise MarketDataProtocolError("market-data latest quote is from the future")
    if age_ns > _timedelta_to_nanoseconds(max_quote_age):
        raise MarketDataProtocolError("market-data latest quote is stale")
    return StockQuote(symbol, IEX_FEED, bid, ask, timestamp, quote["t"], timestamp_ns,
                      retrieved_at, endpoint)


def _timedelta_to_nanoseconds(value: timedelta) -> int:
    return ((value.days * 86_400 + value.seconds) * _NANOSECONDS_PER_SECOND
            + value.microseconds * 1_000)


def _positive_decimal(value: object, label: str) -> Decimal:
    """Accept only finite positive JSON numbers, never strings, floats, or bools."""
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise MarketDataProtocolError(f"market-data latest quote has invalid {label}")
    return value


def _parse_timestamp(value: object) -> tuple[datetime, int]:
    """Parse RFC3339 through nanoseconds exactly, retaining no rounded value."""
    if not isinstance(value, str):
        raise MarketDataProtocolError("market-data latest quote has an invalid timestamp")
    match = _TIMESTAMP_RE.fullmatch(value)
    if match is None:
        raise MarketDataProtocolError("market-data latest quote has an invalid timestamp")
    fraction = match.group("fraction") or ""
    # ``datetime`` receives only the first six digits. Remaining digits are
    # retained separately in epoch nanoseconds, so no rounding is performed.
    microseconds = (fraction[:6].ljust(6, "0") if fraction else "000000")
    iso_value = f"{match.group('date')}T{match.group('time')}.{microseconds}{match.group('offset')}"
    try:
        parsed = datetime.fromisoformat(iso_value.replace("Z", "+00:00"))
    except ValueError:
        raise MarketDataProtocolError("market-data latest quote has an invalid timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MarketDataProtocolError("market-data latest quote has an invalid timestamp")
    timestamp = parsed.astimezone(timezone.utc)
    extra_nanoseconds = int(fraction[6:].ljust(3, "0")) if len(fraction) > 6 else 0
    return timestamp, _datetime_to_nanoseconds(timestamp) + extra_nanoseconds


__all__ = [
    "ALPACA_MARKET_DATA_URL", "IEX_FEED", "MAX_RESPONSE_BYTES",
    "AlpacaLatestIexQuoteClient", "MarketDataConfigurationError", "MarketDataError",
    "MarketDataHttpResponse", "MarketDataProtocolError", "MarketDataRequestError",
    "StockQuote",
]
