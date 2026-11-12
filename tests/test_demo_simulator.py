from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal, Inexact, Rounded, getcontext, setcontext
import unittest

from demo.simulator import DemoError, DemoQuote, DemoSimulator


NOW = datetime(2026, 11, 12, 11, 0, tzinfo=timezone.utc)


def quote(*, bid="149.90", ask="150.00", age=1, source="fixture"):
    retrieved = NOW - timedelta(seconds=age)
    return DemoQuote("AAPL", Decimal(bid), Decimal(ask), retrieved, retrieved, source)


def buy(quantity=1, limit_price="150.00"):
    return {"symbol": "AAPL", "side": "BUY", "quantity": quantity, "limit_price": limit_price}


def sell(quantity=1, limit_price="149.90"):
    return {"symbol": "AAPL", "side": "SELL", "quantity": quantity, "limit_price": limit_price}


class DemoSimulatorTests(unittest.TestCase):
    def assert_error(self, code, call):
        with self.assertRaises(DemoError) as caught:
            call()
        self.assertEqual(caught.exception.code, code)

    def test_initial_snapshot_and_immediate_limit_fill_are_explicitly_simulated(self):
        simulator = DemoSimulator()
        initial = simulator.snapshot()
        self.assertEqual(initial["cash"], "10000.00")
        self.assertEqual(initial["positions"], {"AAPL": 0})
        self.assertEqual(initial["mode"], "SIMULATION_ONLY")
        self.assertFalse(initial["fees_modeled"])
        self.assertIn("no broker connection", initial["warning"])
        self.assertIn("fills are simulated", initial["warning"])

        result = simulator.place_order(buy(2), "fill-1", quote(), NOW)
        self.assertEqual(result["status"], "FILLED")
        self.assertEqual(result["fill_price"], "150.00")
        self.assertEqual(result["mode"], "SIMULATION_ONLY")
        self.assertEqual(simulator.snapshot()["cash"], "9700.00")
        self.assertEqual(simulator.snapshot()["positions"], {"AAPL": 2})
        self.assert_error("ORDER_NOT_CANCELLABLE", lambda: simulator.cancel_order(result["order_id"]))

    def test_limits_and_long_only_constraints_fail_closed_without_reservations(self):
        simulator = DemoSimulator()
        self.assert_error("LIMIT_NOT_MARKETABLE", lambda: simulator.place_order(buy(limit_price="149.99"), "no-fill", quote(), NOW))
        self.assert_error("INSUFFICIENT_POSITION", lambda: simulator.place_order(sell(), "short-attempt", quote(), NOW))
        self.assert_error("INSUFFICIENT_CASH", lambda: simulator.place_order(buy(100, "150.00"), "too-expensive", quote(), NOW))
        state = simulator.snapshot()
        self.assertEqual(state["cash"], "10000.00")
        self.assertEqual(state["positions"], {"AAPL": 0})
        self.assertEqual(state["orders"], [])

    def test_quote_freshness_future_and_mixed_source_fail_closed(self):
        simulator = DemoSimulator()
        self.assert_error("QUOTE_REQUIRED", lambda: simulator.place_order(buy(), "missing", None, NOW))
        self.assert_error("QUOTE_STALE", lambda: simulator.place_order(buy(), "stale", quote(age=16), NOW))
        future = DemoQuote("AAPL", Decimal("1"), Decimal("2"), NOW + timedelta(seconds=1), NOW, "fixture")
        self.assert_error("QUOTE_FUTURE", lambda: simulator.place_order(buy(), "future", future, NOW))
        crossed = DemoQuote("AAPL", Decimal("151"), Decimal("150"), NOW, NOW, "fixture")
        self.assert_error("INVALID_QUOTE", lambda: simulator.place_order(buy(), "crossed", crossed, NOW))
        mixed = DemoQuote("AAPL", Decimal("149.90"), Decimal("150"), NOW, NOW, "fixture+alpaca_iex")
        self.assert_error("INVALID_QUOTE", lambda: simulator.place_order(buy(), "mixed", mixed, NOW))

    def test_payload_is_strict_and_rejects_injection_like_input(self):
        simulator = DemoSimulator()
        for index, limit_price in enumerate(("1e2", "NaN", "Infinity", "150.000000001", "150; DROP TABLE orders")):
            self.assert_error("INVALID_LIMIT_PRICE", lambda p=limit_price, i=index: simulator.place_order(buy(limit_price=p), f"bad-{i}", quote(), NOW))
        self.assert_error("INVALID_QUANTITY", lambda: simulator.place_order(buy(quantity=True), "bool", quote(), NOW))
        self.assert_error("INVALID_PAYLOAD", lambda: simulator.place_order({**buy(), "extra": "x"}, "extra", quote(), NOW))
        self.assert_error("UNSUPPORTED_SYMBOL", lambda: simulator.place_order({**buy(), "symbol": "MSFT"}, "symbol", quote(), NOW))

    def test_hostile_decimal_context_cannot_change_exact_accounting(self):
        original = getcontext().copy()
        hostile = original.copy()
        hostile.prec = 2
        hostile.traps[Inexact] = True
        hostile.traps[Rounded] = True
        setcontext(hostile)
        try:
            simulator = DemoSimulator()
            result = simulator.place_order(buy(3, "150.00"), "hostile-context", quote(), NOW)
            self.assertEqual(result["fill_price"], "150.00")
            self.assertEqual(simulator.snapshot()["cash"], "9550.00")
            self.assertEqual(simulator.snapshot()["positions"], {"AAPL": 3})
        finally:
            setcontext(original)

    def test_idempotency_replays_only_same_canonical_payload_without_duplicate_accounting(self):
        simulator = DemoSimulator()
        first = simulator.place_order(buy(1, "150.00"), "same-key", quote(), NOW)
        replay = simulator.place_order(buy(1, "150.0"), "same-key", quote(), NOW)
        self.assertEqual(replay, first)
        self.assertEqual(simulator.snapshot()["cash"], "9850.00")
        self.assertEqual(len(simulator.snapshot()["orders"]), 1)
        self.assert_error("IDEMPOTENCY_CONFLICT", lambda: simulator.place_order(buy(2), "same-key", quote(), NOW))

    def test_concurrent_duplicate_requests_fill_once(self):
        simulator = DemoSimulator()
        with ThreadPoolExecutor(max_workers=16) as pool:
            results = list(pool.map(lambda _: simulator.place_order(buy(), "concurrent", quote(), NOW), range(32)))
        self.assertEqual({result["order_id"] for result in results}, {"demo-00000001"})
        self.assertEqual(simulator.snapshot()["cash"], "9850.00")
        self.assertEqual(simulator.snapshot()["positions"], {"AAPL": 1})

    def test_concurrent_sells_conserve_position_and_cash(self):
        simulator = DemoSimulator()
        simulator.place_order(buy(10), "seed", quote(), NOW)

        def attempt(index):
            try:
                return simulator.place_order(sell(), f"sell-{index}", quote(), NOW)
            except DemoError as exc:
                return exc.code

        with ThreadPoolExecutor(max_workers=16) as pool:
            outcomes = list(pool.map(attempt, range(20)))
        fills = [value for value in outcomes if isinstance(value, dict)]
        self.assertEqual(len(fills), 10)
        self.assertEqual(outcomes.count("INSUFFICIENT_POSITION"), 10)
        state = simulator.snapshot()
        self.assertEqual(state["positions"], {"AAPL": 0})
        self.assertEqual(state["cash"], "9999.00")
        self.assertEqual(len(state["orders"]), 11)

    def test_no_broker_or_network_surface_and_reset_is_in_memory(self):
        simulator = DemoSimulator()
        self.assertFalse(any(hasattr(simulator, attr) for attr in ("broker", "client", "credentials", "api_key")))
        simulator.place_order(buy(), "memory", quote(), NOW)
        fresh = DemoSimulator()
        self.assertEqual(fresh.snapshot()["cash"], "10000.00")
        self.assertEqual(fresh.snapshot()["orders"], [])


if __name__ == "__main__":
    unittest.main()
