"""Adversarial tests for the planning-only paper order boundary."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import unittest

from control import (CanonicalCommand, ControlPolicy, MarketMark, PaperOrderBoundary)
from reconciliation import CashSnapshot, PositionSnapshot, ReconciliationPolicy, SnapshotMetadata, TradingSnapshot
from risk import RiskLimits

D = Decimal
NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)
POLICY = ControlPolicy("paper-account", ReconciliationPolicy(timedelta(seconds=60), timedelta(seconds=5)),
    RiskLimits(timedelta(seconds=60), D("500"), D("2000"), D("1500"), D("100")), timedelta(seconds=60), timedelta(seconds=5))
COMMAND = CanonicalCommand("BUY", "ASAI", D("1"), D("100"), "limit", "BUY", "BUY")

def evidence():
    snapshot = TradingSnapshot(SnapshotMetadata("paper-account", "paper", NOW - timedelta(seconds=2), True),
        CashSnapshot(D("1000"), "USD"), (PositionSnapshot("ASAI", D("2")),), ())
    return snapshot, snapshot, MarketMark("ASAI", D("100"), NOW - timedelta(seconds=2))

def decide(boundary, request_id="request-1", **changes):
    broker, internal, mark = evidence()
    values = dict(request_id=request_id, client_order_id="client-1", policy=POLICY, command=COMMAND,
        broker=broker, internal=internal, mark=mark, latch_engaged=False, trading_disabled=False, now=NOW)
    values.update(changes)
    return boundary.decide(**values)

class PaperOrderBoundaryTests(unittest.TestCase):
    def test_decision_binds_identifiers_and_preflight_fingerprint(self):
        decision = decide(PaperOrderBoundary())
        self.assertEqual(decision.account_id, "paper-account")
        self.assertEqual(decision.request_id, "request-1")
        self.assertRegex(decision.binding, r"^[0-9a-f]{64}$")
        self.assertEqual(decision.expires_at - decision.decided_at, timedelta(seconds=30))

    def test_failed_controls_consume_id_and_never_create_dispatch_capability(self):
        boundary = PaperOrderBoundary()
        with self.assertRaises(PermissionError):
            decide(boundary, latch_engaged=True)
        with self.assertRaises(ValueError):
            decide(boundary)
        decision = decide(PaperOrderBoundary())
        with self.assertRaises(PermissionError):
            boundary.dispatch(decision, now=NOW)

    def test_concurrent_same_request_has_exactly_one_decision(self):
        boundary = PaperOrderBoundary()
        def invoke(_):
            try:
                return decide(boundary, "concurrent-request")
            except Exception as exc:
                return exc
        with ThreadPoolExecutor(max_workers=16) as pool:
            outcomes = list(pool.map(invoke, range(32)))
        self.assertEqual(sum(not isinstance(item, Exception) for item in outcomes), 1)
        self.assertEqual(sum(isinstance(item, ValueError) for item in outcomes), 31)

    def test_changed_evidence_cannot_reuse_a_request(self):
        boundary = PaperOrderBoundary()
        decide(boundary, "bound-request")
        broker, internal, mark = evidence()
        with self.assertRaises(ValueError):
            boundary.decide(request_id="bound-request", client_order_id="another-client", policy=POLICY,
                command=COMMAND, broker=broker, internal=internal,
                mark=MarketMark("ASAI", D("101"), NOW - timedelta(seconds=2)),
                latch_engaged=False, trading_disabled=False, now=NOW)

if __name__ == "__main__":
    unittest.main()
