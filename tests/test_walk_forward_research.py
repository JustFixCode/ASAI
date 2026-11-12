"""Tests for offline point-in-time expanding baseline walk-forward evaluation."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import unittest

from research.walk_forward import (PointInTimeObservation, WalkForwardConfig,
                                   WalkForwardInputError, run_walk_forward)

D = Decimal
T0 = datetime(2026, 1, 2, tzinfo=timezone.utc)
AS_OF = T0 + timedelta(days=10)


def rows(values=("1", "3", "5", "7", "9", "11", "13"), *, horizon_hours=0.5):
    return tuple(PointInTimeObservation(T0 + timedelta(hours=index),
                                        T0 + timedelta(hours=index + horizon_hours),
                                        D(index), D(value))
                 for index, value in enumerate(values))


class OfflineWalkForwardResearchTests(unittest.TestCase):
    def test_expanding_mean_baseline_makes_honest_oos_predictions_and_metrics(self):
        result = run_walk_forward(rows(), WalkForwardConfig(3, 2, purge_observations=1), as_of=AS_OF)
        self.assertEqual(result.model, "expanding training-target mean baseline (no ML model)")
        self.assertEqual(result.as_of, AS_OF)
        self.assertEqual([(p.prediction, p.actual) for p in result.out_of_sample],
                         [(D("3"), D("9")), (D("3"), D("11")), (D("5"), D("13"))])
        self.assertEqual(result.metrics.count, 3)
        self.assertLess(abs(result.metrics.mean_absolute_error - (D(22) / D(3))), D("1e-25"))
        self.assertLess(abs(result.metrics.mean_error + (D(22) / D(3))), D("1e-25"))
        self.assertLess(abs((result.metrics.root_mean_squared_error * result.metrics.root_mean_squared_error)
                            - (D(164) / D(3))), D("1e-25"))
        self.assertEqual([(w.train_size, w.configured_purged_count, w.temporal_purged_count) for w in result.windows],
                         [(3, 1, 0), (5, 1, 0)])

    def test_temporal_purge_removes_labels_not_available_at_test_feature_time(self):
        delayed = rows(horizon_hours=3)
        result = run_walk_forward(delayed, WalkForwardConfig(5, 1, purge_observations=1), as_of=AS_OF)
        window = result.windows[0]
        self.assertEqual((window.train_size, window.configured_purged_count, window.temporal_purged_count), (3, 1, 2))
        for prediction in window.predictions:
            self.assertLess(window.train_feature_end, prediction.feature_timestamp)
        self.assertEqual(window.baseline_mean, D("3"))

    def test_chronological_split_is_strict_and_repeatable_with_stable_provenance(self):
        fixture, config = rows(), WalkForwardConfig(3, 2, 1)
        first = run_walk_forward(fixture, config, as_of=AS_OF)
        second = run_walk_forward(tuple(fixture), config, as_of=AS_OF)
        self.assertEqual(first, second)
        self.assertEqual(first.provenance, second.provenance)
        for window in first.windows:
            self.assertLess(window.train_feature_end, window.test_feature_start)
            self.assertLess(window.train_feature_start, window.train_feature_end)
            self.assertLessEqual(window.test_feature_start, window.test_feature_end)

    def test_requires_as_of_and_rejects_future_labels(self):
        with self.assertRaises(TypeError):
            run_walk_forward(rows(), WalkForwardConfig(3, 1))  # type: ignore[call-arg]
        future_as_of = T0 + timedelta(hours=2)
        with self.assertRaisesRegex(WalkForwardInputError, "after as_of"):
            run_walk_forward(rows(), WalkForwardConfig(2, 1), as_of=future_as_of)

    def test_separates_overlapping_test_label_intervals_between_folds(self):
        fixture = rows(tuple(str(index) for index in range(12)), horizon_hours=3)
        result = run_walk_forward(fixture, WalkForwardConfig(6, 1), as_of=AS_OF)
        self.assertTrue(any("unverified caller-supplied assertions" in warning for warning in result.warnings))
        self.assertTrue(any("not performance evidence" in warning for warning in result.warnings))
        self.assertTrue(any("prevent overlapping out-of-sample label intervals" in warning for warning in result.warnings))
        for earlier, later in zip(result.windows, result.windows[1:]):
            self.assertLess(earlier.predictions[-1].target_timestamp, later.test_feature_start)
        self.assertEqual([p.feature_timestamp for p in result.out_of_sample],
                         [T0 + timedelta(hours=index) for index in (6, 10)])

    def test_rejects_malformed_ambiguous_and_insufficient_inputs(self):
        with self.assertRaises(WalkForwardInputError):
            PointInTimeObservation(T0, T0, D("1"), D("1"))
        with self.assertRaises(WalkForwardInputError):
            PointInTimeObservation(T0, T0 + timedelta(hours=1), D("NaN"), D("1"))
        with self.assertRaises(WalkForwardInputError):
            WalkForwardConfig(True, 1)
        with self.assertRaises(WalkForwardInputError):
            WalkForwardConfig(2, 0)
        duplicate_time = (rows()[0], PointInTimeObservation(T0, T0 + timedelta(hours=2), D("2"), D("2")))
        with self.assertRaisesRegex(WalkForwardInputError, "strictly chronological"):
            run_walk_forward(duplicate_time, WalkForwardConfig(2, 1), as_of=AS_OF)
        with self.assertRaisesRegex(WalkForwardInputError, "insufficient"):
            run_walk_forward(rows()[:3], WalkForwardConfig(2, 1, 1), as_of=AS_OF)
        with self.assertRaisesRegex(WalkForwardInputError, "built-in tuple or list"):
            run_walk_forward("not rows", WalkForwardConfig(2, 1), as_of=AS_OF)

    def test_revalidates_mutated_frozen_records_and_configuration(self):
        fixture = list(rows())
        object.__setattr__(fixture[0], "target", D("Infinity"))
        with self.assertRaisesRegex(WalkForwardInputError, "invalid target"):
            run_walk_forward(fixture, WalkForwardConfig(3, 1), as_of=AS_OF)
        config = WalkForwardConfig(3, 1)
        object.__setattr__(config, "test_size", True)
        with self.assertRaisesRegex(WalkForwardInputError, "invalid test_size"):
            run_walk_forward(rows(), config, as_of=AS_OF)

    def test_module_stays_stdlib_offline_and_has_no_execution_authority(self):
        source = (Path(__file__).parents[1] / "research" / "walk_forward.py").read_text(encoding="utf-8")
        for forbidden in ("requests", "urllib", "socket", "subprocess", "open(", "eval(", "exec("):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
