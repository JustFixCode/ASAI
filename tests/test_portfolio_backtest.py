"""Tests for deterministic, closed-bar, offline portfolio replay."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN, localcontext
import unittest

from strategy.portfolio_backtest import (
    PortfolioBacktestConfig,
    PortfolioBacktestInputError,
    PortfolioBar,
    PortfolioSignal,
    run_portfolio_backtest,
)

D = Decimal
T0 = datetime(2026, 2, 3, 9, 30, tzinfo=timezone.utc)
AS_OF = T0 + timedelta(days=1)


def grid(*, aaa_opens=("10", "11", "13"), aaa_closes=("10", "12", "14"), bbb_opens=("20", "21", "19"), bbb_closes=("20", "18", "17")):
    bars = []
    for index, values in enumerate(zip(aaa_opens, aaa_closes, bbb_opens, bbb_closes, strict=True)):
        opened = T0 + timedelta(minutes=index)
        closed = opened + timedelta(seconds=59)
        ao, ac, bo, bc = map(D, values)
        bars.extend((PortfolioBar(opened, closed, "AAA", ao, ac), PortfolioBar(opened, closed, "BBB", bo, bc)))
    return tuple(bars)


def signal(index, symbol, side, quantity):
    return PortfolioSignal(T0 + timedelta(minutes=index, seconds=59), symbol, side, D(quantity))


class PortfolioBacktestTests(unittest.TestCase):
    def test_realistic_multi_asset_allocation_accounting_costs_and_next_open(self):
        config = PortfolioBacktestConfig(D("100"), D("5"), D("100"), D("100"), D("100"))
        result = run_portfolio_backtest(grid(), (signal(0, "BBB", "BUY", "3"), signal(0, "AAA", "BUY", "2"), signal(1, "AAA", "SELL", "1")), config, as_of=AS_OF)
        aaa_buy, bbb_buy, aaa_sell = result.orders
        self.assertEqual(("AAA", T0 + timedelta(minutes=1), D("11.11"), D("0.2222"), "FILLED"), (aaa_buy.symbol, aaa_buy.fill_timestamp, aaa_buy.fill_price, aaa_buy.fee, aaa_buy.status))
        self.assertEqual(("BBB", T0 + timedelta(minutes=1), D("21.21"), D("0.6363"), "FILLED"), (bbb_buy.symbol, bbb_buy.fill_timestamp, bbb_buy.fill_price, bbb_buy.fee, bbb_buy.status))
        self.assertEqual((T0 + timedelta(minutes=2), D("12.87"), D("0.1287")), (aaa_sell.fill_timestamp, aaa_sell.fill_price, aaa_sell.fee))
        self.assertEqual((D("26.0328"), (("AAA", D("1")), ("BBB", D("3"))), D("91.0328")), (result.final_cash, result.final_positions, result.final_equity))
        self.assertEqual((D("65"), D("91.0328")), (result.equity[-1].gross_exposure, result.equity[-1].equity))
        self.assertEqual("USD", result.currency)

    def test_signals_are_caller_data_only_and_last_close_is_unfilled(self):
        config = PortfolioBacktestConfig(D("100"), D("5"), D("100"))
        empty = run_portfolio_backtest(grid(), (), config, as_of=AS_OF)
        self.assertEqual((), empty.orders)
        self.assertEqual(D("100"), empty.final_equity)
        result = run_portfolio_backtest(grid(), (signal(2, "AAA", "BUY", "1"),), config, as_of=AS_OF)
        self.assertEqual(("UNFILLED_END_OF_DATA", None), (result.orders[0].status, result.orders[0].fill_timestamp))
        self.assertEqual("COMPLETED_WITH_UNFILLED", result.status)

    def test_no_lookahead_open_execution_and_gross_cap_do_not_use_future_close(self):
        config = PortfolioBacktestConfig(D("100"), D("5"), D("25"))
        signals = (signal(0, "AAA", "BUY", "2"),)
        normal = run_portfolio_backtest(grid(), signals, config, as_of=AS_OF)
        altered = run_portfolio_backtest(grid(aaa_closes=("10", "999", "14")), signals, config, as_of=AS_OF)
        self.assertEqual(("FILLED", T0 + timedelta(minutes=1), D("11")), (normal.orders[0].status, normal.orders[0].fill_timestamp, normal.orders[0].fill_price))
        self.assertEqual((normal.orders[0].status, normal.orders[0].fill_price), (altered.orders[0].status, altered.orders[0].fill_price))
        self.assertNotEqual(normal.equity[1].equity, altered.equity[1].equity)  # Close changes valuation only.
        self._assert_close_to_next_open_zero_width_boundary_is_next_bar_only()

    def test_position_gross_cash_and_long_only_constraints_fail_closed(self):
        position = run_portfolio_backtest(grid(), (signal(0, "AAA", "BUY", "3"),), PortfolioBacktestConfig(D("1000"), D("2"), D("1000")), as_of=AS_OF)
        self.assertEqual("REJECTED_POSITION_LIMIT", position.orders[0].status)
        gross = run_portfolio_backtest(grid(), (signal(0, "AAA", "BUY", "3"),), PortfolioBacktestConfig(D("1000"), D("5"), D("30")), as_of=AS_OF)
        self.assertEqual("REJECTED_GROSS_EXPOSURE", gross.orders[0].status)
        cash = run_portfolio_backtest(grid(), (signal(0, "AAA", "BUY", "2"),), PortfolioBacktestConfig(D("10"), D("5"), D("1000")), as_of=AS_OF)
        self.assertEqual("REJECTED_INSUFFICIENT_CASH", cash.orders[0].status)
        short = run_portfolio_backtest(grid(), (signal(0, "AAA", "SELL", "1"),), PortfolioBacktestConfig(D("100"), D("5"), D("1000")), as_of=AS_OF)
        self.assertEqual("REJECTED_INSUFFICIENT_POSITION", short.orders[0].status)
        self.assertEqual(D("100"), short.final_cash)
        self._assert_same_open_sells_precede_buys_and_release_shared_cash()

    def test_alignment_duplicate_unknown_malformed_and_as_of_fail_closed(self):
        config = PortfolioBacktestConfig(D("100"), D("5"), D("1000"))
        malformed = list(grid())
        malformed.pop()  # BBB is missing in the last interval.
        duplicate = grid() + (grid()[0],)
        unknown = (signal(0, "AAA", "BUY", "1"), PortfolioSignal(T0 + timedelta(seconds=59), "CCC", "BUY", D("1")))
        cases = ((malformed, (), "missing or misaligned"), (duplicate, (), "duplicate bar"), (grid(), unknown, "unknown signal"))
        for candidate_bars, candidate_signals, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(PortfolioBacktestInputError, message):
                    run_portfolio_backtest(candidate_bars, candidate_signals, config, as_of=AS_OF)
        with self.assertRaisesRegex(PortfolioBacktestInputError, "UTC required"):
            run_portfolio_backtest(grid(), (), config, as_of=AS_OF.astimezone(timezone(timedelta(hours=2))))
        with self.assertRaisesRegex(PortfolioBacktestInputError, "duplicate signal"):
            run_portfolio_backtest(grid(), (signal(0, "AAA", "BUY", "1"), signal(0, "AAA", "SELL", "1")), config, as_of=AS_OF)

    def _assert_same_open_sells_precede_buys_and_release_shared_cash(self):
        result = run_portfolio_backtest(
            grid(),
            (signal(0, "BBB", "BUY", "2"), signal(1, "BBB", "SELL", "2"), signal(1, "AAA", "BUY", "3")),
            PortfolioBacktestConfig(D("45"), D("5"), D("1000")),
            as_of=AS_OF,
        )
        # Without sell-first processing, alphabetic AAA would consume only the
        # pre-sale cash and be rejected. The audit order reflects fills.
        self.assertEqual(
            (("BBB", "BUY", "FILLED"), ("BBB", "SELL", "FILLED"), ("AAA", "BUY", "FILLED")),
            tuple((order.symbol, order.side, order.status) for order in result.orders),
        )
        self.assertEqual((D("2"), (("AAA", D("3")), ("BBB", D("0"))), D("44")), (result.final_cash, result.final_positions, result.final_equity))

    def _assert_close_to_next_open_zero_width_boundary_is_next_bar_only(self):
        boundary = T0 + timedelta(minutes=1)
        bars = (
            PortfolioBar(T0, boundary, "AAA", D("10"), D("10")),
            PortfolioBar(T0, boundary, "BBB", D("20"), D("20")),
            PortfolioBar(boundary, boundary + timedelta(minutes=1), "AAA", D("11"), D("12")),
            PortfolioBar(boundary, boundary + timedelta(minutes=1), "BBB", D("21"), D("18")),
        )
        result = run_portfolio_backtest(
            bars,
            (PortfolioSignal(boundary, "AAA", "BUY", D("1")),),
            PortfolioBacktestConfig(D("100"), D("5"), D("1000")),
            as_of=AS_OF,
        )
        self.assertEqual((boundary, D("11"), "FILLED"), (result.orders[0].fill_timestamp, result.orders[0].fill_price, result.orders[0].status))
        self.assertEqual((D("100"), D("89")), (result.equity[0].cash, result.equity[1].cash))

    def _assert_valid_large_appreciation_does_not_trip_input_magnitude_bound(self):
        first_close = T0 + timedelta(minutes=1)
        second_close = first_close + timedelta(minutes=1)
        bars = (
            PortfolioBar(T0, first_close, "AAA", D("0.000000000000000001"), D("0.000000000000000001")),
            PortfolioBar(first_close, second_close, "AAA", D("0.000000000000000001"), D("1000000000")),
        )
        result = run_portfolio_backtest(
            bars,
            (PortfolioSignal(first_close, "AAA", "BUY", D("1000000000")),),
            PortfolioBacktestConfig(D("1"), D("1000000000"), D("1")),
            as_of=AS_OF,
        )
        self.assertEqual(D("1000000000000000000.999999999"), result.final_equity)
        self.assertEqual(D("1000000000000000000"), result.equity[-1].gross_exposure)

    def test_reproducibility_canonical_order_provenance_and_immutable_results(self):
        config = PortfolioBacktestConfig(D("100"), D("5"), D("100"), D("10"), D("5"))
        signals = (signal(0, "BBB", "BUY", "1"), signal(0, "AAA", "BUY", "1"))
        normal = run_portfolio_backtest(grid(), signals, config, as_of=AS_OF)
        reversed_inputs = run_portfolio_backtest(tuple(reversed(grid())), tuple(reversed(signals)), config, as_of=AS_OF)
        self.assertEqual(normal, reversed_inputs)
        with localcontext() as context:
            context.prec, context.rounding = 2, ROUND_DOWN
            self.assertEqual(normal, run_portfolio_backtest(grid(), signals, config, as_of=AS_OF))
        with self.assertRaises(AttributeError):
            normal.orders[0].status = "FILLED"
        self.assertEqual(64, len(normal.provenance))
        self.assertTrue(all("Simulation only" in normal.limitations[0] for _ in (0,)))
        self._assert_valid_large_appreciation_does_not_trip_input_magnitude_bound()


if __name__ == "__main__":
    unittest.main()
