"""Adversarial tests for interval-safe, offline deterministic historical backtesting."""
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN, localcontext
from pathlib import Path
import unittest

from strategy import BacktestBar, BacktestConfig, BacktestInputError, SMAcrossoverStrategy, run_backtest

D = Decimal
T0 = datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc)
AS_OF = T0 + timedelta(days=1)
STRATEGY = SMAcrossoverStrategy(2, 3)
CONFIG = BacktestConfig(D("1000"), D("1"), D("1"), 60)


def bars(closes=("10", "9", "8", "12", "3", "2"), opens=None, symbol="ASAI", *, gap_seconds=1, duration_seconds=59):
    opens = opens or closes
    return tuple(BacktestBar(T0 + timedelta(minutes=index), T0 + timedelta(minutes=index, seconds=duration_seconds),
                             symbol, D(open_), D(close))
                 for index, (open_, close) in enumerate(zip(opens, closes, strict=True)))


class HistoricalBacktestTests(unittest.TestCase):
    def test_closed_bar_signal_fills_only_at_documented_next_open_and_long_only(self):
        result = run_backtest(bars(opens=("10", "9", "8", "12", "13", "2")), STRATEGY, CONFIG, as_of=AS_OF)
        buy, sell = result.orders
        self.assertEqual(("BUY", T0 + timedelta(minutes=3, seconds=59), T0 + timedelta(minutes=4), D("13")), (buy.side, buy.signal_timestamp, buy.fill_timestamp, buy.fill_price))
        self.assertEqual(("SELL", T0 + timedelta(minutes=4, seconds=59), T0 + timedelta(minutes=5), D("2")), (sell.side, sell.signal_timestamp, sell.fill_timestamp, sell.fill_price))
        self.assertEqual((D("0"), D("989"), D("989")), (result.final_position, result.final_cash, result.final_equity))
        self.assertTrue(result.warnings)

    def test_no_lookahead_signal_and_next_open_price_is_auditable(self):
        normal = run_backtest(bars(opens=("10", "9", "8", "12", "13", "2")), STRATEGY, CONFIG, as_of=AS_OF)
        changed = run_backtest(bars(opens=("10", "9", "8", "12", "100", "2")), STRATEGY, CONFIG, as_of=AS_OF)
        self.assertEqual(normal.orders[0].signal_timestamp, changed.orders[0].signal_timestamp)
        self.assertEqual((D("13"), D("100")), (normal.orders[0].fill_price, changed.orders[0].fill_price))

    def test_costs_decimal_math_and_sell_cash_invariant(self):
        config = BacktestConfig(D("1000"), D("1"), D("1"), 60, D("100"), D("10"))
        result = run_backtest(bars(opens=("10", "9", "8", "12", "13", "2")), STRATEGY, config, as_of=AS_OF)
        self.assertEqual((D("13.013"), D("0.13013"), D("1.998"), D("0.01998"), D("988.83489")),
                         (result.orders[0].fill_price, result.orders[0].fee, result.orders[1].fill_price, result.orders[1].fee, result.final_cash))
        self.assertGreaterEqual(result.final_cash, D("0"))
        with localcontext() as context:
            context.prec, context.rounding = 2, ROUND_DOWN
            self.assertEqual(result, run_backtest(bars(opens=("10", "9", "8", "12", "13", "2")), STRATEGY, config, as_of=AS_OF))

    def test_huge_sell_fee_regression_is_rejected_and_boundary_is_safe(self):
        # Previously a fee above proceeds could turn cash negative on the sell.
        with self.assertRaisesRegex(BacktestInputError, "execution configuration"):
            BacktestConfig(D("1000"), D("1"), D("1"), 60, D("10000.000000000000000001"))
        boundary = BacktestConfig(D("20"), D("1"), D("1"), 60, D("10000"))
        result = run_backtest(bars(opens=("10", "9", "8", "12", "10", "2")), STRATEGY, boundary, as_of=AS_OF)
        self.assertEqual("FILLED", result.orders[-1].status)
        self.assertGreaterEqual(result.final_cash, D("0"))

    def test_interval_validation_rejects_overlap_mixed_resolution_large_gap_and_future_close(self):
        fixture = list(bars())
        overlap = BacktestBar(T0 + timedelta(seconds=58), T0 + timedelta(minutes=1, seconds=57), "ASAI", D("1"), D("1"))
        mixed = BacktestBar(T0 + timedelta(minutes=1), T0 + timedelta(minutes=1, seconds=58), "ASAI", D("1"), D("1"))
        seven_day = [fixture[0], BacktestBar(T0 + timedelta(days=7), T0 + timedelta(days=7, seconds=59), "ASAI", D("1"), D("1"))]
        future = [fixture[0], BacktestBar(AS_OF - timedelta(seconds=30), AS_OF + timedelta(seconds=1), "ASAI", D("1"), D("1"))]
        for candidate, message, cutoff in (([fixture[0], overlap], "non-overlapping", AS_OF), ([fixture[0], mixed], "equal duration", AS_OF), (seven_day, "gap exceeds", T0 + timedelta(days=8)), (future, "later than as_of", AS_OF)):
            with self.subTest(message=message):
                with self.assertRaisesRegex(BacktestInputError, message):
                    run_backtest(candidate, STRATEGY, CONFIG, as_of=cutoff)

    def test_permitted_gap_warns_incomplete_and_hashes_interval_and_gap_policy(self):
        two_minutes = BacktestConfig(D("1000"), D("1"), D("1"), 120)
        gapped = (bars()[0], BacktestBar(T0 + timedelta(minutes=2), T0 + timedelta(minutes=2, seconds=59), "ASAI", D("9"), D("9")))
        result = run_backtest(gapped, STRATEGY, two_minutes, as_of=AS_OF)
        self.assertTrue(result.warnings)
        self.assertIn("incomplete", result.warnings[0])
        self.assertNotEqual(result.provenance, run_backtest((bars()[0], BacktestBar(T0 + timedelta(minutes=2), T0 + timedelta(minutes=2, seconds=59), "ASAI", D("8"), D("9"))), STRATEGY, two_minutes, as_of=AS_OF).provenance)
        self.assertNotEqual(result.provenance, run_backtest(gapped, STRATEGY, BacktestConfig(D("1000"), D("1"), D("1"), 180), as_of=AS_OF).provenance)

    def test_invalid_values_as_of_and_type_checks(self):
        with self.assertRaises(BacktestInputError): BacktestBar(T0, T0, "ASAI", D("1"), D("1"))
        with self.assertRaises(BacktestInputError): BacktestBar(T0, T0 + timedelta(minutes=1), "asai", D("1"), D("1"))
        with self.assertRaises(BacktestInputError): BacktestBar(T0, T0 + timedelta(minutes=1), "ASAI", D("NaN"), D("1"))
        with self.assertRaises(BacktestInputError): BacktestConfig(D("1000"), D("1"), D("1"), True)
        with self.assertRaises(BacktestInputError): BacktestConfig(D("1000"), D("1"), D("1"), -1)
        with self.assertRaises(TypeError): run_backtest(bars(), STRATEGY, CONFIG)
        with self.assertRaisesRegex(BacktestInputError, "UTC required"): run_backtest(bars(), STRATEGY, CONFIG, as_of=AS_OF.astimezone(timezone(timedelta(hours=2))))
        with self.assertRaises(BacktestInputError): run_backtest([], STRATEGY, CONFIG, as_of=AS_OF)

    def test_run_revalidates_and_detaches_mutated_bar_fields(self):
        mutations = (
            ("open_timestamp", T0 + timedelta(minutes=1), "precede"),
            ("close_timestamp", T0, "precede"),
            ("symbol", "asai", "invalid symbol"),
            ("open", D("-1"), "invalid bar open"),
            ("close", D("-1"), "invalid bar close"),
        )
        for field, value, message in mutations:
            with self.subTest(field=field):
                fixture = list(bars())
                object.__setattr__(fixture[0], field, value)
                with self.assertRaisesRegex(BacktestInputError, message):
                    run_backtest(tuple(fixture), STRATEGY, CONFIG, as_of=AS_OF)

    def test_run_revalidates_mutated_config_and_strategy_fields(self):
        config_mutations = (
            ("initial_cash", D("-1"), "invalid initial cash"),
            ("order_quantity", D("0"), "invalid order quantity"),
            ("max_position", D("0"), "invalid max position"),
            ("max_gap_seconds", -1, "invalid max gap seconds"),
            ("fee_bps", D("-1"), "invalid fee bps"),
            ("slippage_bps", D("10000"), "execution configuration"),
        )
        for field, value, message in config_mutations:
            with self.subTest(config_field=field):
                config = BacktestConfig(D("1000"), D("1"), D("1"), 60)
                object.__setattr__(config, field, value)
                with self.assertRaisesRegex(BacktestInputError, message):
                    run_backtest(bars(), STRATEGY, config, as_of=AS_OF)
        for field, value, message in (("short_window", 0, "invalid SMA windows"), ("long_window", 2, "invalid SMA windows")):
            with self.subTest(strategy_field=field):
                strategy = SMAcrossoverStrategy(2, 3)
                object.__setattr__(strategy, field, value)
                with self.assertRaisesRegex(BacktestInputError, message):
                    run_backtest(bars(), strategy, CONFIG, as_of=AS_OF)

    def test_timezone_normalization_immutable_records_and_no_integration(self):
        plus_two = timezone(timedelta(hours=2))
        alternate = tuple(BacktestBar(b.open_timestamp.astimezone(plus_two), b.close_timestamp.astimezone(plus_two), b.symbol, b.open, b.close) for b in bars())
        result = run_backtest(bars(), STRATEGY, CONFIG, as_of=AS_OF)
        self.assertEqual(result.provenance, run_backtest(alternate, STRATEGY, CONFIG, as_of=AS_OF).provenance)
        with self.assertRaises(FrozenInstanceError): result.orders[0].status = "FILLED"
        source = (Path(__file__).parents[1] / "strategy" / "backtest.py").read_text(encoding="utf-8")
        for forbidden in ("socket", "requests", "urllib", "subprocess", "open(", "datetime.now", "eval(", "exec("):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__": unittest.main()
