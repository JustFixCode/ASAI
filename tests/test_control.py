"""Adversarial tests for the offline, non-authorizing paper control preflight."""
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN, localcontext
from pathlib import Path
import unittest

from control import CanonicalCommand, ControlPolicy, MarketMark, preflight
from reconciliation import (CashSnapshot, OrderSnapshot, PositionSnapshot, ReconciliationPolicy,
                            SnapshotMetadata, TradingSnapshot)
from risk import RiskLimits

D = Decimal
NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)
RISK = RiskLimits(timedelta(seconds=60), D("500"), D("2000"), D("1500"), D("100"))
POLICY = ControlPolicy("paper-account", ReconciliationPolicy(timedelta(seconds=60), timedelta(seconds=5)),
                       RISK, timedelta(seconds=60), timedelta(seconds=5))


def snapshot(**changes):
    data = dict(
        metadata=SnapshotMetadata("paper-account", "paper", NOW - timedelta(seconds=2), True),
        cash=CashSnapshot(D("1000"), "USD"), positions=(PositionSnapshot("ASAI", D("2")),),
        open_orders=(),
    )
    data.update(changes)
    return TradingSnapshot(**data)


def command(**changes):
    data = dict(action="BUY", instrument="ASAI", quantity=D("1"), limit_price=D("100"),
                order_type="limit", local_recommendation="BUY", remote_recommendation="BUY",
                emergency_risk_reduction=False)
    data.update(changes)
    return CanonicalCommand(**data)


def mark(**changes):
    data = dict(instrument="ASAI", price=D("100"), observed_at=NOW - timedelta(seconds=2))
    data.update(changes)
    return MarketMark(**data)


def run(**changes):
    data = dict(policy=POLICY, command=command(), broker=snapshot(), internal=snapshot(), mark=mark(),
                latch_engaged=False, trading_disabled=False, now=NOW)
    data.update(changes)
    return preflight(**data)


