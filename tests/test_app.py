import json
import os
import sqlite3
import socket
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from app.main import AppError, _crosses_limit, run
from control.preflight import CanonicalCommand, MarketMark
from decimal import Decimal
from datetime import datetime, timezone

ROOT = Path(__file__).parents[1]


def evidence(**changes):
    snapshot = {"account_id":"paper-1", "environment":"paper", "as_of":"2026-01-01T12:00:00+00:00",
                "complete":True, "cash":"1000", "currency":"USD", "positions":[], "open_orders":[]}
    value = {"now":"2026-01-01T12:00:00+00:00", "kill_switch_engaged":False, "trading_disabled":False,
             "request_key":"key-1", "command":{"action":"BUY", "instrument":"AAPL", "quantity":"2",
             "limit_price":"100", "local_recommendation":"BUY", "remote_recommendation":"BUY"},
             "mark":{"instrument":"AAPL", "price":"100", "observed_at":"2026-01-01T12:00:00+00:00"},
             "broker_snapshot":snapshot, "internal_snapshot":snapshot.copy()}
    value.update(changes)
    return value


class AppTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        self.database = self.path / "dev.sqlite"

    def tearDown(self):
        self.tmp.cleanup()

    def invoke(self, raw, manifest=ROOT / "config/asai_safe.yaml", name="evidence.json"):
        ep = self.path / name
        ep.write_text(json.dumps(raw), encoding="utf-8")
        return run(str(manifest), str(ep), str(self.database))

    def test_limit_respecting_lifecycle_audit_and_untrusted_labels(self):
        result = self.invoke(evidence())
        self.assertEqual((result["status"], result["mode"]), ("FILLED", "SIMULATED_PAPER_ONLY"))
        self.assertIn("UNTRUSTED", result["evidence_trust"])
        self.assertIn("NOT_PROOF", result["freshness_and_reconciliation"])
        db = sqlite3.connect(self.database)
        self.assertEqual(db.execute("select event from audit order by id").fetchall(), [("CREATED",), ("FILLED",)])
        self.assertIn("untrusted offline-fixture", db.execute("select detail from audit where event='FILLED'").fetchone()[0])
        db.close()

    def test_buy_above_limit_and_sell_below_limit_never_persist_fill(self):
        sell_snapshot = {**evidence()["broker_snapshot"], "positions":[{"instrument":"AAPL", "quantity":"2"}]}
        for raw in (evidence(mark={"instrument":"AAPL", "price":"100", "observed_at":"2026-01-01T12:00:00+00:00"},
                             command={"action":"BUY", "instrument":"AAPL", "quantity":"2", "limit_price":"90", "local_recommendation":"BUY", "remote_recommendation":"BUY"}),
                    evidence(command={"action":"SELL", "instrument":"AAPL", "quantity":"2", "limit_price":"110", "local_recommendation":"SELL", "remote_recommendation":"SELL"},
                             broker_snapshot=sell_snapshot, internal_snapshot=sell_snapshot.copy())):
            with self.subTest(action=raw["command"]["action"]):
                with self.assertRaisesRegex(AppError, "limit not crossed|preflight failed"):
                    self.invoke(raw)
        sell = CanonicalCommand("SELL", "AAPL", Decimal("2"), Decimal("110"), "limit", "SELL", "SELL")
        buy = CanonicalCommand("BUY", "AAPL", Decimal("2"), Decimal("90"), "limit", "BUY", "BUY")
        mark = MarketMark("AAPL", Decimal("100"), datetime(2026, 1, 1, tzinfo=timezone.utc))
        self.assertFalse(_crosses_limit(buy, mark))
        self.assertFalse(_crosses_limit(sell, mark))
        self.assertFalse(self.database.exists(), "unmatched limits must not create persistence")

    def test_repeated_key_survives_restart_and_keyed_order_ids_do_not_collide(self):
        first = self.invoke(evidence())
        self.assertFalse(first["idempotent_replay"])
        self.assertTrue(self.invoke(evidence())["idempotent_replay"])
        second = self.invoke(evidence(request_key="key-2"), name="second.json")
        self.assertNotEqual(first["order_id"], second["order_id"])

    def test_repeated_key_different_request_denied(self):
        self.invoke(evidence())
        raw = evidence()
        raw["command"]["quantity"] = "3"
        with self.assertRaisesRegex(AppError, "idempotency"):
            self.invoke(raw)

    def test_kill_disabled_stale_and_bad_reconciliation(self):
        cases = [(evidence(kill_switch_engaged=True), "killed"), (evidence(trading_disabled=True), "killed"),
                 (evidence(mark={"instrument":"AAPL", "price":"100", "observed_at":"2026-01-01T11:58:00+00:00"}), "preflight"),
                 (evidence(internal_snapshot={**evidence()["internal_snapshot"], "cash":"999"}), "reconciliation")]
        for raw, text in cases:
            with self.subTest(text=text), self.assertRaisesRegex(AppError, text):
                self.invoke(raw)

    def test_manifest_cannot_enable_live_or_network(self):
        manifest = json.loads((ROOT / "config/asai_safe.yaml").read_text())
        manifest["broker"]["live_trading_enabled"] = True
        mp = self.path / "bad.yaml"
        mp.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(AppError, "invalid manifest|paper-only"):
            self.invoke(evidence(), mp)

    def test_evidence_rejects_duplicate_keys_unknown_structure_symlink_and_fifo(self):
        duplicate = self.path / "duplicate.json"
        duplicate.write_text('{"now":"x","now":"y"}', encoding="utf-8")
        with self.assertRaisesRegex(AppError, "duplicate JSON key"):
            run(str(ROOT / "config/asai_safe.yaml"), str(duplicate), str(self.database))
        with self.assertRaisesRegex(AppError, "invalid command"):
            self.invoke(evidence(command={**evidence()["command"], "unexpected":True}))
        target = self.path / "target.json"
        target.write_text(json.dumps(evidence()))
        link = self.path / "link.json"
        link.symlink_to(target)
        with self.assertRaisesRegex(AppError, "invalid evidence file"):
            run(str(ROOT / "config/asai_safe.yaml"), str(link), str(self.database))
        if hasattr(os, "mkfifo"):
            fifo = self.path / "evidence.fifo"
            os.mkfifo(fifo)
            with self.assertRaisesRegex(AppError, "invalid evidence file"):
                run(str(ROOT / "config/asai_safe.yaml"), str(fifo), str(self.database))

    def test_concurrent_clients_are_atomic(self):
        # Pre-initialize outside contention so the assertion exercises SELECT+INSERT.
        self.invoke(evidence(request_key="preinit"), name="preinit.json")
        barrier = threading.Barrier(2)
        results, errors = [], []
        def client(index):
            raw = evidence(request_key="same-concurrent-key")
            ep = self.path / ("client-%d.json" % index)
            ep.write_text(json.dumps(raw), encoding="utf-8")
            try:
                barrier.wait(timeout=3)
                results.append(run(str(ROOT / "config/asai_safe.yaml"), str(ep), str(self.database)))
            except Exception as exc:  # asserted below, rather than leaking a thread traceback
                errors.append(exc)
        threads = [threading.Thread(target=client, args=(i,)) for i in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(5)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertFalse(errors, errors)
        self.assertEqual(len(results), 2)
        self.assertEqual({item["order_id"] for item in results}, {results[0]["order_id"]})
        self.assertEqual(sorted(item["idempotent_replay"] for item in results), [False, True])
        db = sqlite3.connect(self.database)
        self.assertEqual(db.execute("select count(*) from orders where request_key='same-concurrent-key'").fetchone()[0], 1)
        db.close()

    def test_no_network_or_broker_submission(self):
        with patch.object(socket, "create_connection", side_effect=AssertionError("network")):
            self.assertEqual(self.invoke(evidence())["status"], "FILLED")


if __name__ == "__main__":
    unittest.main()
