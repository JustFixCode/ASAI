"""Fail-closed Alpaca paper adapter for manually governed US stock orders.

The only permitted remote origin is ``https://paper-api.alpaca.markets``.  Live
trading is rejected unconditionally, even if callers supply a different host.
This is an integration primitive, not an autonomous-trading safety boundary.
It intentionally has no retries for order submission: a timeout has unknown
order state and must be resolved with ``get_order`` before any further action.

Credentials are read only by :meth:`AlpacaPaperStocksClient.from_environment` at
runtime. They are never included in exception messages, reprs, or logs.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
import re
import socket
from typing import Any, Callable, Mapping, Optional
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

ALPACA_PAPER_HOST = "paper-api.alpaca.markets"
ALPACA_PAPER_URL = "https://paper-api.alpaca.markets"
PAPER_STOCKS_ONLY_NOTICE = (
    "Only Alpaca paper US-stock order payloads are supported; forex, crypto, "
    "options, and live trading are unsupported."
)
_CLIENT_ORDER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,48}$")
_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.]{0,14}$")
_ORDER_STATUSES = frozenset((
    "new", "accepted", "pending_new", "accepted_for_bidding", "partially_filled",
    "filled", "done_for_day", "canceled", "expired", "replaced", "pending_cancel",
    "pending_replace", "stopped", "rejected", "suspended", "calculated",
))


class BrokerError(RuntimeError):
    """Base adapter error. Messages must never expose credentials."""


class BrokerConfigurationError(BrokerError):
    """The adapter was configured unsafely or lacks runtime credentials."""


class BrokerProtocolError(BrokerError):
    """A response was malformed or did not meet the documented contract."""


class BrokerRequestError(BrokerError):
    """The paper API rejected a request or the connection failed."""


class BrokerTimeoutUnknownStatus(BrokerError):
    """Submission timed out; the order may or may not have reached Alpaca."""

    def __init__(self, client_order_id: str) -> None:
        self.client_order_id = client_order_id
        super().__init__(
            "Paper order submission timed out; order status is unknown. "
            "Use get_order_by_client_order_id before taking any further action."
        )


@dataclass(frozen=True)
class HttpResponse:
    """Minimal transport result used by the urllib and test transports."""

    status: int
    body: bytes


@dataclass(frozen=True)
class OrderRequest:
    """A constrained Alpaca paper US-stock market or limit order.

    ``request_key`` is a stable caller-owned idempotency key. It creates a
    deterministic client_order_id so timeout recovery can look up the same
    intended order. A supplied ``client_order_id`` is accepted only when it is
    exactly that derived value. This does not itself guarantee broker
    idempotency across an unknown network outcome.
    """

    symbol: str
    qty: str
    side: str
    type: str = "market"
    time_in_force: str = "day"
    limit_price: Optional[str] = None
    request_key: str = ""
    client_order_id: Optional[str] = None

    def __post_init__(self) -> None:
        symbol = self.symbol.strip().upper() if isinstance(self.symbol, str) else ""
        if not _SYMBOL_RE.fullmatch(symbol):
            raise BrokerConfigurationError("symbol must be a supported US stock ticker")
        if self.side not in {"buy", "sell"}:
            raise BrokerConfigurationError("side must be buy or sell")
        if self.type not in {"market", "limit"}:
            raise BrokerConfigurationError("only market and limit stock orders are supported")
        if self.time_in_force not in {"day", "gtc"}:
            raise BrokerConfigurationError("time_in_force must be day or gtc")
        if not isinstance(self.qty, str) or not _positive_decimal_text(self.qty):
            raise BrokerConfigurationError("qty must be a positive decimal string")
        if self.type == "limit":
            if not isinstance(self.limit_price, str) or not _positive_decimal_text(self.limit_price):
                raise BrokerConfigurationError("limit orders require positive limit_price")
        elif self.limit_price is not None:
            raise BrokerConfigurationError("market orders must not include limit_price")
        if not isinstance(self.request_key, str) or not _CLIENT_ORDER_ID_RE.fullmatch(self.request_key):
            raise BrokerConfigurationError("request_key must be 1-48 letters, digits, _ or -")
        object.__setattr__(self, "symbol", symbol)
        derived_client_order_id = self._derived_client_order_id()
        if self.client_order_id is not None and self.client_order_id != derived_client_order_id:
            raise BrokerConfigurationError("client_order_id must equal the deterministic request_key-derived id")

    def resolved_client_order_id(self) -> str:
        """Return the deterministic, non-secret order identifier."""
        return self._derived_client_order_id()

    def _derived_client_order_id(self) -> str:
        canonical = json.dumps(
            {"symbol": self.symbol, "qty": self.qty, "side": self.side,
             "type": self.type, "time_in_force": self.time_in_force,
             "limit_price": self.limit_price, "request_key": self.request_key},
            sort_keys=True, separators=(",", ":"),
        )
        return "asai-" + sha256(canonical.encode("utf-8")).hexdigest()[:40]

    def payload(self) -> dict[str, str]:
        result = {
            "symbol": self.symbol, "qty": self.qty, "side": self.side,
            "type": self.type, "time_in_force": self.time_in_force,
            "client_order_id": self.resolved_client_order_id(),
        }
        if self.limit_price is not None:
            result["limit_price"] = self.limit_price
        return result


Transport = Callable[[str, str, Mapping[str, str], Optional[bytes], float], HttpResponse]


def _positive_decimal_text(value: str) -> bool:
    try:
        from decimal import Decimal, InvalidOperation
        parsed = Decimal(value)
        return parsed.is_finite() and parsed > 0
    except (InvalidOperation, ValueError):
        return False


class _NoRedirectHandler(HTTPRedirectHandler):
    """Make every redirect a response, never a credential-bearing follow-up."""

    def redirect_request(self, req: Request, fp: Any, code: int, msg: str,
                         headers: Any, newurl: str) -> None:
        return None


def _urllib_transport(method: str, url: str, headers: Mapping[str, str], body: Optional[bytes], timeout: float) -> HttpResponse:
    """Perform one HTTPS request with redirects disabled and no retries."""
    request = Request(url, data=body, headers=dict(headers), method=method)
    try:
        # urllib follows redirects by default and would otherwise resend API
        # credentials to a redirect target. A 3xx is returned/rejected below.
        opener = build_opener(_NoRedirectHandler())
        with opener.open(request, timeout=timeout) as response:  # nosec B310: fixed HTTPS origin
            return HttpResponse(response.status, response.read())
    except HTTPError as exc:
        return HttpResponse(exc.code, exc.read())
    except (socket.timeout, TimeoutError) as exc:
        raise TimeoutError("network timeout") from exc
    except URLError as exc:
        raise BrokerRequestError("paper API connection failed") from exc


class AlpacaPaperStocksClient:
    """Constrained client for documented Alpaca paper account/order endpoints.

    ``allow_paper_submit`` defaults to False. It must be consciously enabled for
    a manual, separately risk-gated paper workflow. No code path can use an
    Alpaca live hostname or a non-HTTPS transport URL.
    """

    def __init__(
        self, api_key_id: str, api_secret_key: str, *, timeout_seconds: float = 10.0,
        allow_paper_submit: bool = False, base_url: str = ALPACA_PAPER_URL,
        transport: Transport = _urllib_transport,
    ) -> None:
        if base_url != ALPACA_PAPER_URL:
            raise BrokerConfigurationError("live and custom broker hosts are disabled unconditionally")
        if not isinstance(api_key_id, str) or not api_key_id.strip() or not isinstance(api_secret_key, str) or not api_secret_key.strip():
            raise BrokerConfigurationError("runtime paper API credentials are required")
        if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool) or not 0 < timeout_seconds <= 30:
            raise BrokerConfigurationError("timeout_seconds must be between 0 and 30")
        if not callable(transport):
            raise BrokerConfigurationError("transport must be callable")
        self._api_key_id = api_key_id
        self._api_secret_key = api_secret_key
        self._timeout_seconds = float(timeout_seconds)
        self._allow_paper_submit = bool(allow_paper_submit)
        self._transport = transport

    @classmethod
    def from_environment(cls, **kwargs: Any) -> "AlpacaPaperStocksClient":
        """Read APCA_API_KEY_ID and APCA_API_SECRET_KEY only when called."""
        return cls(os.environ.get("APCA_API_KEY_ID", ""), os.environ.get("APCA_API_SECRET_KEY", ""), **kwargs)

    def get_account(self) -> dict[str, Any]:
        """GET https://paper-api.alpaca.markets/v2/account."""
        return self._request_json("GET", "/v2/account", expected={200})

    def get_positions(self) -> list[dict[str, Any]]:
        """GET https://paper-api.alpaca.markets/v2/positions."""
        payload = self._request_json("GET", "/v2/positions", expected={200}, response_types=(list,))
        if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
            raise BrokerProtocolError("paper API returned an invalid positions response")
        return payload

    def submit_order(self, order: OrderRequest) -> dict[str, Any]:
        """POST /v2/orders once; on timeout raises unknown-status exception.

        This low-level primitive is not safe to invoke autonomously. Callers need
        independent authorization, risk gating, audit, reconciliation and timeout
        recovery before manually enabling paper submission.
        """
        if not isinstance(order, OrderRequest):
            raise BrokerConfigurationError("order must be an OrderRequest")
        if not self._allow_paper_submit:
            raise BrokerConfigurationError("paper submission is disabled; independent risk gating is required")
        try:
            response = self._request_json("POST", "/v2/orders", expected={200, 201}, payload=order.payload())
        except TimeoutError as exc:
            raise BrokerTimeoutUnknownStatus(order.resolved_client_order_id()) from exc
        return _validated_order_response(response, expected_client_order_id=order.resolved_client_order_id())

    def get_order(self, order_id: str) -> dict[str, Any]:
        """GET /v2/orders/{order_id}; validates a path-safe broker UUID/string."""
        order_id = _path_id(order_id)
        response = self._request_json("GET", "/v2/orders/" + order_id, expected={200})
        return _validated_order_response(response, expected_order_id=order_id)

    def get_order_by_client_order_id(self, client_order_id: str) -> dict[str, Any]:
        """GET /v2/orders:by_client_order_id for timeout/duplicate investigation."""
        if not isinstance(client_order_id, str) or not _CLIENT_ORDER_ID_RE.fullmatch(client_order_id):
            raise BrokerConfigurationError("invalid client_order_id")
        response = self._request_json("GET", "/v2/orders:by_client_order_id?client_order_id=" + client_order_id, expected={200})
        return _validated_order_response(response, expected_client_order_id=client_order_id)

    def cancel_order(self, order_id: str) -> None:
        """DELETE /v2/orders/{order_id}; a 204 result has no response body."""
        self._request_json("DELETE", "/v2/orders/" + _path_id(order_id), expected={204}, allow_empty=True)

    def _request_json(self, method: str, path: str, *, expected: set[int], payload: Optional[dict[str, str]] = None, allow_empty: bool = False, response_types: tuple[type[Any], ...] = (dict,)) -> Any:
        body = None if payload is None else json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        headers = {"Accept": "application/json", "APCA-API-KEY-ID": self._api_key_id, "APCA-API-SECRET-KEY": self._api_secret_key}
        if body is not None:
            headers["Content-Type"] = "application/json"
        try:
            response = self._transport(method, ALPACA_PAPER_URL + path, headers, body, self._timeout_seconds)
        except (socket.timeout, TimeoutError):
            raise TimeoutError("network timeout") from None
        except Exception:
            raise BrokerRequestError("paper API connection failed") from None
        if not isinstance(response, HttpResponse) or not isinstance(response.status, int) or not isinstance(response.body, bytes):
            raise BrokerProtocolError("transport returned an invalid response")
        if response.status not in expected:
            raise BrokerRequestError("paper API request was rejected or failed")
        if allow_empty and response.status == 204:
            if response.body:
                raise BrokerProtocolError("paper API returned an unexpected response body")
            return None
        try:
            decoded = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BrokerProtocolError("paper API returned invalid JSON") from exc
        if not isinstance(decoded, response_types):
            raise BrokerProtocolError("paper API returned an unexpected JSON response")
        return decoded