class ControlPreflightTests(unittest.TestCase):
    def denied(self, result, reason):
        self.assertFalse(result.passed)
        self.assertEqual(reason, result.reason)
        self.assertIsNone(result.fingerprint)

    def test_paper_limit_buy_passes_only_as_non_authorizing_diagnostic(self):
        result = run()
        self.assertTrue(result.passed)
        self.assertEqual("PREFLIGHT_PASSED_NOT_AUTHORIZATION", result.reason)
        self.assertRegex(result.fingerprint, r"^[0-9a-f]{64}$")
        self.assertFalse(hasattr(result, "approved"))

    def test_stale_future_naive_and_skewed_marks_fail_closed(self):
        self.denied(run(mark=mark(observed_at=NOW - timedelta(seconds=61))), "STALE_MARK")
        self.denied(run(mark=mark(observed_at=NOW + timedelta(microseconds=1))), "FUTURE_MARK")
        self.denied(run(mark=mark(observed_at=NOW.replace(tzinfo=None))), "INVALID_MARK")
        self.denied(run(mark=mark(observed_at=NOW - timedelta(seconds=10))), "MARK_SNAPSHOT_SKEW")

    def test_account_environment_and_currency_are_bound(self):
        other = snapshot(metadata=SnapshotMetadata("other", "paper", NOW - timedelta(seconds=2), True))
        self.denied(run(broker=other, internal=other), "UNEXPECTED_ACCOUNT")
        live = snapshot(metadata=SnapshotMetadata("paper-account", "live", NOW - timedelta(seconds=2), True))
        self.denied(run(broker=live, internal=live), "ENVIRONMENT_NOT_PAPER")
        usd_missing = snapshot(cash=CashSnapshot(D("1000"), "ZAR"))
        self.denied(run(broker=usd_missing, internal=usd_missing), "CURRENCY_NOT_USD")

    def test_reconciliation_conflicts_are_not_overridden(self):
        self.denied(run(internal=snapshot(cash=CashSnapshot(D("999"), "USD"))), "RECONCILIATION_CASH_MISMATCH")
        self.denied(run(internal=snapshot(positions=(PositionSnapshot("OTHER", D("2")),))),
                    "RECONCILIATION_POSITION_MISMATCH")

    def test_open_orders_and_more_than_one_position_are_rejected(self):
        orders = (OrderSnapshot("b", "c", "accepted", "ASAI", "buy", D("1")),)
        self.denied(run(broker=snapshot(open_orders=orders), internal=snapshot(open_orders=orders)), "OPEN_ORDERS_PRESENT")
        positions = (PositionSnapshot("ASAI", D("1")), PositionSnapshot("OTHER", D("1")))
        self.denied(run(broker=snapshot(positions=positions), internal=snapshot(positions=positions)), "MULTIPLE_POSITIONS")

    def test_position_and_independent_mark_must_match_command_instrument(self):
        other = snapshot(positions=(PositionSnapshot("OTHER", D("2")),))
        self.denied(run(broker=other, internal=other), "POSITION_INSTRUMENT_MISMATCH")
        self.denied(run(mark=mark(instrument="OTHER")), "MARK_INSTRUMENT_MISMATCH")

    def test_kill_and_disabled_flags_are_exact_booleans_and_fail_closed(self):
        self.denied(run(latch_engaged=True), "KILL_LATCH_ENGAGED")
        self.denied(run(trading_disabled=True), "TRADING_DISABLED")
        for value in (1, 0, "false", None):
            with self.subTest(value=repr(value)):
                self.denied(run(latch_engaged=value), "INVALID_CONTROL_FLAGS")

    def test_limit_only_and_malformed_values_fail_closed_without_fingerprint(self):
        self.denied(run(command=command(order_type="market")), "INVALID_COMMAND")
        for field, value in (("quantity", 1), ("limit_price", D("NaN")), ("action", []),
                             ("emergency_risk_reduction", 0), ("instrument", " ASAI")):
            with self.subTest(field=field):
                self.denied(run(command=command(**{field: value})), "INVALID_COMMAND")
        self.denied(run(policy="no"), "INVALID_CONTROL_POLICY")
        self.denied(run(now=NOW.replace(tzinfo=None)), "INVALID_EVALUATION_TIME")

    def test_risk_uses_exact_limit_price_and_denials_are_propagated(self):
        # Request price is forwarded exactly to risk: it breaches no-borrowing.
        self.denied(run(command=command(quantity=D("10"), limit_price=D("100"))), "RISK_NOTIONAL_LIMIT")
        self.denied(run(command=command(limit_price=D("950"))), "RISK_NOTIONAL_LIMIT")
        tight = ControlPolicy("paper-account", ReconciliationPolicy(timedelta(seconds=60), timedelta(seconds=5)),
                              RiskLimits(timedelta(seconds=60), D("500"), D("2000"), D("250"), D("0")),
                              timedelta(seconds=60), timedelta(seconds=5))
        self.denied(run(policy=tight), "RISK_EXPOSURE_LIMIT")

    def test_fingerprint_is_deterministic_and_binds_command_evidence(self):
        first, second = run(), run()
        self.assertEqual(first.fingerprint, second.fingerprint)
        changed_command = run(command=command(quantity=D("2")))
        changed_mark = run(mark=mark(price=D("101")))
        tighter_policy = ControlPolicy("paper-account", ReconciliationPolicy(timedelta(seconds=60), timedelta(seconds=5)),
                                       RiskLimits(timedelta(seconds=60), D("499"), D("2000"), D("1500"), D("100")),
                                       timedelta(seconds=60), timedelta(seconds=5))
        changed_policy = run(policy=tighter_policy)
        self.assertNotEqual(first.fingerprint, changed_command.fingerprint)
        self.assertNotEqual(first.fingerprint, changed_mark.fingerprint)
        self.assertNotEqual(first.fingerprint, changed_policy.fingerprint)

    def test_hostile_decimal_context_and_extreme_mark_fail_closed(self):
        tight = ControlPolicy("paper-account", ReconciliationPolicy(timedelta(seconds=60), timedelta(seconds=5)),
                              RiskLimits(timedelta(seconds=60), D("100"), D("2000"), D("1500"), D("0")),
                              timedelta(seconds=60), timedelta(seconds=5))
        with localcontext() as context:
            context.prec = 2
            context.rounding = ROUND_DOWN
            self.denied(run(policy=tight, command=command(quantity=D("1.111"), limit_price=D("90.01"))),
                        "RISK_NOTIONAL_LIMIT")
        self.denied(run(mark=mark(price=D("1e999999"))), "INVALID_MARK")

    def test_records_are_immutable_and_source_has_no_integration_capabilities(self):
        value = command()
        with self.assertRaises(FrozenInstanceError):
            value.action = "SELL"
        source = (Path(__file__).parents[1] / "control" / "preflight.py").read_text(encoding="utf-8")
        for forbidden in ("socket", "requests", "urllib", "sqlite", "subprocess", "open(", "datetime.now", "eval(", "exec("):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
