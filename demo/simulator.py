"""Deliberately small, in-memory simulator for the ASAI demo.

This module is simulation-only.  It never reads credentials, calls a broker, or
creates a real-market order.  State disappears when the process restarts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Context, Decimal, InvalidOperation, localcontext
import re
import threading
from typing import Any


class DemoError(ValueError):
    """Safe, machine-readable simulator failure."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


@dataclass(frozen=True)
class DemoQuote:
    """Quote supplied by the caller; the simulator does not fetch market data."""

    symbol: str
    bid: Decimal
    ask: Decimal
    provider_time: datetime
    retrieved_at: datetime
    source: str


class DemoSimulator:
    """Thread-safe AAPL-only, immediate-fill simulator.

    Orders are limit-only and are filled immediately only against a fresh,
    internally consistent caller-supplied quote.  A non-marketable limit is
    rejected; it is never parked or reserved.  Accounting has no fees.
    """

    _SYMBOL = "AAPL"
    _INITIAL_CASH = Decimal("10000.00")
    _MAX_QUANTITY = 1_000_000
    _MAX_PRICE = Decimal("1000000.00000000")
    # Accepted prices and quantities fit exactly in this owned context. This
    # prevents hostile process-wide Decimal settings from changing accounting.
    _ACCOUNTING_CONTEXT = Context(prec=32)
    _PRICE_RE = re.compile(r"(?:0|[1-9]\d*)(?:\.\d{1,8})?")
    _IDEMPOTENCY_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")
    _MAX_QUOTE_AGE = timedelta(seconds=15)
    _QUOTE_SOURCES = frozenset(("fixture", "alpaca_iex"))
    _WARNING = (
        "SIMULATION ONLY: in-memory demo; no broker connection, credentials, "
        "or live order routing. Quote evidence may be fixture or delayed data; "
        "fills are simulated. State resets when the process restarts."
    )

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cash = self._INITIAL_CASH
        self._position = 0
        self._orders: dict[str, dict[str, Any]] = {}
        self._idempotency: dict[str, tuple[tuple[Any, ...], dict[str, Any]]] = {}
        self._next_order = 1

    def place_order(
        self,
        payload: dict,
        idempotency_key: str,
        quote: DemoQuote | None,
        now: datetime,
    ) -> dict:
        """Validate and immediately fill a marketable limit, or fail closed.

        The idempotency key binds to the canonical validated payload. Repeating
        that payload returns the original result; reusing the key for another
        payload raises ``IDEMPOTENCY_CONFLICT``.
        """
        canonical = self._canonical_payload(payload)
        self._validate_idempotency_key(idempotency_key)
        self._validate_now(now)
        with self._lock:
            previous = self._idempotency.get(idempotency_key)
            if previous is not None:
                if previous[0] != canonical:
                    raise DemoError("IDEMPOTENCY_CONFLICT")
                return dict(previous[1])

            self._validate_quote(quote, now)
            assert quote is not None  # narrowed after fail-closed validation
            symbol, side, quantity, limit_price = canonical
            execution_price = quote.ask if side == "BUY" else quote.bid
            if (side == "BUY" and execution_price > limit_price) or (
                side == "SELL" and execution_price < limit_price
            ):
                raise DemoError("LIMIT_NOT_MARKETABLE")

            # Keep checks and mutation in one locked transaction, using an
            # owned Decimal context rather than ambient process settings.
            with localcontext(self._ACCOUNTING_CONTEXT):
                notional = execution_price * quantity
                if side == "BUY" and notional > self._cash:
                    raise DemoError("INSUFFICIENT_CASH")
                if side == "SELL" and quantity > self._position:
                    raise DemoError("INSUFFICIENT_POSITION")

                order_id = f"demo-{self._next_order:08d}"
                self._next_order += 1
                if side == "BUY":
                    self._cash -= notional
                    self._position += quantity
                else:
                    self._cash += notional
                    self._position -= quantity
            result = self._order_result(
                order_id, symbol, side, quantity, limit_price, execution_price, quote, now
            )
            self._orders[order_id] = result
            self._idempotency[idempotency_key] = (canonical, result)
            return dict(result)

    def cancel_order(self, order_id: str) -> dict:
        """Cancel is intentionally unavailable for immediately filled orders."""
        if not isinstance(order_id, str) or not order_id:
            raise DemoError("INVALID_ORDER_ID")
        with self._lock:
            order = self._orders.get(order_id)
            if order is None:
                raise DemoError("ORDER_NOT_FOUND")
            # The only persisted orders are already FILLED, so no reservation
            # exists to release and cancellation cannot alter accounting.
            raise DemoError("ORDER_NOT_CANCELLABLE")

    def snapshot(self) -> dict:
        """Return a copy of the current simulation-only account state."""
        with self._lock:
            return {
                "mode": "SIMULATION_ONLY",
                "warning": self._WARNING,
                "cash": self._decimal_text(self._cash),
                "positions": {self._SYMBOL: self._position},
                "orders": [dict(order) for order in self._orders.values()],
                "fees_modeled": False,
                "in_memory": True,
            }

    def _canonical_payload(self, payload: dict) -> tuple[str, str, int, Decimal]:
        if type(payload) is not dict or set(payload) != {
            "symbol", "side", "quantity", "limit_price"
        }:
            raise DemoError("INVALID_PAYLOAD")
        symbol = payload["symbol"]
        side = payload["side"]
        quantity = payload["quantity"]
        limit_text = payload["limit_price"]
        if symbol != self._SYMBOL:
            raise DemoError("UNSUPPORTED_SYMBOL")
        if side not in ("BUY", "SELL"):
            raise DemoError("INVALID_SIDE")
        if type(quantity) is not int or not 1 <= quantity <= self._MAX_QUANTITY:
            raise DemoError("INVALID_QUANTITY")
        price = self._parse_price(limit_text, "INVALID_LIMIT_PRICE")
        return (symbol, side, quantity, price)

    def _validate_quote(self, quote: DemoQuote | None, now: datetime) -> None:
        if quote is None:
            raise DemoError("QUOTE_REQUIRED")
        if not isinstance(quote, DemoQuote) or quote.symbol != self._SYMBOL:
            raise DemoError("INVALID_QUOTE")
        # Provenance is closed: callers cannot blend or invent a source label
        # that could be presented as real-time market evidence.
        if quote.source not in self._QUOTE_SOURCES:
            raise DemoError("INVALID_QUOTE")
        self._validate_aware(quote.provider_time, "INVALID_QUOTE_TIME")
        self._validate_aware(quote.retrieved_at, "INVALID_QUOTE_TIME")
        if quote.provider_time > now or quote.retrieved_at > now:
            raise DemoError("QUOTE_FUTURE")
        if quote.provider_time > quote.retrieved_at:
            raise DemoError("INVALID_QUOTE_TIME")
        if now - quote.retrieved_at > self._MAX_QUOTE_AGE:
            raise DemoError("QUOTE_STALE")
        bid = self._quote_price(quote.bid)
        ask = self._quote_price(quote.ask)
        if bid > ask:
            raise DemoError("INVALID_QUOTE")

    def _quote_price(self, value: Any) -> Decimal:
        if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
            raise DemoError("INVALID_QUOTE")
        if value.as_tuple().exponent < -8 or value > self._MAX_PRICE:
            raise DemoError("INVALID_QUOTE")
        return value

    def _parse_price(self, value: Any, code: str) -> Decimal:
        if not isinstance(value, str) or not self._PRICE_RE.fullmatch(value):
            raise DemoError(code)
        try:
            price = Decimal(value)
        except InvalidOperation as exc:  # defensive; regex already excludes this
            raise DemoError(code) from exc
        if price <= 0 or price > self._MAX_PRICE:
            raise DemoError(code)
        return price

    def _validate_idempotency_key(self, key: Any) -> None:
        if not isinstance(key, str) or not self._IDEMPOTENCY_RE.fullmatch(key):
            raise DemoError("INVALID_IDEMPOTENCY_KEY")

    def _validate_now(self, now: datetime) -> None:
        self._validate_aware(now, "INVALID_NOW")

    @staticmethod
    def _validate_aware(value: Any, code: str) -> None:
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise DemoError(code)

    def _order_result(
        self,
        order_id: str,
        symbol: str,
        side: str,
        quantity: int,
        limit_price: Decimal,
        execution_price: Decimal,
        quote: DemoQuote,
        now: datetime,
    ) -> dict:
        return {
            "order_id": order_id,
            "status": "FILLED",
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "limit_price": self._decimal_text(limit_price),
            "fill_price": self._decimal_text(execution_price),
            "filled_at": now.isoformat(),
            "quote_provider_time": quote.provider_time.isoformat(),
            "quote_retrieved_at": quote.retrieved_at.isoformat(),
            "quote_source": quote.source,
            "mode": "SIMULATION_ONLY",
            "warning": self._WARNING,
            "fees_modeled": False,
        }

    @staticmethod
    def _decimal_text(value: Decimal) -> str:
        return format(value, "f")
