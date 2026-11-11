"""Deterministic, side-effect-free reconciliation of broker and internal snapshots.

The caller supplies both complete snapshots and an explicit evaluation time.
Values are compared exactly: this module deliberately has no numeric tolerance.
It is a checker, not an execution control, and MUST NOT be used as the sole
trading authorization.  It does not perform networking, persistence, automatic
actions, logging, or clock reads.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Final

OPEN_ORDER_STATUSES: Final[frozenset[str]] = frozenset((
    "new", "accepted", "pending_new", "accepted_for_bidding", "partially_filled",
    "pending_cancel", "pending_replace", "stopped", "suspended",
))
OPEN_ORDER_SIDES: Final[frozenset[str]] = frozenset(("buy", "sell"))
_ZERO: Final[Decimal] = Decimal("0")
_MAX_DIGITS: Final[int] = 28
_MIN_ADJUSTED: Final[int] = -18
_MAX_ADJUSTED: Final[int] = 18


@dataclass(frozen=True, slots=True)
class ReconciliationPolicy:
    """Freshness limits, supplied explicitly and validated fail-closed."""

    max_evidence_age: timedelta
    max_snapshot_skew: timedelta


@dataclass(frozen=True, slots=True)
class SnapshotMetadata:
    """Identity and provenance completeness for one atomic source snapshot."""

    account_id: str
    environment: str
    as_of: datetime
    complete: bool


@dataclass(frozen=True, slots=True)
class CashSnapshot:
    """Explicit cash balance and currency; neither may be inferred."""

    available_cash: Decimal
    currency: str


@dataclass(frozen=True, slots=True)
class PositionSnapshot:
    """A non-zero long position. Flat books are represented by an empty tuple."""

    instrument: str
    quantity: Decimal


@dataclass(frozen=True, slots=True)
class OrderSnapshot:
    """An open order with identities and exposure-bearing terms."""

    broker_order_id: str
    client_order_id: str
    status: str
    instrument: str
    side: str
    quantity: Decimal


@dataclass(frozen=True, slots=True)
class TradingSnapshot:
    """A complete, point-in-time account snapshot from one source."""

    metadata: SnapshotMetadata
    cash: CashSnapshot
    positions: tuple[PositionSnapshot, ...]
    open_orders: tuple[OrderSnapshot, ...]


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    """Immutable checker outcome; ``clear`` never authorizes an order by itself."""

    clear: bool
    reasons: tuple[str, ...]


def _finite_decimal(value: object) -> bool:
    """Accept finite, deliberately bounded financial Decimals only."""
    if not isinstance(value, Decimal) or not value.is_finite():
        return False
    if value.is_zero():
        return True
    return (len(value.as_tuple().digits) <= _MAX_DIGITS
            and _MIN_ADJUSTED <= value.adjusted() <= _MAX_ADJUSTED)


def _aware_time(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _nonempty_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _canonical_text(value: object) -> bool:
    """Accept opaque identifiers only when they cannot hide whitespace/control collisions."""
    return _nonempty_text(value) and value == value.strip() and not any(char.isspace() or not char.isprintable() for char in value)


def _currency_code(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 3
        and value.isascii()
        and value.isalpha()
        and value.isupper()
    )


def _valid_policy(policy: object) -> bool:
    return (
        isinstance(policy, ReconciliationPolicy)
        and isinstance(policy.max_evidence_age, timedelta)
        and isinstance(policy.max_snapshot_skew, timedelta)
        and timedelta(0) <= policy.max_evidence_age
        and timedelta(0) <= policy.max_snapshot_skew
    )


def _validate_snapshot(snapshot: object, source: str) -> tuple[str, ...]:
    """Return stable, non-sensitive validation codes for one source."""
    prefix = source.upper()
    if not isinstance(snapshot, TradingSnapshot):
        return (prefix + "_SNAPSHOT_MALFORMED",)
    metadata = snapshot.metadata
    if not isinstance(metadata, SnapshotMetadata):
        return (prefix + "_METADATA_MALFORMED",)
    if not _canonical_text(metadata.account_id) or not _canonical_text(metadata.environment):
        return (prefix + "_IDENTITY_MALFORMED",)
    if not _aware_time(metadata.as_of):
        return (prefix + "_TIMESTAMP_MALFORMED",)
    if metadata.complete is not True:
        return (prefix + "_SNAPSHOT_PARTIAL",)
    if (
        not isinstance(snapshot.cash, CashSnapshot)
        or not _finite_decimal(snapshot.cash.available_cash)
        or not _currency_code(snapshot.cash.currency)
    ):
        return (prefix + "_CASH_MALFORMED",)
    if snapshot.cash.available_cash < _ZERO:
        return (prefix + "_CASH_NEGATIVE",)
    if not isinstance(snapshot.positions, tuple) or not isinstance(snapshot.open_orders, tuple):
        return (prefix + "_COLLECTION_MALFORMED",)

    seen_instruments: set[str] = set()
    for position in snapshot.positions:
        if not isinstance(position, PositionSnapshot) or not _canonical_text(position.instrument):
            return (prefix + "_POSITION_MALFORMED",)
        if not _finite_decimal(position.quantity):
            return (prefix + "_POSITION_NONFINITE",)
        if position.quantity <= _ZERO:
            return (prefix + "_POSITION_NONPOSITIVE",)
        if position.instrument in seen_instruments:
            return (prefix + "_POSITION_DUPLICATE",)
        seen_instruments.add(position.instrument)

    broker_ids: set[str] = set()
    client_ids: set[str] = set()
    for order in snapshot.open_orders:
        if not isinstance(order, OrderSnapshot):
            return (prefix + "_ORDER_MALFORMED",)
        if not _canonical_text(order.broker_order_id) or not _canonical_text(order.client_order_id):
            return (prefix + "_ORDER_IDENTITY_MALFORMED",)
        if not isinstance(order.status, str) or order.status not in OPEN_ORDER_STATUSES:
            return (prefix + "_ORDER_STATUS_UNKNOWN",)
        if not _canonical_text(order.instrument):
            return (prefix + "_ORDER_INSTRUMENT_MALFORMED",)
        if not isinstance(order.side, str) or order.side not in OPEN_ORDER_SIDES:
            return (prefix + "_ORDER_SIDE_MALFORMED",)
        if not _finite_decimal(order.quantity) or order.quantity <= _ZERO:
            return (prefix + "_ORDER_QUANTITY_MALFORMED",)
        if order.broker_order_id in broker_ids or order.client_order_id in client_ids:
            return (prefix + "_ORDER_DUPLICATE",)
        broker_ids.add(order.broker_order_id)
        client_ids.add(order.client_order_id)
    return ()


def _positions(snapshot: TradingSnapshot) -> dict[str, Decimal]:
    return {position.instrument: position.quantity for position in snapshot.positions}


def _orders(snapshot: TradingSnapshot) -> dict[tuple[str, str], tuple[str, str, str, Decimal]]:
    return {
        (order.broker_order_id, order.client_order_id): (
            order.status, order.instrument, order.side, order.quantity,
        )
        for order in snapshot.open_orders
    }


def reconcile(
    policy: ReconciliationPolicy,
    broker: TradingSnapshot,
    internal: TradingSnapshot,
    *,
    now: datetime,
) -> ReconciliationResult:
    """Compare complete broker and internal evidence, failing closed by default.

    The result is clear only when source identities, timestamps, cash, every
    position, and every open-order identity/status agree exactly.  Inputs are
    never mutated. Reasons are stable codes and intentionally contain no input
    values, identifiers, or credentials.
    """
    if not _valid_policy(policy):
        return ReconciliationResult(False, ("INVALID_POLICY",))
    if not _aware_time(now):
        return ReconciliationResult(False, ("INVALID_EVALUATION_TIME",))

    reasons = list(_validate_snapshot(broker, "broker"))
    reasons.extend(_validate_snapshot(internal, "internal"))
    if reasons:
        return ReconciliationResult(False, tuple(reasons))

    # Type narrowing follows complete structural validation above.
    assert isinstance(broker, TradingSnapshot) and isinstance(internal, TradingSnapshot)
    broker_meta, internal_meta = broker.metadata, internal.metadata
    if broker_meta.account_id != internal_meta.account_id:
        return ReconciliationResult(False, ("ACCOUNT_MISMATCH",))
    if broker_meta.environment != internal_meta.environment:
        return ReconciliationResult(False, ("ENVIRONMENT_MISMATCH",))

    broker_age = now - broker_meta.as_of
    internal_age = now - internal_meta.as_of
    if broker_age < timedelta(0) or internal_age < timedelta(0):
        return ReconciliationResult(False, ("FUTURE_EVIDENCE",))
    if broker_age > policy.max_evidence_age or internal_age > policy.max_evidence_age:
        return ReconciliationResult(False, ("STALE_EVIDENCE",))
    if abs(broker_meta.as_of - internal_meta.as_of) > policy.max_snapshot_skew:
        return ReconciliationResult(False, ("SNAPSHOT_TIME_SKEW",))

    if (
        broker.cash.currency != internal.cash.currency
        or broker.cash.available_cash != internal.cash.available_cash
    ):
        return ReconciliationResult(False, ("CASH_MISMATCH",))
    if _positions(broker) != _positions(internal):
        return ReconciliationResult(False, ("POSITION_MISMATCH",))
    if _orders(broker) != _orders(internal):
        return ReconciliationResult(False, ("OPEN_ORDER_MISMATCH",))
    return ReconciliationResult(True, ("RECONCILED",))