def _path_id(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
        raise BrokerConfigurationError("invalid order_id")
    return value


def _validated_order_response(
    payload: Any, *, expected_order_id: Optional[str] = None,
    expected_client_order_id: Optional[str] = None,
) -> dict[str, Any]:
    """Reject incomplete, mismatched, or undocumented order state responses."""
    if not isinstance(payload, dict):
        raise BrokerProtocolError("paper API returned an invalid order response")
    order_id = payload.get("id")
    client_order_id = payload.get("client_order_id")
    status = payload.get("status")
    if not isinstance(order_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", order_id):
        raise BrokerProtocolError("paper API returned an invalid order id")
    if not isinstance(client_order_id, str) or not _CLIENT_ORDER_ID_RE.fullmatch(client_order_id):
        raise BrokerProtocolError("paper API returned an invalid client order id")
    if not isinstance(status, str) or status not in _ORDER_STATUSES:
        raise BrokerProtocolError("paper API returned an unknown order status")
    if expected_order_id is not None and order_id != expected_order_id:
        raise BrokerProtocolError("paper API returned a mismatched order id")
    if expected_client_order_id is not None and client_order_id != expected_client_order_id:
        raise BrokerProtocolError("paper API returned a mismatched client order id")
    return payload


__all__ = [
    "ALPACA_PAPER_HOST", "ALPACA_PAPER_URL", "AlpacaPaperStocksClient",
    "BrokerConfigurationError", "BrokerError", "BrokerProtocolError",
    "BrokerRequestError", "BrokerTimeoutUnknownStatus", "HttpResponse",
    "OrderRequest", "PAPER_STOCKS_ONLY_NOTICE",
]
