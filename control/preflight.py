"""Offline paper-control preflight diagnostic, never order authorization.

This side-effect-free module combines caller-provided evidence only to produce a
diagnostic. ``passed`` never authorizes, creates, or enables an order. All
financial arithmetic uses a fixed, trapped Decimal context, independent of any
ambient process context.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import (Decimal, DecimalException, DivisionByZero, Inexact,
                     InvalidOperation, Overflow, Rounded, localcontext)
from hashlib import sha256
import json

from reconciliation import ReconciliationPolicy, TradingSnapshot, reconcile
from risk import AccountState, OrderRequest, Position, RiskLimits, evaluate


@dataclass(frozen=True, slots=True)
class ControlPolicy:
    expected_account_id: str
    reconciliation_policy: ReconciliationPolicy
    risk_limits: RiskLimits
    max_mark_age: timedelta
    max_mark_snapshot_skew: timedelta


@dataclass(frozen=True, slots=True)
class CanonicalCommand:
    """Data-only limit instruction candidate; it has no executable fields."""
    action: str
    instrument: str
    quantity: Decimal
    limit_price: Decimal
    order_type: str
    local_recommendation: str
    remote_recommendation: str
    emergency_risk_reduction: bool = False


@dataclass(frozen=True, slots=True)
class MarketMark:
    instrument: str
    price: Decimal
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class PreflightDiagnostic:
    passed: bool
    reason: str
    fingerprint: str | None = None


_ZERO = Decimal("0")
_ACTIONS = frozenset(("BUY", "SELL"))
_MAX_DIGITS = 28
_MIN_ADJUSTED = -18
_MAX_ADJUSTED = 18
_CONTEXT_PRECISION = 56


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip() and all(
        char.isprintable() and not char.isspace() for char in value
    )


def _decimal(value: object, *, positive: bool = False) -> bool:
    if not isinstance(value, Decimal) or not value.is_finite():
        return False
    if not value.is_zero() and (len(value.as_tuple().digits) > _MAX_DIGITS
                                or not _MIN_ADJUSTED <= value.adjusted() <= _MAX_ADJUSTED):
        return False
    return value > _ZERO if positive else value >= _ZERO


def _exact(operation):
    with localcontext() as context:
        context.prec = _CONTEXT_PRECISION
        context.Emin = _MIN_ADJUSTED
        context.Emax = _MAX_ADJUSTED
        context.clamp = 0
        for signal in (InvalidOperation, DivisionByZero, Overflow, Inexact, Rounded):
            context.traps[signal] = True
        return operation()


def _deny(reason: str) -> PreflightDiagnostic:
    return PreflightDiagnostic(False, reason, None)


def _utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_decimal(value: Decimal) -> str:
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered if rendered not in ("", "-0") else "0"


def _duration(value: timedelta) -> str:
    """Exact canonical timedelta representation, including subsecond values."""
    return str((value.days, value.seconds, value.microseconds))


def _policy_document(policy: ControlPolicy) -> dict[str, object]:
    recon = policy.reconciliation_policy
    risk = policy.risk_limits
    return {
        "expected_account_id": policy.expected_account_id,
        "reconciliation": {"max_evidence_age": _duration(recon.max_evidence_age),
                             "max_snapshot_skew": _duration(recon.max_snapshot_skew)},
        "risk": {"max_data_age": _duration(risk.max_data_age),
                 "max_order_notional": _canonical_decimal(risk.max_order_notional),
                 "max_cash": _canonical_decimal(risk.max_cash),
                 "max_projected_exposure": _canonical_decimal(risk.max_projected_exposure),
                 "min_cash_reserve": _canonical_decimal(risk.min_cash_reserve),
                 "max_leverage": _canonical_decimal(risk.max_leverage)},
        "max_mark_age": _duration(policy.max_mark_age),
        "max_mark_snapshot_skew": _duration(policy.max_mark_snapshot_skew),
    }


def _fingerprint(policy: ControlPolicy, command: CanonicalCommand, broker: TradingSnapshot,
                 internal: TradingSnapshot, mark: MarketMark, now: datetime) -> str:
    """Hash all accepted policy, command, and evidence fields as canonical JSON."""
    def snapshot(value: TradingSnapshot) -> dict[str, object]:
        return {
            "account": value.metadata.account_id, "environment": value.metadata.environment,
            "as_of": _utc(value.metadata.as_of), "cash": _canonical_decimal(value.cash.available_cash),
            "currency": value.cash.currency,
            "positions": sorted((p.instrument, _canonical_decimal(p.quantity)) for p in value.positions),
            "open_orders": sorted((o.broker_order_id, o.client_order_id, o.status, o.instrument,
                                    o.side, _canonical_decimal(o.quantity)) for o in value.open_orders),
        }
    document = {
        "control_policy": _policy_document(policy),
        "command": {"action": command.action, "instrument": command.instrument,
                    "quantity": _canonical_decimal(command.quantity),
                    "limit_price": _canonical_decimal(command.limit_price), "order_type": command.order_type,
                    "local_recommendation": command.local_recommendation,
                    "remote_recommendation": command.remote_recommendation,
                    "emergency_risk_reduction": command.emergency_risk_reduction},
        "broker": snapshot(broker), "internal": snapshot(internal),
        "mark": {"instrument": mark.instrument, "price": _canonical_decimal(mark.price),
                 "observed_at": _utc(mark.observed_at)}, "evaluated_at": _utc(now),
    }
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return sha256(encoded).hexdigest()


def _valid_policy(policy: object) -> bool:
    return (
        isinstance(policy, ControlPolicy) and _text(policy.expected_account_id)
        and isinstance(policy.reconciliation_policy, ReconciliationPolicy)
        and isinstance(policy.risk_limits, RiskLimits)
        and isinstance(policy.max_mark_age, timedelta) and policy.max_mark_age >= timedelta(0)
        and isinstance(policy.max_mark_snapshot_skew, timedelta) and policy.max_mark_snapshot_skew >= timedelta(0)
    )


def _valid_command(command: object) -> bool:
    return (
        isinstance(command, CanonicalCommand) and isinstance(command.action, str) and command.action in _ACTIONS
        and _text(command.instrument) and _decimal(command.quantity, positive=True)
        and _decimal(command.limit_price, positive=True) and command.order_type == "limit"
        and isinstance(command.local_recommendation, str) and command.local_recommendation in _ACTIONS
        and isinstance(command.remote_recommendation, str) and command.remote_recommendation in _ACTIONS
        and type(command.emergency_risk_reduction) is bool
    )


def _valid_mark(mark: object) -> bool:
    return isinstance(mark, MarketMark) and _text(mark.instrument) and _decimal(mark.price, positive=True) and _aware(mark.observed_at)


def preflight(policy: ControlPolicy, command: CanonicalCommand, broker: TradingSnapshot,
              internal: TradingSnapshot, mark: MarketMark, *, latch_engaged: bool,
              trading_disabled: bool, now: datetime) -> PreflightDiagnostic:
    """Return an offline immutable diagnostic; no outcome authorizes an order."""
    if not _valid_policy(policy):
        return _deny("INVALID_CONTROL_POLICY")
    if not _aware(now):
        return _deny("INVALID_EVALUATION_TIME")
    if type(latch_engaged) is not bool or type(trading_disabled) is not bool:
        return _deny("INVALID_CONTROL_FLAGS")
    if latch_engaged:
        return _deny("KILL_LATCH_ENGAGED")
    if trading_disabled:
        return _deny("TRADING_DISABLED")
    if not _valid_command(command):
        return _deny("INVALID_COMMAND")
    if not _valid_mark(mark):
        return _deny("INVALID_MARK")

    result = reconcile(policy.reconciliation_policy, broker, internal, now=now)
    if not result.clear:
        return _deny("RECONCILIATION_" + result.reasons[0])
    assert isinstance(broker, TradingSnapshot) and isinstance(internal, TradingSnapshot)
    metadata = broker.metadata
    if metadata.environment != "paper":
        return _deny("ENVIRONMENT_NOT_PAPER")
    if metadata.account_id != policy.expected_account_id:
        return _deny("UNEXPECTED_ACCOUNT")
    if broker.cash.currency != "USD":
        return _deny("CURRENCY_NOT_USD")
    if broker.open_orders or internal.open_orders:
        return _deny("OPEN_ORDERS_PRESENT")
    if len(broker.positions) > 1:
        return _deny("MULTIPLE_POSITIONS")
    quantity = _ZERO
    if broker.positions:
        position = broker.positions[0]
        if position.instrument != command.instrument:
            return _deny("POSITION_INSTRUMENT_MISMATCH")
        quantity = position.quantity
    if mark.instrument != command.instrument:
        return _deny("MARK_INSTRUMENT_MISMATCH")
    mark_age = now - mark.observed_at
    if mark_age < timedelta(0):
        return _deny("FUTURE_MARK")
    if mark_age > policy.max_mark_age:
        return _deny("STALE_MARK")
    if (abs(mark.observed_at - broker.metadata.as_of) > policy.max_mark_snapshot_skew
            or abs(mark.observed_at - internal.metadata.as_of) > policy.max_mark_snapshot_skew):
        return _deny("MARK_SNAPSHOT_SKEW")

    try:
        equity = _exact(lambda: broker.cash.available_cash + quantity * mark.price)
    except DecimalException:
        return _deny("NUMERIC_SAFETY")
    state = AccountState(mark.observed_at, broker.cash.available_cash, equity,
                         Position(command.instrument, quantity, mark.price), True, True, False)
    request = OrderRequest(command.action, command.instrument, command.quantity, command.limit_price,
                           command.local_recommendation, command.remote_recommendation,
                           command.emergency_risk_reduction)
    decision = evaluate(policy.risk_limits, state, request, now=now)
    if not decision.approved:
        return _deny("RISK_" + decision.code)
    return PreflightDiagnostic(True, "PREFLIGHT_PASSED_NOT_AUTHORIZATION",
                               _fingerprint(policy, command, broker, internal, mark, now))
