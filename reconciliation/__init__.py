"""Pure, fail-closed broker/internal snapshot reconciliation.

This checker compares already-obtained snapshots only.  It performs no networking,
persistence, clock reads, or trading action, and it MUST NOT be used as the sole
authorization to trade.  A separately reviewed control boundary must bind a
fresh clear result to any paper or live execution decision.
"""
from .checker import (
    OPEN_ORDER_STATUSES,
    CashSnapshot,
    OrderSnapshot,
    PositionSnapshot,
    ReconciliationPolicy,
    ReconciliationResult,
    SnapshotMetadata,
    TradingSnapshot,
    reconcile,
)

__all__ = [
    "OPEN_ORDER_STATUSES", "CashSnapshot", "OrderSnapshot", "PositionSnapshot",
    "ReconciliationPolicy", "ReconciliationResult", "SnapshotMetadata",
    "TradingSnapshot", "reconcile",
]
