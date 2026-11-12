"""Deterministic offline multi-asset portfolio simulation.

This module consumes only caller-supplied, already-closed bars and inert caller
signals.  It has no network, broker, order, control, or live-data path.  A
signal at a documented UTC close is eligible only for the following aligned bar
open.  It is a research simulation, not investment advice or executable logic.

Deliberate omissions: dividends, splits and other corporate actions, taxes,
market impact, borrowing, FX conversion, and data authentication.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, Inexact, InvalidOperation, Rounded, localcontext
import hashlib
import json
import re
from typing import Iterable, Literal

D = Decimal
_MAX_BARS = 10_000
_MAX_SIGNALS = 50_000
_MAX_ABS_VALUE = D("1000000000")
# Inputs are bounded at _MAX_ABS_VALUE, but a valid long position can appreciate
# after entry. At most _MAX_BARS distinct symbols can be present, each with a
# bounded position and price, so retain a finite bound for calculated balances
# without rejecting that valid marked-to-market outcome.
_MAX_CALCULATED_ABS_VALUE = D("100000000000000000000000")
_MAX_DECIMAL_PLACES = 18
_MATH_PRECISION = 100
_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,15}$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")


class PortfolioBacktestInputError(ValueError):
    """Raised when supplied historical simulation inputs are ambiguous or unsafe."""


def _decimal(value: object, name: str, *, positive: bool = False, nonnegative: bool = False) -> Decimal:
    if type(value) is not Decimal or not value.is_finite() or value.as_tuple().exponent < -_MAX_DECIMAL_PLACES:
        raise PortfolioBacktestInputError(f"invalid {name}")
    if abs(value) > _MAX_ABS_VALUE or (positive and value <= 0) or (nonnegative and value < 0):
        raise PortfolioBacktestInputError(f"invalid {name}")
    return value


def _utc(value: object, name: str, *, strict: bool = False) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise PortfolioBacktestInputError(f"invalid {name}")
    if strict and value.utcoffset() != timezone.utc.utcoffset(value):
        raise PortfolioBacktestInputError(f"invalid {name}: UTC required")
    return value.astimezone(timezone.utc)


def _symbol(value: object) -> str:
    if type(value) is not str or not _SYMBOL.fullmatch(value):
        raise PortfolioBacktestInputError("invalid symbol")
    return value


def _math(operation, name: str) -> Decimal:
    try:
        with localcontext() as context:
            context.prec = _MATH_PRECISION
            context.traps[Inexact] = True
            context.traps[Rounded] = True
            result = operation()
    except (Inexact, Rounded, InvalidOperation, OverflowError, ValueError) as exc:
        raise PortfolioBacktestInputError(f"inexact or invalid {name}") from exc
    if not result.is_finite() or abs(result) > _MAX_CALCULATED_ABS_VALUE:
        raise PortfolioBacktestInputError(f"invalid {name}")
    return result


@dataclass(frozen=True)
class PortfolioBar:
    """A caller-provided closed OHLC subset for one symbol and interval."""
    open_timestamp: datetime
    close_timestamp: datetime
    symbol: str
    open: Decimal
    close: Decimal

    def __post_init__(self) -> None:
        if _utc(self.open_timestamp, "bar open timestamp") >= _utc(self.close_timestamp, "bar close timestamp"):
            raise PortfolioBacktestInputError("bar open timestamp must precede close timestamp")
        _symbol(self.symbol)
        _decimal(self.open, "bar open", positive=True)
        _decimal(self.close, "bar close", positive=True)


@dataclass(frozen=True)
class PortfolioSignal:
    """Inert instruction supplied by the caller; the engine never creates signals."""
    timestamp: datetime
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: Decimal

    def __post_init__(self) -> None:
        _utc(self.timestamp, "signal timestamp", strict=True)
        _symbol(self.symbol)
        if self.side not in ("BUY", "SELL"):
            raise PortfolioBacktestInputError("invalid signal side")
        _decimal(self.quantity, "signal quantity", positive=True)


@dataclass(frozen=True)
class PortfolioBacktestConfig:
    initial_cash: Decimal
    max_position_per_symbol: Decimal
    max_gross_exposure: Decimal
    fee_bps: Decimal = D("0")
    slippage_bps: Decimal = D("0")
    currency: str = "USD"

    def __post_init__(self) -> None:
        _decimal(self.initial_cash, "initial cash", nonnegative=True)
        _decimal(self.max_position_per_symbol, "max position per symbol", positive=True)
        _decimal(self.max_gross_exposure, "max gross exposure", nonnegative=True)
        _decimal(self.fee_bps, "fee bps", nonnegative=True)
        _decimal(self.slippage_bps, "slippage bps", nonnegative=True)
        if type(self.currency) is not str or not _CURRENCY.fullmatch(self.currency):
            raise PortfolioBacktestInputError("invalid currency")
        if self.fee_bps > D("10000") or self.slippage_bps >= D("10000"):
            raise PortfolioBacktestInputError("invalid execution configuration")


@dataclass(frozen=True)
class PortfolioOrder:
    signal_timestamp: datetime
    fill_timestamp: datetime | None
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: Decimal
    status: Literal["FILLED", "REJECTED_INSUFFICIENT_CASH", "REJECTED_POSITION_LIMIT", "REJECTED_GROSS_EXPOSURE", "REJECTED_INSUFFICIENT_POSITION", "UNFILLED_END_OF_DATA"]
    fill_price: Decimal | None
    fee: Decimal | None
    reason: str


@dataclass(frozen=True)
class PortfolioEquityPoint:
    timestamp: datetime
    cash: Decimal
    positions: tuple[tuple[str, Decimal], ...]
    prices: tuple[tuple[str, Decimal], ...]
    gross_exposure: Decimal
    equity: Decimal


@dataclass(frozen=True)
class PortfolioBacktestResult:
    currency: str
    symbols: tuple[str, ...]
    orders: tuple[PortfolioOrder, ...]
    equity: tuple[PortfolioEquityPoint, ...]
    final_cash: Decimal
    final_positions: tuple[tuple[str, Decimal], ...]
    final_equity: Decimal
    provenance: str
    status: Literal["COMPLETED", "COMPLETED_WITH_REJECTIONS", "COMPLETED_WITH_UNFILLED", "COMPLETED_WITH_REJECTIONS_AND_UNFILLED"]
    limitations: tuple[str, ...]


def _validated_config(config: object) -> PortfolioBacktestConfig:
    if type(config) is not PortfolioBacktestConfig:
        raise PortfolioBacktestInputError("invalid configuration")
    # Reconstruct an owned, revalidated snapshot in case frozen fields were bypassed.
    return PortfolioBacktestConfig(
        _decimal(config.initial_cash, "initial cash", nonnegative=True),
        _decimal(config.max_position_per_symbol, "max position per symbol", positive=True),
        _decimal(config.max_gross_exposure, "max gross exposure", nonnegative=True),
        _decimal(config.fee_bps, "fee bps", nonnegative=True),
        _decimal(config.slippage_bps, "slippage bps", nonnegative=True), config.currency,
    )


def _collect(items: Iterable[object], maximum: int, label: str) -> tuple[object, ...]:
    if isinstance(items, (str, bytes)):
        raise PortfolioBacktestInputError(f"{label} must be a bounded iterable")
    try:
        iterator, result = iter(items), []
        for _ in range(maximum + 1):
            try:
                result.append(next(iterator))
            except StopIteration:
                break
    except TypeError as exc:
        raise PortfolioBacktestInputError(f"{label} must be a bounded iterable") from exc
    if len(result) > maximum:
        raise PortfolioBacktestInputError(f"too many {label}")
    return tuple(result)


def _validated_bars(bars: Iterable[PortfolioBar], as_of: datetime) -> tuple[tuple[PortfolioBar, ...], tuple[str, ...], tuple[datetime, ...]]:
    supplied = _collect(bars, _MAX_BARS, "bars")
    if not supplied:
        raise PortfolioBacktestInputError("bars must not be empty")
    normalized: list[PortfolioBar] = []
    for bar in supplied:
        if type(bar) is not PortfolioBar:
            raise PortfolioBacktestInputError("invalid bar")
        opened, closed = _utc(bar.open_timestamp, "bar open timestamp"), _utc(bar.close_timestamp, "bar close timestamp")
        if opened >= closed:
            raise PortfolioBacktestInputError("bar open timestamp must precede close timestamp")
        if closed > as_of:
            raise PortfolioBacktestInputError("bar close timestamp is later than as_of cutoff")
        normalized.append(PortfolioBar(opened, closed, _symbol(bar.symbol), _decimal(bar.open, "bar open", positive=True), _decimal(bar.close, "bar close", positive=True)))
    values = tuple(sorted(normalized, key=lambda b: (b.open_timestamp, b.close_timestamp, b.symbol)))
    seen: set[tuple[datetime, datetime, str]] = set()
    by_time: dict[tuple[datetime, datetime], list[PortfolioBar]] = {}
    for bar in values:
        key = (bar.open_timestamp, bar.close_timestamp, bar.symbol)
        if key in seen:
            raise PortfolioBacktestInputError("duplicate bar")
        seen.add(key)
        by_time.setdefault((bar.open_timestamp, bar.close_timestamp), []).append(bar)
    intervals = tuple(sorted(by_time))
    first_symbols = tuple(sorted(bar.symbol for bar in by_time[intervals[0]]))
    if not first_symbols:
        raise PortfolioBacktestInputError("bars must contain symbols")
    duration = intervals[0][1] - intervals[0][0]
    prior_close: datetime | None = None
    interval_gap = None
    for opened, closed in intervals:
        if closed - opened != duration:
            raise PortfolioBacktestInputError("bars must have equal duration")
        symbols = tuple(sorted(bar.symbol for bar in by_time[(opened, closed)]))
        if symbols != first_symbols:
            raise PortfolioBacktestInputError("missing or misaligned symbol bar")
        if prior_close is not None:
            if opened < prior_close:
                raise PortfolioBacktestInputError("bar intervals overlap")
            gap = opened - prior_close
            if interval_gap is None:
                interval_gap = gap
            elif gap != interval_gap:
                raise PortfolioBacktestInputError("bars must be synchronously aligned")
        prior_close = closed
    return values, first_symbols, tuple(close for _, close in intervals)


def _validated_signals(signals: Iterable[PortfolioSignal], symbols: tuple[str, ...], close_times: tuple[datetime, ...]) -> tuple[PortfolioSignal, ...]:
    supplied = _collect(signals, _MAX_SIGNALS, "signals")
    normalized: list[PortfolioSignal] = []
    close_set = set(close_times)
    known = set(symbols)
    for signal in supplied:
        if type(signal) is not PortfolioSignal:
            raise PortfolioBacktestInputError("invalid signal")
        timestamp = _utc(signal.timestamp, "signal timestamp", strict=True)
        symbol = _symbol(signal.symbol)
        if symbol not in known:
            raise PortfolioBacktestInputError("unknown signal symbol")
        if timestamp not in close_set:
            raise PortfolioBacktestInputError("signal timestamp must match a closed bar")
        if signal.side not in ("BUY", "SELL"):
            raise PortfolioBacktestInputError("invalid signal side")
        normalized.append(PortfolioSignal(timestamp, symbol, signal.side, _decimal(signal.quantity, "signal quantity", positive=True)))
    values = tuple(sorted(normalized, key=lambda s: (s.timestamp, s.symbol)))
    if any((a.timestamp, a.symbol) == (b.timestamp, b.symbol) for a, b in zip(values, values[1:])):
        raise PortfolioBacktestInputError("duplicate signal for symbol and timestamp")
    return values


def _provenance(bars: tuple[PortfolioBar, ...], signals: tuple[PortfolioSignal, ...], config: PortfolioBacktestConfig, as_of: datetime) -> str:
    payload = {"engine": "offline-portfolio-v1", "as_of": as_of.isoformat(),
               "bars": [(b.open_timestamp.isoformat(), b.close_timestamp.isoformat(), b.symbol, str(b.open), str(b.close)) for b in bars],
               "signals": [(s.timestamp.isoformat(), s.symbol, s.side, str(s.quantity)) for s in signals],
               "config": [str(config.initial_cash), str(config.max_position_per_symbol), str(config.max_gross_exposure), str(config.fee_bps), str(config.slippage_bps), config.currency]}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _status(orders: list[PortfolioOrder]) -> Literal["COMPLETED", "COMPLETED_WITH_REJECTIONS", "COMPLETED_WITH_UNFILLED", "COMPLETED_WITH_REJECTIONS_AND_UNFILLED"]:
    rejected = any(o.status.startswith("REJECTED") for o in orders)
    unfilled = any(o.status == "UNFILLED_END_OF_DATA" for o in orders)
    return "COMPLETED_WITH_REJECTIONS_AND_UNFILLED" if rejected and unfilled else "COMPLETED_WITH_REJECTIONS" if rejected else "COMPLETED_WITH_UNFILLED" if unfilled else "COMPLETED"


def run_portfolio_backtest(bars: Iterable[PortfolioBar], signals: Iterable[PortfolioSignal], config: PortfolioBacktestConfig, *, as_of: datetime) -> PortfolioBacktestResult:
    """Replay caller signals with closed-bar decisions and next-open simulated fills.

    Bars must form a complete UTC-aligned grid with a consistent inter-bar gap.
    Same-open orders process sells before buys, then symbols in lexical order,
    so released shared cash is available deterministically to purchases.
    """
    cutoff = _utc(as_of, "as_of", strict=True)
    config = _validated_config(config)
    values, symbols, close_times = _validated_bars(bars, cutoff)
    signals = _validated_signals(signals, symbols, close_times)
    grid: dict[datetime, dict[str, PortfolioBar]] = {}
    for bar in values:
        grid.setdefault(bar.close_timestamp, {})[bar.symbol] = bar
    close_to_next_open = {close_times[index]: grid[close_times[index + 1]][symbols[0]].open_timestamp for index in range(len(close_times) - 1)}
    by_execution: dict[datetime, list[PortfolioSignal]] = {}
    unfilled: list[PortfolioSignal] = []
    for signal in signals:
        if signal.timestamp not in close_to_next_open:
            unfilled.append(signal)
        else:
            by_execution.setdefault(close_to_next_open[signal.timestamp], []).append(signal)

    cash, positions, orders, equity = config.initial_cash, {symbol: D("0") for symbol in symbols}, [], []
    for close_time in close_times:
        bars_at_close = grid[close_time]
        execution_time = bars_at_close[symbols[0]].open_timestamp
        # A sale at this documented open is known to execute before a purchase
        # at that same open. This avoids falsely rejecting an affordable buy
        # merely because its symbol precedes the sale alphabetically.
        for signal in sorted(by_execution.get(execution_time, ()), key=lambda s: (s.side != "SELL", s.symbol)):
            bar, position = bars_at_close[signal.symbol], positions[signal.symbol]
            multiplier = _math(lambda: D("1") + config.slippage_bps / D("10000") if signal.side == "BUY" else D("1") - config.slippage_bps / D("10000"), "slippage multiplier")
            fill_price = _math(lambda: bar.open * multiplier, "fill price")
            gross = _math(lambda: fill_price * signal.quantity, "gross notional")
            fee = _math(lambda: gross * config.fee_bps / D("10000"), "fee")
            if signal.side == "SELL" and signal.quantity > position:
                orders.append(PortfolioOrder(signal.timestamp, execution_time, signal.symbol, signal.side, signal.quantity, "REJECTED_INSUFFICIENT_POSITION", fill_price, fee, "long-only simulation cannot sell more than held")); continue
            if signal.side == "BUY" and position + signal.quantity > config.max_position_per_symbol:
                orders.append(PortfolioOrder(signal.timestamp, execution_time, signal.symbol, signal.side, signal.quantity, "REJECTED_POSITION_LIMIT", fill_price, fee, "per-symbol long position cap would be exceeded")); continue
            # Cap checks use only prices known at this documented execution open;
            # using this interval's closes here would leak future information.
            gross_after = _math(lambda: sum(positions[s] * bar_at_open.open for s, bar_at_open in bars_at_close.items()) + (gross if signal.side == "BUY" else -gross), "gross exposure")
            if signal.side == "BUY" and gross_after > config.max_gross_exposure:
                orders.append(PortfolioOrder(signal.timestamp, execution_time, signal.symbol, signal.side, signal.quantity, "REJECTED_GROSS_EXPOSURE", fill_price, fee, "gross exposure cap would be exceeded")); continue
            if signal.side == "BUY" and _math(lambda: gross + fee, "buy cost") > cash:
                orders.append(PortfolioOrder(signal.timestamp, execution_time, signal.symbol, signal.side, signal.quantity, "REJECTED_INSUFFICIENT_CASH", fill_price, fee, "cash cannot cover fill and fee")); continue
            cash = _math(lambda: cash - gross - fee if signal.side == "BUY" else cash + gross - fee, "cash")
            positions[signal.symbol] = _math(lambda: position + signal.quantity if signal.side == "BUY" else position - signal.quantity, "position")
            orders.append(PortfolioOrder(signal.timestamp, execution_time, signal.symbol, signal.side, signal.quantity, "FILLED", fill_price, fee, "documented next aligned bar open fill after caller signal"))
        prices = tuple((symbol, bars_at_close[symbol].close) for symbol in symbols)
        gross_exposure = _math(lambda: sum(positions[symbol] * price for symbol, price in prices), "gross exposure")
        account_equity = _math(lambda: cash + gross_exposure, "equity")
        equity.append(PortfolioEquityPoint(close_time, cash, tuple((s, positions[s]) for s in symbols), prices, gross_exposure, account_equity))
    for signal in unfilled:
        orders.append(PortfolioOrder(signal.timestamp, None, signal.symbol, signal.side, signal.quantity, "UNFILLED_END_OF_DATA", None, None, "no next documented aligned bar open exists"))
    # Retain the deterministic same-open execution sequence in the audit trail.
    orders.sort(key=lambda o: (o.signal_timestamp, o.side != "SELL", o.symbol))
    final = equity[-1]
    limitations = ("Simulation only: no dividends, corporate actions, taxes, market impact, borrowing, or FX conversion.", "Caller-supplied data are unauthenticated; no claim of completeness, authorization, production readiness, or profitability is made.")
    return PortfolioBacktestResult(config.currency, symbols, tuple(orders), tuple(equity), final.cash, final.positions, final.equity, _provenance(values, signals, config, cutoff), _status(orders), limitations)
