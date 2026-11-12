"""Tests for immutable, untrusted in-memory historical dataset contracts."""
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN, localcontext
from pathlib import Path
import unittest

from research.historical_dataset import (DatasetBacktestResult, DatasetProvenance, HistoricalDatasetError,
                                         build_historical_dataset, dataset_digest,
                                         run_dataset_backtest, to_backtest_bars)
from strategy import BacktestBar, BacktestConfig, SMAcrossoverStrategy

D = Decimal
T0 = datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc)
AS_OF = T0 + timedelta(days=1)


def provenance():
    return DatasetProvenance("fixture-1", "local_fixture", "Deterministic fixture", "fixture-1", T0)


def bars(closes=("10", "9", "8", "12", "3", "2"), opens=None, symbol="ASAI"):
    opens = opens or closes
    return tuple(BacktestBar(T0 + timedelta(minutes=index), T0 + timedelta(minutes=index, seconds=59),
                             symbol, D(open_), D(close))
                 for index, (open_, close) in enumerate(zip(opens, closes, strict=True)))


class HistoricalDatasetTests(unittest.TestCase):
    def dataset(self, **changes):
        values = {"provenance": provenance(), "adjustment_status": "UNKNOWN", "as_of": AS_OF, "bars": bars()}
        values.update(changes)
        return build_historical_dataset(**values)

    def test_contract_is_immutable_untrusted_explicit_and_hash_reproducible(self):
        first = self.dataset()
        second = self.dataset()
        self.assertTrue(first.untrusted)
        self.assertFalse(first.authenticity_verified)
        self.assertEqual("UNKNOWN", first.adjustment_status)
        self.assertEqual(first.canonical_sha256, second.canonical_sha256)
        self.assertEqual(first.canonical_sha256, dataset_digest(first))
        self.assertEqual((59, (1, 1, 1, 1, 1)), (first.bar_duration_seconds, first.gap_seconds))
        with self.assertRaises(FrozenInstanceError):
            first.symbol = "OTHER"
        object.__setattr__(first, "adjustment_status", "ADJUSTED_UNVERIFIED")
        with self.assertRaisesRegex(HistoricalDatasetError, "canonical_sha256"):
            dataset_digest(first)
        with localcontext() as context:
            context.prec, context.rounding = 2, ROUND_DOWN
            self.assertEqual(second.canonical_sha256, self.dataset().canonical_sha256)

        def broken_bars():
            yield bars()[0]
            raise RuntimeError("untrusted iterator failure")

        with self.assertRaisesRegex(HistoricalDatasetError, "iterable failed"):
            self.dataset(bars=broken_bars())

    def test_rejects_malformed_provenance_adjustments_and_precisions(self):
        bad_provenance = DatasetProvenance("bad id!", "local_fixture", "Fixture", "ref", T0)
        with self.assertRaisesRegex(HistoricalDatasetError, "source_id"):
            self.dataset(provenance=bad_provenance)
        with self.assertRaisesRegex(HistoricalDatasetError, "adjustment_status"):
            self.dataset(adjustment_status="ADJUSTED")
        non_utc = DatasetProvenance("fixture-1", "local_fixture", "Fixture", "ref", T0.astimezone(timezone(timedelta(hours=2))))
        with self.assertRaisesRegex(HistoricalDatasetError, "UTC"):
            self.dataset(provenance=non_utc)
        overprecise_bar = BacktestBar(T0, T0 + timedelta(seconds=59), "ASAI", D("1"), D("1"))
        object.__setattr__(overprecise_bar, "open", D("1.0000000000000000001"))
        with self.assertRaisesRegex(HistoricalDatasetError, "invalid bar open"):
            self.dataset(bars=(overprecise_bar,))

    def test_rejects_duplicate_chronology_mixed_symbols_future_and_gaps_over_bound(self):
        fixture = bars()
        duplicate = (fixture[0], BacktestBar(T0, T0 + timedelta(seconds=59), "ASAI", D("2"), D("2")))
        mixed = (fixture[0], BacktestBar(T0 + timedelta(minutes=1), T0 + timedelta(minutes=1, seconds=59), "OTHER", D("2"), D("2")))
        future = (fixture[0], BacktestBar(AS_OF - timedelta(seconds=30), AS_OF + timedelta(seconds=29), "ASAI", D("2"), D("2")))
        huge_gap = (fixture[0], BacktestBar(T0 + timedelta(days=366), T0 + timedelta(days=366, seconds=59), "ASAI", D("2"), D("2")))
        for candidate, message, cutoff in ((duplicate, "duplicate or overlapping", AS_OF), (mixed, "mixed symbols", AS_OF),
                                          (future, "later than as_of", AS_OF), (huge_gap, "gap exceeds", T0 + timedelta(days=367))):
            with self.subTest(message=message):
                with self.assertRaisesRegex(HistoricalDatasetError, message):
                    self.dataset(bars=candidate, as_of=cutoff)

    def test_adapter_returns_supported_backtest_bars_and_runs_existing_engine(self):
        data = self.dataset(bars=bars(opens=("10", "9", "8", "12", "13", "2")))
        adapted = to_backtest_bars(data)
        self.assertEqual(data.bars, adapted)
        result = run_dataset_backtest(data, SMAcrossoverStrategy(2, 3),
                                      BacktestConfig(D("1000"), D("1"), D("1"), 60))
        self.assertIsInstance(result, DatasetBacktestResult)
        self.assertEqual(("ASAI", D("989"), D("0")), (result.symbol, result.final_cash, result.final_position))
        self.assertEqual(data.canonical_sha256, result.dataset_digest)
        self.assertEqual(data.adjustment_status, result.dataset.adjustment_status)
        with self.assertRaises(FrozenInstanceError):
            result.dataset_digest = "0" * 64
        self.assertEqual(data.as_of, T0 + timedelta(days=1))

    def test_contract_has_no_io_or_execution_authority(self):
        source = (Path(__file__).parents[1] / "research" / "historical_dataset.py").read_text(encoding="utf-8")
        for forbidden in ("socket", "requests", "urllib", "subprocess", "open(", "datetime.now", "eval(", "exec("):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
