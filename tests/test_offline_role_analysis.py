"""Tests for the bounded, side-effect-free offline role analysis module."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import os
from pathlib import Path
import tempfile
import unittest

from research.offline_role_analysis import (
    HistoricalNumericBar,
    OfflineRoleAnalysisError,
    analyze_historical_bars,
)

UTC = timezone.utc
T0 = datetime(2026, 1, 2, 10, 0, tzinfo=UTC)
AS_OF = T0 + timedelta(hours=4)
D = Decimal


def bar(index: int, *, open_="10", high="11", low="9", close="10") -> HistoricalNumericBar:
    opened = T0 + timedelta(minutes=index * 10)
    return HistoricalNumericBar(opened, opened + timedelta(minutes=9), "ASAI", D(open_), D(high), D(low), D(close))


class OfflineRoleAnalysisTests(unittest.TestCase):
    def test_deterministic_roles_include_disagreement_and_limitations(self):
        bars = (bar(0, close="10"), bar(1, open_="12", high="13", low="11", close="12"), bar(2, open_="11", high="12", low="10", close="11"))
        first = analyze_historical_bars(bars, as_of=AS_OF)
        second = analyze_historical_bars(bars, as_of=AS_OF)
        self.assertEqual(first, second)
        self.assertEqual("OFFLINE_HISTORICAL_DESCRIPTIVE_ANALYSIS_ONLY", first.mode)
        self.assertEqual(("trend", "range", "continuity"), tuple(item.role for item in first.observations))
        self.assertEqual("OBSERVED", first.observations[0].status)
        self.assertEqual({"close_change_percent": "10", "direction": "UP"}, dict(first.observations[0].facts))
        self.assertEqual(("Overall close direction and final-bar close direction differ in the supplied history.",), first.disagreements)
        self.assertEqual(4, len(first.evidence_limitations))
        self.assertIn("not forecasts", first.evidence_limitations[2])

    def test_single_closed_bar_makes_data_inadequacy_explicit(self):
        result = analyze_historical_bars((bar(0),), as_of=AS_OF)
        self.assertEqual(("INADEQUATE_DATA",) * 3, tuple(item.status for item in result.observations))
        self.assertIn("fewer than three", result.disagreements[0])
        self.assertTrue(all(item.limitations for item in result.observations))

    def test_canonicalizes_zero_offset_datetimes_for_reproducible_output(self):
        alternate_utc = timezone(timedelta(0), "ALTERNATE_UTC")
        alternative_bar = HistoricalNumericBar(
            T0.replace(tzinfo=alternate_utc),
            (T0 + timedelta(minutes=9)).replace(tzinfo=alternate_utc),
            "ASAI", D("10"), D("11"), D("9"), D("10"),
        )
        result = analyze_historical_bars((alternative_bar,), as_of=AS_OF.replace(tzinfo=alternate_utc))
        canonical = analyze_historical_bars((bar(0),), as_of=AS_OF)
        self.assertIs(result.as_of.tzinfo, UTC)
        self.assertEqual(result.as_of, AS_OF)
        self.assertEqual(result, canonical)

    def test_rejects_future_bar_before_any_analysis(self):
        future = HistoricalNumericBar(T0, AS_OF + timedelta(seconds=1), "ASAI", D("10"), D("11"), D("9"), D("10"))
        with self.assertRaisesRegex(OfflineRoleAnalysisError, "after as_of"):
            analyze_historical_bars((future,), as_of=AS_OF)

    def test_rejects_malformed_types_ohlc_and_chronology(self):
        malformed = HistoricalNumericBar(T0, T0 + timedelta(minutes=1), "ASAI", D("10"), D("11"), D("9"), 10)  # type: ignore[arg-type]
        with self.assertRaisesRegex(OfflineRoleAnalysisError, "finite positive Decimal"):
            analyze_historical_bars((malformed,), as_of=AS_OF)
        invalid_ohlc = HistoricalNumericBar(T0, T0 + timedelta(minutes=1), "ASAI", D("10"), D("9"), D("8"), D("10"))
        with self.assertRaisesRegex(OfflineRoleAnalysisError, "OHLC bounds"):
            analyze_historical_bars((invalid_ohlc,), as_of=AS_OF)
        overlapping = (bar(0), HistoricalNumericBar(T0 + timedelta(minutes=8), T0 + timedelta(minutes=12), "ASAI", D("10"), D("11"), D("9"), D("10")))
        with self.assertRaisesRegex(OfflineRoleAnalysisError, "chronological"):
            analyze_historical_bars(overlapping, as_of=AS_OF)

        class ArbitraryIterator:
            def __iter__(self):
                raise AssertionError("must not invoke caller-controlled iteration")

        with self.assertRaisesRegex(OfflineRoleAnalysisError, "built-in tuple or list"):
            analyze_historical_bars(ArbitraryIterator(), as_of=AS_OF)  # type: ignore[arg-type]

    def test_function_has_no_filesystem_side_effects(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            before = sorted(os.listdir(root))
            result = analyze_historical_bars((bar(0), bar(1, close="11")), as_of=AS_OF)
            self.assertEqual(before, sorted(os.listdir(root)))
            self.assertEqual(2, result.accepted_bar_count)
            self.assertEqual("UP", dict(result.observations[0].facts)["direction"])

    def test_result_is_structured_without_executable_or_trade_fields(self):
        result = analyze_historical_bars((bar(0), bar(1)), as_of=AS_OF)
        rendered = asdict(result)
        self.assertEqual(
            {"mode", "symbol", "as_of", "accepted_bar_count", "observations", "disagreements", "evidence_limitations"},
            set(rendered),
        )
        self.assertNotIn("http", repr(rendered).lower())


if __name__ == "__main__":
    unittest.main()
