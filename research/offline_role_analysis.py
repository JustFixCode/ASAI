"""Pure, deterministic multi-role analysis of caller-supplied historical bars.

This module is intentionally offline and side-effect free.  It neither fetches data nor
uses models, URLs, files, credentials, orders, trading, policy, or risk controls.
It produces descriptive observations of supplied numeric history, never predictions,
trade instructions, performance claims, or recommendations.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
from typing import Literal

_MAX_BARS = 10_000
_MAX_SYMBOL_LENGTH = 32
_MAX_GAP = timedelta(days=31)
_MAX_DECIMAL_DIGITS = 40
_ZERO = Decimal("0")
_HUNDRED = Decimal("100")


class OfflineRoleAnalysisError(ValueError):
    """Raised when historical bars or the requested cutoff are malformed or unsafe."""


@dataclass(frozen=True)
class HistoricalNumericBar:
    """One closed, local historical numeric bar; values are caller assertions only."""

    open_timestamp: datetime
    close_timestamp: datetime
    symbol: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal


@dataclass(frozen=True)
class RoleObservation:
    """A bounded descriptive observation produced from only the accepted bars."""

    role: Literal["trend", "range", "continuity"]
    status: Literal["OBSERVED", "INADEQUATE_DATA"]
    facts: tuple[tuple[str, str], ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class OfflineRoleAnalysis:
    """Structured result that has no authority beyond describing supplied history."""

    mode: Literal["OFFLINE_HISTORICAL_DESCRIPTIVE_ANALYSIS_ONLY"]
    symbol: str
    as_of: datetime
    accepted_bar_count: int
    observations: tuple[RoleObservation, ...]
    disagreements: tuple[str, ...]
    evidence_limitations: tuple[str, ...]


def _utc(value: object, label: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise OfflineRoleAnalysisError(f"{label} must be a timezone-aware datetime")
    if value.utcoffset().total_seconds() != 0:
        raise OfflineRoleAnalysisError(f"{label} must use UTC")
    # Canonicalize zero-offset timezone implementations so result equality and
    # serialized evidence do not depend on a caller-supplied tzinfo object.
    return value.astimezone(timezone.utc)


def _number(value: object, label: str) -> Decimal:
    if type(value) is not Decimal or not value.is_finite() or value <= _ZERO:
        raise OfflineRoleAnalysisError(f"{label} must be a finite positive Decimal")
    digits = len(value.as_tuple().digits)
    if digits > _MAX_DECIMAL_DIGITS or abs(value.adjusted()) > _MAX_DECIMAL_DIGITS:
        raise OfflineRoleAnalysisError(f"{label} exceeds numeric bounds")
    return value


def _format(value: Decimal) -> str:
    """Return stable plain Decimal text without context-sensitive rounding."""
    return format(value, "f")


def _percent_change(first: Decimal, last: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = 80
        return (last - first) * _HUNDRED / first


def _validated_bars(bars: tuple[HistoricalNumericBar, ...] | list[HistoricalNumericBar], as_of: datetime) -> tuple[HistoricalNumericBar, ...]:
    # Do not invoke arbitrary iterators: callers must provide a concrete built-in sequence.
    if type(bars) not in (tuple, list):
        raise OfflineRoleAnalysisError("bars must be a built-in tuple or list of HistoricalNumericBar")
    values = tuple(bars)
    if not values or len(values) > _MAX_BARS:
        raise OfflineRoleAnalysisError("bars must contain 1 to 10000 items")
    symbol: str | None = None
    previous_close: datetime | None = None
    normalized: list[HistoricalNumericBar] = []
    for index, bar in enumerate(values):
        if type(bar) is not HistoricalNumericBar:
            raise OfflineRoleAnalysisError(f"bar {index} must be HistoricalNumericBar")
        opened = _utc(bar.open_timestamp, f"bar {index} open_timestamp")
        closed = _utc(bar.close_timestamp, f"bar {index} close_timestamp")
        if opened >= closed:
            raise OfflineRoleAnalysisError(f"bar {index} must close after it opens")
        if closed > as_of:
            raise OfflineRoleAnalysisError(f"bar {index} closes after as_of")
        if type(bar.symbol) is not str or not bar.symbol or len(bar.symbol) > _MAX_SYMBOL_LENGTH or not bar.symbol.isascii() or not bar.symbol.isalnum():
            raise OfflineRoleAnalysisError(f"bar {index} has invalid symbol")
        if symbol is None:
            symbol = bar.symbol
        elif bar.symbol != symbol:
            raise OfflineRoleAnalysisError("bars must have exactly one symbol")
        # Explicit field checks preserve strict types and field-specific errors.
        open_ = _number(bar.open, f"bar {index} open")
        high = _number(bar.high, f"bar {index} high")
        low = _number(bar.low, f"bar {index} low")
        close = _number(bar.close, f"bar {index} close")
        if low > min(open_, close) or high < max(open_, close) or low > high:
            raise OfflineRoleAnalysisError(f"bar {index} violates OHLC bounds")
        if previous_close is not None:
            if opened <= previous_close:
                raise OfflineRoleAnalysisError("bars must be strictly chronological and non-overlapping")
            if opened - previous_close > _MAX_GAP:
                raise OfflineRoleAnalysisError("bar gap exceeds 31 days")
        normalized.append(HistoricalNumericBar(opened, closed, bar.symbol, open_, high, low, close))
        previous_close = closed
    return tuple(normalized)


def _trend(values: tuple[HistoricalNumericBar, ...]) -> RoleObservation:
    if len(values) < 2:
        return RoleObservation("trend", "INADEQUATE_DATA", (), ("At least two closed bars are required to describe a historical close-to-close change.",))
    change = _percent_change(values[0].close, values[-1].close)
    direction = "UP" if change > _ZERO else "DOWN" if change < _ZERO else "FLAT"
    return RoleObservation("trend", "OBSERVED", (("close_change_percent", _format(change)), ("direction", direction)), ())


def _range(values: tuple[HistoricalNumericBar, ...]) -> RoleObservation:
    if len(values) < 2:
        return RoleObservation("range", "INADEQUATE_DATA", (), ("At least two closed bars are required to describe a multi-bar high-low range.",))
    low, high = min(bar.low for bar in values), max(bar.high for bar in values)
    span = _percent_change(low, high)
    return RoleObservation("range", "OBSERVED", (("low", _format(low)), ("high", _format(high)), ("range_percent_of_low", _format(span))), ())


def _continuity(values: tuple[HistoricalNumericBar, ...]) -> RoleObservation:
    if len(values) < 2:
        return RoleObservation("continuity", "INADEQUATE_DATA", (), ("At least two closed bars are required to describe inter-bar gaps.",))
    gaps = [current.open_timestamp - previous.close_timestamp for previous, current in zip(values, values[1:])]
    largest = max(gaps)
    return RoleObservation("continuity", "OBSERVED", (("largest_gap_seconds", str(int(largest.total_seconds()))), ("gap_count", str(len(gaps)))), ())


def _disagreements(values: tuple[HistoricalNumericBar, ...], trend: RoleObservation) -> tuple[str, ...]:
    if trend.status != "OBSERVED" or len(values) < 3:
        return ("No trend comparison is available because the supplied history has fewer than three closed bars.",)
    overall = dict(trend.facts)["direction"]
    recent_change = values[-1].close - values[-2].close
    recent = "UP" if recent_change > _ZERO else "DOWN" if recent_change < _ZERO else "FLAT"
    if recent != overall and recent != "FLAT" and overall != "FLAT":
        return ("Overall close direction and final-bar close direction differ in the supplied history.",)
    return ()


def analyze_historical_bars(bars: tuple[HistoricalNumericBar, ...] | list[HistoricalNumericBar], *, as_of: datetime) -> OfflineRoleAnalysis:
    """Describe validated, closed local bars at an explicit UTC cutoff, without side effects."""
    cutoff = _utc(as_of, "as_of")
    values = _validated_bars(bars, cutoff)
    observations = (_trend(values), _range(values), _continuity(values))
    return OfflineRoleAnalysis(
        "OFFLINE_HISTORICAL_DESCRIPTIVE_ANALYSIS_ONLY", values[0].symbol, cutoff, len(values), observations,
        _disagreements(values, observations[0]),
        (
            "Bars, timestamps, and prices are unverified caller-supplied historical assertions; this module does not establish completeness, authenticity, or suitability.",
            "The as_of cutoff prevents accepted bars from closing after it, but does not prove real-world publication time or bar finality.",
            "Observations are descriptive only, not forecasts, investment advice, performance evidence, or trading recommendations.",
            "No network, files, URLs, model calls, arbitrary code, credentials, orders, live trading, policy, or risk authority are used.",
        ),
    )
