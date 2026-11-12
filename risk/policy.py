"""Independent, deterministic, long-only risk policy gate.

This module is deliberately side-effect free. It neither submits nor queues
orders, obtains prices, reads the system clock, changes state, imports AI code,
or modifies its limits. An adapter must pass verified snapshots and an
explicit ``now`` and must independently execute only approved decisions.

All financial inputs are finite, bounded ``Decimal`` values. Arithmetic runs in
an explicit local Decimal context with traps, so a hostile ambient context or an
unrepresentable intermediate result fails closed rather than changing a result.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import (Decimal, DecimalException, DivisionByZero, Inexact,
                     InvalidOperation, Overflow, Rounded, localcontext)
from typing import Final

BUY: Final[str] = "BUY"
SELL: Final[str] = "SELL"
HOLD: Final[str] = "HOLD"
_ACTIONS: Final[frozenset[str]] = frozenset((BUY, SELL, HOLD))
_ZERO: Final[Decimal] = Decimal("0")
_ONE: Final[Decimal] = Decimal("1")
# Financial values may have at most 28 significant digits and an adjusted
# exponent in [-18, 18]. This permits sub-unit precision through 1e-18 and
# amounts below 1e19 while making all policy arithmetic bounded and auditable.
_MAX_DIGITS: Final[int] = 28
_MIN_ADJUSTED: Final[int] = -18
_MAX_ADJUSTED: Final[int] = 18
_CONTEXT_PRECISION: Final[int] = 56


@dataclass(frozen=True, slots=True)
class RiskLimits:
    """Immutable limits; all financial values must be bounded non-negative Decimal.

    ``max_leverage`` is deliberately capped at one: this policy never permits
    borrowing or leverage. ``max_cash`` is a hard post-trade balance cap.
    """
    max_data_age: timedelta
    max_order_notional: Decimal
    max_cash: Decimal
    max_projected_exposure: Decimal
    min_cash_reserve: Decimal
    max_leverage: Decimal = _ONE


@dataclass(frozen=True, slots=True)
class Position:
    instrument: str
    quantity: Decimal
    mark_price: Decimal


@dataclass(frozen=True, slots=True)
class AccountState:
    as_of: datetime
    cash: Decimal
    equity: Decimal
    position: Position
    reconciled: bool
    trading_enabled: bool
    kill_switch_engaged: bool


@dataclass(frozen=True, slots=True)
class OrderRequest:
    """A requested non-live policy evaluation; no execution capability exists.

    A SELL ``price`` is a limit's minimum execution price, not a maximum. This
    policy therefore rejects SELLs: without an independently enforced maximum
    proceeds/execution-price bound it cannot prove max-cash or max-notional
    controls for every permitted fill.
    """
    action: str
    instrument: str
    quantity: Decimal
    price: Decimal
    local_recommendation: str
    remote_recommendation: str
    emergency_risk_reduction: bool = False


@dataclass(frozen=True, slots=True)
class RiskDecision:
    approved: bool
    action: str
    code: str
    message: str
    projected_cash: Decimal | None = None
    projected_exposure: Decimal | None = None
    projected_equity: Decimal | None = None


def _decision(action: object, code: str, message: str, *, approved: bool = False,
              cash: Decimal | None = None, exposure: Decimal | None = None,
              equity: Decimal | None = None) -> RiskDecision:
    safe_action = action if isinstance(action, str) and action in _ACTIONS else "REJECTED"
    return RiskDecision(approved, safe_action, code, message, cash, exposure, equity)


def _bounded_decimal(value: object) -> bool:
    if not isinstance(value, Decimal) or not value.is_finite():
        return False
    if value.is_zero():
        return True
    digits = len(value.as_tuple().digits)
    return digits <= _MAX_DIGITS and _MIN_ADJUSTED <= value.adjusted() <= _MAX_ADJUSTED


def _nonnegative_decimal(value: object) -> bool:
    return _bounded_decimal(value) and value >= _ZERO


def _aware_time(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _exact(operation):
    """Evaluate bounded Decimal arithmetic independently of ambient context."""
    with localcontext() as context:
        context.prec = _CONTEXT_PRECISION
        context.Emin = _MIN_ADJUSTED
        context.Emax = _MAX_ADJUSTED
        context.clamp = 0
        for signal in (InvalidOperation, DivisionByZero, Overflow, Inexact, Rounded):
            context.traps[signal] = True
        return operation()


def _valid_limits(limits: object) -> bool:
    if not isinstance(limits, RiskLimits) or not isinstance(limits.max_data_age, timedelta):
        return False
    if limits.max_data_age < timedelta(0):
        return False
    values = (limits.max_order_notional, limits.max_cash, limits.max_projected_exposure,
              limits.min_cash_reserve, limits.max_leverage)
    return all(_nonnegative_decimal(value) for value in values) and limits.max_leverage <= _ONE


def _valid_state(state: object) -> bool:
    if not isinstance(state, AccountState) or not isinstance(state.position, Position):
        return False
    position = state.position
    if not (
        _aware_time(state.as_of) and _nonnegative_decimal(state.cash)
        and _bounded_decimal(state.equity) and state.equity > _ZERO
        and isinstance(position.instrument, str) and bool(position.instrument)
        and _nonnegative_decimal(position.quantity)
        and _bounded_decimal(position.mark_price) and position.mark_price > _ZERO
        and state.reconciled is True and isinstance(state.trading_enabled, bool)
        and state.kill_switch_engaged is False
    ):
        return False
    try:
        return state.equity == _exact(lambda: state.cash + position.quantity * position.mark_price)
    except DecimalException:
        return False


def _valid_request(request: object) -> bool:
    if not isinstance(request, OrderRequest):
        return False
    if not all(isinstance(value, str) for value in (
        request.action, request.local_recommendation, request.remote_recommendation,
    )):
        return False
    return (
        request.action in _ACTIONS and isinstance(request.instrument, str) and bool(request.instrument)
        and _nonnegative_decimal(request.quantity) and _nonnegative_decimal(request.price)
        and request.local_recommendation in _ACTIONS and request.remote_recommendation in _ACTIONS
        and type(request.emergency_risk_reduction) is bool
    )


def evaluate(limits: RiskLimits, state: AccountState, request: OrderRequest, *, now: datetime) -> RiskDecision:
    """Evaluate one action without side effects, failing closed on unsafe input."""
    action = request.action if isinstance(request, OrderRequest) else "REJECTED"
    if not _valid_limits(limits):
        return _decision(action, "INVALID_LIMITS", "Risk limits are malformed or outside numeric bounds.")
    if not _aware_time(now):
        return _decision(action, "INVALID_TIME", "Evaluation time must be timezone-aware.")
    if not _valid_state(state):
        return _decision(action, "UNSAFE_STATE", "State is malformed, unreconciled, killed, or numerically unsafe.")
    if not _valid_request(request):
        return _decision(action, "INVALID_REQUEST", "Request is malformed or outside numeric bounds.")

    age = now - state.as_of
    if age < timedelta(0) or age > limits.max_data_age:
        return _decision(action, "STALE_OR_FUTURE_STATE", "State timestamp is stale or future-dated.")
    if request.instrument != state.position.instrument:
        return _decision(action, "INSTRUMENT_MISMATCH", "Request does not match the reconciled position instrument.")
    if request.local_recommendation != request.remote_recommendation:
        return _decision(action, "CONFLICTING_RECOMMENDATIONS", "Independent recommendations conflict.")
    if request.action != request.local_recommendation:
        return _decision(action, "RECOMMENDATION_MISMATCH", "Request action is not the unanimous recommendation.")

    try:
        current_exposure = _exact(lambda: state.position.quantity * state.position.mark_price)
        if request.action == HOLD:
            if request.quantity != _ZERO or request.price != _ZERO or request.emergency_risk_reduction:
                return _decision(action, "INVALID_HOLD", "HOLD requires zero quantity/price and no emergency flag.")
            return _decision(action, "HOLD", "No exposure-changing action requested.", approved=True,
                             cash=state.cash, exposure=current_exposure, equity=state.equity)

        if request.quantity <= _ZERO or request.price <= _ZERO:
            return _decision(action, "NONPOSITIVE_ORDER", "BUY and SELL require positive Decimal quantity and price.")
        notional = _exact(lambda: request.quantity * request.price)
        if not _bounded_decimal(notional) or notional <= _ZERO or notional > limits.max_order_notional:
            return _decision(action, "NOTIONAL_LIMIT", "Order notional is invalid or exceeds its hard cap.")
        if not _bounded_decimal(current_exposure):
            return _decision(action, "UNSAFE_STATE", "Current marked exposure is outside numeric bounds.")

        if state.trading_enabled is not True:
            return _decision(action, "TRADING_DISABLED", "Trading switch is off; no orders are permitted.")
        if request.emergency_risk_reduction and request.action != SELL:
            return _decision(action, "EMERGENCY_MUST_REDUCE_RISK", "Emergency handling may only sell an existing long position.")
        if request.action == SELL:
            if request.quantity > state.position.quantity:
                return _decision(action, "SHORTING_PROHIBITED", "SELL quantity exceeds the known long position.")
            return _decision(action, "SELL_PRICE_UNBOUNDED", "A sell limit is a minimum price and cannot bound maximum proceeds.")

        projected_cash = _exact(lambda: state.cash - notional)
        projected_quantity = _exact(lambda: state.position.quantity + request.quantity)
        projected_exposure = _exact(lambda: projected_quantity * state.position.mark_price)
        projected_equity = _exact(lambda: projected_cash + projected_exposure)
        if not all(_bounded_decimal(value) for value in (projected_cash, projected_quantity,
                                                           projected_exposure, projected_equity)):
            return _decision(action, "INVALID_PROJECTION", "Projected balances are outside numeric bounds.")
        if projected_cash < limits.min_cash_reserve or projected_cash < _ZERO:
            return _decision(action, "NO_BORROWING", "Projected cash breaches reserve or would borrow.")
        if projected_cash > limits.max_cash:
            return _decision(action, "MAX_CASH_LIMIT", "Projected cash exceeds the hard cash cap.")
        if projected_exposure > limits.max_projected_exposure:
            return _decision(action, "EXPOSURE_LIMIT", "Projected marked exposure exceeds the hard cap.")
        if projected_equity <= _ZERO:
            return _decision(action, "NONPOSITIVE_EQUITY", "Projected equity must remain positive.")
        # Cross-multiply instead of dividing: it is an exact comparison and
        # cannot turn a recurring Decimal ratio into an ambient-context result.
        maximum_exposure = _exact(lambda: limits.max_leverage * projected_equity)
        if not _bounded_decimal(maximum_exposure) or projected_exposure > maximum_exposure:
            return _decision(action, "LEVERAGE_PROHIBITED", "Projected leverage exceeds the no-leverage policy.")
    except DecimalException:
        return _decision(action, "NUMERIC_SAFETY", "Decimal arithmetic was inexact, rounded, or out of range.")

    return _decision(action, "APPROVED", "Action passes deterministic long-only risk policy.", approved=True,
                     cash=projected_cash, exposure=projected_exposure, equity=projected_equity)
