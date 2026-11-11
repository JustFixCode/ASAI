"""Deterministic, offline, long-only historical backtesting.

This research-only module has no network, broker, order-submission, or live-data
integration. Each caller-supplied closed bar explicitly carries its open and close
timestamps. A signal made at a close can only fill at a later bar's documented
open. Bars must have one exact duration and non-overlapping intervals; permitted
inter-bar gaps are explicitly bounded by configuration, but are still reported as
incomplete supplied history rather than evidence of continuous market coverage.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, Inexact, InvalidOperation, Rounded, localcontext
import hashlib
import json
import re
from typing import Iterable, Literal

D = Decimal
_MAX_BARS = 10_000
_MAX_ABS_VALUE = D("1000000000")
_MAX_DECIMAL_PLACES = 18
_MATH_PRECISION = 100
_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,15}$")


class BacktestInputError(ValueError):
    """Raised when bounded historical research inputs are unsafe or ambiguous."""


def _decimal(value: object, name: str, *, positive: bool = False, nonnegative: bool = False) -> Decimal:
    if type(value) is not Decimal or not value.is_finite() or value.as_tuple().exponent < -_MAX_DECIMAL_PLACES:
        raise BacktestInputError(f"invalid {name}")
    if abs(value) > _MAX_ABS_VALUE:
        raise BacktestInputError(f"invalid {name}")
    if positive and value <= 0:
        raise BacktestInputError(f"invalid {name}")
    if nonnegative and value < 0:
        raise BacktestInputError(f"invalid {name}")
    return value


def _timestamp(value: object, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise BacktestInputError(f"invalid {name}")
    return value


def _utc_timestamp(value: object, name: str, *, require_utc: bool = False) -> datetime:
    timestamp = _timestamp(value, name)
    if require_utc and timestamp.utcoffset() != timezone.utc.utcoffset(timestamp):
        raise BacktestInputError(f"invalid {name}: UTC required")
    return timestamp.astimezone(timezone.utc)


def _symbol(value: object) -> str:
    if type(value) is not str or not _SYMBOL.fullmatch(value):
        raise BacktestInputError("invalid symbol")
    return value


@dataclass(frozen=True)
class BacktestBar:
    """One caller-supplied closed OHLC bar with explicit aware interval endpoints."""

    open_timestamp: datetime
    close_timestamp: datetime
    symbol: str
    open: Decimal
    close: Decimal

    def __post_init__(self) -> None:
        opened = _utc_timestamp(self.open_timestamp, "bar open timestamp")
        closed = _utc_timestamp(self.close_timestamp, "bar close timestamp")
        if opened >= closed:
            raise BacktestInputError("bar open timestamp must precede close timestamp")
        _symbol(self.symbol)
        _decimal(self.open, "bar open", positive=True)
        _decimal(self.close, "bar close", positive=True)


@dataclass(frozen=True)
class SMAcrossoverStrategy:
    short_window: int
    long_window: int

    def __post_init__(self) -> None:
        if type(self.short_window) is not int or type(self.long_window) is not int:
            raise BacktestInputError("SMA windows must be integers")
        if not (1 <= self.short_window < self.long_window <= _MAX_BARS):
            raise BacktestInputError("invalid SMA windows")


@dataclass(frozen=True)
class BacktestConfig:
    initial_cash: Decimal
    order_quantity: Decimal
    max_position: Decimal
    max_gap_seconds: int
    fee_bps: Decimal = D("0")
    slippage_bps: Decimal = D("0")

    def __post_init__(self) -> None:
        _decimal(self.initial_cash, "initial cash", nonnegative=True)
        _decimal(self.order_quantity, "order quantity", positive=True)
        _decimal(self.max_position, "max position", positive=True)
        _decimal(self.fee_bps, "fee bps", nonnegative=True)
        _decimal(self.slippage_bps, "slippage bps", nonnegative=True)
        if type(self.max_gap_seconds) is not int or not (0 <= self.max_gap_seconds <= 31_536_000):
            raise BacktestInputError("invalid max gap seconds")
        # A fee above gross proceeds can make an otherwise valid sell borrow cash.
        if self.fee_bps > D("10000") or self.slippage_bps >= D("10000"):
            raise BacktestInputError("invalid execution configuration")


def _validated_strategy(strategy: object) -> SMAcrossoverStrategy:
    """Revalidate and detach strategy values at the execution boundary.

    Frozen dataclasses prevent accidental mutation, but a caller holding an
    object reference can bypass that protection with ``object.__setattr__``.
    The replay validates the fields it will consume and uses an owned snapshot,
    rather than trusting that __post_init__ ran when the object was created.
    """
    if type(strategy) is not SMAcrossoverStrategy:
        raise BacktestInputError("invalid strategy")
    short_window, long_window = strategy.short_window, strategy.long_window
    if type(short_window) is not int or type(long_window) is not int:
        raise BacktestInputError("SMA windows must be integers")
    if not (1 <= short_window < long_window <= _MAX_BARS):
        raise BacktestInputError("invalid SMA windows")
    return SMAcrossoverStrategy(short_window, long_window)


def _validated_config(config: object) -> BacktestConfig:
    """Revalidate and detach every execution configuration field."""
    if type(config) is not BacktestConfig:
        raise BacktestInputError("invalid configuration")
    initial_cash = _decimal(config.initial_cash, "initial cash", nonnegative=True)
    order_quantity = _decimal(config.order_quantity, "order quantity", positive=True)
    max_position = _decimal(config.max_position, "max position", positive=True)
    fee_bps = _decimal(config.fee_bps, "fee bps", nonnegative=True)
    slippage_bps = _decimal(config.slippage_bps, "slippage bps", nonnegative=True)
    max_gap_seconds = config.max_gap_seconds
    if type(max_gap_seconds) is not int or not (0 <= max_gap_seconds <= 31_536_000):
        raise BacktestInputError("invalid max gap seconds")
    if fee_bps > D("10000") or slippage_bps >= D("10000"):
        raise BacktestInputError("invalid execution configuration")
    return BacktestConfig(initial_cash, order_quantity, max_position, max_gap_seconds, fee_bps, slippage_bps)


@dataclass(frozen=True)
class HistoricalOrder:
    signal_timestamp: datetime
    fill_timestamp: datetime | None
    side: Literal["BUY", "SELL"]
    quantity: Decimal
    status: Literal["FILLED", "REJECTED_INSUFFICIENT_CASH", "REJECTED_POSITION_LIMIT", "REJECTED_NEGATIVE_CASH", "UNFILLED_END_OF_DATA"]
    fill_price: Decimal | None
    fee: Decimal | None
    reason: str


@dataclass(frozen=True)
class EquityPoint:
    timestamp: datetime
    cash: Decimal
    position: Decimal
    close: Decimal
    equity: Decimal


@dataclass(frozen=True)
class BacktestResult:
    symbol: str
    orders: tuple[HistoricalOrder, ...]
    equity: tuple[EquityPoint, ...]
    final_cash: Decimal
    final_position: Decimal
    final_equity: Decimal
    provenance: str
    status: Literal["COMPLETED", "COMPLETED_WITH_REJECTIONS", "COMPLETED_WITH_UNFILLED", "COMPLETED_WITH_REJECTIONS_AND_UNFILLED"]
    warnings: tuple[str, ...]


def _safe_math(operation, name: str) -> Decimal:
    try:
        with localcontext() as context:
            context.prec = _MATH_PRECISION
            context.traps[Inexact] = True
            context.traps[Rounded] = True
            result = operation()
    except (Inexact, Rounded, InvalidOperation, OverflowError, ValueError) as exc:
        raise BacktestInputError(f"inexact or invalid {name}") from exc
    if not result.is_finite() or abs(result) > _MAX_ABS_VALUE:
        raise BacktestInputError(f"invalid {name}")
    return result


def _provenance(bars: tuple[BacktestBar, ...], strategy: SMAcrossoverStrategy, config: BacktestConfig, as_of: datetime) -> str:
    payload = {
        "as_of": as_of.isoformat(),
        "bars": [(_utc_timestamp(bar.open_timestamp, "bar open timestamp").isoformat(),
                  _utc_timestamp(bar.close_timestamp, "bar close timestamp").isoformat(), bar.symbol,
                  str(bar.open), str(bar.close)) for bar in bars],
        "strategy": [strategy.short_window, strategy.long_window],
        "config": [str(config.initial_cash), str(config.order_quantity), str(config.max_position),
                   config.max_gap_seconds, str(config.fee_bps), str(config.slippage_bps)],
        "engine": "offline-sma-v3",
    }
    return hashlib.sha256(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")).hexdigest()


def _validated_bars(bars: Iterable[BacktestBar], as_of: datetime, config: BacktestConfig) -> tuple[tuple[BacktestBar, ...], tuple[str, ...]]:
    if isinstance(bars, (str, bytes)):
        raise BacktestInputError("bars must be a bounded iterable")
    try:
        iterator, collected = iter(bars), []
        for _ in range(_MAX_BARS + 1):
            try:
                collected.append(next(iterator))
            except StopIteration:
                break
        supplied = tuple(collected)
    except TypeError as exc:
        raise BacktestInputError("bars must be a bounded iterable") from exc
    if not supplied or len(supplied) > _MAX_BARS:
        raise BacktestInputError("bars must contain 1 to 10000 items")
    if any(type(bar) is not BacktestBar for bar in supplied):
        raise BacktestInputError("invalid bar")

    # Revalidate every consumed field and create owned, UTC-normalized records.
    # This deliberately does not rely on BacktestBar.__post_init__: frozen
    # records may have been mutated through object.__setattr__ after creation.
    normalized: list[BacktestBar] = []
    for bar in supplied:
        opened = _utc_timestamp(bar.open_timestamp, "bar open timestamp")
        closed = _utc_timestamp(bar.close_timestamp, "bar close timestamp")
        if opened >= closed:
            raise BacktestInputError("bar open timestamp must precede close timestamp")
        symbol = _symbol(bar.symbol)
        opening_price = _decimal(bar.open, "bar open", positive=True)
        closing_price = _decimal(bar.close, "bar close", positive=True)
        normalized.append(BacktestBar(opened, closed, symbol, opening_price, closing_price))
    values = tuple(normalized)

    symbol, previous_close, duration = values[0].symbol, None, None
    gaps: list[timedelta] = []
    for bar in values:
        opened, closed = bar.open_timestamp, bar.close_timestamp
        interval = closed - opened
        if bar.symbol != symbol:
            raise BacktestInputError("bars must contain exactly one symbol")
        if closed > as_of:
            raise BacktestInputError("bar close timestamp is later than as_of cutoff")
        if duration is None:
            duration = interval
        elif interval != duration:
            raise BacktestInputError("bars must have equal duration")
        if previous_close is not None:
            if opened <= previous_close:
                raise BacktestInputError("bar intervals must be non-overlapping with open after previous close")
            gap = opened - previous_close
            if gap > timedelta(seconds=config.max_gap_seconds):
                raise BacktestInputError("bar gap exceeds configured maximum")
            gaps.append(gap)
        previous_close = closed
    warnings = () if not gaps else ("Supplied history contains permitted inter-bar gaps; it is incomplete and does not establish continuous market coverage.",)
    return values, warnings


def _signal(closes: tuple[Decimal, ...], strategy: SMAcrossoverStrategy) -> int:
    if len(closes) < strategy.long_window + 1:
        return 0
    current_short_sum = _safe_math(lambda: sum(closes[-strategy.short_window:]), "short SMA sum")
    current_long_sum = _safe_math(lambda: sum(closes[-strategy.long_window:]), "long SMA sum")
    previous_short_sum = _safe_math(lambda: sum(closes[-strategy.short_window - 1:-1]), "previous short SMA sum")
    previous_long_sum = _safe_math(lambda: sum(closes[-strategy.long_window - 1:-1]), "previous long SMA sum")
    current_left = _safe_math(lambda: current_short_sum * D(strategy.long_window), "current SMA comparison")
    current_right = _safe_math(lambda: current_long_sum * D(strategy.short_window), "current SMA comparison")
    previous_left = _safe_math(lambda: previous_short_sum * D(strategy.long_window), "previous SMA comparison")
    previous_right = _safe_math(lambda: previous_long_sum * D(strategy.short_window), "previous SMA comparison")
    return 1 if previous_left <= previous_right and current_left > current_right else -1 if previous_left >= previous_right and current_left < current_right else 0


def _run_status(orders: list[HistoricalOrder]) -> Literal["COMPLETED", "COMPLETED_WITH_REJECTIONS", "COMPLETED_WITH_UNFILLED", "COMPLETED_WITH_REJECTIONS_AND_UNFILLED"]:
    rejected, unfilled = any(o.status.startswith("REJECTED_") for o in orders), any(o.status == "UNFILLED_END_OF_DATA" for o in orders)
    return "COMPLETED_WITH_REJECTIONS_AND_UNFILLED" if rejected and unfilled else "COMPLETED_WITH_REJECTIONS" if rejected else "COMPLETED_WITH_UNFILLED" if unfilled else "COMPLETED"


def run_backtest(bars: Iterable[BacktestBar], strategy: SMAcrossoverStrategy, config: BacktestConfig, *, as_of: datetime) -> BacktestResult:
    """Run closed-bar replay; fills are simulated at documented next-bar opens only."""
    cutoff = _utc_timestamp(as_of, "as_of", require_utc=True)
    strategy = _validated_strategy(strategy)
    config = _validated_config(config)
    values, warnings = _validated_bars(bars, cutoff, config)
    cash, position, orders, equity = config.initial_cash, D("0"), [], []
    pending: tuple[datetime, Literal["BUY", "SELL"]] | None = None
    closes: list[Decimal] = []
    for bar in values:
        opened, closed = _utc_timestamp(bar.open_timestamp, "bar open timestamp"), _utc_timestamp(bar.close_timestamp, "bar close timestamp")
        if pending is not None:
            signal_timestamp, side = pending
            quantity = config.order_quantity if side == "BUY" else position
            if side == "BUY" and position + quantity > config.max_position:
                orders.append(HistoricalOrder(signal_timestamp, opened, side, quantity, "REJECTED_POSITION_LIMIT", None, None, "max long position would be exceeded"))
            elif side != "SELL" or quantity > 0:
                multiplier = _safe_math(lambda: D("1") + config.slippage_bps / D("10000") if side == "BUY" else D("1") - config.slippage_bps / D("10000"), "slippage multiplier")
                fill_price = _safe_math(lambda: bar.open * multiplier, "fill price")
                gross = _safe_math(lambda: fill_price * quantity, "gross notional")
                fee = _safe_math(lambda: gross * config.fee_bps / D("10000"), "fee")
                if side == "BUY" and _safe_math(lambda: gross + fee, "buy cost") > cash:
                    orders.append(HistoricalOrder(signal_timestamp, opened, side, quantity, "REJECTED_INSUFFICIENT_CASH", fill_price, fee, "cash cannot cover fill and fee"))
                elif side == "SELL" and _safe_math(lambda: cash + gross - fee, "post-sale cash") < 0:
                    orders.append(HistoricalOrder(signal_timestamp, opened, side, quantity, "REJECTED_NEGATIVE_CASH", fill_price, fee, "sale would make cash negative"))
                else:
                    cash = _safe_math(lambda: cash - gross - fee if side == "BUY" else cash + gross - fee, "cash")
                    position = _safe_math(lambda: position + quantity if side == "BUY" else position - quantity, "position")
                    orders.append(HistoricalOrder(signal_timestamp, opened, side, quantity, "FILLED", fill_price, fee, "documented next-bar open fill after closed-bar signal"))
            pending = None
        closes.append(bar.close)
        signal = _signal(tuple(closes), strategy)
        if signal == 1 and position == 0:
            pending = (closed, "BUY")
        elif signal == -1 and position > 0:
            pending = (closed, "SELL")
        value = _safe_math(lambda: cash + position * bar.close, "equity")
        equity.append(EquityPoint(closed, cash, position, bar.close, value))
    if pending is not None:
        signal_timestamp, side = pending
        orders.append(HistoricalOrder(signal_timestamp, None, side, config.order_quantity if side == "BUY" else position, "UNFILLED_END_OF_DATA", None, None, "no next documented bar open exists for an auditable fill"))
    final = equity[-1]
    return BacktestResult(values[0].symbol, tuple(orders), tuple(equity), final.cash, final.position, final.equity, _provenance(values, strategy, config, cutoff), _run_status(orders), warnings)
