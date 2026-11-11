"""Adversarial coverage for the standalone deterministic risk policy."""
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import unittest

from risk import BUY, HOLD, SELL, AccountState, OrderRequest, Position, RiskLimits, evaluate

D = Decimal
NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)
LIMITS = RiskLimits(
    max_data_age=timedelta(seconds=60),
    max_order_notional=D("500"),
    max_cash=D("2000"),
    max_projected_exposure=D("1500"),
    min_cash_reserve=D("100"),
    max_leverage=D("1"),
)


def state(**changes):
    result = dict(
        as_of=NOW - timedelta(seconds=10),
        cash=D("1000"),
        equity=D("1200"),
        position=Position("ASAI", D("2"), D("100")),
        reconciled=True,
        trading_enabled=True,
        kill_switch_engaged=False,
    )
    result.update(changes)
    return AccountState(**result)


def request(**changes):
    result = dict(
        action=BUY,
        instrument="ASAI",
        quantity=D("1"),
        price=D("100"),
        local_recommendation=BUY,
        remote_recommendation=BUY,
        emergency_risk_reduction=False,
    )
    result.update(changes)
    return OrderRequest(**result)


class RiskPolicyTests(unittest.TestCase):
    def rejected(self, decision, code):
        self.assertFalse(decision.approved)
        self.assertEqual(code, decision.code)
        self.assertIsNotNone(decision.message)

    def test_approves_decimal_long_only_buy_with_exact_projection(self):
        decision = evaluate(LIMITS, state(), request(), now=NOW)
        self.assertTrue(decision.approved)
        self.assertEqual("APPROVED", decision.code)
        self.assertEqual(D("900"), decision.projected_cash)
        self.assertEqual(D("300"), decision.projected_exposure)
        self.assertEqual(D("1200"), decision.projected_equity)

    def test_hold_is_safe_and_has_no_execution_values(self):
        decision = evaluate(
            LIMITS, state(), request(action=HOLD, quantity=D("0"), price=D("0"),
                                      local_recommendation=HOLD, remote_recommendation=HOLD), now=NOW)
        self.assertTrue(decision.approved)
        self.assertEqual("HOLD", decision.code)
        self.rejected(evaluate(
            LIMITS, state(), request(action=HOLD, quantity=D("1"), price=D("0"),
                                      local_recommendation=HOLD, remote_recommendation=HOLD), now=NOW), "INVALID_HOLD")

    def test_rejects_nan_infinite_float_integer_string_and_boolean_values(self):
        bad_values = (D("NaN"), D("Infinity"), 1.0, 1, "1", True)
        for value in bad_values:
            with self.subTest(value=repr(value)):
                self.rejected(evaluate(LIMITS, state(), request(quantity=value), now=NOW), "INVALID_REQUEST")
                self.rejected(evaluate(LIMITS, state(cash=value, equity=D("1200")), request(), now=NOW), "UNSAFE_STATE")

    def test_missing_wrong_type_and_invalid_limit_inputs_fail_closed(self):
        self.rejected(evaluate(LIMITS, state(), {"action": BUY}, now=NOW), "INVALID_REQUEST")
        self.rejected(evaluate("limits", state(), request(), now=NOW), "INVALID_LIMITS")
        invalid = RiskLimits(timedelta(seconds=1), D("1"), D("1"), D("1"), D("0"), D("1.01"))
        self.rejected(evaluate(invalid, state(), request(), now=NOW), "INVALID_LIMITS")
        self.rejected(evaluate(LIMITS, state(), request(), now=NOW.replace(tzinfo=None)), "INVALID_TIME")

    def test_stale_future_and_naive_timestamps_fail_closed(self):
        for as_of in (NOW - timedelta(seconds=61), NOW + timedelta(microseconds=1), NOW.replace(tzinfo=None)):
            with self.subTest(as_of=as_of):
                self.rejected(evaluate(LIMITS, state(as_of=as_of), request(), now=NOW),
                              "UNSAFE_STATE" if as_of.tzinfo is None else "STALE_OR_FUTURE_STATE")

    def test_unreconciled_switches_kill_and_equity_mismatch_fail_closed(self):
        cases = (
            (dict(reconciled=False), "UNSAFE_STATE"),
            (dict(kill_switch_engaged=True), "UNSAFE_STATE"),
            (dict(equity=D("1199")), "UNSAFE_STATE"),
            (dict(equity=D("0")), "UNSAFE_STATE"),
        )
        for changes, code in cases:
            with self.subTest(changes=changes):
                self.rejected(evaluate(LIMITS, state(**changes), request(), now=NOW), code)

    def test_conflicting_or_nonunanimous_recommendations_are_rejected(self):
        self.rejected(evaluate(LIMITS, state(), request(remote_recommendation=SELL), now=NOW),
                      "CONFLICTING_RECOMMENDATIONS")
        self.rejected(evaluate(LIMITS, state(), request(local_recommendation=HOLD, remote_recommendation=HOLD), now=NOW),
                      "RECOMMENDATION_MISMATCH")

    def test_no_borrowing_exposure_notional_cash_and_leverage_limits(self):
        self.rejected(evaluate(LIMITS, state(), request(quantity=D("6"), price=D("100")), now=NOW), "NOTIONAL_LIMIT")
        self.rejected(evaluate(LIMITS, state(cash=D("150"), equity=D("350")), request(), now=NOW), "NO_BORROWING")
        self.rejected(evaluate(LIMITS, state(), request(quantity=D("10"), price=D("100")), now=NOW), "NOTIONAL_LIMIT")
        tight = RiskLimits(timedelta(seconds=60), D("500"), D("2000"), D("500"), D("0"), D("0.2"))
        self.rejected(evaluate(tight, state(), request(), now=NOW), "LEVERAGE_PROHIBITED")

    def test_sell_cannot_short_and_max_cash_is_enforced(self):
        sell = request(action=SELL, quantity=D("3"), price=D("100"),
                       local_recommendation=SELL, remote_recommendation=SELL)
        self.rejected(evaluate(LIMITS, state(), sell, now=NOW), "SHORTING_PROHIBITED")
        cap = RiskLimits(timedelta(seconds=60), D("500"), D("1050"), D("1500"), D("0"))
        self.rejected(evaluate(cap, state(), request(action=SELL, quantity=D("1"), price=D("100"),
                                                      local_recommendation=SELL, remote_recommendation=SELL), now=NOW),
                      "MAX_CASH_LIMIT")

    def test_disabled_switch_rejects_every_order_including_emergency_reduction(self):
        disabled = state(trading_enabled=False)
        self.rejected(evaluate(LIMITS, disabled, request(), now=NOW), "TRADING_DISABLED")
        regular_sell = request(action=SELL, quantity=D("1"), price=D("100"),
                               local_recommendation=SELL, remote_recommendation=SELL)
        self.rejected(evaluate(LIMITS, disabled, regular_sell, now=NOW), "TRADING_DISABLED")
        emergency_sell = request(action=SELL, quantity=D("1"), price=D("100"),
                                 local_recommendation=SELL, remote_recommendation=SELL,
                                 emergency_risk_reduction=True)
        self.rejected(evaluate(LIMITS, disabled, emergency_sell, now=NOW), "TRADING_DISABLED")
        self.rejected(evaluate(LIMITS, state(), request(emergency_risk_reduction=True), now=NOW),
                      "EMERGENCY_MUST_REDUCE_RISK")

    def test_projected_exposure_uses_trusted_mark_not_manipulable_order_price(self):
        # A maliciously cheap limit cannot hide the post-trade market exposure.
        decision = evaluate(LIMITS, state(), request(price=D("1")), now=NOW)
        self.assertTrue(decision.approved)
        self.assertEqual(D("999"), decision.projected_cash)
        self.assertEqual(D("300"), decision.projected_exposure)
        self.assertEqual(D("1299"), decision.projected_equity)

        # The same trusted mark must enforce the exposure cap despite that
        # request's tiny notional.
        tight_exposure = RiskLimits(timedelta(seconds=60), D("500"), D("2000"), D("250"), D("0"))
        self.rejected(evaluate(tight_exposure, state(), request(price=D("1")), now=NOW),
                      "EXPOSURE_LIMIT")

        # A high sell limit changes cash, but the unsold position remains
        # marked at the independently reconciled value, not the order limit.
        sell = request(action=SELL, quantity=D("1"), price=D("500"),
                       local_recommendation=SELL, remote_recommendation=SELL)
        decision = evaluate(LIMITS, state(), sell, now=NOW)
        self.assertTrue(decision.approved)
        self.assertEqual(D("1500"), decision.projected_cash)
        self.assertEqual(D("100"), decision.projected_exposure)
        self.assertEqual(D("1600"), decision.projected_equity)

    def test_missing_or_stale_market_mark_cannot_approve_orders(self):
        # A zero mark is missing/unusable even if equity is internally coherent.
        unmarked = state(position=Position("ASAI", D("2"), D("0")), equity=D("1000"))
        self.rejected(evaluate(LIMITS, unmarked, request(), now=NOW), "UNSAFE_STATE")
        # as_of is the reconciled marked snapshot timestamp, so an old mark
        # cannot be used for a fresh approval.
        stale_mark = state(as_of=NOW - timedelta(seconds=61))
        self.rejected(evaluate(LIMITS, stale_mark, request(), now=NOW), "STALE_OR_FUTURE_STATE")

    def test_kill_switch_rejects_emergency_sell_before_any_bypass(self):
        killed = state(kill_switch_engaged=True)
        emergency_sell = request(action=SELL, quantity=D("1"), price=D("100"),
                                 local_recommendation=SELL, remote_recommendation=SELL,
                                 emergency_risk_reduction=True)
        self.rejected(evaluate(LIMITS, killed, emergency_sell, now=NOW), "UNSAFE_STATE")

    def test_records_are_frozen_and_evaluation_does_not_mutate_inputs(self):
        before_state, before_request = state(), request()
        with self.assertRaises(FrozenInstanceError):
            before_state.cash = D("0")
        with self.assertRaises(FrozenInstanceError):
            before_request.action = SELL
        evaluate(LIMITS, before_state, before_request, now=NOW)
        self.assertEqual(D("1000"), before_state.cash)
        self.assertEqual(BUY, before_request.action)

    def test_source_has_no_runtime_code_generation_or_external_execution_imports(self):
        source = (Path(__file__).parents[1] / "risk" / "policy.py").read_text(encoding="utf-8")
        for forbidden in ("eval(", "exec(", "compile(", "subprocess", "socket", "requests", "urllib"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
