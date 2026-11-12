"""Offline paper-only orchestration; no network or broker submission path.

All clock, mark, and snapshot values come from caller-supplied replay fixtures.  They
are untrusted offline inputs and are not proof of live freshness or reconciliation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import sqlite3
import stat
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from config.manifest import ConfigurationError, load_manifest, manifest_digest
from reconciliation import (CashSnapshot, OrderSnapshot, ReconciliationPolicy,
                            SnapshotMetadata, PositionSnapshot, TradingSnapshot,
                            reconcile)
from risk import AccountState, OrderRequest, Position, RiskLimits, evaluate
from control.preflight import CanonicalCommand, ControlPolicy, MarketMark, preflight

_MAX_EVIDENCE_BYTES = 1_048_576
_DB_TIMEOUT_SECONDS = 0.25
_ORDER_ID_KEY = b"ASAI offline simulated-order namespace v1"
_REQUIRED_EVIDENCE = frozenset(("now", "request_key", "kill_switch_engaged", "trading_disabled",
    "command", "mark", "broker_snapshot", "internal_snapshot"))

class AppError(ValueError):
    """Expected invalid-input, policy, or bounded local-storage failure."""


def _time(v: str) -> datetime:
    if not isinstance(v, str):
        raise AppError("invalid timestamp")
    try:
        value = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AppError("invalid timestamp") from exc
    if value.tzinfo is None or value.utcoffset() is None:
        raise AppError("timestamp must include timezone")
    return value


def _dec(v: Any) -> Decimal:
    if isinstance(v, bool):
        raise AppError("invalid decimal")
    try:
        value = Decimal(str(v))
    except (InvalidOperation, ValueError) as exc:
        raise AppError("invalid decimal") from exc
    if not value.is_finite():
        raise AppError("non-finite decimal")
    return value


def _exact_object(value: Any, keys: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise AppError("invalid " + label)
    return value


def _strict_json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AppError("invalid evidence file: duplicate JSON key")
        result[key] = value
    return result


def _read_evidence(path: str) -> dict[str, Any]:
    """Read a bounded, regular, non-symlink file without blocking on FIFOs."""
    try:
        flags = os.O_RDONLY | os.O_NONBLOCK
        flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(os.fspath(path), flags)
    except OSError as exc:
        raise AppError("invalid evidence file") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_EVIDENCE_BYTES:
            raise AppError("invalid evidence file")
        chunks: list[bytes] = []
        remaining = _MAX_EVIDENCE_BYTES + 1
        while remaining:
            block = os.read(fd, min(65_536, remaining))
            if not block:
                break
            chunks.append(block)
            remaining -= len(block)
        data = b"".join(chunks)
        if len(data) > _MAX_EVIDENCE_BYTES:
            raise AppError("invalid evidence file")
        raw = json.loads(data.decode("utf-8"), object_pairs_hook=_strict_json_pairs)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, AppError) as exc:
        raise AppError(str(exc) if isinstance(exc, AppError) else "invalid evidence file") from exc
    finally:
        os.close(fd)
    if not isinstance(raw, dict):
        raise AppError("invalid evidence")
    return raw


def _snapshot(raw: Any) -> TradingSnapshot:
    raw = _exact_object(raw, frozenset(("account_id", "environment", "as_of", "complete", "cash",
                                        "currency", "positions", "open_orders")), "snapshot")
    if type(raw["complete"]) is not bool or not isinstance(raw["positions"], list) or not isinstance(raw["open_orders"], list):
        raise AppError("invalid snapshot")
    try:
        positions = tuple(PositionSnapshot(
            _exact_object(item, frozenset(("instrument", "quantity")), "snapshot position")["instrument"],
            _dec(item["quantity"])) for item in raw["positions"])
        orders = tuple(OrderSnapshot(
            _exact_object(item, frozenset(("broker_order_id", "client_order_id", "status", "instrument", "side", "quantity")), "snapshot order")["broker_order_id"],
            item["client_order_id"], item["status"], item["instrument"], item["side"], _dec(item["quantity"])
        ) for item in raw["open_orders"])
        return TradingSnapshot(SnapshotMetadata(raw["account_id"], raw["environment"], _time(raw["as_of"]), raw["complete"]),
                               CashSnapshot(_dec(raw["cash"]), raw["currency"]), positions, orders)
    except (KeyError, TypeError, AppError) as exc:
        raise AppError("invalid snapshot") from exc


def _init(db: sqlite3.Connection) -> None:
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("CREATE TABLE IF NOT EXISTS orders (request_key TEXT PRIMARY KEY, order_id TEXT UNIQUE NOT NULL, status TEXT NOT NULL, command_json TEXT NOT NULL, fingerprint TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, request_key TEXT NOT NULL, event TEXT NOT NULL, detail TEXT NOT NULL, at TEXT NOT NULL, FOREIGN KEY(request_key) REFERENCES orders(request_key))")


def _audit(db: sqlite3.Connection, key: str, event: str, detail: str, now: datetime) -> None:
    db.execute("INSERT INTO audit(request_key,event,detail,at) VALUES(?,?,?,?)", (key, event, detail, now.isoformat()))


def _order_id(request_key: str, fingerprint: str) -> str:
    # Request key is included so different keys cannot collide merely because evidence matches.
    digest = hashlib.blake2b((request_key + "\0" + fingerprint).encode("utf-8"), key=_ORDER_ID_KEY, digest_size=20).hexdigest()
    return "sim-" + digest


def _crosses_limit(command: CanonicalCommand, mark: MarketMark) -> bool:
    return ((command.action == "BUY" and mark.price <= command.limit_price) or
            (command.action == "SELL" and mark.price >= command.limit_price))


def _response(status: str, order_id: str, replay: bool, manifest: dict[str, Any]) -> dict[str, Any]:
    return {"status": status, "order_id": order_id, "idempotent_replay": replay,
            "mode": "SIMULATED_PAPER_ONLY", "manifest_digest": manifest_digest(manifest),
            "evidence_trust": "UNTRUSTED_CALLER_SUPPLIED_OFFLINE_FIXTURE",
            "freshness_and_reconciliation": "OFFLINE_DIAGNOSTIC_ONLY_NOT_PROOF_OF_REAL_FRESHNESS_OR_RECONCILIATION"}


def run(manifest_path: str, evidence_path: str, database: str) -> dict[str, Any]:
    """Validate offline replay evidence and persist only a limit-respecting simulated fill."""
    try:
        manifest = load_manifest(manifest_path)
    except ConfigurationError as exc:
        raise AppError("invalid manifest") from exc
    broker_cfg, data_cfg = manifest["broker"], manifest["market_data"]
    if (broker_cfg["mode"] != "paper" or broker_cfg["live_trading_enabled"] is not False or
            broker_cfg["execution_enabled"] is not False or broker_cfg["submission_enabled"] is not False or
            data_cfg["network_enabled"] is not False):
        raise AppError("manifest violates offline paper-only boundary")

    raw = _read_evidence(evidence_path)
    raw = _exact_object(raw, _REQUIRED_EVIDENCE, "evidence")
    if type(raw["kill_switch_engaged"]) is not bool or type(raw["trading_disabled"]) is not bool:
        raise AppError("invalid control flags")
    if raw["kill_switch_engaged"] or raw["trading_disabled"]:
        raise AppError("system is killed or disabled")
    key = raw["request_key"]
    if not isinstance(key, str) or not key or len(key) > 128:
        raise AppError("invalid request key")
    now, broker, internal = _time(raw["now"]), _snapshot(raw["broker_snapshot"]), _snapshot(raw["internal_snapshot"])
    command_raw = _exact_object(raw["command"], frozenset(("action", "instrument", "quantity", "limit_price", "local_recommendation", "remote_recommendation")), "command")
    mark_raw = _exact_object(raw["mark"], frozenset(("instrument", "price", "observed_at")), "mark")
    try:
        command = CanonicalCommand(command_raw["action"], command_raw["instrument"], _dec(command_raw["quantity"]),
            _dec(command_raw["limit_price"]), "limit", command_raw["local_recommendation"], command_raw["remote_recommendation"])
        mark = MarketMark(mark_raw["instrument"], _dec(mark_raw["price"]), _time(mark_raw["observed_at"]))
    except (KeyError, TypeError, AppError) as exc:
        raise AppError("invalid command or mark") from exc
    limits = RiskLimits(timedelta(seconds=60), Decimal("10000"), Decimal("1000000"), Decimal("1000000"), Decimal("100"))
    recon_policy = ReconciliationPolicy(timedelta(seconds=60), timedelta(seconds=5))
    recon = reconcile(recon_policy, broker, internal, now=now)
    policy = ControlPolicy(broker.metadata.account_id, recon_policy, limits, timedelta(seconds=60), timedelta(seconds=5))
    diagnostic = preflight(policy, command, broker, internal, mark, latch_engaged=False, trading_disabled=False, now=now)
    position = next((item for item in internal.positions if item.instrument == command.instrument), None)
    quantity = position.quantity if position else Decimal("0")
    state = AccountState(internal.metadata.as_of, internal.cash.available_cash, internal.cash.available_cash + quantity * mark.price,
                         Position(command.instrument, quantity, mark.price), recon.clear, True, False)
    decision = evaluate(limits, state, OrderRequest(command.action, command.instrument, command.quantity, command.limit_price,
                        command.local_recommendation, command.remote_recommendation), now=now)
    if not recon.clear:
        raise AppError("reconciliation failed: " + ",".join(recon.reasons))
    if not diagnostic.passed:
        raise AppError("preflight failed: " + diagnostic.reason)
    if not decision.approved:
        raise AppError("risk denied: " + decision.code)
    if not _crosses_limit(command, mark):
        raise AppError("limit not crossed: no simulated fill persisted")

    db: sqlite3.Connection | None = None
    try:
        db = sqlite3.connect(database, timeout=_DB_TIMEOUT_SECONDS, isolation_level=None)
        _init(db)
        db.execute("BEGIN IMMEDIATE")
        old = db.execute("SELECT order_id,status,fingerprint FROM orders WHERE request_key=?", (key,)).fetchone()
        if old:
            if old[2] != diagnostic.fingerprint:
                raise AppError("idempotency key reused with different request")
            db.execute("COMMIT")
            return _response(old[1], old[0], True, manifest)
        order_id = _order_id(key, diagnostic.fingerprint)
        payload = json.dumps(command_raw, sort_keys=True, separators=(",", ":"))
        db.execute("INSERT INTO orders VALUES(?,?,?,?,?,?,?)", (key, order_id, "FILLED", payload, diagnostic.fingerprint, now.isoformat(), now.isoformat()))
        _audit(db, key, "CREATED", "untrusted offline-fixture simulated order", now)
        _audit(db, key, "FILLED", "untrusted offline-fixture limit-respecting simulated fill at mark " + str(mark.price), now)
        db.execute("COMMIT")
        return _response("FILLED", order_id, False, manifest)
    except AppError:
        if db is not None and db.in_transaction:
            db.rollback()
        raise
    except sqlite3.Error as exc:
        if db is not None and db.in_transaction:
            db.rollback()
        raise AppError("database busy or storage conflict") from exc
    finally:
        if db is not None:
            db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline ASAI paper simulation; never sends orders.")
    parser.add_argument("evidence"); parser.add_argument("--manifest", default="config/asai_safe.yaml"); parser.add_argument("--database", default="asai-dev.sqlite3")
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.manifest, args.evidence, args.database), sort_keys=True))
    except AppError as exc:
        parser.error(str(exc))

if __name__ == "__main__":
    main()
