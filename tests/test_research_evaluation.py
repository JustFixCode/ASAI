"""Tests for deterministic, offline evaluation of backtest evidence."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN, localcontext
from pathlib import Path
import unittest

from research.evaluation import (BacktestEvidenceStats, EvidenceThresholds,
                                 EvaluationInputError, evaluate_backtest)
from research.historical_dataset import (DatasetBacktestResult, DatasetProvenance,
                                         build_historical_dataset, run_dataset_backtest)
from strategy import (BacktestBar, BacktestConfig, BacktestResult, EquityPoint,
                      HistoricalOrder, SMAcrossoverStrategy, run_backtest)

D = Decimal
T0 = datetime(2026, 2, 3, tzinfo=timezone.utc)
AS_OF = T0 + timedelta(days=2)
HASH = "a" * 64


def result(equities=("100", "120", "90", "110"), *, orders=()):
    points = tuple(EquityPoint(T0 + timedelta(hours=index), D(value), D("0"), D("1"), D(value))
                   for index, value in enumerate(equities))
    return BacktestResult("ASAI", tuple(orders), points, points[-1].cash, D("0"), points[-1].equity, HASH, "COMPLETED", ())


def thresholds(**changes):
    values = dict(min_equity_points=4, min_filled_orders=0, min_total_return=D("0.05"), max_drawdown=D("0.30"))
    values.update(changes)
    return EvidenceThresholds(**values)


class BacktestEvidenceEvaluationTests(unittest.TestCase):
    def test_decimal_return_max_drawdown_and_reproducible_hash(self):
        fixture = result()
        first = evaluate_backtest(fixture, thresholds(), as_of=AS_OF)
        second = evaluate_backtest(fixture, thresholds(), as_of=AS_OF)
        self.assertEqual(first, second)
        self.assertEqual((first.stats.total_return, first.stats.max_drawdown), (D("0.1"), D("0.25")))
        self.assertEqual(first.classification, "RESEARCH_EVIDENCE_MET")
        self.assertEqual(first.unmet_criteria, ())
        self.assertEqual(len(first.evaluation_hash), 64)
        self.assertEqual(first.source_provenance, HASH)
        self.assertIsInstance(first.stats, BacktestEvidenceStats)
        limited = evaluate_backtest(replace(fixture, warnings=("Permitted gaps leave incomplete coverage.",)), thresholds(), as_of=AS_OF)
        self.assertNotEqual(first.evaluation_hash, limited.evaluation_hash)
        self.assertTrue(any("limitations" in warning.lower() for warning in limited.warnings))
        with localcontext() as context:
            context.prec, context.rounding = 2, ROUND_DOWN
            self.assertEqual(first, evaluate_backtest(fixture, thresholds(), as_of=AS_OF))

    def test_zero_and_negative_equity_are_insufficient_not_profitable_statistics(self):
        for equities in (("0", "0"), ("100", "-1")):
            with self.subTest(equities=equities):
                finding = evaluate_backtest(result(equities), thresholds(min_equity_points=2), as_of=AS_OF)
                self.assertEqual(finding.classification, "INSUFFICIENT_EVIDENCE")
                self.assertIsNone(finding.stats.total_return)
                self.assertIsNone(finding.stats.max_drawdown)
                self.assertIn("positive_equity_required_for_return_and_drawdown", finding.unmet_criteria)

    def test_explicit_thresholds_can_fail_without_claiming_trade_approval(self):
        finding = evaluate_backtest(result(), thresholds(min_total_return=D("0.11"), max_drawdown=D("0.20")), as_of=AS_OF)
        self.assertEqual(finding.classification, "RESEARCH_EVIDENCE_NOT_MET")
        self.assertEqual(finding.unmet_criteria, ("min_total_return", "max_drawdown"))
        self.assertNotIn("approved", " ".join(finding.warnings).lower())
        self.assertTrue(any("unverified" in warning.lower() for warning in finding.warnings))

    def test_insufficient_observations_is_a_distinct_classification(self):
        finding = evaluate_backtest(result(("100", "101")), thresholds(min_equity_points=3), as_of=AS_OF)
        self.assertEqual(finding.classification, "INSUFFICIENT_EVIDENCE")
        self.assertEqual(finding.unmet_criteria, ("min_equity_points",))
        one_point = evaluate_backtest(result(("100",)), thresholds(min_equity_points=1), as_of=AS_OF)
        self.assertEqual("INSUFFICIENT_EVIDENCE", one_point.classification)
        self.assertIsNone(one_point.stats.total_return)
        self.assertIsNone(one_point.stats.max_drawdown)
        self.assertTrue(any("zero drawdown" in warning.lower() for warning in one_point.warnings))

    def test_rejects_tampered_final_equity_invalid_times_and_ambiguous_orders(self):
        fixture = result()
        with self.assertRaisesRegex(EvaluationInputError, "final result fields"):
            evaluate_backtest(replace(fixture, final_equity=D("999")), thresholds(), as_of=AS_OF)
        duplicate = replace(fixture, equity=(fixture.equity[0], fixture.equity[0]))
        with self.assertRaisesRegex(EvaluationInputError, "strictly chronological"):
            evaluate_backtest(duplicate, thresholds(min_equity_points=2), as_of=AS_OF)
        future_point = EquityPoint(AS_OF + timedelta(seconds=1), D("1"), D("0"), D("1"), D("1"))
        future = BacktestResult("ASAI", (), (future_point,), D("1"), D("0"), D("1"), HASH, "COMPLETED", ())
        with self.assertRaisesRegex(EvaluationInputError, "after as_of"):
            evaluate_backtest(future, thresholds(min_equity_points=1), as_of=AS_OF)
        bad_order = HistoricalOrder(T0, T0, "BUY", D("1"), "FILLED", D("1"), D("0"), "bad")
        with self.assertRaisesRegex(EvaluationInputError, "timestamps"):
            evaluate_backtest(result(orders=(bad_order,)), thresholds(), as_of=AS_OF)
        with self.assertRaisesRegex(EvaluationInputError, "status does not match"):
            evaluate_backtest(replace(fixture, status="COMPLETED_WITH_UNFILLED"), thresholds(), as_of=AS_OF)
        off_grid = HistoricalOrder(T0 + timedelta(minutes=30), T0 + timedelta(minutes=31), "BUY", D("1"), "FILLED", D("1"), D("0"), "off-grid")
        with self.assertRaisesRegex(EvaluationInputError, "not an equity observation"):
            evaluate_backtest(replace(fixture, orders=(off_grid,)), thresholds(), as_of=AS_OF)
        malformed = HistoricalOrder(T0, None, "BUY", D("1"), "REJECTED_INSUFFICIENT_CASH", None, None, "missing attempted execution")
        with self.assertRaisesRegex(EvaluationInputError, "missing fill fields"):
            evaluate_backtest(replace(fixture, orders=(malformed,), status="COMPLETED_WITH_REJECTIONS"), thresholds(), as_of=AS_OF)

    def test_actual_backtest_integration_preserves_input_and_counts_orders(self):
        bars = tuple(BacktestBar(T0 + timedelta(minutes=index), T0 + timedelta(minutes=index, seconds=59), "ASAI", D(open_), D(close))
                     for index, (open_, close) in enumerate(zip(("10", "9", "8", "12", "13", "2"), ("10", "9", "8", "12", "3", "2"), strict=True)))
        original = run_backtest(bars, SMAcrossoverStrategy(2, 3), BacktestConfig(D("1000"), D("1"), D("1"), 60), as_of=AS_OF)
        before = original
        finding = evaluate_backtest(original, thresholds(min_equity_points=6, min_filled_orders=2, min_total_return=D("-1"), max_drawdown=D("1")), as_of=AS_OF)
        self.assertEqual(original, before)
        self.assertEqual((finding.stats.equity_points, finding.stats.filled_orders), (6, 2))
        self.assertEqual(finding.classification, "RESEARCH_EVIDENCE_MET")
        dataset = build_historical_dataset(provenance=DatasetProvenance("fixture-e2e", "local_fixture", "Unverified fixture", "fixture-e2e", T0), adjustment_status="UNKNOWN", as_of=AS_OF, bars=bars)
        adjusted_dataset = build_historical_dataset(provenance=DatasetProvenance("fixture-e2e", "local_fixture", "Unverified fixture", "fixture-e2e", T0), adjustment_status="ADJUSTED_UNVERIFIED", as_of=AS_OF, bars=bars)
        replay = run_dataset_backtest(dataset, SMAcrossoverStrategy(2, 3), BacktestConfig(D("1000"), D("1"), D("1"), 60))
        adjusted_replay = run_dataset_backtest(adjusted_dataset, SMAcrossoverStrategy(2, 3), BacktestConfig(D("1000"), D("1"), D("1"), 60))
        evidence_thresholds = thresholds(min_equity_points=6, min_filled_orders=2, min_total_return=D("-1"), max_drawdown=D("1"))
        end_to_end = evaluate_backtest(replay, evidence_thresholds, as_of=AS_OF)
        adjusted_end_to_end = evaluate_backtest(adjusted_replay, evidence_thresholds, as_of=AS_OF)
        self.assertEqual(replay.backtest, adjusted_replay.backtest)
        self.assertNotEqual(replay.dataset_digest, adjusted_replay.dataset_digest)
        self.assertNotEqual(end_to_end.evaluation_hash, adjusted_end_to_end.evaluation_hash)
        self.assertEqual("RESEARCH_EVIDENCE_MET", end_to_end.classification)
        self.assertEqual((6, 2), (end_to_end.stats.equity_points, end_to_end.stats.filled_orders))
        self.assertTrue(any("unverified" in warning.lower() for warning in end_to_end.warnings))
        self.assertTrue(any("stale historical report" in warning.lower() for warning in end_to_end.warnings))
        self.assertTrue(any("limitations" in warning.lower() for warning in end_to_end.warnings))
        self.assertTrue(any("dataset digest" in warning.lower() for warning in end_to_end.warnings))

    def test_dataset_bound_results_reject_incompatible_or_dropped_output_without_claiming_authentication(self):
        bars = tuple(BacktestBar(T0 + timedelta(minutes=index), T0 + timedelta(minutes=index, seconds=59), "ASAI", D("10"), D(str(10 + index)))
                     for index in range(4))
        dataset = build_historical_dataset(provenance=DatasetProvenance("fixture-binding", "local_fixture", "Unverified fixture", "fixture-binding", T0), adjustment_status="UNKNOWN", as_of=AS_OF, bars=bars)
        replay = run_dataset_backtest(dataset, SMAcrossoverStrategy(1, 2), BacktestConfig(D("1000"), D("1"), D("1"), 60))
        settings = thresholds(min_equity_points=4, min_total_return=D("-1"), max_drawdown=D("1"))
        finding = evaluate_backtest(replay, settings, as_of=AS_OF)
        self.assertTrue(any("cannot authenticate" in warning.lower() and "cannot prove" in warning.lower() for warning in finding.warnings))

        cases = (
            (DatasetBacktestResult(replace(replay.backtest, symbol="OTHER"), dataset, replay.dataset_digest), "symbol does not match"),
            (DatasetBacktestResult(replace(replay.backtest, equity=replay.equity[:-1], final_cash=replay.equity[-2].cash, final_position=replay.equity[-2].position, final_equity=replay.equity[-2].equity), dataset, replay.dataset_digest), "dropped or extra"),
            (DatasetBacktestResult(replace(replay.backtest, equity=(replace(replay.equity[0], timestamp=T0 + timedelta(seconds=1)),) + replay.equity[1:]), dataset, replay.dataset_digest), "timestamp does not match"),
            (DatasetBacktestResult(replace(replay.backtest, equity=(replace(replay.equity[0], close=D("999")),) + replay.equity[1:]), dataset, replay.dataset_digest), "close does not match"),
        )
        for spoofed, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(EvaluationInputError, message):
                    evaluate_backtest(spoofed, settings, as_of=AS_OF)
        with self.assertRaisesRegex(EvaluationInputError, "dataset as_of"):
            evaluate_backtest(replay, settings, as_of=dataset.as_of - timedelta(seconds=1))

    def test_position_limit_rejection_without_fill_fields_matches_engine_contract(self):
        points = (EquityPoint(T0, D("100"), D("0"), D("1"), D("100")),
                  EquityPoint(T0 + timedelta(hours=1), D("100"), D("0"), D("1"), D("100")))
        rejected = HistoricalOrder(T0, None, "BUY", D("1"), "REJECTED_POSITION_LIMIT", None, None, "position cap")
        fixture = BacktestResult("ASAI", (rejected,), points, D("100"), D("0"), D("100"), HASH, "COMPLETED_WITH_REJECTIONS", ())
        finding = evaluate_backtest(fixture, thresholds(min_equity_points=2), as_of=AS_OF)
        self.assertEqual(1, finding.stats.rejected_orders)

    def test_input_validation_and_module_has_no_side_effect_interfaces(self):
        with self.assertRaises(EvaluationInputError):
            EvidenceThresholds(True, 0, D("0"), D("0"))
        with self.assertRaises(EvaluationInputError):
            EvidenceThresholds(1, 0, D("0"), D("1.1"))
        with self.assertRaises(EvaluationInputError):
            evaluate_backtest(result(), thresholds(), as_of=T0.astimezone(timezone(timedelta(hours=2))))
        source = (Path(__file__).parents[1] / "research" / "evaluation.py").read_text(encoding="utf-8")
        for forbidden in ("requests", "urllib", "socket", "subprocess", "open(", "eval(", "exec(", "datetime.now"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
