"""Adversarial tests for the pure, fail-closed reconciliation checker."""
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import unittest

from reconciliation import (
    CashSnapshot, OrderSnapshot, PositionSnapshot, ReconciliationPolicy,
    SnapshotMetadata, TradingSnapshot, reconcile,
)

D = Decimal
NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)
POLICY = ReconciliationPolicy(timedelta(seconds=60), timedelta(seconds=5))


def snapshot(**changes):
    data = dict(
        metadata=SnapshotMetadata("paper-account", "paper", NOW - timedelta(seconds=2), True),
        cash=CashSnapshot(D("1000.00"), "USD"),
        positions=(PositionSnapshot("ASAI", D("2")),),
        open_orders=(OrderSnapshot("broker-1", "client-1", "accepted", "ASAI", "buy", D("2")),),
    )
    data.update(changes)
    return TradingSnapshot(**data)


class ReconciliationTests(unittest.TestCase):
    def rejected(self, result, *codes):
        self.assertFalse(result.clear)
        self.assertEqual(codes, result.reasons)

    def test_exact_complete_same_account_environment_reconciles(self):
        result = reconcile(POLICY, snapshot(), snapshot(), now=NOW)
        self.assertTrue(result.clear)
        self.assertEqual(("RECONCILED",), result.reasons)

    def test_exact_decimal_comparison_never_uses_a_tolerance(self):
        self.rejected(reconcile(POLICY, snapshot(), snapshot(cash=CashSnapshot(D("1000.0001"), "USD")), now=NOW),
                      "CASH_MISMATCH")
        self.rejected(reconcile(POLICY, snapshot(), snapshot(positions=(PositionSnapshot("ASAI", D("2.0001")),)), now=NOW),
                      "POSITION_MISMATCH")

    def test_empty_flat_books_are_valid_but_missing_values_cannot_default_to_zero(self):
        flat = snapshot(positions=(), open_orders=())
        self.assertTrue(reconcile(POLICY, flat, flat, now=NOW).clear)
        self.rejected(reconcile(POLICY, snapshot(cash=CashSnapshot(D("0"), "USD")), snapshot(), now=NOW), "CASH_MISMATCH")
        self.rejected(reconcile(POLICY, snapshot(positions=(PositionSnapshot("ASAI", D("0")),)), snapshot(), now=NOW),
                      "BROKER_POSITION_NONPOSITIVE")

    def test_rejects_negative_nonfinite_and_non_decimal_money_or_quantity(self):
        cases = (
            (snapshot(cash=CashSnapshot(D("-1"), "USD")), "BROKER_CASH_NEGATIVE"),
            (snapshot(cash=CashSnapshot(D("NaN"), "USD")), "BROKER_CASH_MALFORMED"),
            (snapshot(cash=CashSnapshot(D("Infinity"), "USD")), "BROKER_CASH_MALFORMED"),
            (snapshot(cash=CashSnapshot(1, "USD")), "BROKER_CASH_MALFORMED"),
            (snapshot(positions=(PositionSnapshot("ASAI", D("-1")),)), "BROKER_POSITION_NONPOSITIVE"),
            (snapshot(positions=(PositionSnapshot("ASAI", D("NaN")),)), "BROKER_POSITION_NONFINITE"),
            (snapshot(positions=(PositionSnapshot("ASAI", 1.0),)), "BROKER_POSITION_NONFINITE"),
        )
        for bad, code in cases:
            with self.subTest(code=code):
                self.rejected(reconcile(POLICY, bad, snapshot(), now=NOW), code)

    def test_rejects_partial_or_malformed_snapshots_before_comparison(self):
        self.rejected(reconcile(POLICY, snapshot(metadata=SnapshotMetadata("a", "paper", NOW, False)), snapshot(), now=NOW),
                      "BROKER_SNAPSHOT_PARTIAL")
        self.rejected(reconcile(POLICY, snapshot(positions=[]), snapshot(), now=NOW), "BROKER_COLLECTION_MALFORMED")
        self.rejected(reconcile(POLICY, object(), snapshot(), now=NOW), "BROKER_SNAPSHOT_MALFORMED")
        self.rejected(reconcile(POLICY, snapshot(metadata=SnapshotMetadata("", "paper", NOW, True)), snapshot(), now=NOW),
                      "BROKER_IDENTITY_MALFORMED")

    def test_rejects_account_and_environment_crossing(self):
        self.rejected(reconcile(POLICY, snapshot(), snapshot(metadata=SnapshotMetadata("other", "paper", NOW, True)), now=NOW),
                      "ACCOUNT_MISMATCH")
        self.rejected(reconcile(POLICY, snapshot(), snapshot(metadata=SnapshotMetadata("paper-account", "live", NOW, True)), now=NOW),
                      "ENVIRONMENT_MISMATCH")

    def test_rejects_naive_future_stale_and_excessively_skewed_evidence(self):
        self.rejected(reconcile(POLICY, snapshot(metadata=SnapshotMetadata("a", "paper", NOW.replace(tzinfo=None), True)), snapshot(), now=NOW),
                      "BROKER_TIMESTAMP_MALFORMED")
        self.rejected(reconcile(POLICY, snapshot(metadata=SnapshotMetadata("paper-account", "paper", NOW + timedelta(microseconds=1), True)), snapshot(), now=NOW),
                      "FUTURE_EVIDENCE")
        self.rejected(reconcile(POLICY, snapshot(metadata=SnapshotMetadata("paper-account", "paper", NOW - timedelta(seconds=61), True)), snapshot(), now=NOW),
                      "STALE_EVIDENCE")
        self.rejected(reconcile(POLICY, snapshot(metadata=SnapshotMetadata("a", "paper", NOW - timedelta(seconds=10), True)), snapshot(metadata=SnapshotMetadata("a", "paper", NOW, True)), now=NOW),
                      "SNAPSHOT_TIME_SKEW")
        self.rejected(reconcile(POLICY, snapshot(), snapshot(), now=NOW.replace(tzinfo=None)), "INVALID_EVALUATION_TIME")

    def test_duplicate_position_symbols_and_order_identities_fail_closed(self):
        duplicate_positions = snapshot(positions=(PositionSnapshot("ASAI", D("1")), PositionSnapshot("ASAI", D("1"))))
        self.rejected(reconcile(POLICY, duplicate_positions, snapshot(), now=NOW), "BROKER_POSITION_DUPLICATE")
        duplicate_broker = snapshot(open_orders=(OrderSnapshot("b", "c1", "accepted", "ASAI", "buy", D("2")), OrderSnapshot("b", "c2", "accepted", "ASAI", "buy", D("2"))))
        self.rejected(reconcile(POLICY, duplicate_broker, snapshot(), now=NOW), "BROKER_ORDER_DUPLICATE")
        duplicate_client = snapshot(open_orders=(OrderSnapshot("b1", "c", "accepted", "ASAI", "buy", D("2")), OrderSnapshot("b2", "c", "accepted", "ASAI", "buy", D("2"))))
        self.rejected(reconcile(POLICY, duplicate_client, snapshot(), now=NOW), "BROKER_ORDER_DUPLICATE")

    def test_unknown_terminal_or_missing_open_order_outcomes_are_rejected(self):
        for status in ("filled", "canceled", "rejected", "mystery", ""):
            with self.subTest(status=status):
                bad = snapshot(open_orders=(OrderSnapshot("b", "c", status, "ASAI", "buy", D("2")),))
                self.rejected(reconcile(POLICY, bad, snapshot(), now=NOW), "BROKER_ORDER_STATUS_UNKNOWN")
        self.rejected(reconcile(POLICY, snapshot(open_orders=(OrderSnapshot("", "c", "accepted", "ASAI", "buy", D("2")),)), snapshot(), now=NOW),
                      "BROKER_ORDER_IDENTITY_MALFORMED")

    def test_order_identity_and_status_both_must_match_exactly(self):
        self.rejected(reconcile(POLICY, snapshot(), snapshot(open_orders=(OrderSnapshot("other", "client-1", "accepted", "ASAI", "buy", D("2")),)), now=NOW),
                      "OPEN_ORDER_MISMATCH")
        self.rejected(reconcile(POLICY, snapshot(), snapshot(open_orders=(OrderSnapshot("broker-1", "client-1", "pending_cancel", "ASAI", "buy", D("2")),)), now=NOW),
                      "OPEN_ORDER_MISMATCH")
        self.rejected(reconcile(POLICY, snapshot(), snapshot(open_orders=()), now=NOW), "OPEN_ORDER_MISMATCH")

    def test_invalid_policy_and_multiple_source_failures_are_deterministic(self):
        self.rejected(reconcile(ReconciliationPolicy(timedelta(seconds=-1), timedelta(0)), snapshot(), snapshot(), now=NOW),
                      "INVALID_POLICY")
        broker = snapshot(cash=CashSnapshot(D("NaN"), "USD"))
        internal = snapshot(metadata=SnapshotMetadata("a", "paper", NOW, False))
        self.rejected(reconcile(POLICY, broker, internal, now=NOW), "BROKER_CASH_MALFORMED", "INTERNAL_SNAPSHOT_PARTIAL")

    def test_cash_currency_is_required_and_must_match(self):
        self.rejected(reconcile(POLICY, snapshot(cash=CashSnapshot(D("1000"), "usd")), snapshot(), now=NOW),
                      "BROKER_CASH_MALFORMED")
        self.rejected(reconcile(POLICY, snapshot(), snapshot(cash=CashSnapshot(D("1000.00"), "ZAR")), now=NOW),
                      "CASH_MISMATCH")

    def test_order_exposure_terms_must_be_valid_and_match(self):
        for order, code in (
            (OrderSnapshot("b", "c", "accepted", "", "buy", D("1")), "BROKER_ORDER_INSTRUMENT_MALFORMED"),
            (OrderSnapshot("b", "c", "accepted", "ASAI", "hold", D("1")), "BROKER_ORDER_SIDE_MALFORMED"),
            (OrderSnapshot("b", "c", "accepted", "ASAI", "buy", D("0")), "BROKER_ORDER_QUANTITY_MALFORMED"),
            (OrderSnapshot("b", "c", [], "ASAI", "buy", D("1")), "BROKER_ORDER_STATUS_UNKNOWN"),
        ):
            with self.subTest(code=code):
                self.rejected(reconcile(POLICY, snapshot(open_orders=(order,)), snapshot(), now=NOW), code)
        self.rejected(reconcile(POLICY, snapshot(), snapshot(open_orders=(
            OrderSnapshot("broker-1", "client-1", "accepted", "OTHER", "buy", D("2")),)), now=NOW),
                      "OPEN_ORDER_MISMATCH")
        self.rejected(reconcile(POLICY, snapshot(), snapshot(open_orders=(
            OrderSnapshot("broker-1", "client-1", "accepted", "ASAI", "sell", D("2")),)), now=NOW),
                      "OPEN_ORDER_MISMATCH")
        self.rejected(reconcile(POLICY, snapshot(), snapshot(open_orders=(
            OrderSnapshot("broker-1", "client-1", "accepted", "ASAI", "buy", D("3")),)), now=NOW),
                      "OPEN_ORDER_MISMATCH")

    def test_whitespace_or_control_text_cannot_create_identity_or_symbol_collisions(self):
        self.rejected(reconcile(POLICY, snapshot(positions=(PositionSnapshot(" ASAI", D("2")),)), snapshot(), now=NOW),
                      "BROKER_POSITION_MALFORMED")
        self.rejected(reconcile(POLICY, snapshot(open_orders=(
            OrderSnapshot("broker-1 ", "client-1", "accepted", "ASAI", "buy", D("2")),)), snapshot(), now=NOW),
                      "BROKER_ORDER_IDENTITY_MALFORMED")
        self.rejected(reconcile(POLICY, snapshot(metadata=SnapshotMetadata("paper-account\n", "paper", NOW, True)), snapshot(), now=NOW),
                      "BROKER_IDENTITY_MALFORMED")

    def test_records_are_immutable_and_checker_never_mutates_input(self):
        before = snapshot()
        with self.assertRaises(FrozenInstanceError):
            before.cash.available_cash = D("0")
        result = reconcile(POLICY, before, before, now=NOW)
        self.assertTrue(result.clear)
        self.assertEqual(D("1000.00"), before.cash.available_cash)

    def test_source_is_pure_and_has_no_network_or_automatic_action_imports(self):
        source = (Path(__file__).parents[1] / "reconciliation" / "checker.py").read_text(encoding="utf-8")
        for forbidden in ("socket", "requests", "urllib", "http", "sqlite", "subprocess", "open(", "datetime.now", "eval(", "exec("):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
