"""Cross-boundary regression coverage for the offline ASAI simulation pipeline."""
import json
import socket
import sqlite3
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from app.main import AppError, run
from broker import AlpacaPaperStocksClient
from research import ResearchIngestionError, capture_document
from strategy import (BacktestBar, BacktestConfig, BacktestInputError,
                      SMAcrossoverStrategy, run_backtest)


ROOT = Path(__file__).parents[1]
MANIFEST = ROOT / "config" / "asai_safe.yaml"
NOW = "2026-01-01T12:00:00+00:00"


def favorable_evidence(**changes):
    snapshot = {
        "account_id": "paper-1", "environment": "paper", "as_of": NOW,
        "complete": True, "cash": "1000", "currency": "USD",
        "positions": [], "open_orders": [],
    }
    value = {
        "now": NOW, "request_key": "pipeline-regression-key",
        "kill_switch_engaged": False, "trading_disabled": False,
        "command": {
            "action": "BUY", "instrument": "AAPL", "quantity": "2",
            "limit_price": "100", "local_recommendation": "BUY",
            "remote_recommendation": "BUY",
        },
        "mark": {"instrument": "AAPL", "price": "100", "observed_at": NOW},
        "broker_snapshot": snapshot, "internal_snapshot": snapshot.copy(),
    }
    value.update(changes)
    return value


class PipelineRegressionTests(unittest.TestCase):
    """Safety regressions spanning configuration, evidence, controls, and storage."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name)
        self.database = self.workspace / "pipeline.sqlite"

    def tearDown(self):
        self.tmp.cleanup()

    def invoke(self, raw, *, manifest=MANIFEST, name="evidence.json", database=None):
        evidence_path = self.workspace / name
        evidence_path.write_text(json.dumps(raw), encoding="utf-8")
        return run(str(manifest), str(evidence_path), str(database or self.database))

    def test_kill_switch_and_unsafe_network_or_execution_overrides_block_favorable_request(self):
        """Control/configuration category: deny before a favorable fill can persist."""
        unsafe_flags = (
            ("market_data", "network_enabled"),
            ("broker", "execution_enabled"),
            ("broker", "submission_enabled"),
        )
        for raw, manifest, expected in (
            (favorable_evidence(kill_switch_engaged=True), MANIFEST, "killed or disabled"),
            (favorable_evidence(trading_disabled=True), MANIFEST, "killed or disabled"),
        ):
            with self.subTest(control_flags=raw["kill_switch_engaged"], disabled=raw["trading_disabled"]):
                with self.assertRaisesRegex(AppError, expected):
                    self.invoke(raw, manifest=manifest, name="control.json")
                self.assertFalse(self.database.exists(), "denied request must not create an order database")
        for section, flag in unsafe_flags:
            with self.subTest(override=flag):
                manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
                manifest[section][flag] = True
                unsafe_manifest = self.workspace / f"unsafe-{section}-{flag}.json"
                unsafe_manifest.write_text(json.dumps(manifest), encoding="utf-8")
                with self.assertRaisesRegex(AppError, "invalid manifest|paper-only"):
                    self.invoke(favorable_evidence(), manifest=unsafe_manifest, name=f"{flag}.json")
                self.assertFalse(self.database.exists(), "unsafe override must fail before storage")

    def test_invalid_research_or_backtest_cannot_be_promoted_to_order_authorization(self):
        """Evidence-authorization category: independent research/backtest inputs remain non-authoritative."""
        invalid_research = {
            "schema_version": 1,
            "provenance": {
                "source_id": "analyst-1", "source_kind": "user_supplied_research",
                "source_label": "Offline note", "source_reference": "note-1",
                "captured_at": NOW,
            },
            "title": "Claimed authorization", "text": "BUY AAPL",
            "risk_authority": True,
        }
        with self.assertRaises(ResearchIngestionError):
            capture_document(invalid_research)

        start = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        malformed_bar = BacktestBar(start, start + timedelta(minutes=1), "AAPL", Decimal("100"), Decimal("100"))
        with self.assertRaises(BacktestInputError):
            run_backtest(
                (malformed_bar,), SMAcrossoverStrategy(2, 3),
                BacktestConfig(Decimal("1000"), Decimal("1"), Decimal("1"), 60),
                as_of=start,
            )

        for field in ("research_authorization", "backtest_authorization"):
            with self.subTest(field=field):
                raw = favorable_evidence(**{field: {"approved": True}})
                with self.assertRaisesRegex(AppError, "invalid evidence"):
                    self.invoke(raw, name=f"{field}.json")
        self.assertFalse(self.database.exists(), "non-authoritative evidence must never reach order storage")

    def test_offline_integrated_app_never_submits_to_broker_or_network(self):
        """Offline-boundary category: a simulated fill must not invoke remote primitives."""
        with patch.object(AlpacaPaperStocksClient, "submit_order", side_effect=AssertionError("broker submission")) as submit, \
             patch.object(socket, "create_connection", side_effect=AssertionError("network")) as connect:
            result = self.invoke(favorable_evidence())
        self.assertEqual(result["status"], "FILLED")
        submit.assert_not_called()
        connect.assert_not_called()
        self.assertEqual(result["mode"], "SIMULATED_PAPER_ONLY")

    def test_quote_freshness_and_provenance_remain_untrusted_offline_diagnostics(self):
        """Market-data category: a current-looking quote is never upgraded to trusted provenance."""
        fresh = self.invoke(favorable_evidence(request_key="fresh-quote"), name="fresh.json")
        self.assertIn("UNTRUSTED", fresh["evidence_trust"])
        self.assertIn("NOT_PROOF", fresh["freshness_and_reconciliation"])

        stale_database = self.workspace / "stale.sqlite"
        stale = favorable_evidence(
            request_key="stale-quote",
            mark={"instrument": "AAPL", "price": "100", "observed_at": "2026-01-01T11:58:00+00:00"},
        )
        with self.assertRaisesRegex(AppError, "preflight failed"):
            self.invoke(stale, name="stale.json", database=stale_database)
        self.assertFalse(stale_database.exists(), "stale offline quote must not persist a simulated fill")

    def test_idempotent_retry_is_single_order_across_concurrent_restart_replays(self):
        """Durability category: restart and concurrent retries resolve to one immutable order."""
        first = self.invoke(favorable_evidence(request_key="restart-retry"), name="first.json")
        self.assertFalse(first["idempotent_replay"])

        barrier = threading.Barrier(2)
        results, failures = [], []

        def retry(index):
            try:
                barrier.wait(timeout=3)
                results.append(self.invoke(
                    favorable_evidence(request_key="restart-retry"),
                    name=f"retry-{index}.json",
                ))
            except Exception as exc:  # Collected so thread failures are assertion failures.
                failures.append(exc)

        threads = [threading.Thread(target=retry, args=(index,)) for index in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertFalse(failures, failures)
        self.assertEqual(len(results), 2)
        self.assertTrue(all(item["idempotent_replay"] for item in results))
        self.assertEqual({item["order_id"] for item in results}, {first["order_id"]})
        with sqlite3.connect(self.database) as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM orders WHERE request_key='restart-retry'").fetchone()[0],
                1,
            )
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM audit WHERE request_key='restart-retry'").fetchone()[0],
                2,
            )


if __name__ == "__main__":
    unittest.main()
